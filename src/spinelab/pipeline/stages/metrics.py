from __future__ import annotations

from spinelab.io import CaseStore
from spinelab.models import CaseManifest
from spinelab.pipeline.contracts import StageExecutionResult
from spinelab.pipeline.stages.measurements import run_measurements_stage


def run_metrics_stage(store: CaseStore, manifest: CaseManifest) -> StageExecutionResult:
    """Legacy shim for callers that still reference the old metrics stage."""
    return run_measurements_stage(store, manifest)
