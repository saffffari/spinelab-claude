from __future__ import annotations

import zipfile
from pathlib import Path

from spinelab.io import (
    CaseStore,
    LegacyCaseImporter,
    SessionHandle,
    SpinePackageError,
    SpinePackageService,
)
from spinelab.models import CaseManifest, PipelineArtifact, StudyAsset


def _build_session_with_payload(
    tmp_path: Path,
) -> tuple[CaseStore, SessionHandle, CaseManifest, SpinePackageService]:
    store = CaseStore(tmp_path)
    manifest = CaseManifest.blank()
    manifest.analysis_pose_mode = "single"
    manifest.patient_name = "Package Patient"
    manifest.patient_id = "CASE-001"
    session = store.session_store.create_blank_session(manifest=manifest)
    store.activate_session(session)

    ct_path = session.workspace_root / "ct" / "volume.nii.gz"
    drr_path = session.workspace_root / "drr" / "standing_ap.png"
    mesh_path = session.workspace_root / "3d" / "supine" / "L1.ply"
    analytics_path = (
        session.workspace_root
        / "analytics"
        / "derived"
        / "segmentation"
        / "segmentation.json"
    )
    dicom_path = session.workspace_root / "dicom" / "ct" / "asset-ct" / "instance-0000.dcm"
    for path, payload in (
        (ct_path, b"ct-volume"),
        (drr_path, b"png-bytes"),
        (mesh_path, b"ply-bytes"),
        (analytics_path, b'{"ok": true}'),
        (dicom_path, b"dicom-original"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    ct_asset = StudyAsset(
        asset_id="asset-ct",
        kind="ct_zstack",
        label="CT",
        source_path=str(ct_path),
        managed_path=str(ct_path),
        processing_role="ct_stack",
    )
    drr_asset = StudyAsset(
        asset_id="asset-drr",
        kind="xray_2d",
        label="X-Ray",
        source_path=str(drr_path),
        managed_path=str(drr_path),
        processing_role="xray_ap",
    )
    mesh_asset = StudyAsset(
        asset_id="asset-mesh",
        kind="mesh_3d",
        label="Model",
        source_path=str(mesh_path),
        managed_path=str(mesh_path),
    )
    manifest.assets.extend([ct_asset, drr_asset, mesh_asset])
    manifest.artifacts.append(
        PipelineArtifact(
            artifact_id="artifact-seg",
            kind="segmentation",
            label="Segmentation",
            path=str(analytics_path),
            stage="segmentation",
            artifact_type="segmentation-manifest",
        )
    )
    store.save_manifest(manifest)
    store.session_store.write_dicom_catalog(
        session,
        {
            "imports": [
                {
                    "working_asset_id": "asset-ct",
                    "bucket": "ct",
                    "patient_id": manifest.patient_id,
                    "modality": "CT",
                    "StudyInstanceUID": "1.2.3",
                    "SeriesInstanceUID": "1.2.3.4",
                    "SeriesDescription": "Axial CT",
                    "file_count": 1,
                    "files": [
                        {
                            "asset_id": "asset-ct-src-0000",
                            "relative_path": "dicom/ct/asset-ct/instance-0000.dcm",
                            "SOPInstanceUID": "1.2.3.4.5",
                            "InstanceNumber": 1,
                            "Rows": 16,
                            "Columns": 16,
                        }
                    ],
                }
            ]
        },
    )
    service = SpinePackageService(store.session_store)
    return store, session, manifest, service


def test_spine_package_round_trips_manifest_and_assets(tmp_path: Path) -> None:
    _store, session, manifest, service = _build_session_with_payload(tmp_path)
    package_path = tmp_path / "case.spine"

    service.save_package(session, manifest, package_path)
    package_manifest = service.validate_package(package_path, validate_hashes=True)
    reopened_session, reopened_manifest = service.open_package(package_path)

    assert package_manifest.scene.primary_ct_id == "asset-ct"
    assert package_manifest.scene.role_bindings["ct_stack"] == "asset-ct"
    assert package_manifest.scene.role_bindings["xray_ap"] == "asset-drr"
    assert package_manifest.scene.analysis_pose_mode == "single"
    assert package_manifest.scene.active_pose == "supine"
    assert reopened_manifest.case_id == manifest.case_id
    assert reopened_manifest.patient_id == "CASE-001"
    assert reopened_manifest.analysis_pose_mode == "single"
    assert reopened_manifest.get_asset_for_role("ct_stack") is not None
    assert reopened_manifest.get_asset_for_role("xray_ap") is not None
    reopened_dicom = (
        reopened_session.workspace_root / "dicom" / "ct" / "asset-ct" / "instance-0000.dcm"
    )
    assert reopened_dicom.read_bytes() == b"dicom-original"


def test_spine_package_export_folder_preserves_required_layout(tmp_path: Path) -> None:
    _store, session, manifest, service = _build_session_with_payload(tmp_path)
    export_root = service.export_package_folder(session, manifest, tmp_path / "exported")

    for relative_dir in (
        "dicom/ct",
        "dicom/mri",
        "dicom/xray",
        "ct",
        "mri",
        "xray",
        "drr",
        "3d/supine",
        "3d/standing",
        "analytics",
    ):
        assert (export_root / relative_dir).is_dir() is True
    assert (export_root / "manifest.json").exists() is True


def test_spine_package_exports_selected_assets(tmp_path: Path) -> None:
    _store, session, manifest, service = _build_session_with_payload(tmp_path)
    groups = service.asset_groups(session, manifest)

    exported = service.export_assets(
        session,
        manifest,
        groups["ct"] + groups["dicom"],
        tmp_path / "selected-assets",
    )

    exported_names = {path.name for path in exported}
    assert "volume.nii.gz" in exported_names
    assert "instance-0000.dcm" in exported_names


def test_spine_package_validate_detects_hash_mismatch(tmp_path: Path) -> None:
    _store, session, manifest, service = _build_session_with_payload(tmp_path)
    package_path = tmp_path / "case.spine"
    service.save_package(session, manifest, package_path)

    tampered_path = tmp_path / "tampered.spine"
    with zipfile.ZipFile(package_path, "r") as source_archive:
        with zipfile.ZipFile(
            tampered_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as target_archive:
            for member in source_archive.infolist():
                payload = source_archive.read(member.filename)
                if member.filename == "ct/volume.nii.gz":
                    payload = b"tampered-volume"
                target_archive.writestr(member, payload)

    try:
        service.validate_package(tampered_path, validate_hashes=True)
    except SpinePackageError as exc:
        assert "hash mismatch" in str(exc).lower()
    else:
        raise AssertionError("Expected package validation to fail on hash mismatch.")


def test_spine_package_validate_detects_missing_manifest(tmp_path: Path) -> None:
    broken_path = tmp_path / "broken.spine"
    with zipfile.ZipFile(broken_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ct/", "")

    try:
        SpinePackageService(CaseStore(tmp_path).session_store).validate_package(broken_path)
    except SpinePackageError as exc:
        assert "manifest.json" in str(exc)
    else:
        raise AssertionError("Expected validation to fail for missing manifest.")


def test_spine_package_summary_includes_runtime_assets(tmp_path: Path) -> None:
    _store, session, manifest, service = _build_session_with_payload(tmp_path)
    package_path = tmp_path / "case.spine"
    service.save_package(session, manifest, package_path)

    summary = service.load_summary(package_path)
    stub = summary.to_case_manifest_stub()

    assert stub.patient_name == "Package Patient"
    assert any(asset.processing_role == "ct_stack" for asset in stub.assets)
    assert any(asset.processing_role == "xray_ap" for asset in stub.assets)


def test_legacy_case_importer_rebases_paths_into_transient_session(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    importer = LegacyCaseImporter(store.session_store)
    case_root = tmp_path / "legacy-case"
    ct_path = case_root / "ct" / "volume.nii.gz"
    artifact_path = case_root / "analytics" / "derived" / "segmentation" / "segmentation.json"
    ct_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    ct_path.write_bytes(b"legacy-ct")
    artifact_path.write_text('{"legacy": true}', encoding="utf-8")

    manifest = CaseManifest.blank()
    manifest.assets.append(
        StudyAsset(
            asset_id="asset-ct",
            kind="ct_zstack",
            label="CT",
            source_path=str(ct_path),
            managed_path=str(ct_path),
            processing_role="ct_stack",
        )
    )
    manifest.artifacts.append(
        PipelineArtifact(
            artifact_id="artifact-seg",
            kind="segmentation",
            label="Segmentation",
            path=str(artifact_path),
            stage="segmentation",
            artifact_type="segmentation-manifest",
        )
    )

    session, rebased_manifest = importer.import_case_folder(case_root, manifest)

    assert session.source_kind == "legacy"
    assert session.legacy_source_path == case_root
    assert Path(rebased_manifest.assets[0].managed_path).is_relative_to(session.workspace_root)
    assert Path(rebased_manifest.artifacts[0].path).is_relative_to(session.workspace_root)
    assert (session.workspace_root / "ct" / "volume.nii.gz").read_bytes() == b"legacy-ct"


def test_session_store_purge_orphaned_sessions_removes_transient_workspaces(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    first = store.session_store.create_blank_session(manifest=CaseManifest.blank())
    second = store.session_store.create_blank_session(manifest=CaseManifest.blank())

    assert first.workspace_root.exists() is True
    assert second.workspace_root.exists() is True

    removed = store.session_store.purge_orphaned_sessions()

    assert removed == 2
    assert list(store.session_store.root.glob("*")) == []
