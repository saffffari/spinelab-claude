"""Viewport components."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "ImageViewport2D": ("spinelab.visualization.viewer_2d", "ImageViewport2D"),
    "XrayProjection": ("spinelab.visualization.viewer_2d", "XrayProjection"),
    "ZStackViewport2D": ("spinelab.visualization.viewer_2d", "ZStackViewport2D"),
    "OrthographicMeshViewport": (
        "spinelab.visualization.viewer_3d",
        "OrthographicMeshViewport",
    ),
    "SpineViewport3D": ("spinelab.visualization.viewer_3d", "SpineViewport3D"),
    "VolumeViewport3D": ("spinelab.visualization.viewer_volume", "VolumeViewport3D"),
    "VIEWPORT_MODES": ("spinelab.visualization.viewport_theme", "VIEWPORT_MODES"),
    "ViewportMode": ("spinelab.visualization.viewport_theme", "ViewportMode"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    module = import_module(module_name)
    return getattr(module, attribute_name)
