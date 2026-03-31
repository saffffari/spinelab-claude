from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineEvent:
    run_id: str
    stage: str
    status: str
    message: str
    progress: float | None = None
