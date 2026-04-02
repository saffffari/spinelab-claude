from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
import SimpleITK as sitk
from scipy import ndimage

from spinelab.io import CaseStore
from spinelab.models import CaseManifest, PipelineArtifact
from spinelab.models.manifest import make_id
from spinelab.ontology import (
    standard_level_sort_key,
    standard_neighbors,
    standard_structure_for_level,
    structure_instance_id_for_level,
)
from spinelab.pipeline.artifacts import (
    segmentation_label_map_path,
    segmentation_manifest_path,
    segmentation_run_manifest_path,
    stage_root,
    write_json_artifact,
)
from spinelab.pipeline.backends import BACKEND_ADAPTERS
from spinelab.pipeline.contracts import (
    BackendDeviceRequirement,
    PipelineStageName,
    StageExecutionResult,
)
from spinelab.pipeline.device import choose_runtime_device
from spinelab.pipeline.stages.common import (
    SEGMENTATION_MODEL_NAME,
    SEGMENTATION_MODEL_VERSION,
    artifact_for_type,
    populate_label_map,
    primary_ct_volume,
    synthetic_vertebrae,
    write_label_map,
)
from spinelab.segmentation import SegmentationBundleRegistry, resolve_segmentation_driver
from spinelab.segmentation_profiles import (
    SegmentationProfile,
    canonical_segmentation_profile,
)
from spinelab.services import active_performance_policy, performance_coordinator
from spinelab.services.performance import ResolvedPerformancePolicy

_ADAPTERS_BY_TOOL = {adapter.spec.tool_name: adapter for adapter in BACKEND_ADAPTERS}
SegmentationProgressCallback = Callable[[float, str], None]


def _normalized_volume_artifact_id(manifest: CaseManifest) -> str:
    artifact = artifact_for_type(manifest, "normalized-volume")
    return artifact.artifact_id if artifact is not None else ""


def _emit_segmentation_progress(
    progress_callback: SegmentationProgressCallback | None,
    fraction: float,
    detail: str,
) -> None:
    if progress_callback is None:
        return
    clamped_fraction = max(0.0, min(1.0, float(fraction)))
    progress_callback(clamped_fraction, detail)


def _set_segmentation_backend(
    manifest: CaseManifest,
    *,
    backend_tool: str,
    environment_id: str,
) -> None:
    if not manifest.pipeline_runs:
        return
    active_run = manifest.pipeline_runs[-1]
    if active_run.stage != PipelineStageName.SEGMENTATION.value:
        return
    active_run.backend_tool = backend_tool
    active_run.environment_id = environment_id
    active_run.backend_health.update(
        {
            "backend_tool": backend_tool,
            "environment_id": environment_id,
        }
    )


def _required_device_for_driver(driver_id: str) -> BackendDeviceRequirement:
    adapter = _ADAPTERS_BY_TOOL.get(driver_id)
    if adapter is None:
        return BackendDeviceRequirement.CUDA
    return adapter.spec.required_device


def _resolve_production_runtime_device(
    manifest: CaseManifest,
    *,
    driver_id: str,
) -> str:
    if manifest.pipeline_runs:
        active_run = manifest.pipeline_runs[-1]
        if active_run.stage == PipelineStageName.SEGMENTATION.value:
            return active_run.effective_device or active_run.device or "cpu"
    required_device = _required_device_for_driver(driver_id)
    preferred_device = (
        "cuda"
        if required_device == BackendDeviceRequirement.CUDA
        else "cpu"
        if required_device == BackendDeviceRequirement.CPU
        else None
    )
    runtime_selection = choose_runtime_device(preferred_device)
    return runtime_selection.effective_device


def _validate_runtime_device(*, driver_id: str, runtime_device: str) -> None:
    required_device = _required_device_for_driver(driver_id)
    if required_device == BackendDeviceRequirement.CUDA and runtime_device != "cuda":
        raise ValueError(
            "Production segmentation requires a CUDA-capable NVIDIA runtime on this machine."
        )
    if required_device == BackendDeviceRequirement.CPU and runtime_device != "cpu":
        raise ValueError(
            "The active segmentation backend requires CPU execution on this machine."
        )


