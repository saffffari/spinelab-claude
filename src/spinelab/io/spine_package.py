from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from spinelab.models import CaseManifest, StudyAsset
from spinelab.models.manifest import utc_now

from .session_store import SESSION_LAYOUT_DIRS, SessionHandle, SessionStore

PACKAGE_SCHEMA_VERSION = "0.1"
PACKAGE_FILE_FILTER = "SpineLab Case (*.spine)"


class SpinePackageError(RuntimeError):
    pass


@dataclass(slots=True)
class SpinePackageAsset:
    id: str
    type: str
    path: str
    format: str
    sha256: str
    size_bytes: int
    subtype: str | None = None
    role: str | None = None
    pose: str | None = None
    structure: str | None = None
    source_asset_id: str | None = None
    created_utc: str | None = None
    dicom_refs: dict[str, str] | None = None
    label: str | None = None
    status: str | None = None


@dataclass(slots=True)
class SpineSceneState:
    primary_ct_id: str | None
    role_bindings: dict[str, str] = field(default_factory=dict)
    analysis_pose_mode: str = ""
    comparison_modalities: dict[str, str] = field(default_factory=dict)
    active_pose: str = "supine"
    visible_asset_ids: list[str] = field(default_factory=list)
    transform_artifact_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SpinePackageManifest:
    schema_version: str
    case_id: str
    patient_id: str
    patient_name: str
    created_utc: str
    updated_utc: str
    assets: list[SpinePackageAsset]
    scene: SpineSceneState
    dicom_index: dict[str, object]
    patient_metadata: dict[str, object] = field(default_factory=dict)
    analysis_state: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["assets"] = [asdict(asset) for asset in self.assets]
        payload["scene"] = asdict(self.scene)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SpinePackageManifest:
        assets_payload = payload.get("assets", [])
        assets = [
            SpinePackageAsset(
                id=str(item["id"]),
                type=str(item["type"]),
                path=str(item["path"]),
                format=str(item["format"]),
                sha256=str(item["sha256"]),
                size_bytes=int(item["size_bytes"]),
                subtype=_optional_str(item.get("subtype")),
                role=_optional_str(item.get("role")),
                pose=_optional_str(item.get("pose")),
                structure=_optional_str(item.get("structure")),
                source_asset_id=_optional_str(item.get("source_asset_id")),
                created_utc=_optional_str(item.get("created_utc")),
                dicom_refs=_optional_str_dict(item.get("dicom_refs")),
                label=_optional_str(item.get("label")),
                status=_optional_str(item.get("status")),
            )
            for item in assets_payload
            if isinstance(item, dict)
        ]
        scene_payload = payload.get("scene", {})
        if not isinstance(scene_payload, dict):
            raise SpinePackageError("Package manifest scene payload is malformed.")
        scene = SpineSceneState(
            primary_ct_id=_optional_str(scene_payload.get("primary_ct_id")),
            role_bindings=_optional_str_dict(scene_payload.get("role_bindings")) or {},
            analysis_pose_mode=_optional_str(scene_payload.get("analysis_pose_mode")) or "",
            comparison_modalities=(
                _optional_str_dict(scene_payload.get("comparison_modalities")) or {}
            ),
            active_pose=str(scene_payload.get("active_pose", "supine")),
            visible_asset_ids=_coerce_str_list(scene_payload.get("visible_asset_ids")),
            transform_artifact_ids=_coerce_str_list(scene_payload.get("transform_artifact_ids")),
        )
        return cls(
            schema_version=str(payload.get("schema_version", "")),
            case_id=str(payload.get("case_id", "")),
            patient_id=str(payload.get("patient_id", "")),
            patient_name=str(payload.get("patient_name", "")),
            created_utc=str(payload.get("created_utc", "")),
            updated_utc=str(payload.get("updated_utc", "")),
            assets=assets,
            scene=scene,
            dicom_index=(
                payload.get("dicom_index", {})
                if isinstance(payload.get("dicom_index"), dict)
                else {}
            ),
            patient_metadata=(
                payload.get("patient_metadata", {})
                if isinstance(payload.get("patient_metadata"), dict)
                else {}
            ),
            analysis_state=(
                payload.get("analysis_state", {})
                if isinstance(payload.get("analysis_state"), dict)
                else {}
            ),
        )


