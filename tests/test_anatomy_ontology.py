from __future__ import annotations

import json
import re
from pathlib import Path

import nibabel as nib
import numpy as np

from spinelab.io import CaseStore
from spinelab.models import CaseManifest, SegmentationProfile
from spinelab.ontology import (
    GLOBAL_STRUCTURE_IDS,
    PRIMITIVE_IDS,
    STANDARD_LEVEL_IDS,
    STANDARD_STRUCTURES,
    SURFACE_PATCH_CLASS_INDEX,
    SURFACE_PATCH_IDS,
    SURFACE_PATCH_SCHEMA_VERSION,
    CaseOntologyContext,
    CoordinateSystem,
    GlobalStructureId,
    Modality,
    PrimitiveId,
    SurfacePatchId,
    VariantTag,
    build_structure_instance_context,
)
from spinelab.pipeline import PipelineOrchestrator
from spinelab.pipeline.contracts import PipelineStageName


def _section_code_literals(text: str, heading: str) -> list[str]:
    after_heading = text.split(heading, 1)[1]
    next_heading_match = re.search(r"^##?#[#]?\s", after_heading, flags=re.MULTILINE)
    if next_heading_match is not None:
        after_heading = after_heading[: next_heading_match.start()]
    return re.findall(r"`([^`]+)`", after_heading)


def test_standard_levels_are_unique_and_frozen() -> None:
    assert STANDARD_LEVEL_IDS == (
        "C7",
        "T1",
        "T2",
        "T3",
        "T4",
        "T5",
        "T6",
        "T7",
        "T8",
        "T9",
        "T10",
        "T11",
        "T12",
        "L1",
        "L2",
        "L3",
        "L4",
        "L5",
        "S1",
    )
    assert len(STANDARD_LEVEL_IDS) == len(set(STANDARD_LEVEL_IDS))
    assert (
        tuple(definition.standard_level_id for definition in STANDARD_STRUCTURES)
        == STANDARD_LEVEL_IDS
    )


def test_surface_patch_indices_are_frozen() -> None:
    assert SURFACE_PATCH_CLASS_INDEX == {
        SurfacePatchId.BACKGROUND_OR_UNKNOWN: 0,
        SurfacePatchId.SUPERIOR_ENDPLATE: 1,
        SurfacePatchId.INFERIOR_ENDPLATE: 2,
        SurfacePatchId.POSTERIOR_BODY_WALL: 3,
        SurfacePatchId.VERTEBRAL_BODY_SURFACE: 4,
        SurfacePatchId.LEFT_PEDICLE: 5,
        SurfacePatchId.RIGHT_PEDICLE: 6,
        SurfacePatchId.LEFT_FACET_SURFACE: 7,
        SurfacePatchId.RIGHT_FACET_SURFACE: 8,
    }
    assert tuple(patch_id.value for patch_id in SURFACE_PATCH_IDS) == (
        "background_or_unknown",
        "superior_endplate",
        "inferior_endplate",
        "posterior_body_wall",
        "vertebral_body_surface",
        "left_pedicle",
        "right_pedicle",
        "left_facet_surface",
        "right_facet_surface",
    )


