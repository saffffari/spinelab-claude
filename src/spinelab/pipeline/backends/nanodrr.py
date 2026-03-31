from __future__ import annotations

from pathlib import Path

from spinelab.pipeline.backends.base import BackendAdapter
from spinelab.pipeline.contracts import (
    BackendAdapterSpec,
    BackendDeviceRequirement,
    EnvironmentSpec,
    PipelineStageName,
    PlatformMode,
)

ENVIRONMENT = EnvironmentSpec(
    env_id="nanodrr",
    manifest_path=Path("envs") / "nanodrr.yml",
    python_version="3.10",
    pytorch_version="2.5.x",
    cuda_version="12.4",
    notes="PyTorch-based DRR rendering sidecar.",
)


class NanoDrrAdapter(BackendAdapter):
    def __init__(self) -> None:
        super().__init__(
            BackendAdapterSpec(
                tool_name="nanodrr",
                environment_id=ENVIRONMENT.env_id,
                required_device=BackendDeviceRequirement.EITHER,
                platform_mode=PlatformMode.WINDOWS_NATIVE,
                healthcheck_command=("python", "-c", "import nanodrr; print(nanodrr.__version__)"),
                supported_stages=(PipelineStageName.DRR,),
            )
        )
