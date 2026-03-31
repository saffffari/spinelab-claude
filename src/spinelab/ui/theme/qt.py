from __future__ import annotations

from PySide6.QtGui import QColor


def qcolor_from_css(value: str) -> QColor:
    if value.startswith("rgba(") and value.endswith(")"):
        channel_values = [part.strip() for part in value[5:-1].split(",")]
        red = int(float(channel_values[0]))
        green = int(float(channel_values[1]))
        blue = int(float(channel_values[2]))
        alpha = float(channel_values[3]) if len(channel_values) > 3 else 1.0
        color = QColor(red, green, blue)
        color.setAlphaF(alpha)
        return color
    return QColor(value)


def qcolor_with_alpha(value: str, alpha: float) -> QColor:
    color = qcolor_from_css(value)
    color.setAlphaF(alpha)
    return color
