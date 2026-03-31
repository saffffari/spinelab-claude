from __future__ import annotations

from spinelab.pipeline.contracts import BackendAdapterSpec


class BackendAdapter:
    def __init__(self, spec: BackendAdapterSpec) -> None:
        self.spec = spec

    def healthcheck_command(self) -> tuple[str, ...]:
        return self.spec.healthcheck_command