def test_primitive_and_global_structure_ids_are_frozen() -> None:
    assert tuple(primitive_id.value for primitive_id in PRIMITIVE_IDS) == (
        PrimitiveId.VERTEBRAL_CENTROID.value,
        PrimitiveId.SUPERIOR_ENDPLATE_PLANE.value,
        PrimitiveId.INFERIOR_ENDPLATE_PLANE.value,
        PrimitiveId.ANTERIOR_SUPERIOR_CORNER.value,
        PrimitiveId.POSTERIOR_SUPERIOR_CORNER.value,
        PrimitiveId.ANTERIOR_INFERIOR_CORNER.value,
        PrimitiveId.POSTERIOR_INFERIOR_CORNER.value,
        PrimitiveId.POSTERIOR_WALL_LINE.value,
        PrimitiveId.SUPERIOR_ENDPLATE_MIDPOINT.value,
        PrimitiveId.INFERIOR_ENDPLATE_MIDPOINT.value,
        PrimitiveId.VERTEBRA_LOCAL_FRAME.value,
    )
    assert tuple(global_id.value for global_id in GLOBAL_STRUCTURE_IDS) == (
        GlobalStructureId.C7_CENTROID.value,
        GlobalStructureId.S1_SUPERIOR_ENDPLATE_PLANE.value,
        GlobalStructureId.S1_SUPERIOR_MIDPOINT.value,
        GlobalStructureId.POSTERIOR_SUPERIOR_S1_CORNER.value,
        GlobalStructureId.LEFT_FEMORAL_HEAD_CENTER.value,
        GlobalStructureId.RIGHT_FEMORAL_HEAD_CENTER.value,
        GlobalStructureId.BICOXOFEMORAL_AXIS_MIDPOINT.value,
        GlobalStructureId.SACRAL_CENTER.value,
    )


def test_variant_policy_marks_extra_levels_as_nonstandard() -> None:
    t13 = build_structure_instance_context(display_label="T13", modality=Modality.CT)
    l6 = build_structure_instance_context(display_label="L6", modality=Modality.CT)
    c3 = build_structure_instance_context(display_label="C3", modality=Modality.MR)

    assert t13.standard_level_id is None
    assert t13.variant_tags == (
        VariantTag.EXTRA_THORACIC_SEGMENT,
        VariantTag.NUMBERING_AMBIGUOUS,
    )
    assert t13.supports_standard_measurements is False

    assert l6.standard_level_id is None
    assert l6.variant_tags == (
        VariantTag.EXTRA_LUMBAR_SEGMENT,
        VariantTag.NUMBERING_AMBIGUOUS,
    )
    assert l6.supports_standard_measurements is False

    assert c3.standard_level_id is None
    assert c3.variant_tags == (
        VariantTag.UPPER_CERVICAL_SPECIAL_CASE,
        VariantTag.NUMBERING_AMBIGUOUS,
    )
    assert c3.supports_standard_measurements is False


def test_case_and_structure_context_round_trip_is_stable() -> None:
    structure_context = build_structure_instance_context(
        display_label="L3",
        modality=Modality.CT,
        superior_neighbor_instance_id="vertebra_L2",
        inferior_neighbor_instance_id="vertebra_L4",
    )
    structure_payload = structure_context.to_dict()

    assert structure_payload["structure_instance_id"] == "vertebra_L3"
    assert structure_payload["standard_level_id"] == "L3"
    assert structure_payload["region_id"] == "lumbar"
    assert structure_payload["structure_type"] == "vertebra"
    assert structure_payload["superior_neighbor_instance_id"] == "vertebra_L2"
    assert structure_payload["inferior_neighbor_instance_id"] == "vertebra_L4"
    assert structure_payload["structure_id"] == "vertebra_L3"

    case_context = CaseOntologyContext(
        case_id="case-123",
        modality=Modality.CT,
        source_coordinate_system=CoordinateSystem.LPS,
        levels_present=("L1", "L2", "L3"),
        unsupported_levels_present=("T13",),
        numbering_review_flags=("ambiguous-count",),
    )
    case_payload = case_context.to_dict()

    assert case_payload["case_id"] == "case-123"
    assert case_payload["modality"] == "CT"
    assert case_payload["source_coordinate_system"] == "LPS"
    assert case_payload["canonical_coordinate_system"] == "LPS"
    assert case_payload["levels_present"] == ["L1", "L2", "L3"]
    assert case_payload["unsupported_levels_present"] == ["T13"]


def test_shared_pipeline_does_not_import_ptv3_local_ontology() -> None:
    pipeline_root = Path(__file__).resolve().parents[1] / "src" / "spinelab" / "pipeline"
    for path in pipeline_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "spinelab.ai.pointcloud.ontology" not in text, str(path)


