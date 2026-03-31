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
    env_id="skellytour-win",
    manifest_path=Path("envs") / "skellytour.yml",
    python_version="3.10",
    pytorch_version="2.5.x",
    cuda_version=None,
    notes=(
        "Local SkellyTour high-label CT baseline used only for qualitative "
        "segmentation comparison."
    ),
)


class SkellyTourAdapter(BackendAdapter):
    def __init__(self) -> None:
        super().__init__(
            BackendAdapterSpec(
                tool_name="skellytour",
                environment_id=ENVIRONMENT.env_id,
                required_device=BackendDeviceRequirement.EITHER,
                platform_mode=PlatformMode.WINDOWS_NATIVE,
                healthcheck_command=(
                    "python",
                    "-c",
                    (
                        "from spinelab.segmentation.bundles import "
                        "_detect_skellytour_version, _resolve_skellytour_executable; "
                        "import sys; "
                        "executable = _resolve_skellytour_executable(); "
                        "sys.stdout.write(_detect_skellytour_version() if executable else ''); "
                        "raise SystemExit(0 if executable else 1)"
                    ),
                ),
                supported_stages=(PipelineStageName.SEGMENTATION,),
            )
        )
