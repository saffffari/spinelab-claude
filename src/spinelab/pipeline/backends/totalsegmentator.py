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
    env_id="totalsegmentator-win",
    manifest_path=Path("envs") / "totalsegmentator_win.yml",
    python_version="3.12",
    pytorch_version=None,
    cuda_version=None,
    notes=(
        "Local Windows TotalSegmentator baseline runtime used only for qualitative "
        "segmentation comparison."
    ),
)


class TotalSegmentatorAdapter(BackendAdapter):
    def __init__(self) -> None:
        super().__init__(
            BackendAdapterSpec(
                tool_name="totalsegmentator",
                environment_id=ENVIRONMENT.env_id,
                required_device=BackendDeviceRequirement.EITHER,
                platform_mode=PlatformMode.WINDOWS_NATIVE,
                healthcheck_command=(
                    "python",
                    "-c",
                    (
                        "from spinelab.segmentation.bundles import "
                        "_detect_totalsegmentator_version, _resolve_totalsegmentator_executable; "
                        "import sys; "
                        "executable = _resolve_totalsegmentator_executable(); "
                        "version = _detect_totalsegmentator_version() if executable else ''; "
                        "sys.stdout.write(version); "
                        "raise SystemExit(0 if executable else 1)"
                    ),
                ),
                supported_stages=(PipelineStageName.SEGMENTATION,),
            )
        )
