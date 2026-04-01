from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QFont


@dataclass(frozen=True)
class TextStyle:
    point_size: int
    line_height: int
    weight: int


@dataclass(frozen=True)
class TypographyTokens:
    family_text: str
    family_display: str
    family_fallback: str
    weight_light: int
    weight_semilight: int
    weight_semibold: int
    weight_regular: int

    def create_font(self, size: int, weight: int, display: bool = False) -> QFont:
        font = QFont(self.family_display if display else self.family_text)
        font.setPointSize(size)
        font.setWeight(QFont.Weight(weight))
        return font


TYPOGRAPHY = TypographyTokens(
    family_text="Segoe UI Variable Text",
    family_display="Segoe UI Variable Display",
    family_fallback="Segoe UI Variable, Segoe UI, system-ui, sans-serif",
    weight_light=300,
    weight_semilight=350,
    weight_semibold=500,
    weight_regular=400,
)

TEXT_STYLES = {
    "header-brand": TextStyle(13, 18, TYPOGRAPHY.weight_semibold),
    "header-text": TextStyle(13, 18, TYPOGRAPHY.weight_regular),
    "header-meta": TextStyle(13, 18, TYPOGRAPHY.weight_regular),
    "workspace-title": TextStyle(20, 26, TYPOGRAPHY.weight_semilight),
    "panel-title": TextStyle(14, 20, TYPOGRAPHY.weight_semibold),
    "section-label": TextStyle(12, 16, TYPOGRAPHY.weight_regular),
    "body": TextStyle(13, 18, TYPOGRAPHY.weight_regular),
    "body-emphasis": TextStyle(13, 18, TYPOGRAPHY.weight_semilight),
    "major-button": TextStyle(13, 18, TYPOGRAPHY.weight_semibold),
    "meta": TextStyle(12, 16, TYPOGRAPHY.weight_regular),
    "micro": TextStyle(11, 14, TYPOGRAPHY.weight_regular),
    "metric-large": TextStyle(28, 32, TYPOGRAPHY.weight_light),
}
