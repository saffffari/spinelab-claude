from __future__ import annotations

import time

import numpy as np

from spinelab.io import CaseStore
from spinelab.models import CaseManifest, PipelineArtifact
from spinelab.models.manifest import make_id
from spinelab.ontology import STANDARD_LEVEL_INDEX
from spinelab.pipeline.artifacts import (
    pose_graph_path,
    prepared_scene_path,
    registration_scene_path,
    write_json_artifact,
)
from spinelab.pipeline.contracts import PipelineStageName, StageExecutionResult
from spinelab.pipeline.stages.common import (
    REGISTRATION_MODEL_NAME,
    REGISTRATION_MODEL_VERSION,
    analysis_generated_asset_id,
    artifact_for_type,
    homogeneous_transform,
    maybe_write_glb_scene,
    read_json_payload,
    rotation_matrix_xyz,
    synthetic_vertebrae,
    transform_to_payload,
)


def _apply_transform_to_point(
    transform: np.ndarray,
    point_xyz: tuple[float, float, float],
) -> list[float]:
    homogeneous = np.array([point_xyz[0], point_xyz[1], point_xyz[2], 1.0], dtype=float)
    transformed = np.asarray(transform, dtype=float) @ homogeneous
    return [float(transformed[0]), float(transformed[1]), float(transformed[2])]


def _transform_axis_aligned_extents(
    transform: np.ndarray,
    extents_xyz: tuple[float, float, float],
) -> list[float]:
    half_extents = np.asarray(extents_xyz, dtype=float) / 2.0
    corner_signs = np.asarray(
        [
            (-1.0, -1.0, -1.0),
            (-1.0, -1.0, 1.0),
            (-1.0, 1.0, -1.0),
            (-1.0, 1.0, 1.0),
            (1.0, -1.0, -1.0),
            (1.0, -1.0, 1.0),
            (1.0, 1.0, -1.0),
            (1.0, 1.0, 1.0),
        ],
        dtype=float,
    )
    corners = corner_signs * half_extents
    transformed_corners = corners @ np.asarray(transform, dtype=float)[:3, :3].T
    minimum = np.min(transformed_corners, axis=0)
    maximum = np.max(transformed_corners, axis=0)
    return [float(value) for value in (maximum - minimum)]


def _interpolate_scalar(level_id: str, anchors: dict[str, float]) -> float:
    order_index = STANDARD_LEVEL_INDEX.get(level_id)
    if order_index is None:
        raise ValueError(f"Unsupported vertebra level for registration scaffold: {level_id}")
    anchor_order = np.asarray([STANDARD_LEVEL_INDEX[key] for key in anchors], dtype=float)
    anchor_values = np.asarray([anchors[key] for key in anchors], dtype=float)
    return float(np.interp(order_index, anchor_order, anchor_values))


def _interpolate_translation(
    level_id: str,
    anchors: dict[str, tuple[float, float, float]],
) -> tuple[float, float, float]:
    x_offset = _interpolate_scalar(
        level_id,
        {anchor_id: values[0] for anchor_id, values in anchors.items()},
    )
    y_offset = _interpolate_scalar(
        level_id,
        {anchor_id: values[1] for anchor_id, values in anchors.items()},
    )
    z_offset = _interpolate_scalar(
        level_id,
        {anchor_id: values[2] for anchor_id, values in anchors.items()},
    )
    return (x_offset, y_offset, z_offset)


def _standing_transform(vertebra_id: str) -> np.ndarray:
    sagittal_rotation_lookup: dict[str, float] = {
        "C7": 8.0,
        "T4": 16.0,
        "T8": 12.0,
        "T12": 6.0,
        "L1": -8.0,
        "L3": -16.0,
        "L5": -24.0,
        "S1": -32.0,
    }
    coronal_translation_lookup: dict[str, tuple[float, float, float]] = {
        "C7": (1.0, -2.0, 0.0),
        "T4": (1.5, -1.0, 0.0),
        "T8": (1.0, 0.0, 0.0),
        "T12": (0.5, 1.0, 0.0),
        "L1": (0.0, 2.0, 0.0),
        "L3": (-0.5, 2.5, 0.0),
        "L5": (-1.0, 3.0, 0.0),
        "S1": (-1.0, 3.0, 0.0),
    }
    rotation = rotation_matrix_xyz(
        ry_degrees=_interpolate_scalar(vertebra_id, sagittal_rotation_lookup),
    )
    translation = _interpolate_translation(vertebra_id, coronal_translation_lookup)
    return homogeneous_transform(rotation, translation)


