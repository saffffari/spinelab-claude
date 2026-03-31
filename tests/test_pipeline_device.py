from pathlib import Path

import spinelab.pipeline.device as device_module
from spinelab.pipeline.device import CudaGpuInfo, choose_runtime_device, windows_path_to_wsl


def test_choose_runtime_device_respects_explicit_cpu_request() -> None:
    selection = choose_runtime_device("cpu")

    assert selection.device == "cpu"
    assert selection.backend == "cpu"
    assert selection.fallback_reason == "Preferred CPU execution requested."


def test_choose_runtime_device_uses_detected_cuda_runtime(monkeypatch) -> None:
    monkeypatch.setattr(
        device_module,
        "probe_nvidia_gpu",
        lambda: CudaGpuInfo(
            gpu_name="RTX 4090",
            total_vram_mb=24564,
            driver_version="591.86",
            cuda_version="12.4",
        ),
    )

    selection = choose_runtime_device()

    assert selection.device == "cuda"
    assert selection.backend == "nvidia-cuda"
    assert selection.gpu_name == "RTX 4090"
    assert selection.total_vram_mb == 24564
    assert selection.cuda_version == "12.4"


def test_windows_path_to_wsl_maps_drive_prefix(tmp_path: Path) -> None:
    target_path = tmp_path / "nested" / "scan.nii.gz"
    target_path.parent.mkdir(parents=True)

    translated = windows_path_to_wsl(target_path)

    assert translated.startswith("/mnt/")
    assert translated.endswith("/nested/scan.nii.gz")
