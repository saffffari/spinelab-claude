from __future__ import annotations

import ctypes
import os
import threading
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, TypeVar, cast

if TYPE_CHECKING:
    from .settings_service import SettingsService

K = TypeVar("K")
V = TypeVar("V")


def gibibytes(value: int) -> int:
    return value * 1024 * 1024 * 1024


class PerformanceMode(StrEnum):
    ADAPTIVE = "adaptive"
    TURBO = "turbo"


def canonical_performance_mode(value: object | None) -> PerformanceMode:
    if isinstance(value, PerformanceMode):
        return value
    normalized = str(value or "").strip().lower()
    if normalized == PerformanceMode.TURBO.value:
        return PerformanceMode.TURBO
    return PerformanceMode.ADAPTIVE


@dataclass(frozen=True, slots=True)
class RuntimeHardwareProfile:
    cpu_count: int
    total_memory_bytes: int | None
    platform: str

    @classmethod
    def detect(cls) -> RuntimeHardwareProfile:
        return cls(
            cpu_count=max(os.cpu_count() or 1, 1),
            total_memory_bytes=_detect_total_memory_bytes(),
            platform=os.name,
        )


@dataclass(frozen=True, slots=True)
class ResolvedPerformancePolicy:
    name: str
    mode: PerformanceMode
    vtk_smp_backend: str
    cpu_heavy_workers: int
    io_workers: int
    render_workers: int
    preview_decode_workers: int
    lod_prewarm_workers: int
    nnunet_preprocess_workers: int
    nnunet_export_workers: int
    blas_threads: int
    image_cache_budget_bytes: int
    raw_mesh_cache_budget_bytes: int
    lod_mesh_cache_budget_bytes: int
    active_volume_cache_budget_bytes: int


PerformancePolicy = ResolvedPerformancePolicy
PerformanceListener = Callable[[PerformanceMode, ResolvedPerformancePolicy], None]


def workstation_policy(mode: PerformanceMode) -> ResolvedPerformancePolicy:
    if mode == PerformanceMode.TURBO:
        return ResolvedPerformancePolicy(
            name="turbo",
            mode=PerformanceMode.TURBO,
            vtk_smp_backend="STDThread",
            cpu_heavy_workers=22,
            io_workers=8,
            render_workers=3,
            preview_decode_workers=6,
            lod_prewarm_workers=3,
            nnunet_preprocess_workers=12,
            nnunet_export_workers=8,
            blas_threads=1,
            image_cache_budget_bytes=gibibytes(2),
            raw_mesh_cache_budget_bytes=gibibytes(6),
            lod_mesh_cache_budget_bytes=gibibytes(12),
            active_volume_cache_budget_bytes=gibibytes(4),
        )
    return ResolvedPerformancePolicy(
        name="adaptive",
        mode=PerformanceMode.ADAPTIVE,
        vtk_smp_backend="STDThread",
        cpu_heavy_workers=14,
        io_workers=4,
        render_workers=2,
        preview_decode_workers=3,
        lod_prewarm_workers=2,
        nnunet_preprocess_workers=6,
        nnunet_export_workers=4,
        blas_threads=1,
        image_cache_budget_bytes=gibibytes(1),
        raw_mesh_cache_budget_bytes=gibibytes(4),
        lod_mesh_cache_budget_bytes=gibibytes(8),
        active_volume_cache_budget_bytes=gibibytes(2),
    )


def workstation_max_policy() -> ResolvedPerformancePolicy:
    return workstation_policy(PerformanceMode.TURBO)


def _clamp_policy_to_hardware(
    policy: ResolvedPerformancePolicy,
    hardware_profile: RuntimeHardwareProfile,
) -> ResolvedPerformancePolicy:
    cpu_count = max(hardware_profile.cpu_count, 1)

    def clamp(requested: int, *, minimum: int = 1) -> int:
        return max(minimum, min(int(requested), cpu_count))

    return ResolvedPerformancePolicy(
        name=policy.name,
        mode=policy.mode,
        vtk_smp_backend=policy.vtk_smp_backend,
        cpu_heavy_workers=clamp(policy.cpu_heavy_workers),
        io_workers=clamp(policy.io_workers),
        render_workers=clamp(policy.render_workers),
        preview_decode_workers=clamp(policy.preview_decode_workers),
        lod_prewarm_workers=clamp(policy.lod_prewarm_workers),
        nnunet_preprocess_workers=clamp(policy.nnunet_preprocess_workers),
        nnunet_export_workers=clamp(policy.nnunet_export_workers),
        blas_threads=max(1, int(policy.blas_threads)),
        image_cache_budget_bytes=max(0, int(policy.image_cache_budget_bytes)),
        raw_mesh_cache_budget_bytes=max(0, int(policy.raw_mesh_cache_budget_bytes)),
        lod_mesh_cache_budget_bytes=max(0, int(policy.lod_mesh_cache_budget_bytes)),
        active_volume_cache_budget_bytes=max(0, int(policy.active_volume_cache_budget_bytes)),
    )


