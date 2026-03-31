from __future__ import annotations

import ctypes
import os
import re
import sys
from ctypes import wintypes
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from PySide6.QtWidgets import QApplication, QWidget

pv: Any
try:
    import pyvista as pv
except ImportError:  # pragma: no cover - local runtime guard
    pv = None

qt_interactor_cls: Any = None
try:
    from pyvistaqt import QtInteractor as _QtInteractor
except ImportError:  # pragma: no cover - local runtime guard
    pass
else:
    qt_interactor_cls = _QtInteractor

_SOFTWARE_RENDER_TOKENS = (
    "mesa",
    "gallium",
    "llvmpipe",
    "softpipe",
    "software rasterizer",
)
_SOFTWARE_MODULE_NAMES = {
    "libgallium_wgl.dll",
    "opengl32sw.dll",
}
_OPENGL_MODULE_PATTERNS = (
    "opengl32.dll",
    "opengl32sw.dll",
    "libgallium_wgl.dll",
    "nvoglv",
    "nvd3dum",
)
_CAPABILITY_PATTERNS = {
    "vendor": re.compile(r"OpenGL vendor string:\s*(.+)"),
    "renderer": re.compile(r"OpenGL renderer string:\s*(.+)"),
    "version": re.compile(r"OpenGL version string:\s*(.+)"),
}


@dataclass(frozen=True)
class RenderBackendProbe:
    classification: str
    backend_class: str
    opengl_vendor: str
    opengl_renderer: str
    opengl_version: str
    render_window_class: str
    loaded_module_paths: tuple[str, ...]
    hardware_ok: bool
    failure_reason: str | None

    def footer_text(self, *, enforce_hardware: bool) -> str:
        if self.hardware_ok:
            label = (
                self.opengl_renderer
                or self.opengl_vendor
                or self.backend_class
                or "Hardware OpenGL"
            )
            return f"Renderer: {label}"
        if not enforce_hardware:
            return "Renderer: offscreen/test mode"
        if self.classification == "software":
            return "Renderer: software OpenGL blocked"
        return "Renderer: hardware OpenGL unconfirmed"

    def footer_state(self, *, enforce_hardware: bool) -> str:
        if self.hardware_ok:
            return "ok"
        if not enforce_hardware:
            return "inactive"
        if self.classification == "software":
            return "blocked"
        return "unknown"

    def viewport_message(self) -> str:
        reason = self.failure_reason or "SpineLab could not confirm a hardware OpenGL renderer."
        if reason.endswith("."):
            return f"Interactive 3D disabled. {reason}"
        return f"Interactive 3D disabled. {reason}."

    def warning_text(self) -> str:
        reason = self.failure_reason or "SpineLab could not confirm a hardware OpenGL renderer."
        return (
            "SpineLab detected a non-hardware OpenGL backend for this desktop runtime.\n\n"
            f"{reason}\n\n"
            "Interactive 3D viewports will stay disabled until the app starts on a "
            "native hardware renderer."
        )


def current_qt_platform_name() -> str:
    app = cast(QApplication | None, QApplication.instance())
    if app is not None:
        try:
            platform_name = str(app.platformName()).strip().lower()
        except Exception:
            platform_name = ""
        if platform_name:
            return platform_name
    return os.environ.get("QT_QPA_PLATFORM", "").strip().lower()


def should_enforce_hardware_rendering() -> bool:
    if current_qt_platform_name() in {"offscreen", "minimal"}:
        return False
    app = cast(QApplication | None, QApplication.instance())
    argv = app.arguments() if app is not None else sys.argv
    return "--smoke-test" not in argv


def clear_render_backend_probe_cache() -> None:
    probe_render_backend.cache_clear()


@lru_cache(maxsize=1)
def probe_render_backend() -> RenderBackendProbe:
    return _probe_render_backend_uncached()