def _build_vertebrae_payload(
    *,
    level_map: dict[str, int],
    label_statistics: dict[str, dict[str, object]],
    placeholder_reason: str | None = None,
    numbering_confidence: float = 1.0,
    supports_standard_measurements: bool = True,
) -> list[dict[str, object]]:
    ordered_levels = sorted(level_map.keys(), key=standard_level_sort_key)
    neighbors = standard_neighbors(ordered_levels)
    payload: list[dict[str, object]] = []
    for level_id in ordered_levels:
        definition = standard_structure_for_level(level_id)
        if definition is None:
            continue
        superior_neighbor, inferior_neighbor = neighbors[level_id]
        entry: dict[str, object] = {
            "vertebra_id": level_id,
            "structure_instance_id": structure_instance_id_for_level(level_id),
            "display_label": level_id,
            "standard_level_id": level_id,
            "region_id": definition.region_id.value,
            "structure_type": definition.structure_type.value,
            "order_index": definition.order_index,
            "label_value": level_map[level_id],
            "numbering_confidence": numbering_confidence,
            "variant_tags": [],
            "supports_standard_measurements": supports_standard_measurements,
            "superior_neighbor_instance_id": (
                structure_instance_id_for_level(superior_neighbor)
                if superior_neighbor is not None
                else None
            ),
            "inferior_neighbor_instance_id": (
                structure_instance_id_for_level(inferior_neighbor)
                if inferior_neighbor is not None
                else None
            ),
            "coordinate_frame": "normalized-volume",
        }
        stats = label_statistics.get(level_id)
        if stats is not None:
            voxel_count = stats.get("voxel_count")
            ijk_bounds = stats.get("ijk_bounds")
            center_hint_ijk = stats.get("center_hint_ijk")
            center_hint_patient_frame_mm = stats.get("center_hint_patient_frame_mm")
            if isinstance(voxel_count, (int, float, str)):
                entry["voxel_count"] = int(voxel_count)
            if ijk_bounds is not None:
                entry["ijk_bounds"] = ijk_bounds
            if center_hint_ijk is not None:
                entry["center_hint_ijk"] = center_hint_ijk
            if center_hint_patient_frame_mm is not None:
                entry["center_hint_patient_frame_mm"] = center_hint_patient_frame_mm
        if placeholder_reason is not None:
            entry["placeholder_reason"] = placeholder_reason
        payload.append(entry)
    return payload


def _ijk_to_patient_frame_mm(
    affine: np.ndarray,
    index_ijk: tuple[int, int, int],
) -> list[float]:
    homogeneous = np.array(
        [float(index_ijk[0]), float(index_ijk[1]), float(index_ijk[2]), 1.0],
        dtype=float,
    )
    world = np.asarray(affine, dtype=float) @ homogeneous
    return [float(world[0]), float(world[1]), float(world[2])]


def _compute_label_statistics(
    label_map: np.ndarray,
    affine: np.ndarray,
    *,
    level_map: dict[str, int],
) -> dict[str, dict[str, object]]:
    if not level_map:
        return {}
    max_label = max(level_map.values())
    label_counts = np.bincount(label_map.reshape(-1), minlength=max_label + 1)
    object_slices = ndimage.find_objects(label_map, max_label=max_label)
    statistics: dict[str, dict[str, object]] = {}
    for level_id, label_value in level_map.items():
        if label_value <= 0 or label_value >= len(label_counts):
            continue
        if int(label_counts[label_value]) <= 0:
            continue
        slices = object_slices[label_value - 1] if label_value - 1 < len(object_slices) else None
        if slices is None:
            continue
        bounds = [
            [int(axis_slice.start), int(axis_slice.stop)]
            for axis_slice in slices
        ]
        roi = label_map[slices] == label_value
        coordinates = np.argwhere(roi)
        if coordinates.size == 0:
            continue
        center_local = coordinates.mean(axis=0)
        center_ijk = (
            int(round(float(center_local[0]) + float(slices[0].start))),
            int(round(float(center_local[1]) + float(slices[1].start))),
            int(round(float(center_local[2]) + float(slices[2].start))),
        )
        statistics[level_id] = {
            "voxel_count": int(label_counts[label_value]),
            "ijk_bounds": bounds,
            "center_hint_ijk": [int(value) for value in center_ijk],
            "center_hint_patient_frame_mm": _ijk_to_patient_frame_mm(affine, center_ijk),
        }
    return statistics