def default_performance_policy() -> ResolvedPerformancePolicy:
    return _clamp_policy_to_hardware(
        workstation_policy(PerformanceMode.ADAPTIVE),
        RuntimeHardwareProfile.detect(),
    )


@dataclass(slots=True)
class _ExecutorHandle:
    generation: int
    executor: ThreadPoolExecutor


@dataclass(slots=True)
class _CacheHandle:
    cache: object
    estimate_size: object


class PerformanceCoordinator:
    def __init__(
        self,
        *,
        settings: SettingsService | None = None,
        hardware_profile: RuntimeHardwareProfile | None = None,
    ) -> None:
        self._hardware_profile = hardware_profile or RuntimeHardwareProfile.detect()
        self._settings = settings
        self._lock = threading.RLock()
        self._listeners: set[PerformanceListener] = set()
        self._executor_generation = 0
        self._executors: dict[str, _ExecutorHandle] = {}
        self._retired_executors: list[ThreadPoolExecutor] = []
        self._caches: dict[str, _CacheHandle] = {}
        self._configured = False
        self._segmentation_slot = threading.BoundedSemaphore(1)
        initial_mode = self._load_mode_from_settings(settings)
        self._active_mode = initial_mode
        self._policy = self.resolve_policy(initial_mode)

    @property
    def hardware_profile(self) -> RuntimeHardwareProfile:
        return self._hardware_profile

    @property
    def active_mode(self) -> PerformanceMode:
        with self._lock:
            return self._active_mode

    @property
    def active_policy(self) -> ResolvedPerformancePolicy:
        with self._lock:
            return self._policy

    def attach_settings(self, settings: SettingsService | None) -> None:
        with self._lock:
            if settings is None or settings is self._settings:
                return
            self._settings = settings
            loaded_mode = self._load_mode_from_settings(settings)
            if loaded_mode == self._active_mode:
                return
            self._active_mode = loaded_mode
            self._policy = self.resolve_policy(loaded_mode)
            self._executor_generation += 1
            listeners = tuple(self._listeners)
            policy = self._policy
        for listener in listeners:
            listener(loaded_mode, policy)

    def resolve_policy(
        self,
        mode: PerformanceMode | str | None = None,
    ) -> ResolvedPerformancePolicy:
        requested_mode = canonical_performance_mode(mode)
        return _clamp_policy_to_hardware(
            workstation_policy(requested_mode),
            self._hardware_profile,
        )

    def add_listener(self, listener: PerformanceListener) -> None:
        with self._lock:
            self._listeners.add(listener)

    def remove_listener(self, listener: PerformanceListener) -> None:
        with self._lock:
            self._listeners.discard(listener)

    def set_mode(
        self,
        mode: PerformanceMode | str | None,
        *,
        persist: bool = True,
    ) -> ResolvedPerformancePolicy:
        normalized_mode = canonical_performance_mode(mode)
        with self._lock:
            if normalized_mode == self._active_mode:
                return self._policy
            self._active_mode = normalized_mode
            self._policy = self.resolve_policy(normalized_mode)
            self._executor_generation += 1
            listeners = tuple(self._listeners)
            policy = self._policy
            settings = self._settings
        if persist and settings is not None:
            settings.save_performance_mode(normalized_mode.value)
        for listener in listeners:
            listener(normalized_mode, policy)
        return policy

    def configure_runtime_environment(
        self,
        *,
        settings: SettingsService | None = None,
        mode: PerformanceMode | str | None = None,
        policy: ResolvedPerformancePolicy | None = None,
    ) -> ResolvedPerformancePolicy:
        if settings is not None:
            self.attach_settings(settings)
        resolved_policy = policy or (
            self.set_mode(mode, persist=False) if mode is not None else self.active_policy
        )
        _configure_blas_thread_env(resolved_policy.blas_threads)
        _configure_vtk_backend(resolved_policy.vtk_smp_backend)
        with self._lock:
            self._configured = True
        return resolved_policy

    def runtime_configured(self) -> bool:
        with self._lock:
            return self._configured

    def get_cache(
        self,
        name: str,
        *,
        max_bytes: int,
        estimate_size: Callable[[V], int],
    ) -> BoundedCache[K, V]:
        with self._lock:
            existing = self._caches.get(name)
            if existing is None or existing.estimate_size is not estimate_size:
                cache: BoundedCache[str, V] = BoundedCache(
                    max_bytes=max_bytes,
                    estimate_size=estimate_size,
                )
                self._caches[name] = _CacheHandle(cache=cache, estimate_size=estimate_size)
                return cast(BoundedCache[K, V], cache)
            existing_cache = cast(BoundedCache[object, object], existing.cache)
            existing_cache.resize(max_bytes)
            return cast(BoundedCache[K, V], existing_cache)

    def executor(self, kind: str) -> ThreadPoolExecutor:
        retired_executor: ThreadPoolExecutor | None = None
        with self._lock:
            generation = self._executor_generation
            existing = self._executors.get(kind)
            if existing is not None and existing.generation == generation:
                return existing.executor
            if existing is not None:
                retired_executor = existing.executor
                self._retired_executors.append(existing.executor)
            executor = ThreadPoolExecutor(
                max_workers=_executor_workers_for_kind(self._policy, kind),
                thread_name_prefix=f"spinelab-{kind}",
            )
            self._executors[kind] = _ExecutorHandle(generation=generation, executor=executor)
        if retired_executor is not None:
            retired_executor.shutdown(wait=False, cancel_futures=False)
        return executor

    def cpu_executor(self) -> ThreadPoolExecutor:
        return self.executor("cpu")

    def io_executor(self) -> ThreadPoolExecutor:
        return self.executor("io")

    def preview_executor(self) -> ThreadPoolExecutor:
        return self.executor("preview")

    def render_executor(self) -> ThreadPoolExecutor:
        return self.executor("render")

    def lod_prewarm_executor(self) -> ThreadPoolExecutor:
        return self.executor("lod-prewarm")

    @contextmanager
    def segmentation_slot(self):
        self._segmentation_slot.acquire()
        try:
            yield
        finally:
            self._segmentation_slot.release()

    def shutdown(self) -> None:
        with self._lock:
            executors = [handle.executor for handle in self._executors.values()]
            executors.extend(self._retired_executors)
            self._executors.clear()
            self._retired_executors = []
        for executor in executors:
            executor.shutdown(wait=False, cancel_futures=False)

    def _load_mode_from_settings(self, settings: SettingsService | None) -> PerformanceMode:
        if settings is None:
            return PerformanceMode.ADAPTIVE
        stored_mode = settings.load_performance_mode()
        return canonical_performance_mode(stored_mode)