def classify_render_backend(
    *,
    backend_class: str,
    opengl_vendor: str,
    opengl_renderer: str,
    opengl_version: str,
    render_window_class: str,
    loaded_module_paths: tuple[str, ...],
    supports_opengl: bool = True,
) -> RenderBackendProbe:
    normalized_backend = backend_class.strip()
    normalized_vendor = opengl_vendor.strip()
    normalized_renderer = opengl_renderer.strip()
    normalized_version = opengl_version.strip()
    normalized_window_class = render_window_class.strip()
    normalized_paths = tuple(
        str(Path(path).resolve(strict=False)) if path else ""
        for path in loaded_module_paths
        if path
    )
    searchable_text = " ".join(
        (
            normalized_backend,
            normalized_window_class,
            normalized_vendor,
            normalized_renderer,
            normalized_version,
        )
    ).lower()

    if not supports_opengl:
        return RenderBackendProbe(
            classification="unknown",
            backend_class=normalized_backend,
            opengl_vendor=normalized_vendor,
            opengl_renderer=normalized_renderer,
            opengl_version=normalized_version,
            render_window_class=normalized_window_class,
            loaded_module_paths=normalized_paths,
            hardware_ok=False,
            failure_reason="VTK reported that the render window does not support OpenGL.",
        )

    software_module = next(
        (
            path
            for path in normalized_paths
            if Path(path).name.lower() in _SOFTWARE_MODULE_NAMES
        ),
        None,
    )
    if software_module is not None:
        return RenderBackendProbe(
            classification="software",
            backend_class=normalized_backend,
            opengl_vendor=normalized_vendor,
            opengl_renderer=normalized_renderer,
            opengl_version=normalized_version,
            render_window_class=normalized_window_class,
            loaded_module_paths=normalized_paths,
            hardware_ok=False,
            failure_reason=(
                f"Loaded software OpenGL module {Path(software_module).name} "
                "from the desktop app environment."
            ),
        )

    env_local_opengl = next(
        (
            path
            for path in normalized_paths
            if Path(path).name.lower() == "opengl32.dll" and _is_env_local_opengl_path(path)
        ),
        None,
    )
    if env_local_opengl is not None:
        return RenderBackendProbe(
            classification="software",
            backend_class=normalized_backend,
            opengl_vendor=normalized_vendor,
            opengl_renderer=normalized_renderer,
            opengl_version=normalized_version,
            render_window_class=normalized_window_class,
            loaded_module_paths=normalized_paths,
            hardware_ok=False,
            failure_reason=(
                "Resolved OPENGL32.dll from the Conda environment instead of the "
                "system OpenGL driver path."
            ),
        )

    if any(token in searchable_text for token in _SOFTWARE_RENDER_TOKENS):
        return RenderBackendProbe(
            classification="software",
            backend_class=normalized_backend,
            opengl_vendor=normalized_vendor,
            opengl_renderer=normalized_renderer,
            opengl_version=normalized_version,
            render_window_class=normalized_window_class,
            loaded_module_paths=normalized_paths,
            hardware_ok=False,
            failure_reason="VTK reported a software OpenGL renderer.",
        )

    if not normalized_window_class:
        return RenderBackendProbe(
            classification="unknown",
            backend_class=normalized_backend,
            opengl_vendor=normalized_vendor,
            opengl_renderer=normalized_renderer,
            opengl_version=normalized_version,
            render_window_class=normalized_window_class,
            loaded_module_paths=normalized_paths,
            hardware_ok=False,
            failure_reason="VTK did not expose an OpenGL render window.",
        )

    if not normalized_vendor or not normalized_renderer:
        return RenderBackendProbe(
            classification="unknown",
            backend_class=normalized_backend,
            opengl_vendor=normalized_vendor,
            opengl_renderer=normalized_renderer,
            opengl_version=normalized_version,
            render_window_class=normalized_window_class,
            loaded_module_paths=normalized_paths,
            hardware_ok=False,
            failure_reason="VTK did not report a usable OpenGL vendor and renderer.",
        )

    return RenderBackendProbe(
        classification="hardware",
        backend_class=normalized_backend,
        opengl_vendor=normalized_vendor,
        opengl_renderer=normalized_renderer,
        opengl_version=normalized_version,
        render_window_class=normalized_window_class,
        loaded_module_paths=normalized_paths,
        hardware_ok=True,
        failure_reason=None,
    )


