from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RawPalette:
    green_500: str = "#53BC3A"
    blue_500: str = "#448FD4"
    red_500: str = "#FC443F"
    orange_500: str = "#FF7D34"
    yellow_500: str = "#F2BD37"
    neutral_100: str = "#B8B8B8"
    neutral_500: str = "#383838"
    neutral_700: str = "#181818"
    neutral_800: str = "#121212"
    neutral_900: str = "#0A0A0A"
    sand_300: str = "#B59E89"
    svg_asset_default: str = "#242424"


RAW_PALETTE = RawPalette()


def hex_to_rgba(hex_color: str, opacity: float) -> str:
    hex_value = hex_color.lstrip("#")
    red = int(hex_value[0:2], 16)
    green = int(hex_value[2:4], 16)
    blue = int(hex_value[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {opacity:.3f})"


def shade_hex(hex_color: str, factor: float) -> str:
    hex_value = hex_color.lstrip("#")
    red = int(int(hex_value[0:2], 16) * factor)
    green = int(int(hex_value[2:4], 16) * factor)
    blue = int(int(hex_value[4:6], 16) * factor)
    return f"#{red:02X}{green:02X}{blue:02X}"
