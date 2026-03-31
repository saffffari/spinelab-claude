from __future__ import annotations

import json
from pathlib import Path

import nibabel as nib
import numpy as np

from spinelab.io import CaseStore
from spinelab.models import CaseManifest
from spinelab.pipeline.contracts import PipelineStageName
from spinelab.pipeline.manifest_bridge import apply_stage_result
from spinelab.pipeline.stage_registry import expand_requested_stages
from spinelab.pipeline.stages.findings import run_findings_stage
from spinelab.pipeline.stages.landmarks import run_landmarks_stage
from spinelab.pipeline.stages.measurements import run_measurements_stage
from spinelab.pipeline.stages.mesh import run_mesh_stage
from spinelab.pipeline.stages.normalize import run_normalize_stage
from spinelab.pipeline.stages.segmentation import run_segmentation_stage
from spinelab.segmentation_profiles import SegmentationProfile


def _prepare_landmarks_case(tmp_path: Path) -> tuple[CaseStore, CaseManifest]:
    store = CaseStore(tmp_path / "data-root")
    manifest = CaseManifest.blank()
    manifest.patient_name = "Measurement Test"
    manifest.comparison_modalities = {"primary": "ct", "secondary": "xray"}
    manifest.segmentation_profile = SegmentationProfile.SCAFFOLD.value

    volume_path = tmp_path / "ct_volume.nii.gz"
    volume_data = np.arange(64, dtype=np.int16).reshape((4, 4, 4))
    nib.save(nib.Nifti1Image(volume_data, np.diag([1.2, 1.2, 2.5, 1.0])), str(volume_path))

    asset = store.import_asset(manifest, volume_path, kind="ct_zstack", label="CT")
    manifest.assign_asset_to_role(asset.asset_id, "ct_stack")
    store.save_manifest(manifest)

    for stage_runner in (
        run_normalize_stage,
        run_segmentation_stage,
        run_mesh_stage,
        run_landmarks_stage,
    ):
        result = stage_runner(store, manifest)
        apply_stage_result(manifest, result)
        store.save_manifest(manifest)
    return store, manifest


def test_single_pose_measurements_emit_native_local_and_regional_metrics(
    tmp_path: Path,
) -> None:
    store, manifest = _prepare_landmarks_case(tmp_path)

    result = run_measurements_stage(store, manifest)
    apply_stage_result(manifest, result)

    records_by_key = {record.key: record for record in manifest.measurements.records}

    assert records_by_key["lumbar_lordosis"].valid is True
    assert records_by_key["lumbar_lordosis"].measurement_mode == "single_pose_native_3d"
    assert records_by_key["lumbar_lordosis"].coordinate_frame == "patient-body-supine"
    assert records_by_key["thoracic_kyphosis"].valid is True
    assert records_by_key["disc_height_middle_l1_l2"].valid is True
    assert records_by_key["listhesis_l1_l2"].valid is True
    assert records_by_key["segmental_lordosis_l1_l2"].valid is True

    assert records_by_key["cobb_angle"].valid is False
    assert "radiograph-equivalent coronal Cobb" in records_by_key["cobb_angle"].invalid_reason
    assert records_by_key["sagittal_vertical_axis"].valid is False
    assert records_by_key["pelvic_tilt"].valid is False

    measurements_artifact = next(
        artifact for artifact in manifest.artifacts if artifact.artifact_type == "measurements"
    )
    payload = json.loads(Path(measurements_artifact.path).read_text(encoding="utf-8"))
    assert payload["measurement_mode"] == "single_pose_native_3d"
    assert payload["coordinate_frame"] == "patient-body-supine"


def test_findings_stage_skips_adjacent_segment_metrics(tmp_path: Path) -> None:
    store, manifest = _prepare_landmarks_case(tmp_path)

    measurement_result = run_measurements_stage(store, manifest)
    apply_stage_result(manifest, measurement_result)
    findings_result = run_findings_stage(store, manifest)

    finding_keys = {
        metric_key
        for finding in findings_result.findings
        for metric_key in finding.source_metric_keys
    }

    assert "lumbar_lordosis" in finding_keys
    assert "thoracic_kyphosis" in finding_keys
    assert "cobb_angle" in finding_keys
    assert "sagittal_vertical_axis" in finding_keys
    assert "pelvic_tilt" in finding_keys
    assert not any(key.startswith("disc_height_") for key in finding_keys)
    assert not any(key.startswith("listhesis_") for key in finding_keys)
    assert not any(key.startswith("segmental_lordosis_") for key in finding_keys)


def test_measurements_stage_depends_on_landmarks_not_registration() -> None:
    requested = expand_requested_stages((PipelineStageName.MEASUREMENTS,))

    assert PipelineStageName.LANDMARKS in requested
    assert PipelineStageName.REGISTRATION not in requested
