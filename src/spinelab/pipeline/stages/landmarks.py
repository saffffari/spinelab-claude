from __future__ import annotations

from typing import Any, cast

from spinelab.io import CaseStore
from spinelab.models import CaseManifest, PipelineArtifact
from spinelab.models.manifest import make_id
from spinelab.ontology import (
    SURFACE_PATCH_CLASS_INDEX,
    SURFACE_PATCH_SCHEMA_VERSION,
    GlobalStructureId,
    Modality,
    PrimitiveId,
    SurfacePatchId,
    build_structure_instance_context,
    standard_level_sort_key,
)
from spinelab.pipeline.artifacts import (
    landmarks_summary_path,
    ptv3_summary_path,
    write_json_artifact,
)
from spinelab.pipeline.contracts import PipelineStageName, StageExecutionResult
from spinelab.pipeline.stages.common import (
    PTV3_MODEL_NAME,
    PTV3_MODEL_VERSION,
    artifact_for_type,
    read_json_payload,
    synthetic_vertebrae,
)


def _plane_payload(
    point: tuple[float, float, float],
    normal: tuple[float, float, float],
) -> dict[str, object]:
    return {"point_mm": list(point), "normal": list(normal)}


def _landmark_bundle(
    center: tuple[float, float, float],
    extents: tuple[float, float, float],
) -> dict[str, object]:
    cx, cy, cz = center
    ex, ey, ez = (extent / 2.0 for extent in extents)
    superior_midpoint = (cx, cy, cz + ez)
    inferior_midpoint = (cx, cy, cz - ez)
    anterior_superior = (cx, cy + ey, cz + ez)
    posterior_superior = (cx, cy - ey, cz + ez)
    anterior_inferior = (cx, cy + ey, cz - ez)
    posterior_inferior = (cx, cy - ey, cz - ez)
    return {
        PrimitiveId.VERTEBRAL_CENTROID.value: {"point_mm": list(center)},
        PrimitiveId.SUPERIOR_ENDPLATE_PLANE.value: _plane_payload(
            superior_midpoint,
            (0.0, 0.0, 1.0),
        ),
        PrimitiveId.INFERIOR_ENDPLATE_PLANE.value: _plane_payload(
            inferior_midpoint,
            (0.0, 0.0, 1.0),
        ),
        PrimitiveId.ANTERIOR_SUPERIOR_CORNER.value: {"point_mm": list(anterior_superior)},
        PrimitiveId.POSTERIOR_SUPERIOR_CORNER.value: {"point_mm": list(posterior_superior)},
        PrimitiveId.ANTERIOR_INFERIOR_CORNER.value: {"point_mm": list(anterior_inferior)},
        PrimitiveId.POSTERIOR_INFERIOR_CORNER.value: {"point_mm": list(posterior_inferior)},
        PrimitiveId.POSTERIOR_WALL_LINE.value: {
            "points_mm": [list(posterior_superior), list(posterior_inferior)],
            "normal": [0.0, -1.0, 0.0],
        },
        PrimitiveId.SUPERIOR_ENDPLATE_MIDPOINT.value: {"point_mm": list(superior_midpoint)},
        PrimitiveId.INFERIOR_ENDPLATE_MIDPOINT.value: {"point_mm": list(inferior_midpoint)},
        PrimitiveId.VERTEBRA_LOCAL_FRAME.value: {
            "origin_mm": list(center),
            "axes": {
                "left_right": [1.0, 0.0, 0.0],
                "anterior_posterior": [0.0, 1.0, 0.0],
                "superior_inferior": [0.0, 0.0, 1.0],
            },
        },
    }


