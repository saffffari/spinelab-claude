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
    env_id="landmarkpt",
    manifest_path=Path("envs") / "landmarkpt.yml",
    python_version="3.10",
    pytorch_version="2.5.x",
    cuda_version="12.4",
    notes="LandmarkPointTransformer research sidecar with compiled sparse ops.",
)


class LandmarkPointTransformerAdapter(BackendAdapter):
    def __init__(self) -> None:
        super().__init__(
            BackendAdapterSpec(
                tool_name="landmarkpt",
                environment_id=ENVIRONMENT.env_id,
                required_device=BackendDeviceRequirement.CUDA,
                platform_mode=PlatformMode.WSL_ALLOWED,
                healthcheck_command=("python", "-c", "import pointcept"),
                supported_stages=(PipelineStageName.LANDMARKS,),
            )
        )
