from pathlib import Path

from PySide6.QtCore import QSettings

from spinelab.segmentation.drivers import NNUNetV2SegmentationDriver, resolve_segmentation_driver
from spinelab.services import SettingsService
from spinelab.services.performance import (
    PerformanceCoordinator,
    PerformanceMode,
    ResolvedPerformancePolicy,
    RuntimeHardwareProfile,
)


def _settings_service(tmp_path: Path) -> SettingsService:
    service = SettingsService()
    service._settings = QSettings(  # pyright: ignore[reportPrivateUsage]
        str(tmp_path / "performance.ini"),
        QSettings.Format.IniFormat,
    )
    return service


def _policy(*, mode: PerformanceMode, preprocess: int, export: int) -> ResolvedPerformancePolicy:
    return ResolvedPerformancePolicy(
        name=mode.value,
        mode=mode,
        vtk_smp_backend="STDThread",
        cpu_heavy_workers=8,
        io_workers=4,
        render_workers=2,
        preview_decode_workers=3,
        lod_prewarm_workers=2,
        nnunet_preprocess_workers=preprocess,
        nnunet_export_workers=export,
        blas_threads=1,
        image_cache_budget_bytes=1024,
        raw_mesh_cache_budget_bytes=2048,
        lod_mesh_cache_budget_bytes=4096,
        active_volume_cache_budget_bytes=512,
    )


def test_performance_coordinator_defaults_to_adaptive_on_first_launch(tmp_path: Path) -> None:
    coordinator = PerformanceCoordinator(
        settings=_settings_service(tmp_path),
        hardware_profile=RuntimeHardwareProfile(
            cpu_count=24,
            total_memory_bytes=128 * 1024 * 1024 * 1024,
            platform="nt",
        ),
    )

    assert coordinator.active_mode == PerformanceMode.ADAPTIVE
    assert coordinator.active_policy.mode == PerformanceMode.ADAPTIVE


def test_performance_coordinator_restores_saved_mode_from_settings(tmp_path: Path) -> None:
    settings = _settings_service(tmp_path)
    settings.save_performance_mode("turbo")

    coordinator = PerformanceCoordinator(
        settings=settings,
        hardware_profile=RuntimeHardwareProfile(
            cpu_count=24,
            total_memory_bytes=128 * 1024 * 1024 * 1024,
            platform="nt",
        ),
    )

    assert coordinator.active_mode == PerformanceMode.TURBO
    assert coordinator.active_policy.mode == PerformanceMode.TURBO


def test_performance_coordinator_clamps_workers_to_detected_cpu_count() -> None:
    coordinator = PerformanceCoordinator(
        hardware_profile=RuntimeHardwareProfile(
            cpu_count=4,
            total_memory_bytes=64 * 1024 * 1024 * 1024,
            platform="nt",
        ),
    )

    policy = coordinator.resolve_policy(PerformanceMode.TURBO)

    assert policy.cpu_heavy_workers == 4
    assert policy.io_workers == 4
    assert policy.render_workers <= 4
    assert policy.preview_decode_workers == 4
    assert policy.lod_prewarm_workers <= 4
    assert policy.nnunet_preprocess_workers == 4
    assert policy.nnunet_export_workers == 4


def test_performance_coordinator_reuses_and_resizes_named_caches() -> None:
    coordinator = PerformanceCoordinator(
        hardware_profile=RuntimeHardwareProfile(
            cpu_count=8,
            total_memory_bytes=32 * 1024 * 1024 * 1024,
            platform="nt",
        ),
    )
    estimate_size = len

    cache = coordinator.get_cache(
        "preview-images",
        max_bytes=6,
        estimate_size=estimate_size,
    )
    cache.put("first", b"123456")

    resized_cache = coordinator.get_cache(
        "preview-images",
        max_bytes=3,
        estimate_size=estimate_size,
    )

    assert resized_cache is cache
    assert resized_cache.max_bytes == 3
    assert resized_cache.total_bytes == 0


def test_resolve_segmentation_driver_uses_runtime_policy_worker_counts() -> None:
    driver = resolve_segmentation_driver(
        "nnunetv2",
        performance_policy=_policy(
            mode=PerformanceMode.TURBO,
            preprocess=9,
            export=7,
        ),
    )

    assert isinstance(driver, NNUNetV2SegmentationDriver)
    assert driver._preprocessing_workers == 9  # pyright: ignore[reportPrivateUsage]
    assert driver._export_workers == 7  # pyright: ignore[reportPrivateUsage]
