from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from spinelab.io import CaseStore
from spinelab.models import CaseManifest, PipelineArtifact
from spinelab.models.manifest import make_id
from spinelab.pipeline.artifacts import (
    point_cloud_data_dir,
    point_cloud_manifest_path,
    point_cloud_mesh_dir,
    prepared_scene_path,
    write_json_artifact,
)
from spinelab.pipeline.contracts import PipelineStageName, StageExecutionResult
from spinelab.pipeline.stages.common import (
    analysis_generated_asset_id,
    artifact_for_type,
    read_json_payload,
)
from spinelab.pipeline.stages.mesh_pipeline import (
    hydrate_segmentation_entries,
    label_statistics_for_entries,
    load_label_map,
    parse_segmentation_entries,
    write_polydata,
)
from spinelab.pipeline.stages.point_cloud_pipeline import (
    POINT_CLOUD_PIPELINE_VERSION,
    PointCloudPipelineConfig,
    extract_vertebra_point_cloud,
    write_point_cloud_ply,
)
from spinelab.services import active_performance_policy, configure_runtime_policy


def run_point_cloud_stage(
    store: CaseStore, manifest: CaseManifest
) -> StageExecutionResult:
    configure_runtime_policy()
    segmentation_artifact = artifact_for_type(manifest, "segmentation")
    if segmentation_artifact is None:
        raise ValueError("Point cloud extraction requires a segmentation artifact.")

    segmentation_payload = read_json_payload(manifest, "segmentation")
    if segmentation_payload is None:
        raise ValueError(
            "Point cloud extraction requires a readable segmentation contract."
        )

    label_map_path_raw = segmentation_payload.get("label_map_path")
    if not isinstance(label_map_path_raw, str) or not label_map_path_raw:
        raise ValueError("Segmentation contract is missing the label map path.")

    stage_started_at = time.perf_counter()
    parse_started_at = time.perf_counter()
    vertebra_entries = parse_segmentation_entries(segmentation_payload)
    if not vertebra_entries:
        raise ValueError(
            "Segmentation contract does not expose any vertebra label entries."
        )

    label_map_path = Path(label_map_path_raw)
    if not label_map_path.is_absolute():
        label_map_path = (
            Path(segmentation_artifact.path).parent / label_map_path
        ).resolve()

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

    pc_dir = point_cloud_data_dir(store, manifest)
    pc_dir.mkdir(parents=True, exist_ok=True)
    mesh_dir = point_cloud_mesh_dir(store, manifest)
    mesh_dir.mkdir(parents=True, exist_ok=True)

    config = PointCloudPipelineConfig()
    policy = active_performance_policy()
    backend_metadata = {
        "model_bundle_id": str(segmentation_payload.get("model_bundle_id", "")),
        "model_display_name": str(
            segmentation_payload.get("model_display_name", "")
        ),
        "model_family": str(segmentation_payload.get("model_family", "")),
        "driver_id": str(segmentation_payload.get("driver_id", "")),
        "runtime_environment_id": str(
            segmentation_payload.get("runtime_environment_id", "")
        ),
        "resolved_checkpoint_id": str(
            segmentation_payload.get("resolved_checkpoint_id", "")
        ),
    }
    warnings: list[str] = []
    manifest_entries: list[dict[str, object]] = []
    scene_entries: list[dict[str, object]] = []
    complete_count = 0

    extraction_started_at = time.perf_counter()
    max_workers = min(
        max(policy.cpu_heavy_workers, 1), max(len(vertebra_entries), 1)
    )
    if max_workers > 1:
        with ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="pointcloud-stage",
        ) as executor:
            results = list(
                executor.map(
                    lambda current_entry: extract_vertebra_point_cloud(
                        label_map_data,
                        label_map_affine,
                        current_entry,
                        config=config,
                        seed_key=manifest.case_id,
                    ),
                    vertebra_entries,
                )
            )
    else:
        results = [
            extract_vertebra_point_cloud(
                label_map_data,
                label_map_affine,
                entry,
                config=config,
                seed_key=manifest.case_id,
            )
            for entry in vertebra_entries
        ]
    extraction_elapsed = time.perf_counter() - extraction_started_at

    write_started_at = time.perf_counter()
    for entry, result in zip(vertebra_entries, results, strict=True):
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
                [float(value) for value in row]
                for row in result.roi_affine.tolist()
            ],
            "surface_nets_vertex_count": result.surface_nets_vertex_count,
            "elapsed_seconds": round(float(result.elapsed_seconds), 6),
        }
        if result.status != "complete":
            warnings.append(f"{entry.vertebra_id}: {result.status}")
            manifest_entries.append(entry_payload)
            continue

        point_cloud_path = pc_dir / f"{entry.vertebra_id}.ply"
        mesh_ply_path = mesh_dir / f"{entry.vertebra_id}.ply"
        if result.points is None or result.normals is None:
            warnings.append(f"{entry.vertebra_id}: missing point cloud data")
            manifest_entries.append(entry_payload)
            continue

        write_point_cloud_ply(
            point_cloud_path,
            points=result.points,
            normals=result.normals,
        )

        if result.mesh_polydata is not None:
            write_polydata(mesh_ply_path, result.mesh_polydata)

        entry_payload.update(
            {
                "point_cloud_path": str(point_cloud_path),
                "mesh_path": str(mesh_ply_path),
                "center_mm": [float(v) for v in result.center_mm]
                if result.center_mm
                else None,
                "extents_mm": [float(v) for v in result.extents_mm]
                if result.extents_mm
                else None,
            }
        )
        if result.center_mm and result.extents_mm:
            scene_entries.append(
                {
                    "vertebra_id": entry.vertebra_id,
                    "display_label": entry.display_label,
                    "selection_key": entry.vertebra_id,
                    "pose_name": "baseline",
                    "mesh_path": str(mesh_ply_path),
                    "center_mm": [float(v) for v in result.center_mm],
                    "extents_mm": [float(v) for v in result.extents_mm],
                }
            )
        complete_count += 1
        manifest_entries.append(entry_payload)
    write_elapsed = time.perf_counter() - write_started_at

    if complete_count == 0:
        raise ValueError(
            "Point cloud extraction produced no valid vertebra point clouds."
        )

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
            "models": scene_entries,
        },
    )
    prepared_scene_elapsed = time.perf_counter() - prepared_scene_started_at

    manifest_output = point_cloud_manifest_path(store, manifest)
    write_json_artifact(
        manifest_output,
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
                [float(value) for value in row]
                for row in label_map_affine.tolist()
            ],
            "pipeline_version": POINT_CLOUD_PIPELINE_VERSION,
            "extraction_algorithm": "vtk_surface_nets",
            "surface_nets_settings": {
                "iterations": config.surface_nets_iterations,
                "relaxation_factor": config.surface_nets_relaxation_factor,
            },
            "point_cloud_settings": {
                "target_size": config.point_cloud_size,
                "subsampling": "farthest_point_sampling",
            },
            "coordinate_frame": "surface-mesh",
            "source_coordinate_frame": "normalized-volume",
            "surface_from_volume_transform": {
                "type": "label-map-physical-space",
                "note": (
                    "Point cloud positions are in the physical world frame "
                    "defined by the segmentation label-map affine."
                ),
            },
            "qc_summary": {
                "status": "complete",
                "requested_vertebra_count": len(vertebra_entries),
                "produced_vertebra_count": complete_count,
                "missing_or_failed_vertebra_count": len(vertebra_entries)
                - complete_count,
                "warnings": warnings,
            },
            "vertebrae": manifest_entries,
            "gui_review_surface": "measurement",
        },
    )

    pc_manifest_artifact = PipelineArtifact(
        artifact_id=make_id("artifact"),
        kind="json",
        label="Per-Vertebra Point Cloud Manifest",
        path=str(manifest_output),
        stage=PipelineStageName.POINT_CLOUD.value,
        artifact_type="point-cloud-manifest",
        coordinate_frame="surface-mesh",
        review_surface="measurement",
        summary="Smooth point clouds extracted from segmentation via Surface Nets.",
        source_artifact_ids=[segmentation_artifact.artifact_id],
        metadata={
            "algorithm": "vtk_surface_nets",
            "vertebra_count": str(complete_count),
            "point_cloud_dir": str(pc_dir),
            "mesh_dir": str(mesh_dir),
            **backend_metadata,
        },
    )
    pc_data_asset_id = analysis_generated_asset_id(
        PipelineStageName.POINT_CLOUD.value, "data"
    )
    pc_data_artifact = PipelineArtifact(
        artifact_id=make_id("artifact"),
        kind="directory",
        label="Vertebra Point Clouds",
        path=str(pc_dir),
        stage=PipelineStageName.POINT_CLOUD.value,
        artifact_type="point-cloud-data",
        coordinate_frame="surface-mesh",
        review_surface="measurement",
        status="complete",
        summary="Per-vertebra point clouds for PTv3 inference.",
        asset_id=pc_data_asset_id,
        source_artifact_ids=[pc_manifest_artifact.artifact_id],
        metadata={"vertebra_count": str(complete_count)},
    )
    pc_data_artifact.metadata.update(backend_metadata)
    prepared_scene_artifact = PipelineArtifact(
        artifact_id=make_id("artifact"),
        kind="json",
        label="Prepared Baseline Scene",
        path=str(prepared_scene_output),
        stage=PipelineStageName.POINT_CLOUD.value,
        artifact_type="prepared-scene-baseline",
        coordinate_frame="surface-mesh",
        review_surface="measurement",
        summary="Prepared baseline scene metadata for Measurement and Report reuse.",
        source_artifact_ids=[pc_manifest_artifact.artifact_id],
        metadata={
            "pose_name": "baseline",
            "model_count": str(len(scene_entries)),
        },
    )
    prepared_scene_artifact.metadata.update(backend_metadata)

    message = f"Extracted {complete_count} vertebra point cloud(s) via Surface Nets."
    return StageExecutionResult(
        stage=PipelineStageName.POINT_CLOUD,
        message=message,
        outputs=[
            str(manifest_output),
            str(pc_dir),
            str(mesh_dir),
            str(prepared_scene_output),
        ],
        artifacts=[
            pc_manifest_artifact,
            pc_data_artifact,
            prepared_scene_artifact,
        ],
        warnings=warnings,
        timings={
            "parse_inputs_seconds": round(parse_elapsed, 6),
            "load_label_map_seconds": round(load_label_map_elapsed, 6),
            "label_statistics_seconds": round(label_statistics_elapsed, 6),
            "extraction_seconds": round(extraction_elapsed, 6),
            "write_seconds": round(write_elapsed, 6),
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
