from __future__ import annotations

from dataclasses import dataclass

from .palette import RAW_PALETTE, hex_to_rgba, shade_hex


@dataclass(frozen=True)
class ThemeColors:
    shell_bg: str
    shell_elevated: str
    panel_bg: str
    panel_inner_bg: str
    sidebar_bg: str
    text_primary: str
    text_secondary: str
    text_muted: str
    border_soft: str
    focus: str
    focus_soft: str
    focus_reference: str
    focus_reference_soft: str
    success: str
    success_soft: str
    warning: str
    warning_soft: str
    warning_strong: str
    warning_strong_soft: str
    info: str
    info_soft: str
    danger: str
    danger_soft: str
    adaptive_track: str
    adaptive_handle: str
    turbo_track: str
    turbo_track_soft: str
    turbo_handle: str
    turbo_glow: str
    viewport_bg: str
    viewport_empty_bg: str
    viewport_overlay: str
    scrollbar_thumb: str
    scrollbar_track: str
    axis_x: str
    axis_y: str
    axis_z: str


THEME_COLORS = ThemeColors(
    shell_bg=RAW_PALETTE.neutral_900,
    shell_elevated=RAW_PALETTE.neutral_800,
    panel_bg=hex_to_rgba(RAW_PALETTE.neutral_800, 0.85),
    panel_inner_bg="transparent",
    sidebar_bg=hex_to_rgba(RAW_PALETTE.neutral_800, 0.85),
    text_primary=RAW_PALETTE.neutral_100,
    text_secondary=hex_to_rgba(RAW_PALETTE.neutral_100, 0.78),
    text_muted=hex_to_rgba(RAW_PALETTE.neutral_100, 0.60),
    border_soft=hex_to_rgba(RAW_PALETTE.neutral_100, 0.07),
    focus=RAW_PALETTE.orange_500,
    focus_soft=hex_to_rgba(RAW_PALETTE.orange_500, 0.20),
    focus_reference=shade_hex(RAW_PALETTE.orange_500, 0.82),
    focus_reference_soft=hex_to_rgba(shade_hex(RAW_PALETTE.orange_500, 0.82), 0.24),
    success=RAW_PALETTE.green_500,
    success_soft=hex_to_rgba(RAW_PALETTE.green_500, 0.20),
    warning=RAW_PALETTE.yellow_500,
    warning_soft=hex_to_rgba(RAW_PALETTE.yellow_500, 0.20),
    warning_strong=RAW_PALETTE.orange_500,
    warning_strong_soft=hex_to_rgba(RAW_PALETTE.orange_500, 0.20),
    info=RAW_PALETTE.blue_500,
    info_soft=hex_to_rgba(RAW_PALETTE.blue_500, 0.20),
    danger=RAW_PALETTE.red_500,
    danger_soft=hex_to_rgba(RAW_PALETTE.red_500, 0.20),
    adaptive_track=hex_to_rgba(RAW_PALETTE.neutral_100, 0.08),
    adaptive_handle=shade_hex(RAW_PALETTE.neutral_100, 0.85),
    turbo_track=hex_to_rgba(RAW_PALETTE.red_500, 0.34),
    turbo_track_soft=hex_to_rgba(RAW_PALETTE.red_500, 0.16),
    turbo_handle=RAW_PALETTE.red_500,
    turbo_glow=hex_to_rgba(RAW_PALETTE.red_500, 0.14),
    viewport_bg=RAW_PALETTE.neutral_900,
    viewport_empty_bg=RAW_PALETTE.neutral_900,
    viewport_overlay=hex_to_rgba(RAW_PALETTE.neutral_100, 0.06),
    scrollbar_thumb=hex_to_rgba(RAW_PALETTE.neutral_100, 0.18),
    scrollbar_track="transparent",
    axis_x=RAW_PALETTE.red_500,
    axis_y=RAW_PALETTE.green_500,
    axis_z=RAW_PALETTE.blue_500,
)
