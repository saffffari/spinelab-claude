"""Windows 11 Mica/Acrylic backdrop support via DWM API.

Enables the system backdrop material on the main window so that sidebar
panels with semi-transparent backgrounds pick up the desktop wallpaper
tint, matching the native Windows 11 aesthetic.

On non-Windows platforms or pre-Win11 builds this is a silent no-op.
"""
from __future__ import annotations

import sys


def enable_mica(window_id: int) -> bool:
    """Apply Mica backdrop to a native window handle.

    Returns True if the backdrop was applied successfully.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        dwmapi = ctypes.windll.dwmapi  # type: ignore[attr-defined]

        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(window_id),
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )

        # DWMWA_SYSTEMBACKDROP_TYPE = 38
        # Values: 0=Auto, 1=None, 2=Mica, 3=Acrylic, 4=MicaAlt
        DWMWA_SYSTEMBACKDROP_TYPE = 38
        backdrop_type = ctypes.c_int(2)  # Mica
        result = dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(window_id),
            DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(backdrop_type),
            ctypes.sizeof(backdrop_type),
        )
        return result == 0
    except Exception:
        return False
