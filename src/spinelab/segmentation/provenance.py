from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spinelab.io import CaseStore
from spinelab.models import CaseManifest
from spinelab.pipeline.artifacts import read_json_artifact
from spinelab.services import SettingsService


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = normalized.strip("-")
    return slug or "segmentation-backend"


@dataclass(frozen=True, slots=True)
class SegmentationBackendSummary:
    backend_id: str
    display_name: str
    family: str
    driver_id: str
    runtime_environment_id: str
    checkpoint_id: str
    model_name: str
    model_version: str

    @property
    def export_slug(self) -> str:
        preferred = self.backend_id or self.display_name or self.family
        return _slugify(preferred)

    @property
    def compact_label(self) -> str:
        parts = [self.display_name or self.family or self.model_name]
        if self.checkpoint_id:
            parts.append(self.checkpoint_id)
        return " · ".join(part for part in parts if part)

    def to_metadata(self) -> dict[str, str]:
        return {
            "backend_id": self.backend_id,
            "display_name": self.display_name,
            "family": self.family,
            "driver_id": self.driver_id,
            "runtime_environment_id": self.runtime_environment_id,
            "checkpoint_id": self.checkpoint_id,
            "model_name": self.model_name,
            "model_version": self.model_version,
        }


def summary_from_payload(payload: dict[str, Any] | None) -> SegmentationBackendSummary | None:
    if not isinstance(payload, dict):
        return None
    backend_id = str(
        payload.get("model_bundle_id")
        or payload.get("model_version")
        or payload.get("model_name")
        or ""
    ).strip()
    display_name = str(
        payload.get("model_display_name")
        or payload.get("model_bundle_id")
        or payload.get("model_name")
        or ""
    ).strip()
    family = str(payload.get("model_family") or payload.get("model_name") or "").strip()
    driver_id = str(payload.get("driver_id") or "").strip()
    runtime_environment_id = str(payload.get("runtime_environment_id") or "").strip()
    checkpoint_id = str(
        payload.get("resolved_checkpoint_id") or payload.get("checkpoint_id") or ""
    ).strip()
    model_name = str(payload.get("model_name") or family or display_name).strip()
    model_version = str(payload.get("model_version") or backend_id or "").strip()
    if not any(
        (
            backend_id,
            display_name,
            family,
            driver_id,
            runtime_environment_id,
            checkpoint_id,
            model_name,
            model_version,
        )
    ):
        return None
    if not backend_id:
        backend_id = model_version or model_name or display_name
    if not display_name:
        display_name = family or model_name or backend_id
    return SegmentationBackendSummary(
        backend_id=backend_id,
        display_name=display_name,
        family=family or display_name,
        driver_id=driver_id,
        runtime_environment_id=runtime_environment_id,
        checkpoint_id=checkpoint_id,
        model_name=model_name or display_name,
        model_version=model_version or backend_id,
    )


def summary_for_manifest(manifest: CaseManifest) -> SegmentationBackendSummary | None:
    segmentation_artifact = next(
        (artifact for artifact in manifest.artifacts if artifact.artifact_type == "segmentation"),
        None,
    )
    if segmentation_artifact is None:
        return None
    artifact_path = Path(segmentation_artifact.path)
    if not artifact_path.exists():
        return None
    payload = read_json_artifact(artifact_path)
    return summary_from_payload(payload if isinstance(payload, dict) else None)


def summary_for_active_bundle(
    store: CaseStore,
    settings: SettingsService | None = None,
) -> SegmentationBackendSummary | None:
    from spinelab.segmentation.bundles import SegmentationBundleRegistry

    registry = SegmentationBundleRegistry(store, settings=settings)
    try:
        runtime_model = registry.resolve_active_bundle().active_runtime_model()
    except Exception:
        return None
    return summary_from_payload(
        {
            "model_bundle_id": runtime_model.model_id,
            "model_display_name": runtime_model.display_name,
            "model_family": runtime_model.family,
            "driver_id": runtime_model.driver_id,
            "runtime_environment_id": runtime_model.environment_id,
            "resolved_checkpoint_id": runtime_model.checkpoint.checkpoint_id,
            "model_name": runtime_model.family,
            "model_version": runtime_model.model_id,
        }
    )
