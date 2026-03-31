"""Backend pipeline contracts, orchestration, stage registry, and GUI-facing helpers."""

from .contracts import (
    BackendAdapterSpec,
    BackendDeviceRequirement,
    EnvironmentSpec,
    PipelineStageName,
    PipelineStageSpec,
    PlatformMode,
    StageExecutionResult,
)
from .device import RuntimeDeviceSelection, choose_runtime_device, probe_nvidia_gpu
from .manifest_bridge import import_review_summary, latest_completed_run
from .orchestrator import (
    ANALYSIS_STAGE_SEQUENCE,
    AnalysisProgressEvent,
    AnalysisProgressUpdate,
    PipelineOrchestrator,
)
from .stage_registry import DEFAULT_ANALYSIS_SEQUENCE, STAGE_SPECS

__all__ = [
    "ANALYSIS_STAGE_SEQUENCE",
    "AnalysisProgressEvent",
    "AnalysisProgressUpdate",
    "BackendAdapterSpec",
    "BackendDeviceRequirement",
    "DEFAULT_ANALYSIS_SEQUENCE",
    "EnvironmentSpec",
    "PipelineStageSpec",
    "PipelineOrchestrator",
    "PipelineStageName",
    "PlatformMode",
    "RuntimeDeviceSelection",
    "STAGE_SPECS",
    "StageExecutionResult",
    "choose_runtime_device",
    "import_review_summary",
    "latest_completed_run",
    "probe_nvidia_gpu",
]