@dataclass(slots=True)
class PackageSummary:
    package_path: Path
    case_id: str
    patient_id: str
    patient_name: str
    updated_utc: str
    assets: list[StudyAsset] = field(default_factory=list)

    def to_case_manifest_stub(self) -> CaseManifest:
        manifest = CaseManifest.blank()
        manifest.case_id = self.case_id
        manifest.patient_id = self.patient_id
        manifest.patient_name = self.patient_name
        manifest.updated_at = self.updated_utc or manifest.updated_at
        manifest.assets = list(self.assets)
        return manifest


class SpinePackageService:
    def __init__(self, session_store: SessionStore) -> None:
        self._session_store = session_store

    def load_summary(self, package_path: Path) -> PackageSummary:
        manifest = self._read_package_manifest(package_path)
        assets: list[StudyAsset] = []
        for item in _coerce_dict_list(manifest.analysis_state.get("assets")):
            assets.append(
                StudyAsset(
                    asset_id=str(item.get("asset_id", "")),
                    kind=str(item.get("kind", "")),
                    label=str(item.get("label", "")),
                    source_path=str(item.get("source_path", "")),
                    managed_path=str(item.get("managed_path", "")),
                    status=str(item.get("status", "ready")),
                    processing_role=(
                        str(item["processing_role"])
                        if item.get("processing_role") is not None
                        else None
                    ),
                    created_at=str(item.get("created_at", utc_now())),
                )
            )
        return PackageSummary(
            package_path=Path(package_path),
            case_id=manifest.case_id,
            patient_id=manifest.patient_id,
            patient_name=manifest.patient_name,
            updated_utc=manifest.updated_utc,
            assets=assets,
        )

    def validate_package(
        self,
        package_path: Path,
        *,
        validate_hashes: bool = True,
    ) -> SpinePackageManifest:
        manifest = self._read_package_manifest(Path(package_path))
        self._validate_package(Path(package_path), manifest, validate_hashes=validate_hashes)
        return manifest

    def open_package(self, package_path: Path) -> tuple[SessionHandle, CaseManifest]:
        package_path = Path(package_path)
        manifest = self._read_package_manifest(package_path)
        self._validate_package(package_path, manifest, validate_hashes=False)
        runtime_manifest = self._runtime_manifest_from_package_manifest(manifest)
        session = self._session_store.create_blank_session(
            manifest=runtime_manifest,
            source_kind="package",
            saved_package_path=package_path,
        )
        with zipfile.ZipFile(package_path, "r") as archive:
            for member in archive.namelist():
                if member == "manifest.json":
                    continue
                archive.extract(member, session.workspace_root)
        runtime_manifest = self._hydrate_runtime_manifest(session, runtime_manifest)
        self._session_store.write_runtime_manifest(session, runtime_manifest)
        self._session_store.write_dicom_catalog(
            session,
            manifest.dicom_index if isinstance(manifest.dicom_index, dict) else {"imports": []},
        )
        session.mark_clean()
        return session, runtime_manifest

    def save_package(
        self,
        session: SessionHandle,
        manifest: CaseManifest,
        package_path: Path,
    ) -> Path:
        package_path = Path(package_path)
        package_path.parent.mkdir(parents=True, exist_ok=True)
        package_manifest = self._build_package_manifest(session, manifest)
        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".spine",
            dir=package_path.parent,
        )
        temp_path = Path(temp_file.name)
        temp_file.close()
        try:
            with zipfile.ZipFile(
                temp_path,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                allowZip64=True,
            ) as archive:
                self._write_required_directories(archive)
                for asset in sorted(package_manifest.assets, key=lambda item: item.path):
                    archive.write(session.workspace_root / Path(asset.path), asset.path)
                archive.writestr(
                    "manifest.json",
                    json.dumps(package_manifest.to_dict(), indent=2),
                )
            temp_path.replace(package_path)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
        session.saved_package_path = package_path
        session.mark_clean()
        return package_path

    def export_package_folder(
        self,
        session: SessionHandle,
        manifest: CaseManifest,
        output_dir: Path,
    ) -> Path:
        output_dir = Path(output_dir)
        export_root = output_dir / manifest.case_id
        if export_root.exists():
            shutil.rmtree(export_root, ignore_errors=True)
        export_root.mkdir(parents=True, exist_ok=True)
        for relative_dir in SESSION_LAYOUT_DIRS:
            (export_root / relative_dir).mkdir(parents=True, exist_ok=True)
        package_manifest = self._build_package_manifest(session, manifest)
        for asset in package_manifest.assets:
            source_path = session.workspace_root / Path(asset.path)
            destination = export_root / Path(asset.path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination)
        (export_root / "manifest.json").write_text(
            json.dumps(package_manifest.to_dict(), indent=2),
            encoding="utf-8",
        )
        return export_root

    def export_assets(
        self,
        session: SessionHandle,
        manifest: CaseManifest,
        asset_ids: list[str],
        output_dir: Path,
    ) -> list[Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        package_manifest = self._build_package_manifest(session, manifest)
        selected = [asset for asset in package_manifest.assets if asset.id in set(asset_ids)]
        exported: list[Path] = []
        for asset in selected:
            source_path = session.workspace_root / Path(asset.path)
            destination = _unique_destination(output_dir / Path(asset.path).name)
            shutil.copy2(source_path, destination)
            exported.append(destination)
        return exported

    def asset_groups(
        self,
        session: SessionHandle,
        manifest: CaseManifest,
    ) -> dict[str, list[str]]:
        package_manifest = self._build_package_manifest(session, manifest)
        groups: dict[str, list[str]] = {
            "dicom": [],
            "ct": [],
            "drr": [],
            "mesh": [],
            "analytics": [],
            "reports": [],
            "all": [],
        }
        for asset in package_manifest.assets:
            groups["all"].append(asset.id)
            if asset.type == "dicom":
                groups["dicom"].append(asset.id)
            elif asset.type == "ct":
                groups["ct"].append(asset.id)
            elif asset.type == "drr":
                groups["drr"].append(asset.id)
            elif asset.type == "mesh":
                groups["mesh"].append(asset.id)
            elif asset.type == "report":
                groups["reports"].append(asset.id)
                groups["analytics"].append(asset.id)
            elif asset.type in {"analytics", "measurements"}:
                groups["analytics"].append(asset.id)
        return groups

    def _read_package_manifest(self, package_path: Path) -> SpinePackageManifest:
        if not package_path.exists():
            raise SpinePackageError(f"Case package does not exist: {package_path}")
        if package_path.suffix.lower() != ".spine":
            raise SpinePackageError(f"Unsupported case format: {package_path.suffix}")
        try:
            with zipfile.ZipFile(package_path, "r") as archive:
                payload = json.loads(archive.read("manifest.json").decode("utf-8"))
        except KeyError as exc:
            raise SpinePackageError("Case package is missing manifest.json.") from exc
        except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
            raise SpinePackageError(f"Unable to open case package: {exc}") from exc
        manifest = SpinePackageManifest.from_dict(payload)
        if manifest.schema_version != PACKAGE_SCHEMA_VERSION:
            raise SpinePackageError(
                f"Unsupported package schema version: {manifest.schema_version}"
            )
        return manifest

    def _validate_package(
        self,
        package_path: Path,
        manifest: SpinePackageManifest,
        *,
        validate_hashes: bool,
    ) -> None:
        required_entries = {"manifest.json", *{f"{entry}/" for entry in SESSION_LAYOUT_DIRS}}
        with zipfile.ZipFile(package_path, "r") as archive:
            names = set(archive.namelist())
            missing = [
                entry
                for entry in required_entries
                if entry not in names
                and not any(name.startswith(entry.rstrip("/") + "/") for name in names)
            ]
            if missing:
                raise SpinePackageError(
                    "Case package is missing required layout entries: "
                    + ", ".join(sorted(missing))
                )
            for asset in manifest.assets:
                if asset.path not in names:
                    raise SpinePackageError(f"Package asset is missing: {asset.path}")
                if not validate_hashes:
                    continue
                payload = archive.read(asset.path)
                digest = hashlib.sha256(payload).hexdigest()
                if digest != asset.sha256:
                    raise SpinePackageError(f"Package asset hash mismatch: {asset.path}")

    def _build_package_manifest(
        self,
        session: SessionHandle,
        manifest: CaseManifest,
    ) -> SpinePackageManifest:
        dicom_index = self._session_store.load_dicom_catalog(session)
        assets = self._collect_package_assets(session, manifest, dicom_index)
        scene = self._build_scene_state(manifest)
        return SpinePackageManifest(
            schema_version=PACKAGE_SCHEMA_VERSION,
            case_id=manifest.case_id,
            patient_id=manifest.patient_id,
            patient_name=manifest.patient_name,
            created_utc=manifest.created_at,
            updated_utc=utc_now(),
            assets=assets,
            scene=scene,
            dicom_index=dicom_index,
            patient_metadata={
                "age_text": manifest.age_text,
                "sex": manifest.sex,
                "diagnosis": manifest.diagnosis,
                "procedure_history": list(manifest.procedure_history),
            },
            analysis_state=self._serialize_runtime_state(session, manifest),
        )

    def _collect_package_assets(
        self,
        session: SessionHandle,
        manifest: CaseManifest,
        dicom_index: dict[str, object],
    ) -> list[SpinePackageAsset]:
        study_asset_lookup = {
            _relative_workspace_path(session.workspace_root, Path(asset.managed_path)): asset
            for asset in manifest.assets
            if _is_workspace_path(session.workspace_root, asset.managed_path)
        }
        artifact_lookup = {
            _relative_workspace_path(session.workspace_root, Path(artifact.path)): artifact
            for artifact in manifest.artifacts
            if _is_workspace_path(session.workspace_root, artifact.path)
        }
        dicom_asset_lookup = _dicom_asset_lookup(dicom_index)
        assets: list[SpinePackageAsset] = []
        for file_path in sorted(_workspace_files(session.workspace_root)):
            relative_path = _relative_workspace_path(session.workspace_root, file_path)
            asset = study_asset_lookup.get(relative_path)
            artifact = artifact_lookup.get(relative_path)
            dicom_payload = dicom_asset_lookup.get(relative_path)
            asset_id = (
                asset.asset_id
                if asset is not None
                else (
                    artifact.artifact_id
                    if artifact is not None
                    else str(dicom_payload.get("asset_id"))
                    if dicom_payload is not None
                    else f"pkg-{hashlib.sha1(relative_path.encode('utf-8')).hexdigest()[:12]}"
                )
            )
            asset_type = _asset_type_for_relative_path(relative_path, file_path)
            pose = _pose_for_relative_path(relative_path)
            assets.append(
                SpinePackageAsset(
                    id=asset_id,
                    type=asset_type,
                    path=relative_path,
                    format=_format_for_path(file_path),
                    sha256=_sha256_file(file_path),
                    size_bytes=file_path.stat().st_size,
                    subtype=(artifact.artifact_type if artifact is not None else None),
                    role=(asset.processing_role if asset is not None else None),
                    pose=pose,
                    source_asset_id=(
                        str(dicom_payload.get("working_asset_id"))
                        if dicom_payload is not None and dicom_payload.get("working_asset_id")
                        else None
                    ),
                    created_utc=(
                        asset.created_at
                        if asset is not None
                        else str(dicom_payload.get("created_utc"))
                        if dicom_payload is not None and dicom_payload.get("created_utc")
                        else None
                    ),
                    dicom_refs=(
                        {
                            key: str(value)
                            for key, value in dicom_payload.items()
                            if key
                            in {
                                "StudyInstanceUID",
                                "SeriesInstanceUID",
                                "SOPInstanceUID",
                            }
                            and value is not None
                        }
                        if dicom_payload is not None
                        else None
                    ),
                    label=(
                        asset.label
                        if asset is not None
                        else artifact.label if artifact is not None else None
                    ),
                    status=(
                        asset.status
                        if asset is not None
                        else artifact.status if artifact is not None else None
                    ),
                )
            )
        return assets

    def _build_scene_state(self, manifest: CaseManifest) -> SpineSceneState:
        role_bindings = {
            asset.processing_role: asset.asset_id
            for asset in manifest.assets
            if asset.processing_role
        }
        visible_asset_ids = [
            asset.asset_id
            for asset in manifest.assets
            if asset.kind in {"ct_zstack", "mesh_3d", "xray_2d"}
        ]
        transform_artifact_ids = [
            artifact.artifact_id
            for artifact in manifest.artifacts
            if artifact.stage in {"mesh", "registration"}
        ]
        primary_ct = manifest.get_asset_for_role("ct_stack")
        active_pose = (
            "standing"
            if any(
                "standing" in asset.label.lower()
                for asset in manifest.assets
                if asset.kind == "mesh_3d"
            )
            else "supine"
        )
        return SpineSceneState(
            primary_ct_id=primary_ct.asset_id if primary_ct is not None else None,
            role_bindings=role_bindings,
            analysis_pose_mode=manifest.analysis_pose_mode,
            comparison_modalities=dict(manifest.comparison_modalities),
            active_pose=active_pose,
            visible_asset_ids=visible_asset_ids,
            transform_artifact_ids=transform_artifact_ids,
        )

    def _serialize_runtime_state(
        self,
        session: SessionHandle,
        manifest: CaseManifest,
    ) -> dict[str, object]:
        payload = manifest.to_dict()
        for asset_payload in payload.get("assets", []):
            if not isinstance(asset_payload, dict):
                continue
            asset_payload["managed_path"] = _serialize_path_field(
                session.workspace_root,
                asset_payload.get("managed_path"),
            )
            asset_payload["source_path"] = _serialize_path_field(
                session.workspace_root,
                asset_payload.get("source_path"),
            )
        for artifact_payload in payload.get("artifacts", []):
            if not isinstance(artifact_payload, dict):
                continue
            artifact_payload["path"] = _serialize_path_field(
                session.workspace_root,
                artifact_payload.get("path"),
            )
        for run_payload in payload.get("pipeline_runs", []):
            if not isinstance(run_payload, dict):
                continue
            run_payload["inputs"] = [
                _serialize_path_field(session.workspace_root, item)
                for item in _coerce_str_list(run_payload.get("inputs"))
            ]
            run_payload["outputs"] = [
                _serialize_path_field(session.workspace_root, item)
                for item in _coerce_str_list(run_payload.get("outputs"))
            ]
            run_payload["performance_trace_path"] = _serialize_path_field(
                session.workspace_root,
                run_payload.get("performance_trace_path"),
            )
        for volume_payload in payload.get("volumes", []):
            if not isinstance(volume_payload, dict):
                continue
            volume_payload["source_path"] = _serialize_path_field(
                session.workspace_root,
                volume_payload.get("source_path"),
            )
            volume_payload["canonical_path"] = _serialize_path_field(
                session.workspace_root,
                volume_payload.get("canonical_path"),
            )
        return payload

    def _runtime_manifest_from_package_manifest(
        self,
        manifest: SpinePackageManifest,
    ) -> CaseManifest:
        payload = dict(manifest.analysis_state)
        if not payload:
            payload = CaseManifest.blank().to_dict()
            payload["case_id"] = manifest.case_id
            payload["patient_id"] = manifest.patient_id
            payload["patient_name"] = manifest.patient_name
        payload.setdefault("case_id", manifest.case_id)
        payload.setdefault("patient_id", manifest.patient_id)
        payload.setdefault("patient_name", manifest.patient_name)
        payload.setdefault("created_at", manifest.created_utc or utc_now())
        payload.setdefault("updated_at", manifest.updated_utc or utc_now())
        payload.setdefault("diagnosis", str(manifest.patient_metadata.get("diagnosis", "")))
        payload.setdefault("age_text", str(manifest.patient_metadata.get("age_text", "")))
        payload.setdefault("sex", str(manifest.patient_metadata.get("sex", "")))

        def _restore(value: object) -> str:
            return _restore_path_field(value)

        for asset_payload in _coerce_dict_list(payload.get("assets")):
            asset_payload["managed_path"] = _restore(asset_payload.get("managed_path"))
            asset_payload["source_path"] = _restore(asset_payload.get("source_path"))
        for artifact_payload in _coerce_dict_list(payload.get("artifacts")):
            artifact_payload["path"] = _restore(artifact_payload.get("path"))
        for run_payload in _coerce_dict_list(payload.get("pipeline_runs")):
            run_payload["inputs"] = [
                _restore(item) for item in _coerce_str_list(run_payload.get("inputs"))
            ]
            run_payload["outputs"] = [
                _restore(item) for item in _coerce_str_list(run_payload.get("outputs"))
            ]
            run_payload["performance_trace_path"] = _restore(
                run_payload.get("performance_trace_path")
            )
        for volume_payload in _coerce_dict_list(payload.get("volumes")):
            volume_payload["source_path"] = _restore(volume_payload.get("source_path"))
            volume_payload["canonical_path"] = _restore(volume_payload.get("canonical_path"))
        return CaseManifest.from_dict(payload)

    def _hydrate_runtime_manifest(
        self,
        session: SessionHandle,
        manifest: CaseManifest,
    ) -> CaseManifest:
        payload = manifest.to_dict()
        for asset_payload in _coerce_dict_list(payload.get("assets")):
            asset_payload["managed_path"] = _hydrate_path(
                session.workspace_root,
                asset_payload.get("managed_path"),
            )
            asset_payload["source_path"] = _hydrate_path(
                session.workspace_root,
                asset_payload.get("source_path"),
            )
        for artifact_payload in _coerce_dict_list(payload.get("artifacts")):
            artifact_payload["path"] = _hydrate_path(
                session.workspace_root,
                artifact_payload.get("path"),
            )
        for run_payload in _coerce_dict_list(payload.get("pipeline_runs")):
            run_payload["inputs"] = [
                _hydrate_path(session.workspace_root, item)
                for item in _coerce_str_list(run_payload.get("inputs"))
            ]
            run_payload["outputs"] = [
                _hydrate_path(session.workspace_root, item)
                for item in _coerce_str_list(run_payload.get("outputs"))
            ]
            run_payload["performance_trace_path"] = _hydrate_path(
                session.workspace_root,
                run_payload.get("performance_trace_path"),
            )
        for volume_payload in _coerce_dict_list(payload.get("volumes")):
            volume_payload["source_path"] = _hydrate_path(
                session.workspace_root,
                volume_payload.get("source_path"),
            )
            volume_payload["canonical_path"] = _hydrate_path(
                session.workspace_root,
                volume_payload.get("canonical_path"),
            )
        return CaseManifest.from_dict(payload)

    def _write_required_directories(self, archive: zipfile.ZipFile) -> None:
        for relative_dir in SESSION_LAYOUT_DIRS:
            archive.writestr(f"{relative_dir}/", "")


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_str_dict(payload: object) -> dict[str, str] | None:
    if not isinstance(payload, dict):
        return None
    result = {str(key): str(value) for key, value in payload.items() if value is not None}
    return result or None


def _coerce_str_list(payload: object) -> list[str]:
    if not isinstance(payload, list):
        return []
    return [str(item) for item in payload]


def _coerce_dict_list(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _workspace_files(workspace_root: Path) -> list[Path]:
    files: list[Path] = []
    for relative_dir in SESSION_LAYOUT_DIRS:
        root = workspace_root / relative_dir
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                files.append(path)
    return files


def _is_workspace_path(workspace_root: Path, raw_path: str) -> bool:
    if not raw_path:
        return False
    path = Path(raw_path)
    if not path.is_absolute():
        return True
    try:
        path.resolve().relative_to(workspace_root.resolve())
        return True
    except ValueError:
        return False


def _relative_workspace_path(workspace_root: Path, path: Path) -> str:
    return path.resolve().relative_to(workspace_root.resolve()).as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format_for_path(path: Path) -> str:
    suffixes = "".join(path.suffixes).lower().lstrip(".")
    return suffixes or "bin"


def _asset_type_for_relative_path(relative_path: str, path: Path) -> str:
    if relative_path.startswith("dicom/"):
        return "dicom"
    if relative_path.startswith("ct/"):
        return "ct"
    if relative_path.startswith("mri/"):
        return "mri"
    if relative_path.startswith("xray/"):
        return "xray"
    if relative_path.startswith("drr/"):
        return "drr"
    if relative_path.startswith("3d/"):
        return "mesh"
    if relative_path.startswith("analytics/"):
        suffix = "".join(path.suffixes).lower()
        if suffix == ".pdf":
            return "report"
        if suffix in {".csv", ".json"} and "measure" in relative_path.lower():
            return "measurements"
        return "analytics"
    return "other"


def _pose_for_relative_path(relative_path: str) -> str | None:
    if relative_path.startswith("3d/supine/"):
        return "supine"
    if relative_path.startswith("3d/standing/"):
        return "standing"
    return None


def _serialize_path_field(workspace_root: Path, value: object) -> str:
    if value is None:
        return ""
    path = Path(str(value))
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(workspace_root.resolve()).as_posix()
    except ValueError:
        return str(value)


def _restore_path_field(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _hydrate_path(workspace_root: Path, value: object) -> str:
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    path = Path(raw)
    if path.is_absolute():
        return str(path)
    return str(workspace_root / path)


def _unique_destination(destination: Path) -> Path:
    if not destination.exists():
        return destination
    index = 1
    suffix = "".join(destination.suffixes)
    stem = destination.name[: -len(suffix)] if suffix else destination.name
    while True:
        candidate = destination.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _dicom_asset_lookup(dicom_index: dict[str, object]) -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {}
    imports = dicom_index.get("imports")
    if not isinstance(imports, list):
        return lookup
    for entry in imports:
        if not isinstance(entry, dict):
            continue
        files = entry.get("files")
        if not isinstance(files, list):
            continue
        for file_entry in files:
            if not isinstance(file_entry, dict):
                continue
            relative_path = file_entry.get("relative_path")
            if not isinstance(relative_path, str) or not relative_path.strip():
                continue
            merged = dict(file_entry)
            merged["working_asset_id"] = entry.get("working_asset_id")
            lookup[relative_path] = merged
    return lookup
