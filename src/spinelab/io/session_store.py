from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from spinelab.models import CaseManifest
from spinelab.models.manifest import utc_now

SESSION_LAYOUT_DIRS = (
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
)


def default_session_root() -> Path:
    override = os.environ.get("SPINELAB_SESSION_ROOT")
    if override:
        return Path(override)
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "SpineLab" / "sessions"
    return Path.home() / "AppData" / "Local" / "SpineLab" / "sessions"


@dataclass(slots=True)
class SessionHandle:
    session_id: str
    case_id: str
    workspace_root: Path
    runtime_root: Path
    saved_package_path: Path | None = None
    source_kind: str = "blank"
    legacy_source_path: Path | None = None
    dirty: bool = False
    created_utc: str = field(default_factory=utc_now)
    updated_utc: str = field(default_factory=utc_now)

    @property
    def runtime_manifest_path(self) -> Path:
        return self.runtime_root / "case_manifest.json"

    @property
    def dicom_catalog_path(self) -> Path:
        return self.runtime_root / "dicom_catalog.json"

    def mark_dirty(self) -> None:
        self.dirty = True
        self.updated_utc = utc_now()

    def mark_clean(self) -> None:
        self.dirty = False
        self.updated_utc = utc_now()

    def sync_case_id(self, case_id: str) -> None:
        self.case_id = case_id
        self.updated_utc = utc_now()


class SessionStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_session_root()

    def ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def create_blank_session(
        self,
        *,
        manifest: CaseManifest | None = None,
        source_kind: str = "blank",
        saved_package_path: Path | None = None,
        legacy_source_path: Path | None = None,
    ) -> SessionHandle:
        self.ensure_root()
        runtime_manifest = manifest or CaseManifest.blank()
        session_id = f"session-{uuid4().hex[:12]}"
        session_root = self.root / session_id
        workspace_root = session_root / "workspace"
        runtime_root = session_root / "runtime"
        runtime_root.mkdir(parents=True, exist_ok=True)
        self._ensure_workspace_layout(workspace_root)
        handle = SessionHandle(
            session_id=session_id,
            case_id=runtime_manifest.case_id,
            workspace_root=workspace_root,
            runtime_root=runtime_root,
            saved_package_path=saved_package_path,
            source_kind=source_kind,
            legacy_source_path=legacy_source_path,
        )
        self.write_runtime_manifest(handle, runtime_manifest)
        self.write_dicom_catalog(handle, {"imports": []})
        handle.mark_clean()
        return handle

    def purge_orphaned_sessions(self) -> int:
        if not self.root.exists():
            return 0
        removed = 0
        for session_root in self.root.iterdir():
            if not session_root.is_dir():
                continue
            shutil.rmtree(session_root, ignore_errors=True)
            removed += 1
        return removed

    def destroy_session(self, session: SessionHandle) -> None:
        shutil.rmtree(session.workspace_root.parent, ignore_errors=True)

    def write_runtime_manifest(self, session: SessionHandle, manifest: CaseManifest) -> Path:
        session.runtime_root.mkdir(parents=True, exist_ok=True)
        manifest.updated_at = utc_now()
        session.sync_case_id(manifest.case_id)
        session.runtime_manifest_path.write_text(
            json.dumps(manifest.to_dict(), indent=2),
            encoding="utf-8",
        )
        return session.runtime_manifest_path

    def load_runtime_manifest(self, session: SessionHandle) -> CaseManifest:
        payload = json.loads(session.runtime_manifest_path.read_text(encoding="utf-8"))
        return CaseManifest.from_dict(payload)

    def load_dicom_catalog(self, session: SessionHandle) -> dict[str, object]:
        if not session.dicom_catalog_path.exists():
            return {"imports": []}
        try:
            payload = json.loads(session.dicom_catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"imports": []}
        if not isinstance(payload, dict):
            return {"imports": []}
        imports = payload.get("imports")
        if not isinstance(imports, list):
            payload["imports"] = []
        return payload

    def write_dicom_catalog(self, session: SessionHandle, payload: dict[str, object]) -> Path:
        session.runtime_root.mkdir(parents=True, exist_ok=True)
        session.dicom_catalog_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        return session.dicom_catalog_path

    def session_path(self, session: SessionHandle, relative_path: str) -> Path:
        return session.workspace_root / Path(relative_path)

    def relative_workspace_path(self, session: SessionHandle, path: Path) -> str:
        return path.resolve().relative_to(session.workspace_root.resolve()).as_posix()

    def _ensure_workspace_layout(self, workspace_root: Path) -> None:
        for relative_dir in SESSION_LAYOUT_DIRS:
            (workspace_root / relative_dir).mkdir(parents=True, exist_ok=True)
