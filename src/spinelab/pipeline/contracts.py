from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from spinelab.models import FindingRecord, MetricRecord, PipelineArtifact, VolumeMetadata


class BackendDeviceRequirement(StrEnum):
    CPU = "cpu"
    CUDA = "cuda"
    EITHER = "either"


class PlatformMode(StrEnum):
    WINDOWS_NATIVE = "windows-native"
    WSL_ALLOWED = "wsl-allowed"


class PipelineStageName(StrEnum):
    INGEST = "ingest"
    NORMALIZE = "normalize"
    SEGMENTATION = "segmentation"
    MESH = "mesh"
    LANDMARKS = "landmarks"
    REGISTRATION = "registration"
    MEASUREMENTS = "measurements"
    METRICS = "metrics"
    FINDINGS = "findings"
    DRR = "drr"
    EXPORTS = "exports"
    VIEWER_EVIDENCE = "viewer-evidence"


@dataclass(frozen=True)
class EnvironmentSpec:
    env_id: str
    manifest_path: Path
    python_version: str
    pytorch_version: str | None = None
    cuda_version: str | None = None
    notes: str = ""


@dataclass(frozen=True)
class BackendAdapterSpec:
    tool_name: str
    environment_id: str
    required_device: BackendDeviceRequirement
    platform_mode: PlatformMode
    healthcheck_command: tuple[str, ...]
    supported_stages: tuple[PipelineStageName, ...]


@dataclass(slots=True)
class StageExecutionResult:
    stage: PipelineStageName
    status: str = "complete"
    message: str = ""
    outputs: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    artifacts: list[PipelineArtifact] = field(default_factory=list)
    metrics: list[MetricRecord] = field(default_factory=list)
    findings: list[FindingRecord] = field(default_factory=list)
    volumes: list[VolumeMetadata] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


StageRunner = Callable[..., StageExecutionResult]


@dataclass(frozen=True)
class PipelineStageSpec:
    stage: PipelineStageName
    runner: StageRunner
    dependencies: tuple[PipelineStageName, ...] = ()
    produced_artifact_types: tuple[str, ...] = ()
    review_surface: str = ""
    backend_tool: str = "internal"
    environment_id: str = "app"
    cache_scope: str = "stage"
    failure_semantics: str = "fail_closed"
    description: str = ""
