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
from spinelab.segmentation import DEFAULT_NNUNET_CONDA_ENV_NAME

ENVIRONMENT = EnvironmentSpec(
    env_id="cads-nnunet-win",
    manifest_path=Path("envs") / "cads_nnunet_win.yml",
    python_version="3.10",
    pytorch_version="2.5.1",
    cuda_version="12.4",
    notes="Local Windows nnU-Net v2 sidecar for CADS composite segmentation.",
)


class NnUNetV2Adapter(BackendAdapter):
    def __init__(self) -> None:
        super().__init__(
            BackendAdapterSpec(
                tool_name="nnunetv2",
                environment_id=ENVIRONMENT.env_id,
                required_device=BackendDeviceRequirement.EITHER,
                platform_mode=PlatformMode.WINDOWS_NATIVE,
                healthcheck_command=(
                    "conda",
                    "run",
                    "-n",
                    DEFAULT_NNUNET_CONDA_ENV_NAME,
                    "python",
                    "-c",
                    "import nnunetv2",
                ),
                supported_stages=(PipelineStageName.SEGMENTATION,),
            )
        )
