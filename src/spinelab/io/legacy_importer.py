from __future__ import annotations

import shutil
from pathlib import Path

from spinelab.models import CaseManifest

from .session_store import SESSION_LAYOUT_DIRS, SessionHandle, SessionStore


class LegacyCaseImporter:
    def __init__(self, session_store: SessionStore) -> None:
        self._session_store = session_store

    def import_case_folder(
        self,
        case_root: Path,
        manifest: CaseManifest,
    ) -> tuple[SessionHandle, CaseManifest]:
        case_root = Path(case_root)
        session = self._session_store.create_blank_session(
            manifest=manifest,
            source_kind="legacy",
            legacy_source_path=case_root,
        )
        for relative_dir in SESSION_LAYOUT_DIRS:
            source_dir = case_root / relative_dir
            destination_dir = session.workspace_root / relative_dir
            if not source_dir.exists():
                destination_dir.mkdir(parents=True, exist_ok=True)
                continue
            for source_path in source_dir.rglob("*"):
                if source_path.is_dir():
                    continue
                destination = destination_dir / source_path.relative_to(source_dir)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, destination)
        rebased = self._rebase_manifest_paths(manifest, case_root, session.workspace_root)
        self._session_store.write_runtime_manifest(session, rebased)
        session.mark_clean()
        return session, rebased

    def _rebase_manifest_paths(
        self,
        manifest: CaseManifest,
        source_root: Path,
        target_root: Path,
    ) -> CaseManifest:
        payload = manifest.to_dict()
        for asset_payload in payload.get("assets", []):
            if not isinstance(asset_payload, dict):
                continue
            asset_payload["managed_path"] = _rebase_path(
                asset_payload.get("managed_path"),
                source_root,
                target_root,
            )
            asset_payload["source_path"] = _rebase_path(
                asset_payload.get("source_path"),
                source_root,
                target_root,
            )
        for artifact_payload in payload.get("artifacts", []):
            if not isinstance(artifact_payload, dict):
                continue
            artifact_payload["path"] = _rebase_path(
                artifact_payload.get("path"),
                source_root,
                target_root,
            )
        for run_payload in payload.get("pipeline_runs", []):
            if not isinstance(run_payload, dict):
                continue
            run_payload["inputs"] = [
                _rebase_path(item, source_root, target_root)
                for item in run_payload.get("inputs", [])
            ]
            run_payload["outputs"] = [
                _rebase_path(item, source_root, target_root)
                for item in run_payload.get("outputs", [])
            ]
            run_payload["performance_trace_path"] = _rebase_path(
                run_payload.get("performance_trace_path"),
                source_root,
                target_root,
            )
        for volume_payload in payload.get("volumes", []):
            if not isinstance(volume_payload, dict):
                continue
            volume_payload["source_path"] = _rebase_path(
                volume_payload.get("source_path"),
                source_root,
                target_root,
            )
            volume_payload["canonical_path"] = _rebase_path(
                volume_payload.get("canonical_path"),
                source_root,
                target_root,
            )
        return CaseManifest.from_dict(payload)


def _rebase_path(value: object, source_root: Path, target_root: Path) -> str:
    if value is None:
        return ""
    path = Path(str(value))
    if not path.is_absolute():
        return str(target_root / path)
    try:
        relative = path.resolve().relative_to(source_root.resolve())
    except ValueError:
        return str(path)
    return str(target_root / relative)
