from __future__ import annotations

from dataclasses import dataclass


def concentric_radius(parent_radius: int, inset: int = 8, minimum: int = 10) -> int:
    return max(minimum, parent_radius - inset)


def capsule_radius(height: int) -> int:
    return max(10, height // 2)


@dataclass(frozen=True)
class GeometryTokens:
    unit: int = 8
    default_padding: int = 8
    inspector_gap: int = 8
    inspector_row_gap: int = 4
    sidebar_section_gap: int = 4
    sidebar_section_min: int = 88
    header_padding_y: int = 2
    footer_padding_y: int = 6
    header_control_height: int = 28
    control_height_sm: int = 28
    control_height_md: int = 36
    control_height_lg: int = 44
    turbo_slider_height: int = 56
    turbo_button_width: int = 80
    toolbar_control_size: int = 24
    major_button_height: int = 44
    radius_window: int = 12
    radius_panel: int = 12
    radius_inner: int = 8
    splitter_handle: int = 6
    overlay_gap: int = 8
    overlay_slider_width: int = 96
    inspector_preview_width: int = 268
    inspector_preview_height: int = 264
    asset_thumbnail_size: int = 56
    analyze_button_height: int = 88
    sidebar_min: int = 248
    inspector_min: int = 288
    viewport_min: int = 320

    @property
    def panel_padding(self) -> int:
        return 12

    @property
    def inspector_padding(self) -> int:
        return self.default_padding

    @property
    def viewport_padding(self) -> int:
        return self.default_padding

    @property
    def viewport_gap(self) -> int:
        return 6

    @property
    def overlay_padding(self) -> int:
        return self.default_padding

    @property
    def radius_nested(self) -> int:
        return concentric_radius(self.radius_inner, self.default_padding)


GEOMETRY = GeometryTokens()