def _copy_file_or_hardlink(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.hardlink_to(source)
    except OSError:
        shutil.copy2(source, destination)


def _write_segmentation_outputs(
    *,
    store: CaseStore,
    manifest: CaseManifest,
    volume,
    label_map: np.ndarray,
    vertebrae_payload: list[dict[str, object]],
    model_name: str,
    model_version: str,
    checkpoint_id: str,
    segmentation_profile: str,
    qc_summary: dict[str, object],
    extra_metadata: dict[str, str] | None = None,
    extra_payload: dict[str, object] | None = None,
    extra_outputs: list[str] | None = None,
    source_label_map_path: Path | None = None,
) -> StageExecutionResult:
    write_started_at = time.perf_counter()
    label_map_path = segmentation_label_map_path(store, manifest)
    if source_label_map_path is None:
        write_label_map(label_map_path, label_map, volume)
    else:
        _copy_file_or_hardlink(source_label_map_path, label_map_path)
    segmentation_path = segmentation_manifest_path(store, manifest)
    normalized_volume_artifact_id = _normalized_volume_artifact_id(manifest)
    serialized_level_map = {
        str(item["vertebra_id"]): int(str(item["label_value"])) for item in vertebrae_payload
    }
    payload = {
        "case_id": manifest.case_id,
        "patient_id": manifest.patient_id,
        "modality": volume.modality,
        "model_name": model_name,
        "model_version": model_version,
        "model_display_name": (
            extra_payload.get("model_display_name")
            if extra_payload is not None
            and isinstance(extra_payload.get("model_display_name"), str)
            else model_name
        ),
        "checkpoint_id": checkpoint_id,
        "segmentation_profile": segmentation_profile,
        "label_map_path": str(label_map_path),
        "source_volume_id": volume.volume_id,
        "source_normalized_volume_artifact_id": normalized_volume_artifact_id,
        "voxel_spacing": list(volume.voxel_spacing or (1.0, 1.0, 1.0)),
        "orientation": volume.orientation,
        "coordinate_frame": "normalized-volume",
        "vertebrae": vertebrae_payload,
        "level_map": serialized_level_map,
        "qc_summary": qc_summary,
        "gui_review_surface": "import",
    }
    if extra_payload is not None:
        payload.update(extra_payload)
    write_json_artifact(segmentation_path, payload)

    normalized_volume_artifact = artifact_for_type(manifest, "normalized-volume")
    metadata = {
        "model_name": model_name,
        "model_version": model_version,
        "model_display_name": payload["model_display_name"],
        "checkpoint_id": checkpoint_id,
        "segmentation_profile": segmentation_profile,
    }
    if extra_metadata is not None:
        metadata.update(extra_metadata)

    segmentation_artifact = PipelineArtifact(
        artifact_id=make_id("artifact"),
        kind="json",
        label="Vertebra Segmentation Contract",
        path=str(segmentation_path),
        stage=PipelineStageName.SEGMENTATION.value,
        artifact_type="segmentation",
        coordinate_frame="normalized-volume",
        review_surface="import",
        summary="Per-vertebra label contract prepared for Import review.",
        source_artifact_ids=(
            [normalized_volume_artifact.artifact_id]
            if normalized_volume_artifact is not None
            else []
        ),
        metadata=metadata,
    )
    label_map_artifact = PipelineArtifact(
        artifact_id=make_id("artifact"),
        kind="nifti",
        label="Segmentation Label Map",
        path=str(label_map_path),
        stage=PipelineStageName.SEGMENTATION.value,
        artifact_type="segmentation-label-map",
        coordinate_frame="normalized-volume",
        review_surface="import",
        summary="Label map generated for the real GUI Analyze path.",
        source_artifact_ids=[segmentation_artifact.artifact_id],
        metadata={
            "label_count": str(len(vertebrae_payload)),
            "segmentation_profile": segmentation_profile,
        },
    )
    outputs = [str(segmentation_path), str(label_map_path)]
    if extra_outputs is not None:
        outputs.extend(extra_outputs)
    return StageExecutionResult(
        stage=PipelineStageName.SEGMENTATION,
        message="Prepared vertebra segmentation artifacts for Import review.",
        outputs=outputs,
        timings={
            "write_outputs_seconds": round(time.perf_counter() - write_started_at, 6),
        },
        artifacts=[segmentation_artifact, label_map_artifact],
    )

def _materialize_input_nifti(volume, working_root: Path) -> Path:
    source_path = Path(volume.canonical_path)
    output_path = working_root / "normalized-volume.nii.gz"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = "".join(source_path.suffixes).lower()
    if source_path.is_file() and suffix in {".nii", ".nii.gz"}:
        _copy_file_or_hardlink(source_path, output_path)
        return output_path
    if source_path.is_file():
        image = sitk.ReadImage(str(source_path))
        sitk.WriteImage(image, str(output_path))
        return output_path
    if source_path.is_dir():
        series_ids = sitk.ImageSeriesReader.GetGDCMSeriesIDs(str(source_path))
        reader = sitk.ImageSeriesReader()
        if series_ids:
            file_names = sitk.ImageSeriesReader.GetGDCMSeriesFileNames(
                str(source_path),
                series_ids[0],
            )
            reader.SetFileNames(list(file_names))
            image = reader.Execute()
            sitk.WriteImage(image, str(output_path))
            return output_path
        slice_paths = sorted(
            [path for path in source_path.iterdir() if path.is_file()],
            key=lambda path: path.name.lower(),
        )
        if not slice_paths:
            raise ValueError(f"CT stack directory is empty: {source_path}")
        reader.SetFileNames([str(path) for path in slice_paths])
        image = reader.Execute()
        sitk.WriteImage(image, str(output_path))
        return output_path
    raise ValueError(f"Unsupported normalized CT input path: {source_path}")


def _write_production_run_manifest(
    *,
    store: CaseStore,
    manifest: CaseManifest,
    runtime_model,
    staged_volume_path: Path,
    prediction_result,
    prediction_path: Path,
) -> Path:
    run_manifest_path = segmentation_run_manifest_path(store, manifest)
    source_volume = primary_ct_volume(manifest)
    payload = {
        "case_id": manifest.case_id,
        "source_volume_id": source_volume.volume_id if source_volume is not None else "",
        "model_bundle_id": runtime_model.model_id,
        "model_family": runtime_model.family,
        "driver_id": runtime_model.driver_id,
        "runtime_environment_id": runtime_model.environment_id,
        "resolved_checkpoint_id": runtime_model.checkpoint.checkpoint_id,
        "checkpoint_name": runtime_model.checkpoint.checkpoint_name,
        "checkpoint_path": str(runtime_model.checkpoint_path),
        "runtime_results_root": str(runtime_model.runtime_results_root),
        "staged_volume_path": str(staged_volume_path),
        "prediction_path": str(prediction_path),
        "prediction_diagnostics_path": (
            str(prediction_result.outputs[0].diagnostics_path)
            if prediction_result.outputs
            and prediction_result.outputs[0].diagnostics_path is not None
            else ""
        ),
        "prediction_dir": str(prediction_result.prediction_dir),
        "staged_input_dir": str(prediction_result.staged_input_dir),
        "command": list(prediction_result.command),
        "sidecar_log_path": (
            str(prediction_result.log_path) if prediction_result.log_path is not None else ""
        ),
        "device": prediction_result.device,
        "started_at_utc": prediction_result.started_at_utc,
        "finished_at_utc": prediction_result.finished_at_utc,
        "stdout": prediction_result.stdout,
        "stderr": prediction_result.stderr,
    }
    write_json_artifact(run_manifest_path, payload)
    return run_manifest_path


def _run_scaffold_segmentation(
    store: CaseStore,
    manifest: CaseManifest,
    volume,
    *,
    progress_callback: SegmentationProgressCallback | None = None,
) -> StageExecutionResult:
    _emit_segmentation_progress(progress_callback, 0.10, "Preparing scaffold segmentation")
    _set_segmentation_backend(manifest, backend_tool="internal", environment_id="app")
    stage_started_at = time.perf_counter()
    label_map = populate_label_map(volume.dimensions)
    _emit_segmentation_progress(progress_callback, 0.55, "Synthesizing vertebra label map")
    populate_elapsed = time.perf_counter() - stage_started_at
    synthetic_levels = synthetic_vertebrae()
    level_map = {vertebra.vertebra_id: vertebra.label_value for vertebra in synthetic_levels}
    label_statistics_started_at = time.perf_counter()
    label_statistics = _compute_label_statistics(
        label_map,
        np.diag(
            [
                *(volume.voxel_spacing or (1.0, 1.0, 1.0)),
                1.0,
            ]
        ),
        level_map=level_map,
    )
    label_statistics_elapsed = time.perf_counter() - label_statistics_started_at
    _emit_segmentation_progress(
        progress_callback,
        0.85,
        "Preparing labeled vertebra outputs",
    )
    vertebrae_payload = _build_vertebrae_payload(
        level_map=level_map,
        label_statistics=label_statistics,
        placeholder_reason="GUI-first segmentation scaffold until nnU-Net bundle lands.",
    )
    _emit_segmentation_progress(progress_callback, 0.95, "Writing segmentation contract")
    result = _write_segmentation_outputs(
        store=store,
        manifest=manifest,
        volume=volume,
        label_map=label_map,
        vertebrae_payload=vertebrae_payload,
        model_name=SEGMENTATION_MODEL_NAME,
        model_version=SEGMENTATION_MODEL_VERSION,
        checkpoint_id="cads-pretrained",
        segmentation_profile=SegmentationProfile.SCAFFOLD.value,
        qc_summary={
            "status": "scaffold",
            "message": (
                "Segmentation review path is wired in-app; production nnU-Net "
                "weights are still pending."
            ),
            "label_statistics_ready": True,
            "vertebra_count": len(vertebrae_payload),
        },
    )
    result.timings.update(
        {
            "populate_label_map_seconds": round(populate_elapsed, 6),
            "label_statistics_seconds": round(label_statistics_elapsed, 6),
        }
    )
    return result


def _run_production_segmentation(
    store: CaseStore,
    manifest: CaseManifest,
    volume,
    *,
    performance_policy: ResolvedPerformancePolicy | None = None,
    progress_callback: SegmentationProgressCallback | None = None,
    disable_tta: bool = False,
    tile_step_size: float = 0.5,
) -> StageExecutionResult:
    _emit_segmentation_progress(
        progress_callback,
        0.10,
        "Resolving active segmentation bundle",
    )
    registry = SegmentationBundleRegistry(store)
    bundle = registry.resolve_active_bundle()
    runtime_model = bundle.active_runtime_model()
    if runtime_model.modality != volume.modality:
        raise ValueError(
            "Active segmentation bundle modality "
            f"{runtime_model.modality!r} does not match case modality {volume.modality!r}."
        )

    _set_segmentation_backend(
        manifest,
        backend_tool=runtime_model.driver_id,
        environment_id=runtime_model.environment_id,
    )
    runtime_device = _resolve_production_runtime_device(
        manifest,
        driver_id=runtime_model.driver_id,
    )
    _validate_runtime_device(
        driver_id=runtime_model.driver_id,
        runtime_device=runtime_device,
    )
    production_started_at = time.perf_counter()
    working_root = stage_root(store, manifest, PipelineStageName.SEGMENTATION.value) / "runtime"
    if working_root.exists():
        shutil.rmtree(working_root, ignore_errors=True)
    staged_volume_started_at = time.perf_counter()
    _emit_segmentation_progress(progress_callback, 0.20, "Staging normalized volume input")
    staged_volume_path = _materialize_input_nifti(volume, working_root)
    staged_volume_elapsed = time.perf_counter() - staged_volume_started_at

    resolved_policy = performance_policy or active_performance_policy()
    driver = resolve_segmentation_driver(
        runtime_model.driver_id,
        performance_policy=resolved_policy,
    )
    prediction_started_at = time.perf_counter()

    def _prediction_progress(fraction: float, detail: str) -> None:
        mapped = 0.20 + (fraction * 0.65)
        _emit_segmentation_progress(progress_callback, mapped, detail)

    _emit_segmentation_progress(progress_callback, 0.20, "Starting backend prediction")
    with performance_coordinator().segmentation_slot():
        prediction_result = driver.predict(
            staged_volume_path,
            runtime_model,
            working_root / "predict",
            device=runtime_device,
            disable_tta=disable_tta,
            tile_step_size=tile_step_size,
            progress_callback=_prediction_progress,
        )
    prediction_elapsed = time.perf_counter() - prediction_started_at
    prediction_output = prediction_result.outputs[0]

    label_map_started_at = time.perf_counter()
    _emit_segmentation_progress(
        progress_callback,
        0.85,
        "Preparing labeled vertebra outputs",
    )
    label_image: Any = nib.load(str(prediction_output.prediction_path))
    label_map = np.asarray(label_image.dataobj, dtype=np.int16)
    label_statistics = _compute_label_statistics(
        label_map,
        np.asarray(label_image.affine, dtype=float),
        level_map=runtime_model.label_mapping,
    )
    label_statistics_elapsed = time.perf_counter() - label_map_started_at
    present_level_map = {
        level_id: label_value
        for level_id, label_value in runtime_model.label_mapping.items()
        if level_id in label_statistics
    }
    if not present_level_map:
        raise ValueError(
            "Production segmentation completed without any labeled vertebrae in the "
            "prediction volume."
        )
    vertebrae_payload = _build_vertebrae_payload(
        level_map=present_level_map,
        label_statistics=label_statistics,
    )
    run_manifest_path = _write_production_run_manifest(
        store=store,
        manifest=manifest,
        runtime_model=runtime_model,
        staged_volume_path=staged_volume_path,
        prediction_result=prediction_result,
        prediction_path=prediction_output.prediction_path,
    )
    _emit_segmentation_progress(progress_callback, 0.95, "Writing segmentation contract")
    result = _write_segmentation_outputs(
        store=store,
        manifest=manifest,
        volume=volume,
        label_map=label_map,
        vertebrae_payload=vertebrae_payload,
        model_name=runtime_model.family,
        model_version=runtime_model.model_id,
        checkpoint_id=runtime_model.checkpoint.checkpoint_id,
        segmentation_profile=SegmentationProfile.PRODUCTION.value,
        qc_summary={
            "status": "complete",
            "message": "Production segmentation backend executed successfully.",
            "label_statistics_ready": True,
            "vertebra_count": len(vertebrae_payload),
            "expected_vertebra_count": len(runtime_model.label_mapping),
        },
        extra_metadata={
            "model_bundle_id": runtime_model.model_id,
            "model_display_name": runtime_model.display_name,
            "model_family": runtime_model.family,
            "driver_id": runtime_model.driver_id,
            "runtime_environment_id": runtime_model.environment_id,
            "resolved_checkpoint_id": runtime_model.checkpoint.checkpoint_id,
        },
        extra_payload={
            "model_bundle_id": runtime_model.model_id,
            "model_display_name": runtime_model.display_name,
            "model_family": runtime_model.family,
            "driver_id": runtime_model.driver_id,
            "runtime_environment_id": runtime_model.environment_id,
            "resolved_checkpoint_id": runtime_model.checkpoint.checkpoint_id,
            "segmentation_run_manifest_path": str(run_manifest_path),
        },
        extra_outputs=[str(run_manifest_path)],
        source_label_map_path=prediction_output.prediction_path,
    )
    run_manifest_artifact = PipelineArtifact(
        artifact_id=make_id("artifact"),
        kind="json",
        label="Segmentation Run Manifest",
        path=str(run_manifest_path),
        stage=PipelineStageName.SEGMENTATION.value,
        artifact_type="segmentation-run-manifest",
        coordinate_frame="normalized-volume",
        review_surface="import",
        summary="Runtime provenance for the production segmentation execution.",
        source_artifact_ids=[],
        metadata={
            "model_bundle_id": runtime_model.model_id,
            "driver_id": runtime_model.driver_id,
            "runtime_environment_id": runtime_model.environment_id,
            "resolved_checkpoint_id": runtime_model.checkpoint.checkpoint_id,
        },
    )
    if result.artifacts:
        run_manifest_artifact.source_artifact_ids = [result.artifacts[0].artifact_id]
    result.artifacts.append(run_manifest_artifact)
    result.timings.update(
        {
            "production_stage_seconds": round(time.perf_counter() - production_started_at, 6),
            "materialize_input_volume_seconds": round(staged_volume_elapsed, 6),
            "prediction_seconds": round(prediction_elapsed, 6),
            "label_statistics_seconds": round(label_statistics_elapsed, 6),
        }
    )
    return result


def run_segmentation_stage(
    store: CaseStore,
    manifest: CaseManifest,
    *,
    performance_policy: ResolvedPerformancePolicy | None = None,
    progress_callback: SegmentationProgressCallback | None = None,
    disable_tta: bool = False,
    tile_step_size: float = 0.5,
) -> StageExecutionResult:
    volume = primary_ct_volume(manifest)
    if volume is None or volume.modality != "ct":
        raise ValueError("Segmentation requires a normalized CT volume assigned to the case.")

    profile = canonical_segmentation_profile(manifest.segmentation_profile)
    manifest.segmentation_profile = profile
    if profile == SegmentationProfile.SCAFFOLD.value:
        return _run_scaffold_segmentation(
            store,
            manifest,
            volume,
            progress_callback=progress_callback,
        )
    return _run_production_segmentation(
        store,
        manifest,
        volume,
        performance_policy=performance_policy,
        progress_callback=progress_callback,
        disable_tta=disable_tta,
        tile_step_size=tile_step_size,
    )