def run_registration_stage(store: CaseStore, manifest: CaseManifest) -> StageExecutionResult:
    landmarks_artifact = artifact_for_type(manifest, "landmarks")
    if landmarks_artifact is None:
        raise ValueError("Registration requires vertebral landmarks and primitives.")
    baseline_scene_artifact = artifact_for_type(manifest, "prepared-scene-baseline")

    stage_started_at = time.perf_counter()
    pose_graph_output = pose_graph_path(store, manifest)
    scene_output = registration_scene_path(store, manifest)
    vertebrae = synthetic_vertebrae()
    transforms = {
        vertebra.vertebra_id: _standing_transform(vertebra.vertebra_id) for vertebra in vertebrae
    }

    pose_nodes = [
        {
            "vertebra_id": vertebra.vertebra_id,
            "source_frame": "patient-body-supine",
            "target_frame": "patient-body-standing",
            "transform_matrix": transform_to_payload(transforms[vertebra.vertebra_id]),
            "uncertainty": {
                "translation_mm": 2.0,
                "rotation_deg": 3.5,
                "status": "placeholder",
            },
        }
        for vertebra in vertebrae
    ]
    pose_graph_started_at = time.perf_counter()
    write_json_artifact(
        pose_graph_output,
        {
            "case_id": manifest.case_id,
            "registration_model": REGISTRATION_MODEL_NAME,
            "registration_version": REGISTRATION_MODEL_VERSION,
            "target_pose_input": {
                "adapter": "generic-calibrated-multiview",
                "first_concrete_adapter": "eos-biplanar",
                "current_status": "contract_ready",
            },
            "coordinate_frame": "patient-body-standing",
            "nodes": pose_nodes,
            "adjacency": [
                [vertebrae[index].vertebra_id, vertebrae[index + 1].vertebra_id]
                for index in range(len(vertebrae) - 1)
            ],
            "calibration_status": "placeholder",
            "registration_objective_summary": (
                "GUI-first pose graph scaffold wired while PolyPose sidecar integration is pending."
            ),
            "gui_review_surface": "measurement",
        },
    )
    pose_graph_elapsed = time.perf_counter() - pose_graph_started_at

    artifacts = [
        PipelineArtifact(
            artifact_id=make_id("artifact"),
            kind="json",
            label="Standing Pose Graph",
            path=str(pose_graph_output),
            stage=PipelineStageName.REGISTRATION.value,
            artifact_type="registration",
            coordinate_frame="patient-body-standing",
            review_surface="measurement",
            summary="Pose graph persisted in a shared global patient frame.",
            source_artifact_ids=[landmarks_artifact.artifact_id],
            metadata={
                "registration_model": REGISTRATION_MODEL_NAME,
                "registration_version": REGISTRATION_MODEL_VERSION,
            },
        )
    ]

    geometry_lookup = {vertebra.vertebra_id: vertebra for vertebra in vertebrae}
    if maybe_write_glb_scene(scene_output, transforms, geometry_lookup):
        artifacts.append(
            PipelineArtifact(
                artifact_id=make_id("artifact"),
                kind="scene",
                label="Standing Registration Scene",
                path=str(scene_output),
                stage=PipelineStageName.REGISTRATION.value,
                artifact_type="registration-scene",
                coordinate_frame="patient-body-standing",
                review_surface="measurement",
                status="complete",
                summary="Standing pose scene available for existing 3D review viewports.",
                asset_id=analysis_generated_asset_id(
                    PipelineStageName.REGISTRATION.value,
                    "standing-scene",
                ),
                source_artifact_ids=[artifacts[0].artifact_id],
                metadata={"format": "glb"},
            )
        )

    prepared_scene_elapsed = 0.0
    if baseline_scene_artifact is not None:
        baseline_payload = read_json_payload(manifest, "prepared-scene-baseline")
        models_payload = (
            baseline_payload.get("models")
            if isinstance(baseline_payload, dict)
            else None
        )
        if isinstance(models_payload, list):
            prepared_scene_started_at = time.perf_counter()
            baseline_lookup = {
                str(item.get("vertebra_id", "")).upper(): item
                for item in models_payload
                if isinstance(item, dict)
            }
            standing_models: list[dict[str, object]] = []
            for vertebra in vertebrae:
                baseline_model = baseline_lookup.get(vertebra.vertebra_id)
                if baseline_model is None:
                    continue
                mesh_path = baseline_model.get("mesh_path")
                center_mm = baseline_model.get("center_mm")
                extents_mm = baseline_model.get("extents_mm")
                if not isinstance(mesh_path, str) or not mesh_path:
                    continue
                if not isinstance(center_mm, list) or len(center_mm) != 3:
                    continue
                if not isinstance(extents_mm, list) or len(extents_mm) != 3:
                    continue
                transform = transforms[vertebra.vertebra_id]
                standing_models.append(
                    {
                        "vertebra_id": vertebra.vertebra_id,
                        "display_label": (
                            baseline_model.get("display_label") or vertebra.vertebra_id
                        ),
                        "selection_key": vertebra.vertebra_id,
                        "render_id": f"{vertebra.vertebra_id}_STANDING",
                        "mesh_path": mesh_path,
                        "pose_name": "standing",
                        "center_mm": _apply_transform_to_point(
                            transform,
                            (
                                float(center_mm[0]),
                                float(center_mm[1]),
                                float(center_mm[2]),
                            ),
                        ),
                        "extents_mm": _transform_axis_aligned_extents(
                            transform,
                            (
                                float(extents_mm[0]),
                                float(extents_mm[1]),
                                float(extents_mm[2]),
                            ),
                        ),
                        "transform_matrix": transform_to_payload(transform),
                        "checksum": baseline_model.get("checksum") or "",
                    }
                )
            if standing_models:
                prepared_scene_output = prepared_scene_path(store, manifest, "standing")
                write_json_artifact(
                    prepared_scene_output,
                    {
                        "schema_version": "spinelab.prepared_scene.v1",
                        "case_id": manifest.case_id,
                        "pose_name": "standing",
                        "coordinate_frame": "patient-body-standing",
                        "source_registration_artifact_id": artifacts[0].artifact_id,
                        "models": standing_models,
                    },
                )
                prepared_scene_elapsed = time.perf_counter() - prepared_scene_started_at
                artifacts.append(
                    PipelineArtifact(
                        artifact_id=make_id("artifact"),
                        kind="json",
                        label="Prepared Standing Scene",
                        path=str(prepared_scene_output),
                        stage=PipelineStageName.REGISTRATION.value,
                        artifact_type="prepared-scene-standing",
                        coordinate_frame="patient-body-standing",
                        review_surface="measurement",
                        summary=(
                            "Prepared standing scene metadata for Measurement and "
                            "Report reuse."
                        ),
                        source_artifact_ids=[artifacts[0].artifact_id],
                        metadata={
                            "pose_name": "standing",
                            "model_count": str(len(standing_models)),
                        },
                    )
                )

    outputs = [str(pose_graph_output)]
    if scene_output.exists():
        outputs.append(str(scene_output))
    if artifacts[-1].artifact_type == "prepared-scene-standing":
        outputs.append(artifacts[-1].path)
    return StageExecutionResult(
        stage=PipelineStageName.REGISTRATION,
        message="Prepared shared-frame registration outputs for Measurement review.",
        outputs=outputs,
        artifacts=artifacts,
        timings={
            "pose_graph_write_seconds": round(pose_graph_elapsed, 6),
            "prepared_scene_seconds": round(prepared_scene_elapsed, 6),
            "stage_setup_seconds": round(
                max(0.0, (time.perf_counter() - stage_started_at) - pose_graph_elapsed),
                6,
            ),
        },
    )
