from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from spinelab.io import CaseStore
from spinelab.models import CaseManifest, PipelineArtifact
from spinelab.models.manifest import make_id
from spinelab.ontology import SURFACE_PATCH_SCHEMA_VERSION
from spinelab.pipeline.artifacts import (
    baseline_mesh_dir,
    inference_mesh_dir,
    mesh_manifest_path,
    point_cloud_dir,
    prepared_scene_path,
    raw_mesh_dir,
    write_json_artifact,
)
from spinelab.pipeline.contracts import PipelineStageName, StageExecutionResult
from spinelab.pipeline.stages.common import (
    analysis_generated_asset_id,
    artifact_for_type,
    read_json_payload,
)
from spinelab.pipeline.stages.mesh_pipeline import (
    BENCHMARK_EXTRACTION_ALGORITHMS,
    DEFAULT_EXTRACTION_ALGORITHM,
    MESH_PIPELINE_VERSION,
    MeshPipelineConfig,
    extract_vertebra_mesh,
    file_checksum,
    hydrate_segmentation_entries,
    label_statistics_for_entries,
    load_label_map,
    mesh_center_and_extents,
    parse_segmentation_entries,
    write_point_cloud,
    write_polydata,
)
from spinelab.services import active_performance_policy, configure_runtime_policy