_COORDINATOR: PerformanceCoordinator | None = None


def performance_coordinator(
    settings: SettingsService | None = None,
) -> PerformanceCoordinator:
    global _COORDINATOR
    if _COORDINATOR is None:
        _COORDINATOR = PerformanceCoordinator(settings=settings)
    elif settings is not None:
        _COORDINATOR.attach_settings(settings)
    return _COORDINATOR


def active_performance_mode() -> PerformanceMode:
    return performance_coordinator().active_mode


def active_performance_policy() -> ResolvedPerformancePolicy:
    return performance_coordinator().active_policy


def configure_runtime_policy(
    policy: ResolvedPerformancePolicy | None = None,
    *,
    settings: SettingsService | None = None,
    mode: PerformanceMode | str | None = None,
) -> ResolvedPerformancePolicy:
    return performance_coordinator(settings).configure_runtime_environment(
        settings=settings,
        mode=mode,
        policy=policy,
    )


def runtime_policy_configured() -> bool:
    return performance_coordinator().runtime_configured()


def reset_performance_coordinator() -> None:
    global _COORDINATOR
    if _COORDINATOR is not None:
        _COORDINATOR.shutdown()
    _COORDINATOR = None


def _executor_workers_for_kind(policy: ResolvedPerformancePolicy, kind: str) -> int:
    if kind == "cpu":
        return policy.cpu_heavy_workers
    if kind == "io":
        return policy.io_workers
    if kind == "preview":
        return policy.preview_decode_workers
    if kind == "render":
        return policy.render_workers
    if kind == "lod-prewarm":
        return policy.lod_prewarm_workers
    return policy.cpu_heavy_workers


def _configure_blas_thread_env(thread_count: int) -> None:
    normalized = str(max(1, int(thread_count)))
    for variable_name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[variable_name] = normalized


def _configure_vtk_backend(backend_name: str) -> None:
    try:
        import vtk
    except Exception:
        return
    try:
        vtk.vtkSMPTools.SetBackend(backend_name)
    except Exception:
        pass


def _detect_total_memory_bytes() -> int | None:
    if os.name != "nt":
        return None

    class _MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullTotalPhys)
    except Exception:
        return None
    return None


class BoundedCache[K, V]:
    def __init__(
        self,
        *,
        max_bytes: int,
        estimate_size: Callable[[V], int],
    ) -> None:
        self._max_bytes = max(0, int(max_bytes))
        self._estimate_size = estimate_size
        self._entries: OrderedDict[K, tuple[V, int]] = OrderedDict()
        self._total_bytes = 0
        self._lock = threading.RLock()

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    @property
    def total_bytes(self) -> int:
        with self._lock:
            return self._total_bytes

    def get(self, key: K) -> V | None:
        with self._lock:
            entry = self._entries.pop(key, None)
            if entry is None:
                return None
            self._entries[key] = entry
            return entry[0]

    def put(self, key: K, value: V) -> V:
        with self._lock:
            size_bytes = max(0, int(self._estimate_size(value)))
            existing = self._entries.pop(key, None)
            if existing is not None:
                self._total_bytes -= existing[1]
            self._entries[key] = (value, size_bytes)
            self._total_bytes += size_bytes
            self._evict_locked()
            return value

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._total_bytes = 0

    def resize(self, max_bytes: int) -> None:
        with self._lock:
            self._max_bytes = max(0, int(max_bytes))
            self._evict_locked()

    def _evict_locked(self) -> None:
        while self._entries and self._total_bytes > self._max_bytes:
            _key, (_value, size_bytes) = self._entries.popitem(last=False)
            self._total_bytes -= size_bytes