def test_docs_data_contracts_match_frozen_ontology_lists() -> None:
    docs_path = Path(__file__).resolve().parents[1] / "docs" / "data_contracts.md"
    text = docs_path.read_text(encoding="utf-8")

    assert _section_code_literals(text, "### Frozen Surface Patch Classes") == [
        f"{patch_id.value} = {SURFACE_PATCH_CLASS_INDEX[patch_id]}"
        for patch_id in SURFACE_PATCH_IDS
    ]
    assert _section_code_literals(text, "### Frozen Primitive Ids") == [
        primitive_id.value for primitive_id in PRIMITIVE_IDS
    ]
    assert _section_code_literals(text, "### Frozen Global Structure Ids") == [
        global_id.value for global_id in GLOBAL_STRUCTURE_IDS
    ]


def test_mesh_and_landmarks_contracts_use_shared_ontology(tmp_path: Path) -> None:
    store = CaseStore(tmp_path / "data-root")
    manifest = CaseManifest.blank()
    manifest.patient_name = "Ontology Contract Case"
    manifest.segmentation_profile = SegmentationProfile.SCAFFOLD.value

    volume_path = tmp_path / "ontology_case_volume.nii.gz"
    volume_data = np.arange(64, dtype=np.int16).reshape((4, 4, 4))
    nib.save(nib.Nifti1Image(volume_data, np.diag([1.0, 1.0, 1.0, 1.0])), str(volume_path))

    asset = store.import_asset(manifest, volume_path, kind="ct_zstack", label="CT")
    manifest.assign_asset_to_role(asset.asset_id, "ct_stack")

    orchestrator = PipelineOrchestrator(store)
    updated_manifest = orchestrator.submit_case_analysis(
        manifest,
        preferred_device="cpu",
        requested_stages=(PipelineStageName.LANDMARKS,),
    )

    mesh_artifact = next(
        artifact
        for artifact in updated_manifest.artifacts
        if artifact.artifact_type == "mesh-manifest"
    )
    landmarks_artifact = next(
        artifact for artifact in updated_manifest.artifacts if artifact.artifact_type == "landmarks"
    )
    ptv3_artifact = next(
        artifact
        for artifact in updated_manifest.artifacts
        if artifact.artifact_type == "ptv3-vertebrae"
    )

    mesh_payload = json.loads(Path(mesh_artifact.path).read_text(encoding="utf-8"))
    landmarks_payload = json.loads(Path(landmarks_artifact.path).read_text(encoding="utf-8"))
    ptv3_payload = json.loads(Path(ptv3_artifact.path).read_text(encoding="utf-8"))

    first_mesh_entry = next(
        entry for entry in mesh_payload["vertebrae"] if entry["status"] == "complete"
    )
    assert first_mesh_entry["structure_instance_id"].startswith(("vertebra_", "sacrum_"))
    assert first_mesh_entry["standard_level_id"] in STANDARD_LEVEL_IDS
    assert first_mesh_entry["supports_standard_measurements"] is True
    assert mesh_payload["point_cloud_settings"]["surface_patch_schema_version"] == (
        SURFACE_PATCH_SCHEMA_VERSION
    )

    point_cloud = np.load(first_mesh_entry["point_cloud_path"])
    assert str(point_cloud["structure_instance_id"]) == first_mesh_entry["structure_instance_id"]
    assert str(point_cloud["standard_level_id"]) == first_mesh_entry["standard_level_id"]

    first_landmark_entry = landmarks_payload["vertebrae"][0]
    assert set(first_landmark_entry["primitives"]) == {
        primitive_id.value for primitive_id in PRIMITIVE_IDS
    }
    assert first_landmark_entry["standard_level_id"] in STANDARD_LEVEL_IDS
    assert (
        ptv3_payload["vertebrae"][0]["surface_patch_schema_version"]
        == SURFACE_PATCH_SCHEMA_VERSION
    )

    global_structure_ids = {
        entry["structure_id"] for entry in landmarks_payload["global_structures"]
    }
    assert global_structure_ids <= {global_id.value for global_id in GLOBAL_STRUCTURE_IDS}
