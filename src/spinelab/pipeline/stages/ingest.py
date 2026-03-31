from __future__ import annotations

from spinelab.io import CaseStore
from spinelab.models import CaseManifest, PipelineArtifact
from spinelab.models.manifest import make_id
from spinelab.pipeline.artifacts import ingest_summary_path, write_json_artifact
from spinelab.pipeline.contracts import PipelineStageName, StageExecutionResult


def run_ingest_stage(store: CaseStore, manifest: CaseManifest) -> StageExecutionResult:
    summary_path = ingest_summary_path(store, manifest)
    assets_payload = [
        {
            "asset_id": asset.asset_id,
            "kind": asset.kind,
            "label": asset.label,
            "source_path": asset.source_path,
            "managed_path": asset.managed_path,
            "processing_role": asset.processing_role,
            "status": asset.status,
        }
        for asset in manifest.assets
    ]
    payload = {
        "case_id": manifest.case_id,
        "asset_count": len(assets_payload),
        "assets": assets_payload,
        "gui_primary_surface": "import",
    }
    write_json_artifact(summary_path, payload)
    artifact = PipelineArtifact(
        artifact_id=make_id("artifact"),
        kind="json",
        label="Ingest Asset Summary",
        path=str(summary_path),
        stage=PipelineStageName.INGEST.value,
        artifact_type="ingest-summary",
        coordinate_frame="source-assets",
        review_surface="import",
        summary=f"{len(assets_payload)} source assets indexed for Analyze.",
        metadata={"asset_count": str(len(assets_payload))},
    )
    return StageExecutionResult(
        stage=PipelineStageName.INGEST,
        message=f"Ingested {len(assets_payload)} source assets.",
        outputs=[str(summary_path)],
        artifacts=[artifact],
    )
