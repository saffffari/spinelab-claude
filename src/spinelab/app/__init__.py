"""Application entrypoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .application import create_application

if TYPE_CHECKING:
    from .main_window import MainWindow

__all__ = ["MainWindow", "create_application"]


def __getattr__(name: str) -> Any:
    if name == "MainWindow":
        from .main_window import MainWindow

        return MainWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
