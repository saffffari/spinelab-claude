from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from spinelab.ui.theme import RAW_PALETTE, THEME_COLORS
from spinelab.ui.theme.palette import shade_hex


class ViewportMode(StrEnum):
    SOLID = "solid"
    TRANSPARENT = "transparent"
    WIRE = "wire"
    POINTS = "points"


@dataclass(frozen=True)
class ViewportRenderMode:
    opacity: float
    show_edges: bool
    style: str
    point_size: int
    edge_width: int
    lighting: bool
    smooth_shading: bool


@dataclass(frozen=True)
class MeshVisualColors:
    fill: str
    edge: str


VIEWPORT_MODES = {
    ViewportMode.SOLID: ViewportRenderMode(
        opacity=1.0,
        show_edges=False,
        style="surface",
        point_size=10,
        edge_width=1,
        lighting=True,
        smooth_shading=True,
    ),
    ViewportMode.TRANSPARENT: ViewportRenderMode(
        opacity=0.48,
        show_edges=True,
        style="surface",
        point_size=10,
        edge_width=2,
        lighting=True,
        smooth_shading=True,
    ),
    ViewportMode.WIRE: ViewportRenderMode(
        opacity=1.0,
        show_edges=True,
        style="wireframe",
        point_size=10,
        edge_width=2,
        lighting=False,
        smooth_shading=False,
    ),
    ViewportMode.POINTS: ViewportRenderMode(
        opacity=1.0,
        show_edges=False,
        style="points",
        point_size=8,
        edge_width=2,
        lighting=False,
        smooth_shading=False,
    ),
}

MODEL_BASE_COLOR = shade_hex(RAW_PALETTE.neutral_100, 0.82)
MODEL_BASE_EDGE_COLOR = shade_hex(RAW_PALETTE.neutral_900, 1.35)
MODEL_SELECTED_COLOR = shade_hex(RAW_PALETTE.orange_500, 0.84)
MODEL_SELECTED_EDGE_COLOR = shade_hex(RAW_PALETTE.orange_500, 0.9)
MODEL_REFERENCE_COLOR = shade_hex(RAW_PALETTE.orange_500, 0.94)
MODEL_REFERENCE_EDGE_COLOR = shade_hex(RAW_PALETTE.orange_500, 0.78)
MODEL_STANDING_COLOR = shade_hex(RAW_PALETTE.neutral_100, 0.70)
MODEL_STANDING_EDGE_COLOR = shade_hex(RAW_PALETTE.neutral_900, 1.15)
MODEL_STANDING_SELECTED_COLOR = MODEL_SELECTED_COLOR
MODEL_STANDING_SELECTED_EDGE_COLOR = MODEL_SELECTED_EDGE_COLOR
MODEL_STANDING_REFERENCE_COLOR = MODEL_REFERENCE_COLOR
MODEL_STANDING_REFERENCE_EDGE_COLOR = MODEL_REFERENCE_EDGE_COLOR
VIEWPORT_BACKGROUND = THEME_COLORS.viewport_bg
VIEWPORT_GRID_MINOR_COLOR = shade_hex(RAW_PALETTE.neutral_900, 1.8)
VIEWPORT_GRID_MAJOR_COLOR = shade_hex(RAW_PALETTE.neutral_900, 2.3)


def resolve_mesh_visual_colors(
    pose_name: str | None,
    *,
    selected: bool,
    reference: bool,
) -> MeshVisualColors:
    if pose_name == "standing":
        if reference:
            return MeshVisualColors(
                MODEL_STANDING_REFERENCE_COLOR,
                MODEL_STANDING_REFERENCE_EDGE_COLOR,
            )
        if selected:
            return MeshVisualColors(
                MODEL_STANDING_SELECTED_COLOR,
                MODEL_STANDING_SELECTED_EDGE_COLOR,
            )
        return MeshVisualColors(MODEL_STANDING_COLOR, MODEL_STANDING_EDGE_COLOR)

    if reference:
        return MeshVisualColors(MODEL_REFERENCE_COLOR, MODEL_REFERENCE_EDGE_COLOR)
    if selected:
        return MeshVisualColors(MODEL_SELECTED_COLOR, MODEL_SELECTED_EDGE_COLOR)
    return MeshVisualColors(MODEL_BASE_COLOR, MODEL_BASE_EDGE_COLOR)


def resolve_mode_edge_color(
    mode: ViewportMode,
    edge_color: str,
    *,
    active: bool,
    reference: bool,
) -> str:
    if mode == ViewportMode.SOLID and not active and not reference:
        return MODEL_BASE_EDGE_COLOR
    return edge_color