def _global_structures(landmark_vertebrae: list[dict[str, object]]) -> list[dict[str, object]]:
    lookup: dict[str, dict[str, Any]] = {}
    for entry in landmark_vertebrae:
        level_id = str(entry.get("standard_level_id", entry.get("vertebra_id", ""))).upper()
        if level_id:
            lookup[level_id] = cast(dict[str, Any], entry)
    payload: list[dict[str, Any]] = []
    c7 = lookup.get("C7")
    if c7 is not None:
        c7_primitives = cast(dict[str, dict[str, Any]], c7["primitives"])
        payload.append(
            {
                "structure_id": GlobalStructureId.C7_CENTROID.value,
                "point_mm": list(
                    c7_primitives[PrimitiveId.VERTEBRAL_CENTROID.value]["point_mm"]
                ),
                "source_level_id": "C7",
            }
        )
    s1 = lookup.get("S1")
    if s1 is not None:
        s1_primitives = cast(dict[str, dict[str, Any]], s1["primitives"])
        payload.extend(
            [
                {
                    "structure_id": GlobalStructureId.S1_SUPERIOR_ENDPLATE_PLANE.value,
                    "point_mm": list(
                        s1_primitives[PrimitiveId.SUPERIOR_ENDPLATE_PLANE.value]["point_mm"]
                    ),
                    "normal": list(
                        s1_primitives[PrimitiveId.SUPERIOR_ENDPLATE_PLANE.value]["normal"]
                    ),
                    "source_level_id": "S1",
                },
                {
                    "structure_id": GlobalStructureId.S1_SUPERIOR_MIDPOINT.value,
                    "point_mm": list(
                        s1_primitives[PrimitiveId.SUPERIOR_ENDPLATE_MIDPOINT.value]["point_mm"]
                    ),
                    "source_level_id": "S1",
                },
                {
                    "structure_id": GlobalStructureId.POSTERIOR_SUPERIOR_S1_CORNER.value,
                    "point_mm": list(
                        s1_primitives[PrimitiveId.POSTERIOR_SUPERIOR_CORNER.value]["point_mm"]
                    ),
                    "source_level_id": "S1",
                },
                {
                    "structure_id": GlobalStructureId.SACRAL_CENTER.value,
                    "point_mm": list(
                        s1_primitives[PrimitiveId.VERTEBRAL_CENTROID.value]["point_mm"]
                    ),
                    "source_level_id": "S1",
                },
            ]
        )
    return payload


