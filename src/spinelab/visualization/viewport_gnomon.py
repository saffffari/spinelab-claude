from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from spinelab.ui.theme import GEOMETRY, THEME_COLORS, qcolor_from_css, qcolor_with_alpha

GNOMON_VIEWPORT = (0.02, 0.02, 0.18, 0.18)
GNOMON_LINE_WIDTH = 2
GNOMON_MARGIN = GEOMETRY.overlay_padding
GNOMON_BUBBLE_DIAMETER = 18.0
GNOMON_OVERLAY_SIZE = max(
    GEOMETRY.control_height_sm * 2 + GEOMETRY.unit * 4,
    GEOMETRY.unit * 10,
)


@dataclass(frozen=True)
class PlanarGnomonSpec:
    horizontal_negative: str
    horizontal_positive: str
    vertical_negative: str
    vertical_positive: str
    horizontal_color: str
    vertical_color: str


@dataclass(frozen=True)
class SpatialGnomonAxis:
    label: str
    color: str
    endpoint: tuple[float, float]


PLANAR_GNOMON_SPECS: dict[str, PlanarGnomonSpec] = {
    "ap": PlanarGnomonSpec(
        horizontal_negative="R",
        horizontal_positive="L",
        vertical_negative="I",
        vertical_positive="S",
        horizontal_color=THEME_COLORS.axis_y,
        vertical_color=THEME_COLORS.axis_z,
    ),
    "lat": PlanarGnomonSpec(
        horizontal_negative="P",
        horizontal_positive="A",
        vertical_negative="I",
        vertical_positive="S",
        horizontal_color=THEME_COLORS.axis_x,
        vertical_color=THEME_COLORS.axis_z,
    ),
    "axial": PlanarGnomonSpec(
        horizontal_negative="R",
        horizontal_positive="L",
        vertical_negative="P",
        vertical_positive="A",
        horizontal_color=THEME_COLORS.axis_y,
        vertical_color=THEME_COLORS.axis_x,
    ),
}

SPATIAL_GNOMON_AXES: tuple[SpatialGnomonAxis, ...] = (
    SpatialGnomonAxis("S", THEME_COLORS.axis_z, (0.0, -1.0)),
    SpatialGnomonAxis("L", THEME_COLORS.axis_y, (0.92, 0.46)),
    SpatialGnomonAxis("A", THEME_COLORS.axis_x, (-0.92, 0.46)),
)


def planar_gnomon_spec(view_kind: str) -> PlanarGnomonSpec:
    return PLANAR_GNOMON_SPECS.get(view_kind, PLANAR_GNOMON_SPECS["ap"])


def configure_plotter_gnomon(plotter: Any) -> Any:
    return plotter.add_axes(
        x_color=THEME_COLORS.axis_x,
        y_color=THEME_COLORS.axis_y,
        z_color=THEME_COLORS.axis_z,
        labels_off=True,
        line_width=GNOMON_LINE_WIDTH,
        viewport=GNOMON_VIEWPORT,
    )


def position_gnomon_overlay(widget: QWidget, surface: QWidget | None) -> None:
    if surface is None:
        return
    widget.adjustSize()
    size = widget.size()
    if not size.isValid() or size.isEmpty():
        size = widget.sizeHint().expandedTo(widget.minimumSizeHint())
    widget.setGeometry(
        surface.x() + GNOMON_MARGIN,
        surface.y() + max(surface.height() - size.height() - GNOMON_MARGIN, 0),
        size.width(),
        size.height(),
    )


