from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import pydicom
import SimpleITK as sitk
from pydicom.errors import InvalidDicomError

from spinelab.models import CaseManifest, MeasurementSet, PipelineRun, StudyAsset
from spinelab.models.manifest import utc_now

from .session_store import SessionHandle, SessionStore, default_session_root

DEFAULT_DATA_ROOT = Path(os.environ.get("SPINELAB_DATA_ROOT", r"D:\dev\spinelab_data"))
EXTERNAL_CASE_PREFIX = "external::"
DEMO_CASE_ID = "demo-test-processed"
DEMO_DATASET_NAMES = ("demo_case", "test_processed")


class CaseStore:
    def __init__(self, data_root: Path = DEFAULT_DATA_ROOT) -> None:
        self.data_root = Path(data_root)
        self.cases_root = self.data_root / "cases"
        self.raw_test_data_root = self.data_root / "raw_test_data"
        session_root = (
            self.data_root / "_sessions"
            if self.data_root != DEFAULT_DATA_ROOT and "SPINELAB_SESSION_ROOT" not in os.environ
            else default_session_root()
        )
        self._session_store = SessionStore(session_root)
        self._active_session: SessionHandle | None = None

    @property
    def session_store(self) -> SessionStore:
        return self._session_store

    @property
    def active_session(self) -> SessionHandle | None:
        return self._active_session

    def activate_session(self, session: SessionHandle) -> None:
        self._active_session = session

    def clear_active_session(self) -> None:
        self._active_session = None

    def active_runtime_manifest(self) -> CaseManifest | None:
        if self._active_session is None:
            return None
        return self._session_store.load_runtime_manifest(self._active_session)

    def ensure_roots(self) -> None:
        self.cases_root.mkdir(parents=True, exist_ok=True)
        self.raw_test_data_root.mkdir(parents=True, exist_ok=True)

    def case_dir(self, case_id: str) -> Path:
        if self._session_matches(case_id):
            assert self._active_session is not None
            return self._active_session.workspace_root
        return self.cases_root / case_id

    def ct_dir(self, case_id: str) -> Path:
        return self.case_dir(case_id) / "ct"

    def mri_dir(self, case_id: str) -> Path:
        return self.case_dir(case_id) / "mri"

    def xray_dir(self, case_id: str) -> Path:
        return self.case_dir(case_id) / "xray"

    def drr_dir(self, case_id: str) -> Path:
        return self.case_dir(case_id) / "drr"

    def three_d_dir(self, case_id: str) -> Path:
        return self.case_dir(case_id) / "3d"

    def supine_mesh_dir(self, case_id: str) -> Path:
        return self.three_d_dir(case_id) / "supine"

    def standing_mesh_dir(self, case_id: str) -> Path:
        return self.three_d_dir(case_id) / "standing"

    def analytics_dir(self, case_id: str) -> Path:
        return self.case_dir(case_id) / "analytics"

    def analytics_derived_dir(self, case_id: str) -> Path:
        return self.analytics_dir(case_id) / "derived"

    def analytics_reports_dir(self, case_id: str) -> Path:
        return self.analytics_dir(case_id) / "reports"

    def manifest_path(self, case_id: str) -> Path:
        if self._session_matches(case_id):
            assert self._active_session is not None
            return self._active_session.runtime_manifest_path
        return self.analytics_dir(case_id) / "manifest.json"

    def case_output_dir(self, case_id: str) -> Path:
        return self.analytics_dir(case_id) / "exports"

    def hidden_case_refs_path(self) -> Path:
        return self.cases_root / ".hidden_case_refs.json"

    def ensure_case_layout(self, case_id: str) -> None:
        if self._session_matches(case_id):
            assert self._active_session is not None
            self._session_store.ensure_root()
            return
        self.ensure_roots()
        for path in (
            self.ct_dir(case_id),
            self.mri_dir(case_id),
            self.xray_dir(case_id),
            self.drr_dir(case_id),
            self.supine_mesh_dir(case_id),
            self.standing_mesh_dir(case_id),
            self.analytics_dir(case_id),
        ):
            path.mkdir(parents=True, exist_ok=True)

    def create_output_bundle_dir(
        self,
        case_id: str,
        *,
        bundle_label: str = "measurement-bundle",
    ) -> Path:
        self.ensure_case_layout(case_id)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        bundle_root = self._unique_destination(
            self.case_output_dir(case_id) / f"{timestamp}-{bundle_label}"
        )
        bundle_root.mkdir(parents=True, exist_ok=False)
        return bundle_root

    def list_hidden_case_refs(self) -> list[str]:
        path = self.hidden_case_refs_path()
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(payload, list):
            return []
        hidden_refs = {
            str(case_ref).strip()
            for case_ref in payload
            if str(case_ref).strip()
        }
        return sorted(hidden_refs)

    def hide_case_from_explorer(self, case_ref: str) -> None:
        hidden_refs = set(self.list_hidden_case_refs())
        hidden_refs.add(case_ref)
        self._write_hidden_case_refs(hidden_refs)

    def clear_cases_from_explorer(self) -> list[str]:
        hidden_refs = set(self.list_hidden_case_refs())
        hidden_refs.update(manifest.case_id for manifest in self.list_imported_manifests())
        hidden_refs.update(
            self.external_case_ref(manifest.case_id) for manifest in self.list_test_manifests()
        )
        self._write_hidden_case_refs(hidden_refs)
        return sorted(hidden_refs)

    def restore_case_to_explorer(self, case_ref: str) -> None:
        hidden_refs = set(self.list_hidden_case_refs())
        hidden_refs.discard(case_ref)
        self._write_hidden_case_refs(hidden_refs)

    def case_is_hidden(self, case_ref: str) -> bool:
        return case_ref in set(self.list_hidden_case_refs())

    def save_manifest(self, manifest: CaseManifest) -> Path:
        if self._session_matches(manifest.case_id):
            assert self._active_session is not None
            path = self._session_store.write_runtime_manifest(self._active_session, manifest)
            self._active_session.mark_dirty()
            return path
        self.ensure_case_layout(manifest.case_id)
        manifest.updated_at = utc_now()
        path = self.manifest_path(manifest.case_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
        return path

    def load_manifest(self, case_id: str) -> CaseManifest:
        if self._session_matches(case_id):
            assert self._active_session is not None
            return self._session_store.load_runtime_manifest(self._active_session)
        if case_id.startswith(EXTERNAL_CASE_PREFIX):
            dataset_name = case_id.removeprefix(EXTERNAL_CASE_PREFIX)
            dataset_root = self.raw_test_data_root / dataset_name
            return self._build_test_manifest(dataset_root)
        payload = json.loads(self.manifest_path(case_id).read_text(encoding="utf-8"))
        return CaseManifest.from_dict(payload)

    def list_imported_manifests(self) -> list[CaseManifest]:
        self.ensure_roots()
        manifests: list[CaseManifest] = []
        for manifest_path in self.cases_root.glob("*/analytics/manifest.json"):
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifests.append(CaseManifest.from_dict(payload))
        manifests.sort(key=lambda manifest: manifest.updated_at, reverse=True)
        return manifests

    def list_test_manifests(self) -> list[CaseManifest]:
        if not self.raw_test_data_root.exists():
            return []
        manifests: list[CaseManifest] = []
        datasets = sorted(
            self.raw_test_data_root.iterdir(),
            key=lambda path: path.name.lower(),
        )
        for dataset_root in datasets:
            if dataset_root.is_dir() and self._looks_like_structured_test_dataset(dataset_root):
                manifests.append(self._build_test_manifest(dataset_root))
        return manifests

    def list_manifests(self) -> list[CaseManifest]:
        manifests = self.list_imported_manifests()
        manifests.extend(self.list_test_manifests())
        manifests.sort(key=lambda manifest: manifest.updated_at, reverse=True)
        return manifests

    def import_asset(
        self,
        manifest: CaseManifest,
        source_path: Path,
        *,
        kind: str | None = None,
        label: str | None = None,
    ) -> StudyAsset:
        if self._session_matches(manifest.case_id):
            return self._import_asset_into_session(
                manifest,
                source_path,
                kind=kind,
                label=label,
            )
        self.ensure_roots()
        inferred_kind, inferred_label = self._infer_asset_type(source_path)
        asset_kind = kind or inferred_kind
        asset_label = label or inferred_label
        destination = self._copy_into_case_bucket(
            manifest.case_id,
            source_path,
            kind=asset_kind,
        )
        asset = StudyAsset(
            asset_id=f"asset-{uuid4().hex[:10]}",
            kind=asset_kind,
            label=asset_label,
            source_path=str(source_path),
            managed_path=str(destination),
        )
        manifest.assets.append(asset)
        self.save_manifest(manifest)
        return asset

    def import_stack(
        self,
        manifest: CaseManifest,
        source_paths: list[Path],
        *,
        label: str = "CT",
    ) -> StudyAsset:
        if self._session_matches(manifest.case_id):
            return self._import_stack_into_session(
                manifest,
                source_paths,
                label=label,
            )
        self.ensure_roots()
        stack_id = uuid4().hex[:10]
        stack_dir = self.ct_dir(manifest.case_id) / f"stack-{stack_id}"
        stack_dir.mkdir(parents=True, exist_ok=True)
        for source_path in source_paths:
            if source_path.is_file():
                target = self._unique_destination(stack_dir / source_path.name)
                shutil.copy2(source_path, target)
        source_root = source_paths[0].parent if source_paths else Path()
        asset = StudyAsset(
            asset_id=f"asset-{stack_id}",
            kind="ct_zstack",
            label=label,
            source_path=str(source_root),
            managed_path=str(stack_dir),
        )
        manifest.assets.append(asset)
        self.save_manifest(manifest)
        return asset

    def create_blank_case(self) -> CaseManifest:
        return CaseManifest.blank()

    def ensure_demo_case(self) -> CaseManifest:
        self.ensure_roots()
        path = self.manifest_path(DEMO_CASE_ID)
        dataset_root = self._find_demo_dataset_root()
        if dataset_root is not None:
            manifest = self._build_test_manifest(dataset_root)
            manifest.case_id = DEMO_CASE_ID
            manifest.patient_name = "Demo Processed Case"
            manifest.patient_id = "DEMO-001"
            manifest.diagnosis = "Preprocessed demo case"
            self.save_manifest(manifest)
        elif not path.exists():
            manifest = CaseManifest.demo()
            manifest.case_id = DEMO_CASE_ID
            self.save_manifest(manifest)
        return self.load_manifest(DEMO_CASE_ID)

    def _find_demo_dataset_root(self) -> Path | None:
        for dataset_name in self._demo_dataset_names():
            dataset_root = self.raw_test_data_root / dataset_name
            if dataset_root.exists():
                return dataset_root
        return None

    def _demo_dataset_names(self) -> Iterable[str]:
        return DEMO_DATASET_NAMES

    def case_is_editable(self, case_id: str) -> bool:
        if self._session_matches(case_id):
            return True
        return self.manifest_path(case_id).exists()

    def delete_asset(self, manifest: CaseManifest, asset_id: str) -> bool:
        asset = manifest.get_asset(asset_id)
        if asset is None or not self.case_is_editable(manifest.case_id):
            return False

        case_root = self.case_dir(manifest.case_id).resolve()
        managed_path = Path(asset.managed_path)

        manifest.assets = [
            candidate for candidate in manifest.assets if candidate.asset_id != asset.asset_id
        ]

        if managed_path.exists():
            resolved_path = managed_path.resolve()
            if resolved_path.is_relative_to(case_root):
                if resolved_path.is_dir():
                    shutil.rmtree(resolved_path, ignore_errors=True)
                else:
                    resolved_path.unlink(missing_ok=True)

        if self._session_matches(manifest.case_id):
            assert self._active_session is not None
            self._delete_session_dicom_payload(asset_id)

        self.save_manifest(manifest)
        return True

    def external_case_ref(self, dataset_name: str) -> str:
        return f"{EXTERNAL_CASE_PREFIX}{dataset_name}"

    def _import_asset_into_session(
        self,
        manifest: CaseManifest,
        source_path: Path,
        *,
        kind: str | None = None,
        label: str | None = None,
    ) -> StudyAsset:
        assert self._active_session is not None
        inferred_kind, inferred_label = self._infer_asset_type(source_path)
        asset_kind = kind or inferred_kind
        asset_label = label or inferred_label
        if asset_kind == "ct_zstack":
            if source_path.is_dir():
                dicom_paths = self._dicom_paths_from_directory(source_path)
                return self._import_ct_dicom_series(manifest, dicom_paths, source_root=source_path)
            if self._is_dicom_file(source_path):
                return self._import_ct_dicom_series(
                    manifest,
                    [source_path],
                    source_root=source_path.parent,
                )
            destination = self._copy_into_case_bucket(
                manifest.case_id,
                source_path,
                kind=asset_kind,
            )
            asset = StudyAsset(
                asset_id=f"asset-{uuid4().hex[:10]}",
                kind=asset_kind,
                label=asset_label,
                source_path=str(source_path),
                managed_path=str(destination),
            )
            manifest.assets.append(asset)
            self.save_manifest(manifest)
            return asset

        destination = self._copy_into_case_bucket(manifest.case_id, source_path, kind=asset_kind)
        asset = StudyAsset(
            asset_id=f"asset-{uuid4().hex[:10]}",
            kind=asset_kind,
            label=asset_label,
            source_path=str(source_path),
            managed_path=str(destination),
        )
        manifest.assets.append(asset)
        self.save_manifest(manifest)
        if asset_kind == "xray_2d" and self._is_dicom_file(source_path):
            self._preserve_original_dicom(
                working_asset=asset,
                source_files=[source_path],
                bucket="xray",
                source_root=source_path.parent,
            )
        elif asset_kind == "mri_2d" and self._is_dicom_file(source_path):
            self._preserve_original_dicom(
                working_asset=asset,
                source_files=[source_path],
                bucket="mri",
                source_root=source_path.parent,
            )
        return asset

    def _import_stack_into_session(
        self,
        manifest: CaseManifest,
        source_paths: list[Path],
        *,
        label: str = "CT",
    ) -> StudyAsset:
        dicom_paths = [path for path in source_paths if self._is_dicom_file(path)]
        if dicom_paths:
            return self._import_ct_dicom_series(
                manifest,
                dicom_paths,
                source_root=dicom_paths[0].parent,
            )
        return self._import_asset_into_session(
            manifest,
            source_paths[0],
            kind="ct_zstack",
            label=label,
        )

    def _import_ct_dicom_series(
        self,
        manifest: CaseManifest,
        source_files: list[Path],
        *,
        source_root: Path,
    ) -> StudyAsset:
        assert self._active_session is not None
        asset_id = f"asset-{uuid4().hex[:10]}"
        destination = self._unique_destination(self.ct_dir(manifest.case_id) / f"{asset_id}.nii.gz")
        image = self._read_dicom_series(source_files)
        sitk.WriteImage(image, str(destination), useCompression=True)
        asset = StudyAsset(
            asset_id=asset_id,
            kind="ct_zstack",
            label="CT",
            source_path=str(source_root),
            managed_path=str(destination),
        )
        manifest.assets.append(asset)
        self.save_manifest(manifest)
        self._preserve_original_dicom(
            working_asset=asset,
            source_files=source_files,
            bucket="ct",
            source_root=source_root,
        )
        return asset

    def _read_dicom_series(self, source_files: list[Path]) -> sitk.Image:
        reader = sitk.ImageSeriesReader()
        reader.MetaDataDictionaryArrayUpdateOn()
        reader.LoadPrivateTagsOn()
        reader.SetFileNames([str(path) for path in source_files])
        return cast(sitk.Image, reader.Execute())

    def _preserve_original_dicom(
        self,
        *,
        working_asset: StudyAsset,
        source_files: list[Path],
        bucket: str,
        source_root: Path,
    ) -> None:
        assert self._active_session is not None
        session = self._active_session
        dicom_root = session.workspace_root / "dicom" / bucket / working_asset.asset_id
        dicom_root.mkdir(parents=True, exist_ok=True)
        catalog = self._session_store.load_dicom_catalog(session)
        imports = catalog.get("imports")
        if not isinstance(imports, list):
            imports = []
            catalog["imports"] = imports
        file_entries: list[dict[str, object]] = []
        ordered_files = sorted(source_files, key=lambda path: path.name.lower())
        for index, source_file in enumerate(ordered_files):
            metadata = self._dicom_metadata(source_file)
            asset_id = f"{working_asset.asset_id}-src-{index:04d}"
            file_name = self._safe_dicom_filename(metadata, index)
            destination = self._unique_destination(dicom_root / file_name)
            shutil.copy2(source_file, destination)
            relative_path = self._session_store.relative_workspace_path(session, destination)
            file_entries.append(
                {
                    "asset_id": asset_id,
                    "relative_path": relative_path,
                    "SOPInstanceUID": metadata.get("SOPInstanceUID", ""),
                    "InstanceNumber": metadata.get("InstanceNumber"),
                    "ImagePositionPatient": metadata.get("ImagePositionPatient"),
                    "ImageOrientationPatient": metadata.get("ImageOrientationPatient"),
                    "PixelSpacing": metadata.get("PixelSpacing"),
                    "SliceThickness": metadata.get("SliceThickness"),
                    "SpacingBetweenSlices": metadata.get("SpacingBetweenSlices"),
                    "Rows": metadata.get("Rows"),
                    "Columns": metadata.get("Columns"),
                    "created_utc": utc_now(),
                }
            )
        imports[:] = [
            entry
            for entry in imports
            if isinstance(entry, dict) and entry.get("working_asset_id") != working_asset.asset_id
        ]
        first_metadata = self._dicom_metadata(source_files[0]) if source_files else {}
        imports.append(
            {
                "working_asset_id": working_asset.asset_id,
                "bucket": bucket,
                "source_root": str(source_root),
                "patient_id": first_metadata.get("patient_id", ""),
                "modality": first_metadata.get("modality", ""),
                "StudyInstanceUID": first_metadata.get("StudyInstanceUID", ""),
                "SeriesInstanceUID": first_metadata.get("SeriesInstanceUID", ""),
                "SeriesDescription": first_metadata.get("SeriesDescription", ""),
                "StudyDate": first_metadata.get("StudyDate", ""),
                "StudyTime": first_metadata.get("StudyTime", ""),
                "AccessionNumber": first_metadata.get("AccessionNumber", ""),
                "Manufacturer": first_metadata.get("Manufacturer", ""),
                "ManufacturerModelName": first_metadata.get("ManufacturerModelName", ""),
                "FrameOfReferenceUID": first_metadata.get("FrameOfReferenceUID", ""),
                "RescaleSlope": first_metadata.get("RescaleSlope"),
                "RescaleIntercept": first_metadata.get("RescaleIntercept"),
                "file_count": len(file_entries),
                "files": file_entries,
            }
        )
        self._session_store.write_dicom_catalog(session, catalog)

    def _copy_into_case_bucket(self, case_id: str, source_path: Path, *, kind: str) -> Path:
        destination_root = self._case_bucket_dir(case_id, source_path=source_path, kind=kind)
        destination_root.mkdir(parents=True, exist_ok=True)
        destination = self._unique_destination(destination_root / source_path.name)
        if source_path.is_dir():
            shutil.copytree(source_path, destination)
            return destination
        shutil.copy2(source_path, destination)
        return destination

    def _case_bucket_dir(self, case_id: str, *, source_path: Path, kind: str) -> Path:
        normalized_kind = kind.strip().lower()
        if normalized_kind == "ct_zstack":
            return self.ct_dir(case_id)
        if normalized_kind == "mri_2d":
            return self.mri_dir(case_id)
        if normalized_kind == "mesh_3d":
            return (
                self.standing_mesh_dir(case_id)
                if self._looks_like_standing_mesh(source_path)
                else self.supine_mesh_dir(case_id)
            )
        if normalized_kind == "xray_2d":
            return (
                self.drr_dir(case_id)
                if self._looks_like_drr(source_path)
                else self.xray_dir(case_id)
            )
        return self.analytics_dir(case_id)

    def _session_matches(self, case_id: str) -> bool:
        return self._active_session is not None and self._active_session.case_id == case_id

    def _is_dicom_file(self, source_path: Path) -> bool:
        if source_path.suffix.lower() == ".dcm":
            return True
        try:
            pydicom.dcmread(
                str(source_path),
                stop_before_pixels=True,
                force=True,
                specific_tags=["SOPInstanceUID"],
            )
            return True
        except (InvalidDicomError, OSError):
            return False

    def _dicom_paths_from_directory(self, source_root: Path) -> list[Path]:
        files = [
            path
            for path in sorted(source_root.rglob("*"), key=lambda item: item.name.lower())
            if path.is_file() and self._is_dicom_file(path)
        ]
        if not files:
            raise FileNotFoundError(f"No DICOM files found under {source_root}.")
        return files

    def _dicom_metadata(self, source_path: Path) -> dict[str, object]:
        try:
            dataset = pydicom.dcmread(str(source_path), stop_before_pixels=True, force=True)
        except (InvalidDicomError, OSError):
            return {}
        return {
            "patient_id": str(getattr(dataset, "PatientID", "") or ""),
            "modality": str(getattr(dataset, "Modality", "") or ""),
            "StudyInstanceUID": str(getattr(dataset, "StudyInstanceUID", "") or ""),
            "SeriesInstanceUID": str(getattr(dataset, "SeriesInstanceUID", "") or ""),
            "SOPInstanceUID": str(getattr(dataset, "SOPInstanceUID", "") or ""),
            "SeriesDescription": str(getattr(dataset, "SeriesDescription", "") or ""),
            "StudyDate": str(getattr(dataset, "StudyDate", "") or ""),
            "StudyTime": str(getattr(dataset, "StudyTime", "") or ""),
            "AccessionNumber": str(getattr(dataset, "AccessionNumber", "") or ""),
            "Manufacturer": str(getattr(dataset, "Manufacturer", "") or ""),
            "ManufacturerModelName": str(getattr(dataset, "ManufacturerModelName", "") or ""),
            "FrameOfReferenceUID": str(getattr(dataset, "FrameOfReferenceUID", "") or ""),
            "InstanceNumber": getattr(dataset, "InstanceNumber", None),
            "ImagePositionPatient": list(getattr(dataset, "ImagePositionPatient", []) or []),
            "ImageOrientationPatient": list(getattr(dataset, "ImageOrientationPatient", []) or []),
            "PixelSpacing": list(getattr(dataset, "PixelSpacing", []) or []),
            "SliceThickness": getattr(dataset, "SliceThickness", None),
            "SpacingBetweenSlices": getattr(dataset, "SpacingBetweenSlices", None),
            "Rows": getattr(dataset, "Rows", None),
            "Columns": getattr(dataset, "Columns", None),
            "RescaleSlope": getattr(dataset, "RescaleSlope", None),
            "RescaleIntercept": getattr(dataset, "RescaleIntercept", None),
        }

    def _safe_dicom_filename(self, metadata: dict[str, object], index: int) -> str:
        sop_instance_uid = str(metadata.get("SOPInstanceUID", "") or "").strip()
        if sop_instance_uid:
            normalized = re.sub(r"[^0-9A-Za-z]+", "-", sop_instance_uid).strip("-")
            if normalized:
                return f"{normalized}.dcm"
        return f"instance-{index:04d}.dcm"

    def _delete_session_dicom_payload(self, asset_id: str) -> None:
        assert self._active_session is not None
        session = self._active_session
        catalog = self._session_store.load_dicom_catalog(session)
        imports = catalog.get("imports")
        if not isinstance(imports, list):
            return
        retained: list[dict[str, object]] = []
        for entry in imports:
            if not isinstance(entry, dict):
                continue
            if entry.get("working_asset_id") == asset_id:
                bucket = str(entry.get("bucket", "")).strip()
                dicom_root = session.workspace_root / "dicom" / bucket / asset_id
                shutil.rmtree(dicom_root, ignore_errors=True)
                continue
            retained.append(entry)
        catalog["imports"] = retained
        self._session_store.write_dicom_catalog(session, catalog)

    def _write_hidden_case_refs(self, case_refs: Iterable[str]) -> None:
        path = self.hidden_case_refs_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = sorted({str(case_ref).strip() for case_ref in case_refs if str(case_ref).strip()})
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _unique_destination(self, destination: Path) -> Path:
        if not destination.exists():
            return destination
        index = 1
        while True:
            suffix = "".join(destination.suffixes)
            stem = destination.name[: -len(suffix)] if suffix else destination.name
            candidate = destination.with_name(f"{stem}-{index}{suffix}")
            if not candidate.exists():
                return candidate
            index += 1

    def _infer_asset_type(self, source_path: Path) -> tuple[str, str]:
        if source_path.is_dir():
            return "ct_zstack", "CT"
        name = source_path.name.lower()
        suffix = "".join(source_path.suffixes).lower()
        name_tokens = set(re.sub(r"[^a-z0-9]+", " ", name).split())
        if suffix in {".vtp", ".vtk", ".stl", ".ply", ".obj", ".glb", ".gltf"}:
            return "mesh_3d", "Model"
        if suffix in {".nii", ".nii.gz", ".nrrd", ".mhd", ".mha"}:
            return "ct_zstack", "CT"
        if name_tokens & {"mri", "mr", "t1", "t2"}:
            return "mri_2d", "MRI"
        if suffix == ".dcm" and name_tokens & {"ct", "stack", "series"}:
            return "ct_zstack", "CT"
        return "xray_2d", "X-Ray"

    def _looks_like_drr(self, source_path: Path) -> bool:
        name = source_path.name.lower()
        name_tokens = set(re.sub(r"[^a-z0-9]+", " ", name).split())
        if name.startswith("testing_drr_"):
            return True
        return bool(name_tokens & {"drr", "scaffold", "nanodrr"})

    def _looks_like_standing_mesh(self, source_path: Path) -> bool:
        name = source_path.name.lower()
        return any(token in name for token in ("standing", "posed", "registration"))

    def _looks_like_structured_test_dataset(self, dataset_root: Path) -> bool:
        return any(
            (dataset_root / child_name).exists()
            for child_name in ("DRR", "Segmentation", "Mesh", "Reports", "PolyPose")
        )

    def _build_test_manifest(self, dataset_root: Path) -> CaseManifest:
        dataset_name = dataset_root.name
        manifests_assets: list[StudyAsset] = []

        drr_root = dataset_root / "DRR"
        segmentation_root = dataset_root / "Segmentation"
        mesh_root = dataset_root / "Mesh"
        reports_root = dataset_root / "Reports"
        polypose_root = dataset_root / "PolyPose"

        if drr_root.exists():
            drr_files = sorted(
                [path for path in drr_root.iterdir() if path.is_file()],
                key=lambda path: path.name.lower(),
            )
            for index, drr_file in enumerate(drr_files):
                role = None
                lower_name = drr_file.name.lower()
                if "lat" in lower_name:
                    role = "xray_lat"
                elif "ap" in lower_name and not any(
                    asset.processing_role == "xray_ap" for asset in manifests_assets
                ):
                    role = "xray_ap"
                manifests_assets.append(
                    StudyAsset(
                        asset_id=f"{dataset_name}-drr-{index}",
                        kind="xray_2d",
                        label="X-Ray",
                        source_path=str(drr_file),
                        managed_path=str(drr_file),
                        processing_role=role,
                    )
                )

        if segmentation_root.exists():
            segmentation_files = sorted(
                [path for path in segmentation_root.iterdir() if path.is_file()],
                key=lambda path: path.name.lower(),
            )
            if segmentation_files:
                segmentation_file = segmentation_files[0]
                manifests_assets.append(
                    StudyAsset(
                        asset_id=f"{dataset_name}-segmentation",
                        kind="ct_zstack",
                        label="CT",
                        source_path=str(segmentation_file),
                        managed_path=str(segmentation_file),
                        processing_role="ct_stack",
                    )
                )

        if mesh_root.exists():
            mesh_files = sorted(
                [path for path in mesh_root.iterdir() if path.is_file()],
                key=lambda path: path.name.lower(),
            )
            if mesh_files:
                manifests_assets.append(
                    StudyAsset(
                        asset_id=f"{dataset_name}-mesh",
                        kind="mesh_3d",
                        label="Model",
                        source_path=str(mesh_root),
                        managed_path=str(mesh_files[0]),
                    )
                )

        if polypose_root.exists():
            standing_candidates = sorted(
                [
                    path
                    for path in polypose_root.rglob("*")
                    if path.is_file() and path.suffix.lower() in {".glb", ".gltf"}
                ],
                key=lambda path: path.name.lower(),
            )
            if standing_candidates:
                standing_model = standing_candidates[0]
                manifests_assets.append(
                    StudyAsset(
                        asset_id=f"{dataset_name}-standing-model",
                        kind="mesh_3d",
                        label="Standing Model",
                        source_path=str(standing_model),
                        managed_path=str(standing_model),
                    )
                )

        pipeline_runs: list[PipelineRun] = []
        if segmentation_root.exists():
            pipeline_runs.append(
                PipelineRun(
                    stage="segmentation",
                    status="complete",
                    outputs=["segmentation"],
                )
            )
        if drr_root.exists():
            pipeline_runs.append(
                PipelineRun(
                    stage="drr",
                    status="complete",
                    outputs=["drr_images"],
                )
            )
        if mesh_root.exists():
            pipeline_runs.append(
                PipelineRun(
                    stage="mesh",
                    status="complete",
                    outputs=["mesh"],
                )
            )
        if polypose_root.exists():
            pipeline_runs.append(
                PipelineRun(
                    stage="polypose",
                    status="complete",
                    outputs=["polypose"],
                )
            )
        if reports_root.exists():
            pipeline_runs.append(
                PipelineRun(
                    stage="reports",
                    status="complete",
                    outputs=["reports"],
                )
            )

        updated_at = utc_now()
        if dataset_root.exists():
            updated_at = utc_now()
        measurements = (
            MeasurementSet.demo_targets()
            if dataset_name in DEMO_DATASET_NAMES
            else MeasurementSet(values={}, reviewed=False, provenance="pending")
        )
        return CaseManifest(
            case_id=dataset_name,
            patient_name=dataset_name.replace("_", " ").title(),
            patient_id=dataset_name.upper(),
            diagnosis="Preprocessed test dataset",
            cobb_angle=measurements.values.get("Cobb Angle", ""),
            procedure_history=[
                "Loaded from raw test data library",
                "Uses future output folder structure",
            ],
            updated_at=updated_at,
            assets=manifests_assets,
            pipeline_runs=pipeline_runs,
            measurements=measurements,
        )
