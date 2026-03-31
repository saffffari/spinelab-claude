"""Application services."""

from .performance import (
    BoundedCache,
    PerformanceCoordinator,
    PerformanceMode,
    PerformancePolicy,
    ResolvedPerformancePolicy,
    RuntimeHardwareProfile,
    active_performance_mode,
    active_performance_policy,
    canonical_performance_mode,
    configure_runtime_policy,
    performance_coordinator,
    reset_performance_coordinator,
    runtime_policy_configured,
    workstation_max_policy,
)
from .render_backend import (
    RenderBackendProbe,
    classify_render_backend,
    clear_render_backend_probe_cache,
    current_qt_platform_name,
    probe_render_backend,
    should_enforce_hardware_rendering,
)
from .settings_service import SettingsService

__all__ = [
    "BoundedCache",
    "PerformanceCoordinator",
    "PerformanceMode",
    "PerformancePolicy",
    "RenderBackendProbe",
    "ResolvedPerformancePolicy",
    "RuntimeHardwareProfile",
    "SettingsService",
    "active_performance_mode",
    "active_performance_policy",
    "canonical_performance_mode",
    "classify_render_backend",
    "configure_runtime_policy",
    "clear_render_backend_probe_cache",
    "current_qt_platform_name",
    "performance_coordinator",
    "probe_render_backend",
    "reset_performance_coordinator",
    "runtime_policy_configured",
    "should_enforce_hardware_rendering",
    "workstation_max_policy",
]
