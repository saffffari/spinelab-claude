from pathlib import Path

from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from spinelab.io.case_store import DEMO_CASE_ID, CaseStore
from spinelab.models import CaseManifest, SegmentationProfile


def test_case_store_round_trip(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    manifest = CaseManifest.demo()
    manifest.analysis_pose_mode = "dual"
    manifest.comparison_modalities = {"primary": "ct", "secondary": "mri"}
    manifest.segmentation_profile = "legacy-bootstrap"
    store.save_manifest(manifest)
    loaded = store.load_manifest(manifest.case_id)
    assert loaded.case_id == manifest.case_id
    assert loaded.patient_name == "Sarah Johnson"
    assert loaded.patient_id == "P001"
    assert loaded.diagnosis == "Adolescent Idiopathic Scoliosis"
    assert len(loaded.assets) == 0
    assert loaded.analysis_pose_mode == "dual"
    assert loaded.comparison_modalities == {"primary": "ct", "secondary": "mri"}
    assert loaded.segmentation_profile == SegmentationProfile.PRODUCTION.value
    assert store.manifest_path(manifest.case_id) == (
        tmp_path / "cases" / manifest.case_id / "analytics" / "manifest.json"
    )
    assert store.ct_dir(manifest.case_id).is_dir() is True
    assert store.mri_dir(manifest.case_id).is_dir() is True
    assert store.xray_dir(manifest.case_id).is_dir() is True
    assert store.drr_dir(manifest.case_id).is_dir() is True
    assert store.supine_mesh_dir(manifest.case_id).is_dir() is True
    assert store.standing_mesh_dir(manifest.case_id).is_dir() is True
    assert store.analytics_dir(manifest.case_id).is_dir() is True


def test_import_asset_persists_processing_role(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    manifest = CaseManifest.demo()
    store.save_manifest(manifest)

    source_file = tmp_path / "standing_ap.png"
    source_file.write_bytes(b"fake-image")

    asset = store.import_asset(manifest, source_file, kind="xray_2d", label="X-Ray")
    manifest.assign_asset_to_role(asset.asset_id, "xray_ap")
    store.save_manifest(manifest)

    loaded = store.load_manifest(manifest.case_id)
    assigned_asset = loaded.get_asset_for_role("xray_ap")
    assert assigned_asset is not None
    assert assigned_asset.asset_id == asset.asset_id
    assert Path(assigned_asset.managed_path).exists()
    assert Path(assigned_asset.managed_path).parent == store.xray_dir(manifest.case_id)


def test_import_ct_asset_persists_under_case_ct_folder(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    manifest = CaseManifest.demo()
    store.save_manifest(manifest)

    source_file = tmp_path / "volume.nii.gz"
    source_file.write_bytes(b"fake-ct")

    asset = store.import_asset(manifest, source_file, kind="ct_zstack", label="CT")

    assert Path(asset.managed_path).parent == store.ct_dir(manifest.case_id)
    assert Path(asset.managed_path).exists() is True


def test_import_asset_treats_projection_dicom_as_xray_not_ct(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    manifest = CaseManifest.demo()
    store.save_manifest(manifest)

    source_file = tmp_path / "projection.dcm"
    _write_test_dicom(source_file, view_position="LAT")

    asset = store.import_asset(manifest, source_file)

    assert asset.kind == "xray_2d"
    assert Path(asset.managed_path).parent == store.xray_dir(manifest.case_id)


def test_blank_case_is_unsaved_and_empty(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)

    manifest = store.create_blank_case()

    assert manifest.patient_name == ""
    assert manifest.assets == []
    assert manifest.segmentation_profile == SegmentationProfile.PRODUCTION.value
    assert store.case_is_editable(manifest.case_id) is False


def test_create_output_bundle_dir_uses_data_root_outputs(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)

    first = store.create_output_bundle_dir("case-001", bundle_label="measurement-export")
    second = store.create_output_bundle_dir("case-001", bundle_label="measurement-export")

    assert first.parent == tmp_path / "cases" / "case-001" / "analytics" / "exports"
    assert second.parent == tmp_path / "cases" / "case-001" / "analytics" / "exports"
    assert first.exists() is True
    assert second.exists() is True
    assert first != second


def test_delete_asset_removes_file_and_manifest_entry(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    manifest = CaseManifest.demo()
    store.save_manifest(manifest)

    source_file = tmp_path / "standing_lat.png"
    source_file.write_bytes(b"fake-image")

    asset = store.import_asset(manifest, source_file, kind="xray_2d", label="X-Ray")
    managed_path = Path(asset.managed_path)

    assert managed_path.exists()
    assert store.delete_asset(manifest, asset.asset_id) is True
    assert manifest.get_asset(asset.asset_id) is None
    assert managed_path.exists() is False


def test_hide_case_from_explorer_persists_without_deleting_case(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    manifest = CaseManifest.demo()
    store.save_manifest(manifest)
    external_ref = store.external_case_ref("demo_case")

    store.hide_case_from_explorer(manifest.case_id)
    store.hide_case_from_explorer(external_ref)

    assert store.case_is_hidden(manifest.case_id) is True
    assert store.case_is_hidden(external_ref) is True
    assert store.manifest_path(manifest.case_id).exists() is True

    store.restore_case_to_explorer(manifest.case_id)

    assert store.case_is_hidden(manifest.case_id) is False
    assert store.case_is_hidden(external_ref) is True


def test_clear_cases_from_explorer_hides_imported_and_external_cases(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    manifest = CaseManifest.demo()
    store.save_manifest(manifest)

    dataset_root = tmp_path / "raw_test_data" / "demo_case"
    (dataset_root / "DRR").mkdir(parents=True)
    (dataset_root / "Segmentation").mkdir(parents=True)
    (dataset_root / "DRR" / "original_ct_ap_reg_u16.png").write_bytes(b"png")
    (dataset_root / "Segmentation" / "series_labels.nii.gz").write_bytes(b"nii")

    hidden_refs = store.clear_cases_from_explorer()

    assert manifest.case_id in hidden_refs
    assert store.external_case_ref("demo_case") in hidden_refs
    assert store.case_is_hidden(manifest.case_id) is True
    assert store.case_is_hidden(store.external_case_ref("demo_case")) is True


def test_test_image_dataset_is_openable_from_case_store(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    dataset_root = tmp_path / "raw_test_data" / "demo_case"
    (dataset_root / "DRR").mkdir(parents=True)
    (dataset_root / "Segmentation").mkdir(parents=True)
    (dataset_root / "Mesh").mkdir(parents=True)
    (dataset_root / "PolyPose" / "standing_mesh").mkdir(parents=True)

    (dataset_root / "DRR" / "original_ct_ap_reg_u16.png").write_bytes(b"png")
    (dataset_root / "Segmentation" / "series_labels.nii.gz").write_bytes(b"nii")
    (dataset_root / "Mesh" / "L1.ply").write_bytes(b"ply")
    (dataset_root / "PolyPose" / "standing_mesh" / "standing_demo_mesh.glb").write_bytes(b"glb")

    manifests = store.list_test_manifests()
    assert len(manifests) == 1
    assert manifests[0].case_id == "demo_case"

    loaded = store.load_manifest(store.external_case_ref("demo_case"))
    assert loaded.case_id == "demo_case"
    assert loaded.get_asset_for_role("xray_ap") is not None
    assert loaded.get_asset_for_role("ct_stack") is not None
    assert any(asset.managed_path.endswith(".glb") for asset in loaded.assets)


def test_ensure_demo_case_builds_saved_case_from_demo_case_folder(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    dataset_root = tmp_path / "raw_test_data" / "demo_case"
    (dataset_root / "DRR").mkdir(parents=True)
    (dataset_root / "Segmentation").mkdir(parents=True)
    (dataset_root / "Mesh").mkdir(parents=True)
    (dataset_root / "PolyPose" / "standing_mesh").mkdir(parents=True)

    (dataset_root / "DRR" / "original_ct_ap_reg_u16.png").write_bytes(b"png")
    (dataset_root / "Segmentation" / "series_labels.nii.gz").write_bytes(b"nii")
    (dataset_root / "Mesh" / "L1.ply").write_bytes(b"ply")
    (dataset_root / "PolyPose" / "standing_mesh" / "standing_demo_mesh.glb").write_bytes(b"glb")

    manifest = store.ensure_demo_case()

    assert manifest.case_id == DEMO_CASE_ID
    assert manifest.patient_name == "Demo Processed Case"
    assert store.case_is_editable(DEMO_CASE_ID) is True
    assert any(asset.managed_path.endswith(".glb") for asset in manifest.assets)


def _write_test_dicom(path: Path, *, view_position: str) -> None:
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = generate_uid()
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = generate_uid()

    dataset = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\0" * 128)
    dataset.PatientName = "Test^Patient"
    dataset.PatientID = "TEST123"
    dataset.StudyInstanceUID = generate_uid()
    dataset.SeriesInstanceUID = generate_uid()
    dataset.SOPClassUID = file_meta.MediaStorageSOPClassUID
    dataset.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    dataset.Modality = "DX"
    dataset.ViewPosition = view_position
    dataset.Rows = 8
    dataset.Columns = 8
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.PixelData = (b"\0\0") * (dataset.Rows * dataset.Columns)
    dataset.save_as(
        str(path),
        little_endian=True,
        implicit_vr=False,
        enforce_file_format=True,
    )
