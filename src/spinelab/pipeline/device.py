from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_CUDA_VERSION_PATTERN = re.compile(r"CUDA Version:\s*([0-9.]+)")


@dataclass(frozen=True)
class CudaGpuInfo:
    gpu_name: str
    total_vram_mb: int | None
    driver_version: str | None
    cuda_version: str | None


@dataclass(frozen=True)
class RuntimeDeviceSelection:
    requested_device: str
    effective_device: str
    backend: str
    cuda_version: str | None = None
    gpu_name: str | None = None
    total_vram_mb: int | None = None
    driver_version: str | None = None
    fallback_reason: str | None = None
    backend_health: dict[str, str] = field(default_factory=dict)

    @property
    def device(self) -> str:
        return self.effective_device


def _parse_query_output(stdout: str) -> tuple[str, int | None, str | None] | None:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        return None
    value_parts = [part.strip() for part in lines[0].split(",")]
    if len(value_parts) < 3:
        return None
    gpu_name, total_vram_text, driver_version = value_parts[:3]
    try:
        total_vram_mb = int(total_vram_text)
    except ValueError:
        total_vram_mb = None
    return gpu_name, total_vram_mb, driver_version or None


def _probe_cuda_runtime_version(
    executable: str,
    *,
    timeout_ms: int,
) -> str | None:
    try:
        completed = subprocess.run(
            [executable],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    match = _CUDA_VERSION_PATTERN.search(completed.stdout)
    if match is None:
        return None
    return match.group(1).strip() or None


def probe_nvidia_gpu(timeout_ms: int = 3000) -> CudaGpuInfo | None:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return None
    try:
        completed = subprocess.run(
            [
                executable,
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    parsed = _parse_query_output(completed.stdout)
    if parsed is None:
        return None
    gpu_name, total_vram_mb, driver_version = parsed
    return CudaGpuInfo(
        gpu_name=gpu_name,
        total_vram_mb=total_vram_mb,
        driver_version=driver_version,
        cuda_version=_probe_cuda_runtime_version(executable, timeout_ms=timeout_ms),
    )


def choose_runtime_device(preferred_device: str | None = None) -> RuntimeDeviceSelection:
    normalized_preference = (preferred_device or "auto").strip().lower() or "auto"
    if normalized_preference == "cpu":
        return RuntimeDeviceSelection(
            requested_device="cpu",
            effective_device="cpu",
            backend="cpu",
            fallback_reason="Preferred CPU execution requested.",
            backend_health={"status": "preferred-cpu"},
        )

    executable = shutil.which("nvidia-smi")
    if executable is None:
        fallback_reason = "No CUDA-capable NVIDIA runtime detected."
        if normalized_preference == "cuda":
            fallback_reason = (
                "Preferred CUDA execution requested, but no NVIDIA runtime was detected."
            )
        return RuntimeDeviceSelection(
            requested_device=normalized_preference,
            effective_device="cpu",
            backend="cpu",
            fallback_reason=fallback_reason,
            backend_health={"status": "nvidia-smi-missing"},
        )

    gpu = probe_nvidia_gpu()
    if gpu is None:
        fallback_reason = "No CUDA-capable NVIDIA runtime detected."
        if normalized_preference == "cuda":
            fallback_reason = (
                "Preferred CUDA execution requested, but the NVIDIA runtime probe failed."
            )
        return RuntimeDeviceSelection(
            requested_device=normalized_preference,
            effective_device="cpu",
            backend="cpu",
            fallback_reason=fallback_reason,
            backend_health={"status": "probe-failed", "probe": Path(executable).name},
        )

    return RuntimeDeviceSelection(
        requested_device=normalized_preference,
        effective_device="cuda",
        backend="nvidia-cuda",
        cuda_version=gpu.cuda_version,
        gpu_name=gpu.gpu_name,
        total_vram_mb=gpu.total_vram_mb,
        driver_version=gpu.driver_version,
        backend_health={"status": "ready", "probe": Path(executable).name},
    )


def supports_wsl() -> bool:
    return shutil.which("wsl.exe") is not None


def windows_path_to_wsl(path: Path) -> str:
    resolved = Path(path).resolve()
    drive = resolved.drive.rstrip(":").lower()
    relative_path = resolved.as_posix().split(":/", 1)[-1]
    return f"/mnt/{drive}/{relative_path}"