class ViewportGnomonOverlay(QWidget):
    def __init__(self, parent: QWidget | None = None, *, view_kind: str = "ap") -> None:
        super().__init__(parent)
        self.setObjectName("ViewportGnomon")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(GNOMON_OVERLAY_SIZE, GNOMON_OVERLAY_SIZE)
        self._view_kind = view_kind
        self._spec = planar_gnomon_spec(view_kind)

    @property
    def spec(self) -> PlanarGnomonSpec:
        return self._spec

    def set_view_kind(self, view_kind: str) -> None:
        self._view_kind = view_kind
        next_spec = planar_gnomon_spec(view_kind)
        if next_spec == self._spec:
            if view_kind == "3d":
                self.update()
            return
        self._spec = next_spec
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._view_kind == "3d":
            self._paint_spatial_gnomon(painter)
            painter.end()
            return

        bubble_diameter = GNOMON_BUBBLE_DIAMETER
        bubble_radius = bubble_diameter / 2.0
        margin = float(GEOMETRY.unit)
        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        left_x = margin + bubble_radius
        right_x = self.width() - margin - bubble_radius
        top_y = margin + bubble_radius
        bottom_y = self.height() - margin - bubble_radius

        horizontal_pen = QPen(qcolor_from_css(self._spec.horizontal_color))
        horizontal_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        horizontal_pen.setWidth(GNOMON_LINE_WIDTH)
        painter.setPen(horizontal_pen)
        painter.drawLine(
            QPointF(left_x + bubble_radius + GEOMETRY.unit / 2.0, center.y()),
            QPointF(right_x - bubble_radius - GEOMETRY.unit / 2.0, center.y()),
        )

        vertical_pen = QPen(qcolor_from_css(self._spec.vertical_color))
        vertical_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        vertical_pen.setWidth(GNOMON_LINE_WIDTH)
        painter.setPen(vertical_pen)
        painter.drawLine(
            QPointF(center.x(), bottom_y - bubble_radius - GEOMETRY.unit / 2.0),
            QPointF(center.x(), top_y + bubble_radius + GEOMETRY.unit / 2.0),
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor_from_css(THEME_COLORS.text_primary))
        painter.drawEllipse(center, 2.5, 2.5)

        bubble_font = QFont(painter.font())
        bubble_font.setBold(True)
        bubble_font.setPointSizeF(max(8.0, bubble_font.pointSizeF() or 8.0))
        painter.setFont(bubble_font)

        self._draw_bubble(
            painter,
            QRectF(
                left_x - bubble_radius,
                center.y() - bubble_radius,
                bubble_diameter,
                bubble_diameter,
            ),
            self._spec.horizontal_negative,
            self._spec.horizontal_color,
        )
        self._draw_bubble(
            painter,
            QRectF(
                right_x - bubble_radius,
                center.y() - bubble_radius,
                bubble_diameter,
                bubble_diameter,
            ),
            self._spec.horizontal_positive,
            self._spec.horizontal_color,
        )
        self._draw_bubble(
            painter,
            QRectF(
                center.x() - bubble_radius,
                top_y - bubble_radius,
                bubble_diameter,
                bubble_diameter,
            ),
            self._spec.vertical_positive,
            self._spec.vertical_color,
        )
        self._draw_bubble(
            painter,
            QRectF(
                center.x() - bubble_radius,
                bottom_y - bubble_radius,
                bubble_diameter,
                bubble_diameter,
            ),
            self._spec.vertical_negative,
            self._spec.vertical_color,
        )
        painter.end()

    def _paint_spatial_gnomon(self, painter: QPainter) -> None:
        bubble_diameter = GNOMON_BUBBLE_DIAMETER
        bubble_radius = bubble_diameter / 2.0
        center = QPointF(self.width() * 0.42, self.height() * 0.58)
        axis_length = min(self.width(), self.height()) * 0.30

        center_pen = QPen(qcolor_from_css(THEME_COLORS.text_primary))
        center_pen.setWidth(1)
        painter.setPen(center_pen)
        painter.setBrush(qcolor_from_css(THEME_COLORS.text_primary))
        painter.drawEllipse(center, 2.5, 2.5)

        for axis in SPATIAL_GNOMON_AXES:
            color = qcolor_from_css(axis.color)
            direction_x, direction_y = axis.endpoint
            end = QPointF(
                center.x() + direction_x * axis_length,
                center.y() + direction_y * axis_length,
            )
            line_end = QPointF(
                center.x() + direction_x * max(axis_length - bubble_radius - GEOMETRY.unit, 0.0),
                center.y() + direction_y * max(axis_length - bubble_radius - GEOMETRY.unit, 0.0),
            )
            pen = QPen(color)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setWidth(GNOMON_LINE_WIDTH)
            painter.setPen(pen)
            painter.drawLine(center, line_end)
            self._draw_bubble(
                painter,
                QRectF(
                    end.x() - bubble_radius,
                    end.y() - bubble_radius,
                    bubble_diameter,
                    bubble_diameter,
                ),
                axis.label,
                axis.color,
            )

    def _draw_bubble(
        self,
        painter: QPainter,
        rect: QRectF,
        text: str,
        color: str,
    ) -> None:
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor_with_alpha(color, 0.22))
        painter.drawEllipse(rect)
        painter.setPen(qcolor_from_css(THEME_COLORS.text_primary))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()