def _detected_standard_vertebrae(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for raw_entry in payload.get("vertebrae", []):
        if not isinstance(raw_entry, dict):
            continue
        level_id = str(raw_entry.get("standard_level_id", raw_entry.get("vertebra_id", ""))).upper()
        if not level_id:
            continue
        entries.append(raw_entry)
    entries.sort(
        key=lambda entry: standard_level_sort_key(
            str(entry.get("standard_level_id", entry.get("vertebra_id", ""))).upper()
        )
    )
    return entries


def run_landmarks_stage(store: CaseStore, manifest: CaseManifest) -> StageExecutionResult:
    pc_artifact = artifact_for_type(manifest, "point-cloud-manifest")
    if pc_artifact is None:
        raise ValueError("Landmark derivation requires a point cloud manifest.")

    segmentation_payload = read_json_payload(manifest, "segmentation") or {}
    modality = Modality(str(segmentation_payload.get("modality", Modality.CT.value)).upper())
    detected_vertebrae = _detected_standard_vertebrae(segmentation_payload)
    if not detected_vertebrae:
        raise ValueError("Landmark derivation requires detected standard vertebra entries.")

    ptv3_path = ptv3_summary_path(store, manifest)
    landmarks_path = landmarks_summary_path(store, manifest)

    placeholder_geometry = {
        vertebra.vertebra_id: vertebra for vertebra in synthetic_vertebrae()
    }
    ptv3_vertebrae: list[dict[str, object]] = []
    landmark_vertebrae: list[dict[str, object]] = []
    for entry in detected_vertebrae:
        level_id = str(entry.get("standard_level_id", entry.get("vertebra_id", ""))).upper()
        vertebra = placeholder_geometry.get(level_id)
        if vertebra is None:
            continue
        context = build_structure_instance_context(
            structure_instance_id=str(entry.get("structure_instance_id") or "") or None,
            display_label=str(entry.get("display_label") or level_id),
            modality=modality,
            numbering_confidence=float(entry.get("numbering_confidence", 1.0)),
            superior_neighbor_instance_id=(
                str(entry.get("superior_neighbor_instance_id"))
                if entry.get("superior_neighbor_instance_id")
                else None
            ),
            inferior_neighbor_instance_id=(
                str(entry.get("inferior_neighbor_instance_id"))
                if entry.get("inferior_neighbor_instance_id")
                else None
            ),
        )
        vertex_groups = {
            patch_id.value: {
                "class_index": SURFACE_PATCH_CLASS_INDEX[patch_id],
                "support": "baseline_mesh",
                "status": "placeholder",
            }
            for patch_id in SurfacePatchId
        }
        ptv3_vertebrae.append(
            {
                "vertebra_id": level_id,
                "structure_instance_id": context.structure_instance_id,
                "display_label": context.display_label,
                "standard_level_id": context.standard_level_id,
                "region_id": context.region_id.value,
                "structure_type": context.structure_type.value,
                "order_index": context.order_index,
                "numbering_confidence": context.numbering_confidence,
                "variant_tags": [tag.value for tag in context.variant_tags],
                "supports_standard_measurements": bool(
                    entry.get(
                        "supports_standard_measurements",
                        context.supports_standard_measurements,
                    )
                ),
                "coordinate_frame": "vertebra-local",
                "surface_patch_schema_version": SURFACE_PATCH_SCHEMA_VERSION,
                "model_name": PTV3_MODEL_NAME,
                "model_version": PTV3_MODEL_VERSION,
                "confidence": 0.79,
                "uncertainty_text": (
                    "Placeholder dense vertex-group predictions until PTv3 "
                    "training lands."
                ),
                "vertex_groups": vertex_groups,
                "reserved_heads": {"pathology_anomaly": "deferred"},
            }
        )
        landmark_vertebrae.append(
            {
                "vertebra_id": level_id,
                "structure_instance_id": context.structure_instance_id,
                "display_label": context.display_label,
                "standard_level_id": context.standard_level_id,
                "region_id": context.region_id.value,
                "structure_type": context.structure_type.value,
                "order_index": context.order_index,
                "numbering_confidence": context.numbering_confidence,
                "variant_tags": [tag.value for tag in context.variant_tags],
                "supports_standard_measurements": bool(
                    entry.get(
                        "supports_standard_measurements",
                        context.supports_standard_measurements,
                    )
                ),
                "coordinate_frame": "patient-body-supine",
                "supporting_artifact_ids": [pc_artifact.artifact_id],
                "supporting_vertex_groups": list(vertex_groups),
                "primitives": _landmark_bundle(vertebra.center, vertebra.extents),
            }
        )

    write_json_artifact(
        ptv3_path,
        {
            "case_id": manifest.case_id,
            "model_name": PTV3_MODEL_NAME,
            "model_version": PTV3_MODEL_VERSION,
            "vertebrae": ptv3_vertebrae,
            "gui_review_surface": "measurement",
        },
    )
    write_json_artifact(
        landmarks_path,
        {
            "case_id": manifest.case_id,
            "landmark_model": f"{PTV3_MODEL_NAME}:{PTV3_MODEL_VERSION}",
            "coordinate_frame": "patient-body-supine",
            "vertebrae": landmark_vertebrae,
            "global_structures": _global_structures(landmark_vertebrae),
            "gui_review_surface": "measurement",
        },
    )

    ptv3_artifact = PipelineArtifact(
        artifact_id=make_id("artifact"),
        kind="json",
        label="PTv3 Vertebra Vertex Groups",
        path=str(ptv3_path),
        stage=PipelineStageName.LANDMARKS.value,
        artifact_type="ptv3-vertebrae",
        coordinate_frame="vertebra-local",
        review_surface="measurement",
        summary="Dense vertex-group scaffold persisted for PTv3-derived anatomy.",
        source_artifact_ids=[pc_artifact.artifact_id],
        metadata={"model_name": PTV3_MODEL_NAME, "model_version": PTV3_MODEL_VERSION},
    )
    landmarks_artifact = PipelineArtifact(
        artifact_id=make_id("artifact"),
        kind="json",
        label="Vertebral Landmarks And Primitives",
        path=str(landmarks_path),
        stage=PipelineStageName.LANDMARKS.value,
        artifact_type="landmarks",
        coordinate_frame="patient-body-supine",
        review_surface="measurement",
        summary=(
            "Landmarks derived from PTv3 vertex groups for downstream "
            "registration and measurements."
        ),
        source_artifact_ids=[ptv3_artifact.artifact_id, pc_artifact.artifact_id],
        metadata={"vertebra_count": str(len(landmark_vertebrae))},
    )
    return StageExecutionResult(
        stage=PipelineStageName.LANDMARKS,
        message="Prepared PTv3 vertex groups and landmark primitives.",
        outputs=[str(ptv3_path), str(landmarks_path)],
        artifacts=[ptv3_artifact, landmarks_artifact],
    )