def run_mesh_stage(store: CaseStore, manifest: CaseManifest) -> StageExecutionResult:
    configure_runtime_policy()
    segmentation_artifact = artifact_for_type(manifest, "segmentation")
    if segmentation_artifact is None:
        raise ValueError("Mesh generation requires a segmentation artifact.")

    segmentation_payload = read_json_payload(manifest, "segmentation")
    if segmentation_payload is None:
        raise ValueError("Mesh generation requires a readable segmentation contract.")

    label_map_path_raw = segmentation_payload.get("label_map_path")
    if not isinstance(label_map_path_raw, str) or not label_map_path_raw:
        raise ValueError("Segmentation contract is missing the label map path.")

    stage_started_at = time.perf_counter()
    parse_started_at = time.perf_counter()
    vertebra_entries = parse_segmentation_entries(segmentation_payload)
    if not vertebra_entries:
        raise ValueError("Segmentation contract does not expose any vertebra label entries.")

    label_map_path = Path(label_map_path_raw)
    if not label_map_path.is_absolute():
        label_map_path = (Path(segmentation_artifact.path).parent / label_map_path).resolve()
    load_label_map_started_at = time.perf_counter()
    label_map_data, label_map_affine = load_label_map(label_map_path)
    load_label_map_elapsed = time.perf_counter() - load_label_map_started_at
    label_statistics_started_at = time.perf_counter()
    label_statistics = label_statistics_for_entries(label_map_data, vertebra_entries)
    vertebra_entries = hydrate_segmentation_entries(
        vertebra_entries,
        label_statistics,
        label_map_affine,
    )
    parse_elapsed = time.perf_counter() - parse_started_at
    label_statistics_elapsed = time.perf_counter() - label_statistics_started_at

    baseline_dir = baseline_mesh_dir(store, manifest)
    inference_dir = inference_mesh_dir(store, manifest)
    raw_dir = raw_mesh_dir(store, manifest)
    ptv3_dir = point_cloud_dir(store, manifest)
    baseline_dir.mkdir(parents=True, exist_ok=True)
    inference_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    ptv3_dir.mkdir(parents=True, exist_ok=True)

    config = MeshPipelineConfig()
    policy = active_performance_policy()
    backend_metadata = {
        "model_bundle_id": str(segmentation_payload.get("model_bundle_id", "")),
        "model_display_name": str(segmentation_payload.get("model_display_name", "")),
        "model_family": str(segmentation_payload.get("model_family", "")),
        "driver_id": str(segmentation_payload.get("driver_id", "")),
        "runtime_environment_id": str(segmentation_payload.get("runtime_environment_id", "")),
        "resolved_checkpoint_id": str(segmentation_payload.get("resolved_checkpoint_id", "")),
    }
    warnings: list[str] = []
    manifest_entries: list[dict[str, object]] = []
    baseline_scene_entries: list[dict[str, object]] = []
    complete_count = 0
    extraction_started_at = time.perf_counter()
    max_workers = min(max(policy.cpu_heavy_workers, 1), max(len(vertebra_entries), 1))
    if max_workers > 1:
        with ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="mesh-stage",
        ) as executor:
            results = list(
                executor.map(
                    lambda current_entry: extract_vertebra_mesh(
                        label_map_data,
                        label_map_affine,
                        current_entry,
                        algorithm=DEFAULT_EXTRACTION_ALGORITHM,
                        config=config,
                        point_cloud_seed_key=manifest.case_id,
                    ),
                    vertebra_entries,
                )
            )
    else:
        results = [
            extract_vertebra_mesh(
                label_map_data,
                label_map_affine,
                entry,
                algorithm=DEFAULT_EXTRACTION_ALGORITHM,
                config=config,
                point_cloud_seed_key=manifest.case_id,
            )
            for entry in vertebra_entries
        ]
    extraction_elapsed = time.perf_counter() - extraction_started_at

    write_started_at = time.perf_counter()
    for entry, result in zip(vertebra_entries, results, strict=False):
        entry_payload: dict[str, object] = {
            "vertebra_id": entry.vertebra_id,
            "structure_instance_id": entry.structure_instance_id,
            "display_label": entry.display_label,
            "standard_level_id": entry.standard_level_id,
            "region_id": entry.region_id,
            "structure_type": entry.structure_type,
            "order_index": entry.order_index,
            "label_value": entry.label_value,
            "numbering_confidence": entry.numbering_confidence,
            "variant_tags": list(entry.variant_tags),
            "supports_standard_measurements": entry.supports_standard_measurements,
            "superior_neighbor_instance_id": entry.superior_neighbor_instance_id,
            "inferior_neighbor_instance_id": entry.inferior_neighbor_instance_id,
            "voxel_count": entry.voxel_count,
            "status": result.status,
            "coordinate_frame": "surface-mesh",
            "source_coordinate_frame": "normalized-volume",
            "source_segmentation_artifact_id": segmentation_artifact.artifact_id,
            "source_volume_id": segmentation_payload.get("source_volume_id", ""),
            "roi_bounds_ijk": [
                [result.roi_bounds_ijk[0][0], result.roi_bounds_ijk[0][1]],
                [result.roi_bounds_ijk[1][0], result.roi_bounds_ijk[1][1]],
                [result.roi_bounds_ijk[2][0], result.roi_bounds_ijk[2][1]],
            ],
            "roi_affine": [
                [float(value) for value in row] for row in result.roi_affine.tolist()
            ],
            "extraction_algorithm": result.extraction_algorithm,
            "elapsed_seconds": round(float(result.elapsed_seconds), 6),
            "mesh_stats": result.mesh_stats or {},
            "qc_summary": result.qc_summary or {},
        }
        if result.status != "complete":
            warnings.append(f"{entry.vertebra_id}: {result.status}")
            manifest_entries.append(entry_payload)
            continue

        raw_path = raw_dir / f"{entry.vertebra_id}.ply"
        baseline_path = baseline_dir / f"{entry.vertebra_id}.ply"
        inference_path = inference_dir / f"{entry.vertebra_id}.ply"
        point_cloud_path = ptv3_dir / f"{entry.vertebra_id}.npz"
        assert result.point_cloud is not None
        assert result.point_normals is not None

        write_polydata(raw_path, result.raw_mesh)
        write_polydata(baseline_path, result.measurement_mesh)
        write_polydata(inference_path, result.inference_mesh)
        write_point_cloud(
            point_cloud_path,
            points=result.point_cloud,
            normals=result.point_normals,
            vertebra_id=entry.vertebra_id,
            structure_instance_id=entry.structure_instance_id,
            standard_level_id=entry.standard_level_id,
            display_label=entry.display_label,
            coordinate_frame="surface-mesh",
            source_mesh_path=baseline_path,
        )

        entry_payload.update(
            {
                "raw_mesh_path": str(raw_path),
                "high_resolution_mesh_path": str(baseline_path),
                "inference_mesh_path": str(inference_path),
                "point_cloud_path": str(point_cloud_path),
                "checksum": file_checksum(baseline_path),
            }
        )
        center, extents = mesh_center_and_extents(result.measurement_mesh)
        baseline_scene_entries.append(
            {
                "vertebra_id": entry.vertebra_id,
                "display_label": entry.display_label,
                "selection_key": entry.vertebra_id,
                "mesh_path": str(baseline_path),
                "pose_name": "baseline",
                "center_mm": [float(value) for value in center],
                "extents_mm": [float(value) for value in extents],
                "checksum": entry_payload["checksum"],
            }
        )
        complete_count += 1
        manifest_entries.append(entry_payload)
    write_elapsed = time.perf_counter() - write_started_at

    if complete_count == 0:
        raise ValueError("Mesh generation produced no measurement-grade vertebra meshes.")

    prepared_scene_started_at = time.perf_counter()
    prepared_scene_output = prepared_scene_path(store, manifest, "baseline")
    write_json_artifact(
        prepared_scene_output,
        {
            "schema_version": "spinelab.prepared_scene.v1",
            "case_id": manifest.case_id,
            "pose_name": "baseline",
            "coordinate_frame": "surface-mesh",
            "source_segmentation_artifact_id": segmentation_artifact.artifact_id,
            "models": baseline_scene_entries,
        },
    )
    prepared_scene_elapsed = time.perf_counter() - prepared_scene_started_at

    manifest_path = mesh_manifest_path(store, manifest)
    write_json_artifact(
        manifest_path,
        {
            "case_id": manifest.case_id,
            "source_volume_id": segmentation_payload.get("source_volume_id", ""),
            "source_segmentation_artifact_id": segmentation_artifact.artifact_id,
            "source_segmentation_version": segmentation_artifact.metadata.get(
                "model_version",
                segmentation_payload.get("model_version", "pending"),
            ),
            "segmentation_backend": backend_metadata,
            "label_map_path": label_map_path_raw,
            "label_map_affine": [
                [float(value) for value in row] for row in label_map_affine.tolist()
            ],
            "pipeline_version": MESH_PIPELINE_VERSION,
            "canonical_mesh_type": "triangles",
            "mesh_file_format": "binary_little_endian_ply",
            "extraction_algorithm": DEFAULT_EXTRACTION_ALGORITHM,
            "benchmark_candidates": list(BENCHMARK_EXTRACTION_ALGORITHMS),
            "smoothing_settings": {
                "measurement_smoothing": {
                    "algorithm": "vtkWindowedSincPolyDataFilter",
                    "iterations": config.measurement_smoothing_iterations,
                    "pass_band": config.measurement_smoothing_pass_band,
                    "minimum_triangle_count": config.measurement_min_cells_for_smoothing,
                }
            },
            "decimation_settings": {
                "inference_decimation": {
                    "algorithm": "vtkQuadricDecimation",
                    "target_reduction": config.inference_target_reduction,
                    "minimum_triangle_count": config.inference_min_cells_for_decimation,
                }
            },
            "point_cloud_settings": {
                "sample_count": config.point_cloud_size,
                "sampling": "area_weighted_triangle_sampling",
                "surface_patch_schema_version": SURFACE_PATCH_SCHEMA_VERSION,
            },
            "coordinate_frame": "surface-mesh",
            "source_coordinate_frame": "normalized-volume",
            "surface_from_volume_transform": {
                "type": "label-map-physical-space",
                "note": (
                    "Mesh vertices are written in the physical world frame defined by the "
                    "segmentation label-map affine."
                ),
            },
            "qc_summary": {
                "status": "complete",
                "requested_vertebra_count": len(vertebra_entries),
                "produced_vertebra_count": complete_count,
                "missing_or_failed_vertebra_count": len(vertebra_entries) - complete_count,
                "warnings": warnings,
            },
            "vertebrae": manifest_entries,
            "gui_review_surface": "measurement",
        },
    )

    mesh_manifest_artifact = PipelineArtifact(
        artifact_id=make_id("artifact"),
        kind="json",
        label="Per-Vertebra Mesh Manifest",
        path=str(manifest_path),
        stage=PipelineStageName.MESH.value,
        artifact_type="mesh-manifest",
        coordinate_frame="surface-mesh",
        review_surface="measurement",
        summary="Production vertebra meshes prepared from the segmentation label map.",
        source_artifact_ids=[segmentation_artifact.artifact_id],
        metadata={
            "algorithm": DEFAULT_EXTRACTION_ALGORITHM,
            "vertebra_count": str(complete_count),
            "point_cloud_dir": str(ptv3_dir),
            **backend_metadata,
        },
    )
    baseline_asset_id = analysis_generated_asset_id(PipelineStageName.MESH.value, "baseline")
    baseline_mesh_artifact = PipelineArtifact(
        artifact_id=make_id("artifact"),
        kind="directory",
        label="Baseline Vertebra Meshes",
        path=str(baseline_dir),
        stage=PipelineStageName.MESH.value,
        artifact_type="mesh-baseline",
        coordinate_frame="surface-mesh",
        review_surface="measurement",
        status="complete",
        summary="Measurement-grade vertebra meshes for Measurement review.",
        asset_id=baseline_asset_id,
        source_artifact_ids=[mesh_manifest_artifact.artifact_id],
        metadata={"vertebra_count": str(complete_count)},
    )
    baseline_mesh_artifact.metadata.update(backend_metadata)
    inference_mesh_artifact = PipelineArtifact(
        artifact_id=make_id("artifact"),
        kind="directory",
        label="PTv3 Inference Meshes",
        path=str(inference_dir),
        stage=PipelineStageName.MESH.value,
        artifact_type="mesh-inference",
        coordinate_frame="surface-mesh",
        review_surface="measurement",
        summary="Inference meshes and PTv3-ready point clouds derived from measurement meshes.",
        source_artifact_ids=[mesh_manifest_artifact.artifact_id],
        metadata={
            "raw_mesh_dir": str(raw_dir),
            "point_cloud_dir": str(ptv3_dir),
            "vertebra_count": str(complete_count),
            **backend_metadata,
        },
    )
    prepared_scene_artifact = PipelineArtifact(
        artifact_id=make_id("artifact"),
        kind="json",
        label="Prepared Baseline Scene",
        path=str(prepared_scene_output),
        stage=PipelineStageName.MESH.value,
        artifact_type="prepared-scene-baseline",
        coordinate_frame="surface-mesh",
        review_surface="measurement",
        summary="Prepared baseline scene metadata for Measurement and Report reuse.",
        source_artifact_ids=[mesh_manifest_artifact.artifact_id],
        metadata={"pose_name": "baseline", "model_count": str(len(baseline_scene_entries))},
    )
    prepared_scene_artifact.metadata.update(backend_metadata)
    message = (
        f"Prepared {complete_count} production vertebra mesh(es) for Measurement review."
    )
    return StageExecutionResult(
        stage=PipelineStageName.MESH,
        message=message,
        outputs=[
            str(manifest_path),
            str(raw_dir),
            str(baseline_dir),
            str(inference_dir),
            str(ptv3_dir),
            str(prepared_scene_output),
        ],
        artifacts=[
            mesh_manifest_artifact,
            baseline_mesh_artifact,
            inference_mesh_artifact,
            prepared_scene_artifact,
        ],
        warnings=warnings,
        timings={
            "parse_inputs_seconds": round(parse_elapsed, 6),
            "load_label_map_seconds": round(load_label_map_elapsed, 6),
            "label_statistics_seconds": round(label_statistics_elapsed, 6),
            "mesh_extraction_seconds": round(extraction_elapsed, 6),
            "mesh_write_seconds": round(write_elapsed, 6),
            "prepared_scene_seconds": round(prepared_scene_elapsed, 6),
            "stage_preamble_seconds": round(
                max(
                    0.0,
                    (extraction_started_at - stage_started_at)
                    - parse_elapsed
                    - load_label_map_elapsed
                    - label_statistics_elapsed,
                ),
                6,
            ),
        },
    )