def _probe_render_backend_uncached() -> RenderBackendProbe:
    loaded_module_paths = _loaded_relevant_module_paths()
    app = cast(QApplication | None, QApplication.instance())
    if app is None:
        return classify_render_backend(
            backend_class="",
            opengl_vendor="",
            opengl_renderer="",
            opengl_version="",
            render_window_class="",
            loaded_module_paths=loaded_module_paths,
            supports_opengl=False,
        )

    if qt_interactor_cls is None or pv is None:
        return classify_render_backend(
            backend_class="",
            opengl_vendor="",
            opengl_renderer="",
            opengl_version="",
            render_window_class="",
            loaded_module_paths=loaded_module_paths,
            supports_opengl=False,
        )

    host = QWidget()
    plotter = None
    supports_opengl = True
    backend_class = ""
    render_window_class = ""
    opengl_vendor = ""
    opengl_renderer = ""
    opengl_version = ""
    try:
        plotter = qt_interactor_cls(host)
        render_window = getattr(plotter, "ren_win", None) or getattr(
            plotter, "render_window", None
        )
        render_window_class = type(render_window).__name__ if render_window is not None else ""
        if render_window is not None and hasattr(render_window, "SupportsOpenGL"):
            try:
                supports_opengl = bool(render_window.SupportsOpenGL())
            except Exception:
                supports_opengl = True
        if render_window is not None and hasattr(render_window, "GetRenderingBackend"):
            try:
                backend_class = str(render_window.GetRenderingBackend() or "")
            except Exception:
                backend_class = ""
        if render_window is not None and hasattr(render_window, "ReportCapabilities"):
            try:
                capabilities = str(render_window.ReportCapabilities() or "")
            except Exception:
                capabilities = ""
            opengl_vendor, opengl_renderer, opengl_version = _parse_capabilities(capabilities)
        loaded_module_paths = _loaded_relevant_module_paths()
    except Exception as exc:
        return RenderBackendProbe(
            classification="unknown",
            backend_class=backend_class,
            opengl_vendor=opengl_vendor,
            opengl_renderer=opengl_renderer,
            opengl_version=opengl_version,
            render_window_class=render_window_class,
            loaded_module_paths=loaded_module_paths,
            hardware_ok=False,
            failure_reason=f"Renderer probe failed: {exc}",
        )
    finally:
        if plotter is not None:
            try:
                plotter.close()
            except Exception:
                pass
            try:
                plotter.deleteLater()
            except Exception:
                pass
        host.deleteLater()

    return classify_render_backend(
        backend_class=backend_class,
        opengl_vendor=opengl_vendor,
        opengl_renderer=opengl_renderer,
        opengl_version=opengl_version,
        render_window_class=render_window_class,
        loaded_module_paths=loaded_module_paths,
        supports_opengl=supports_opengl,
    )


def _parse_capabilities(report: str) -> tuple[str, str, str]:
    values: dict[str, str] = {}
    for key, pattern in _CAPABILITY_PATTERNS.items():
        match = pattern.search(report)
        values[key] = match.group(1).strip() if match is not None else ""
    return values["vendor"], values["renderer"], values["version"]


def _loaded_relevant_module_paths() -> tuple[str, ...]:
    if sys.platform != "win32":
        return ()
    all_paths = _enumerate_loaded_module_paths_windows()
    relevant_paths = [
        path
        for path in all_paths
        if _is_relevant_opengl_module_name(Path(path).name.lower())
    ]
    unique_paths = dict.fromkeys(relevant_paths)
    return tuple(unique_paths)


def _is_relevant_opengl_module_name(module_name: str) -> bool:
    return any(pattern in module_name for pattern in _OPENGL_MODULE_PATTERNS)


def _is_env_local_opengl_path(path: str) -> bool:
    normalized_path = str(Path(path).resolve(strict=False)).lower()
    prefixes = [
        str(Path(candidate).resolve(strict=False)).lower()
        for candidate in {sys.prefix, os.environ.get("CONDA_PREFIX", "")}
        if candidate
    ]
    if not prefixes:
        return False
    return any(
        normalized_path == prefix
        or normalized_path.startswith(f"{prefix}\\")
        or normalized_path.startswith(f"{prefix}/")
        for prefix in prefixes
    )


def _enumerate_loaded_module_paths_windows() -> tuple[str, ...]:
    process_handle = ctypes.windll.kernel32.GetCurrentProcess()
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    enum_modules = psapi.EnumProcessModulesEx
    enum_modules.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.HMODULE),
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.DWORD,
    ]
    enum_modules.restype = wintypes.BOOL

    get_module_file_name = psapi.GetModuleFileNameExW
    get_module_file_name.argtypes = [
        wintypes.HANDLE,
        wintypes.HMODULE,
        wintypes.LPWSTR,
        wintypes.DWORD,
    ]
    get_module_file_name.restype = wintypes.DWORD

    list_modules_all = 0x03
    needed = wintypes.DWORD()
    module_count = 256
    while True:
        module_array = (wintypes.HMODULE * module_count)()
        success = enum_modules(
            process_handle,
            module_array,
            ctypes.sizeof(module_array),
            ctypes.byref(needed),
            list_modules_all,
        )
        if not success:
            error_code = kernel32.GetLastError()
            raise OSError(error_code, "EnumProcessModulesEx failed")
        required = int(needed.value // ctypes.sizeof(wintypes.HMODULE))
        if required <= module_count:
            break
        module_count = required + 32

    resolved_paths: list[str] = []
    for module_handle in module_array[:required]:
        buffer = ctypes.create_unicode_buffer(32768)
        length = get_module_file_name(process_handle, module_handle, buffer, len(buffer))
        if length <= 0:
            continue
        resolved_paths.append(buffer.value)
    return tuple(resolved_paths)
