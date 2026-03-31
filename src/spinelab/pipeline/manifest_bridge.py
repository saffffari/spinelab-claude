from __future__ import annotations

from spinelab.models import CaseManifest, PipelineArtifact, StudyAsset
from spinelab.pipeline.contracts import PipelineStageName, StageExecutionResult
from spinelab.pipeline.stages.common import generated_asset_prefix

_GENERATED_ASSET_LABELS: dict[str, tuple[str, str]] = {
    "mesh-baseline": ("mesh_3d", "Model"),
    "registration-scene": ("mesh_3d", "Standing Model"),
}


def reset_stage_state(manifest: CaseManifest, stages: tuple[PipelineStageName, ...]) -> None:
    stage_values = {stage.value for stage in stages}
    manifest.artifacts = [
        artifact for artifact in manifest.artifacts if artifact.stage not in stage_values
    ]
    manifest.assets = [
        asset
        for asset in manifest.assets
        if not any(
            asset.asset_id.startswith(generated_asset_prefix(stage.value))
            for stage in stages
        )
    ]
    manifest.pipeline_runs = [
        run for run in manifest.pipeline_runs if run.stage not in stage_values
    ]
    if PipelineStageName.NORMALIZE in stages:
        manifest.volumes = []
    if PipelineStageName.MEASUREMENTS in stages or PipelineStageName.METRICS in stages:
        manifest.measurements.records = []
        manifest.measurements.values = {}
        manifest.measurements.reviewed = False
        manifest.measurements.provenance = "pending"
        manifest.cobb_angle = ""
    if PipelineStageName.FINDINGS in stages:
        manifest.findings = []
        manifest.review_decisions = []


def apply_stage_result(manifest: CaseManifest, result: StageExecutionResult) -> None:
    manifest.artifacts.extend(result.artifacts)
    _upsert_generated_assets(manifest, result.artifacts)
    if result.volumes:
        manifest.volumes = list(result.volumes)
    if result.metrics:
        manifest.measurements.records = list(result.metrics)
        manifest.measurements.values = {
            metric.label: metric.value_text for metric in result.metrics if metric.value_text
        }
        manifest.measurements.reviewed = False
        manifest.measurements.provenance = "artifact-backed"
        manifest.cobb_angle = next(
            (metric.value_text for metric in result.metrics if metric.key == "cobb_angle"),
            manifest.cobb_angle,
        )
    if result.findings:
        manifest.findings = list(result.findings)


def latest_artifact_for_surface(
    manifest: CaseManifest,
    surface: str,
) -> PipelineArtifact | None:
    for artifact in reversed(manifest.artifacts):
        if artifact.review_surface == surface:
            return artifact
    return None


def latest_completed_run(manifest: CaseManifest) -> tuple[str, str]:
    if not manifest.pipeline_runs:
        return ("No analysis yet", "Run Analyze in Import to populate stage contracts.")
    latest_run = manifest.pipeline_runs[-1]
    stage_label = latest_run.stage.replace("_", " ").title()
    status_label = latest_run.status.title()
    if latest_run.status == "failed":
        detail = latest_run.error_text or latest_run.message or "Stage failed."
    else:
        detail = latest_run.message or f"{stage_label} finished with status {status_label}."
    return (f"{stage_label} · {status_label}", detail)


def import_review_summary(manifest: CaseManifest) -> tuple[str, str]:
    artifact = latest_artifact_for_surface(manifest, "import")
    if artifact is None:
        return (
            "Awaiting Import review output",
            "Analyze will surface canonical volume and segmentation contracts here.",
        )
    model_bits = []
    if artifact.metadata.get("model_name"):
        model_bits.append(artifact.metadata["model_name"])
    if artifact.metadata.get("model_version"):
        model_bits.append(artifact.metadata["model_version"])
    suffix = f" ({' · '.join(model_bits)})" if model_bits else ""
    detail = artifact.summary or artifact.label
    return (f"{artifact.label}{suffix}", detail)


def _upsert_generated_assets(
    manifest: CaseManifest,
    artifacts: list[PipelineArtifact],
) -> None:
    lookup = {asset.asset_id: asset for asset in manifest.assets}
    for artifact in artifacts:
        if artifact.asset_id is None:
            continue
        label_pair = _GENERATED_ASSET_LABELS.get(artifact.artifact_type)
        if label_pair is None:
            continue
        kind, label = label_pair
        asset = lookup.get(artifact.asset_id)
        if asset is None:
            asset = StudyAsset(
                asset_id=artifact.asset_id,
                kind=kind,
                label=label,
                source_path=artifact.path,
                managed_path=artifact.path,
                status=artifact.status,
            )
            manifest.assets.append(asset)
            lookup[artifact.asset_id] = asset
            continue
        asset.kind = kind
        asset.label = label
        asset.source_path = artifact.path
        asset.managed_path = artifact.path
        asset.status = artifact.status
