from __future__ import annotations

from dataclasses import asdict

from spinelab.io import CaseStore
from spinelab.models import CaseManifest, FindingRecord, PipelineArtifact
from spinelab.models.manifest import make_id
from spinelab.pipeline.artifacts import findings_summary_path, write_json_artifact
from spinelab.pipeline.contracts import PipelineStageName, StageExecutionResult
from spinelab.pipeline.stages.common import artifact_for_type

_SUMMARY_FINDING_KEYS = {
    "cobb_angle",
    "sagittal_vertical_axis",
    "thoracic_kyphosis",
    "lumbar_lordosis",
    "pelvic_tilt",
}


def _finding_from_metric(metric_key: str, value: float | None) -> tuple[str, str, str]:
    if value is None:
        return (
            "warning",
            "Measurement unavailable",
            (
                "The metric is intentionally fail-closed until the required primitives "
                "or field of view exist."
            ),
        )
    if metric_key == "cobb_angle":
        if value >= 25.0:
            return (
                "warning",
                "Coronal curvature review",
                (
                    "Registered geometry suggests a clinically relevant coronal curve "
                    "that warrants review."
                ),
            )
        return (
            "normal",
            "Coronal alignment within current scaffold range",
            (
                "Current registered geometry did not cross the in-app review "
                "threshold for coronal curvature."
            ),
        )
    if metric_key == "sagittal_vertical_axis":
        if value >= 30.0:
            return (
                "warning",
                "Sagittal balance review",
                "Registered geometry suggests elevated sagittal offset.",
            )
        return (
            "normal",
            "Sagittal balance within current scaffold range",
            (
                "Current registered geometry stayed within the in-app review "
                "threshold for sagittal offset."
            ),
        )
    return (
        "normal",
        "Measurement recorded",
        "Artifact-backed measurement record was produced for GUI review.",
    )


def run_findings_stage(store: CaseStore, manifest: CaseManifest) -> StageExecutionResult:
    measurements_artifact = artifact_for_type(manifest, "measurements")
    findings: list[FindingRecord] = []
    for metric in manifest.measurements.records:
        if metric.key not in _SUMMARY_FINDING_KEYS:
            continue
        severity, title, reasoning = _finding_from_metric(metric.key, metric.value)
        detail = metric.invalid_reason if not metric.valid else metric.value_text
        findings.append(
            FindingRecord(
                finding_id=make_id("finding"),
                severity=severity,
                diagnosis_title=title,
                reasoning=f"{reasoning} Source metric: {metric.label} ({detail}).",
                vertebra_pair="T4-L5" if metric.key == "cobb_angle" else "",
                plane=(
                    "coronal"
                    if metric.key == "cobb_angle"
                    else "sagittal" if metric.key == "sagittal_vertical_axis" else None
                ),
                source_metric_keys=[metric.key],
            )
        )

    summary_path = findings_summary_path(store, manifest)
    write_json_artifact(
        summary_path,
        {
            "case_id": manifest.case_id,
            "finding_count": len(findings),
            "findings": [asdict(finding) for finding in findings],
            "gui_review_surface": "report",
        },
    )
    artifact = PipelineArtifact(
        artifact_id=make_id("artifact"),
        kind="json",
        label="Findings Summary",
        path=str(summary_path),
        stage=PipelineStageName.FINDINGS.value,
        artifact_type="findings",
        coordinate_frame="patient-body-standing",
        review_surface="report",
        summary="Review findings derived from artifact-backed measurement outputs.",
        source_artifact_ids=(
            [measurements_artifact.artifact_id] if measurements_artifact is not None else []
        ),
        metadata={"finding_count": str(len(findings))},
    )
    return StageExecutionResult(
        stage=PipelineStageName.FINDINGS,
        message=f"Prepared {len(findings)} review finding(s).",
        outputs=[str(summary_path)],
        artifacts=[artifact],
        findings=findings,
    )
