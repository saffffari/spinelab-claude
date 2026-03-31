from __future__ import annotations

from math import cos, pi, sin

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from spinelab.ui.theme import (
    GEOMETRY,
    RAW_PALETTE,
    THEME_COLORS,
    TYPOGRAPHY,
    capsule_radius,
    qcolor_from_css,
    qcolor_with_alpha,
)
from spinelab.ui.widgets import CapsuleButton, apply_text_role
from spinelab.workspaces.report_model import KpiCardData, RegionalSummaryData, VertebraTrendSeries

AXIS_LABEL_FONT_SIZE = 11


def parse_color(value: str) -> QColor:
    return qcolor_from_css(value)


def translucent(color_value: str, alpha: float) -> QColor:
    return qcolor_with_alpha(color_value, alpha)


def smooth_path(points: list[QPointF]) -> QPainterPath:
    path = QPainterPath()
    if not points:
        return path
    path.moveTo(points[0])
    if len(points) == 1:
        return path
    for index in range(1, len(points)):
        previous = points[index - 1]
        current = points[index]
        midpoint_x = (previous.x() + current.x()) / 2
        control_a = QPointF(midpoint_x, previous.y())
        control_b = QPointF(midpoint_x, current.y())
        path.cubicTo(control_a, control_b, current)
    return path


def draw_chart_axis_labels(
    painter: QPainter,
    plot_rect: QRectF,
    *,
    x_label: str,
    y_label: str,
) -> None:
    painter.save()
    painter.setFont(TYPOGRAPHY.create_font(AXIS_LABEL_FONT_SIZE, TYPOGRAPHY.weight_regular))
    painter.setPen(parse_color(THEME_COLORS.text_muted))

    x_label_rect = QRectF(
        plot_rect.left(),
        plot_rect.bottom() + (GEOMETRY.unit * 2),
        plot_rect.width(),
        GEOMETRY.unit * 2,
    )
    painter.drawText(
        x_label_rect,
        int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
        x_label,
    )

    y_label_rect = QRectF(
        plot_rect.left() - (GEOMETRY.unit * 5),
        plot_rect.top(),
        GEOMETRY.unit * 3,
        plot_rect.height(),
    )
    painter.translate(y_label_rect.left(), y_label_rect.bottom())
    painter.rotate(-90)
    painter.drawText(
        QRectF(0.0, 0.0, y_label_rect.height(), y_label_rect.width()),
        int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
        y_label,
    )
    painter.restore()


class MetricFilterChip(CapsuleButton):
    metric_toggled = Signal(str, bool)

    def __init__(self, metric_key: str, label: str, accent_color: str) -> None:
        super().__init__(label, checkable=True)
        self._metric_key = metric_key
        self._accent_color = accent_color
        self.setChecked(True)
        self.setFixedHeight(GEOMETRY.control_height_sm)
        self.toggled.connect(self._handle_toggled)
        self._apply_style()

    def _handle_toggled(self, checked: bool) -> None:
        self._apply_style()
        self.metric_toggled.emit(self._metric_key, checked)

    def _apply_style(self) -> None:
        accent = parse_color(self._accent_color)
        base = translucent(self._accent_color, 0.16 if self.isChecked() else 0.06)
        text = accent.name()
        muted_text = translucent(self._accent_color, 0.74).name(QColor.NameFormat.HexArgb)
        radius = capsule_radius(GEOMETRY.control_height_sm)
        self.setStyleSheet(
            f"""
            QPushButton {{
                background: {base.name(QColor.NameFormat.HexArgb)};
                color: {text if self.isChecked() else muted_text};
                border: 0;
                border-radius: {radius}px;
                padding-left: {GEOMETRY.unit * 2}px;
                padding-right: {GEOMETRY.unit * 2}px;
            }}
            QPushButton:hover {{
                background: {translucent(self._accent_color, 0.22).name(QColor.NameFormat.HexArgb)};
            }}
            """
        )


class GlowSparklineWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._values: tuple[float, ...] = ()
        self._accent_color = THEME_COLORS.focus
        self.setMinimumHeight(GEOMETRY.unit * 7)

    def set_data(self, values: tuple[float, ...], accent_color: str) -> None:
        self._values = values
        self._accent_color = accent_color
        self.update()

    def paintEvent(self, event) -> None:  # pragma: no cover - paint path
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(GEOMETRY.unit, GEOMETRY.unit, -GEOMETRY.unit, -GEOMETRY.unit)
        if rect.width() <= 0 or rect.height() <= 0:
            return

        values = self._values or (0.0, 0.0, 0.0, 0.0)
        min_value = min(values)
        max_value = max(values)
        span = max(max_value - min_value, 1e-6)
        points: list[QPointF] = []
        step = rect.width() / max(len(values) - 1, 1)
        for index, value in enumerate(values):
            x = rect.left() + (index * step)
            y = rect.bottom() - ((value - min_value) / span) * rect.height()
            points.append(QPointF(x, y))

        line_pen = QPen(parse_color(self._accent_color), GEOMETRY.unit // 2)
        line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(line_pen)
        painter.drawPath(smooth_path(points))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(parse_color(self._accent_color))
        marker_radius = max(GEOMETRY.unit // 4, 2)
        for point in points:
            painter.drawEllipse(point, marker_radius, marker_radius)


class KpiCardWidget(QFrame):
    def __init__(self, card: KpiCardData) -> None:
        super().__init__()
        self._card = card
        self.setObjectName("ReportKpiCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(GEOMETRY.viewport_min // 2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
        )
        layout.setSpacing(GEOMETRY.unit)

        title_label = QLabel(card.title)
        apply_text_role(title_label, "meta")
        layout.addWidget(title_label)

        value_row = QHBoxLayout()
        value_row.setContentsMargins(0, 0, 0, 0)
        value_row.setSpacing(GEOMETRY.unit)

        self._value_label = QLabel(card.value_text)
        apply_text_role(self._value_label, "metric-large", display=True)
        value_row.addWidget(self._value_label)
        value_row.addStretch(1)

        self._delta_label = QLabel(card.delta_text)
        apply_text_role(self._delta_label, "body-emphasis")
        value_row.addWidget(self._delta_label)
        layout.addLayout(value_row)

        self._caption_label = QLabel(card.caption_text)
        apply_text_role(self._caption_label, "meta")
        self._caption_label.setWordWrap(True)
        layout.addWidget(self._caption_label)

        self._sparkline = GlowSparklineWidget()
        self._sparkline.set_data(card.spark_values, card.accent_color)
        layout.addWidget(self._sparkline)

    def paintEvent(self, event) -> None:  # pragma: no cover - paint path
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(0, 0, -1, -1)
        radius = GEOMETRY.radius_inner

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(parse_color(THEME_COLORS.viewport_overlay))
        painter.drawRoundedRect(rect, radius, radius)

        glow_rect = rect.adjusted(GEOMETRY.unit, GEOMETRY.unit * 3, -GEOMETRY.unit, -GEOMETRY.unit)
        painter.setBrush(translucent(self._card.accent_color, 0.10))
        painter.drawRoundedRect(glow_rect, radius, radius)
        super().paintEvent(event)


class TrendChartWidget(QFrame):
    vertebra_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ReportChartCard")
        self.setMinimumHeight(GEOMETRY.viewport_min + (GEOMETRY.unit * 6))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._vertebrae: tuple[str, ...] = ()
        self._series: tuple[VertebraTrendSeries, ...] = ()
        self._active_metric_keys: tuple[str, ...] = ()
        self._selected_vertebra_id: str | None = None

    def set_chart_data(
        self,
        vertebrae: tuple[str, ...],
        series: tuple[VertebraTrendSeries, ...],
    ) -> None:
        self._vertebrae = vertebrae
        self._series = series
        self.update()

    def set_active_metric_keys(self, metric_keys: tuple[str, ...]) -> None:
        self._active_metric_keys = metric_keys
        self.update()

    def set_selected_vertebra(self, vertebra_id: str | None) -> None:
        self._selected_vertebra_id = vertebra_id
        self.update()

    def _active_series(self) -> list[VertebraTrendSeries]:
        if not self._active_metric_keys:
            return []
        return [series for series in self._series if series.key in self._active_metric_keys]

    def _plot_rect(self) -> QRectF:
        return QRectF(
            GEOMETRY.unit * 7,
            GEOMETRY.unit * 3,
            max(self.width() - (GEOMETRY.unit * 10), 1),
            max(self.height() - (GEOMETRY.unit * 13), 1),
        )

    def axis_labels(self) -> tuple[str, str]:
        return ("Vertebral Level (ID)", "Relative Motion (mm)")

    def _index_for_position(self, point_x: float) -> int | None:
        if not self._vertebrae:
            return None
        plot_rect = self._plot_rect()
        if point_x < plot_rect.left() or point_x > plot_rect.right():
            return None
        step = plot_rect.width() / max(len(self._vertebrae) - 1, 1)
        return int(
            max(
                0,
                min(
                    len(self._vertebrae) - 1,
                    round((point_x - plot_rect.left()) / step),
                ),
            )
        )

    def mousePressEvent(self, event) -> None:
        index = self._index_for_position(event.position().x())
        if index is None:
            self.vertebra_requested.emit("")
            return
        self.vertebra_requested.emit(self._vertebrae[index])

    def paintEvent(self, event) -> None:  # pragma: no cover - paint path
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(0, 0, -1, -1)
        radius = GEOMETRY.radius_inner
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(parse_color(THEME_COLORS.viewport_overlay))
        painter.drawRoundedRect(rect, radius, radius)

        plot_rect = self._plot_rect()
        x_label, y_label = self.axis_labels()
        draw_chart_axis_labels(painter, plot_rect, x_label=x_label, y_label=y_label)
        active_series = self._active_series()
        if not self._vertebrae or not active_series:
            draw_empty_chart_state(painter, plot_rect, "No pose comparison data")
            return

        visible_values = [value for series in active_series for value in series.values]
        min_value = min(visible_values)
        max_value = max(visible_values)
        if min_value == max_value:
            min_value -= 1.0
            max_value += 1.0
        value_span = max_value - min_value

        grid_pen = QPen(translucent(RAW_PALETTE.neutral_100, 0.12), 1)
        painter.setPen(grid_pen)
        grid_count = 4
        for index in range(grid_count + 1):
            y = plot_rect.top() + (plot_rect.height() * index / grid_count)
            painter.drawLine(QPointF(plot_rect.left(), y), QPointF(plot_rect.right(), y))

        baseline_value = 0.0 if min_value <= 0.0 <= max_value else min_value
        baseline_y = plot_rect.bottom() - (
            ((baseline_value - min_value) / value_span) * plot_rect.height()
        )
        baseline_pen = QPen(translucent(THEME_COLORS.text_primary, 0.16), GEOMETRY.unit // 3)
        painter.setPen(baseline_pen)
        painter.drawLine(
            QPointF(plot_rect.left(), baseline_y),
            QPointF(plot_rect.right(), baseline_y),
        )

        step = plot_rect.width() / max(len(self._vertebrae) - 1, 1)
        selected_index = (
            self._vertebrae.index(self._selected_vertebra_id)
            if self._selected_vertebra_id in self._vertebrae
            else None
        )
        if selected_index is not None:
            selected_x = plot_rect.left() + (selected_index * step)
            painter.setPen(QPen(translucent(THEME_COLORS.focus, 0.28), GEOMETRY.unit // 3))
            painter.drawLine(
                QPointF(selected_x, plot_rect.top()),
                QPointF(selected_x, plot_rect.bottom()),
            )

        for series in active_series:
            points: list[QPointF] = []
            for index, value in enumerate(series.values):
                x = plot_rect.left() + (index * step)
                y = plot_rect.bottom() - ((value - min_value) / value_span) * plot_rect.height()
                points.append(QPointF(x, y))

            path = smooth_path(points)
            line_pen = QPen(parse_color(series.color), GEOMETRY.unit // 2)
            line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(line_pen)
            painter.drawPath(path)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(parse_color(series.color))
            marker_radius = max(GEOMETRY.unit // 3, 3)
            for index, point in enumerate(points):
                radius = marker_radius + 1 if index == selected_index else marker_radius
                painter.drawEllipse(point, radius, radius)

        axis_font = TYPOGRAPHY.create_font(11, TYPOGRAPHY.weight_regular)
        painter.setFont(axis_font)
        painter.setPen(parse_color(THEME_COLORS.text_muted))
        label_step = max(1, len(self._vertebrae) // 8)
        for index, vertebra_id in enumerate(self._vertebrae):
            if index % label_step != 0 and vertebra_id != self._selected_vertebra_id:
                continue
            x = plot_rect.left() + (index * step)
            painter.drawText(
                QRectF(
                    x - (GEOMETRY.unit * 2),
                    plot_rect.bottom() + GEOMETRY.unit,
                    GEOMETRY.unit * 4,
                    GEOMETRY.unit * 2,
                ),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                vertebra_id,
            )


class RegionalBarChartWidget(QFrame):
    region_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ReportChartCard")
        self.setMinimumHeight(GEOMETRY.viewport_min)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._summaries: tuple[RegionalSummaryData, ...] = ()
        self._selected_region_id: str | None = None

    def set_summaries(self, summaries: tuple[RegionalSummaryData, ...]) -> None:
        self._summaries = summaries
        self.update()

    def set_selected_region(self, region_id: str | None) -> None:
        self._selected_region_id = region_id
        self.update()

    def _row_rects(self) -> list[tuple[str, QRectF]]:
        content = QRectF(
            GEOMETRY.unit * 6,
            GEOMETRY.unit * 3,
            max(self.width() - (GEOMETRY.unit * 8), 1),
            max(self.height() - (GEOMETRY.unit * 9), 1),
        )
        row_height = content.height() / max(len(self._summaries), 1)
        rects: list[tuple[str, QRectF]] = []
        for index, summary in enumerate(self._summaries):
            rects.append(
                (
                    summary.region_id,
                    QRectF(
                        content.left(),
                        content.top() + (index * row_height),
                        content.width(),
                        row_height,
                    ),
                )
            )
        return rects

    def axis_labels(self) -> tuple[str, str]:
        return ("Motion Magnitude (mm)", "Spinal Region (region)")

    def mousePressEvent(self, event) -> None:
        point = event.position()
        for region_id, row_rect in self._row_rects():
            if row_rect.contains(point):
                self.region_requested.emit(region_id)
                return
        self.region_requested.emit("")

    def paintEvent(self, event) -> None:  # pragma: no cover - paint path
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(0, 0, -1, -1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(parse_color(THEME_COLORS.viewport_overlay))
        painter.drawRoundedRect(rect, GEOMETRY.radius_inner, GEOMETRY.radius_inner)

        row_rects = self._row_rects()
        plot_rect = (
            QRectF(
                row_rects[0][1].left(),
                row_rects[0][1].top(),
                row_rects[0][1].width(),
                row_rects[-1][1].bottom() - row_rects[0][1].top(),
            )
            if row_rects
            else QRectF(
                GEOMETRY.unit * 6,
                GEOMETRY.unit * 3,
                max(self.width() - (GEOMETRY.unit * 8), 1),
                max(self.height() - (GEOMETRY.unit * 9), 1),
            )
        )
        x_label, y_label = self.axis_labels()
        draw_chart_axis_labels(painter, plot_rect, x_label=x_label, y_label=y_label)

        if not self._summaries:
            draw_empty_chart_state(painter, QRectF(rect), "No regional motion data")
            return

        max_total = max(summary.total_magnitude for summary in self._summaries)
        painter.setFont(TYPOGRAPHY.create_font(12, TYPOGRAPHY.weight_regular))
        for summary, (_, row_rect) in zip(self._summaries, row_rects, strict=False):
            label_rect = QRectF(
                row_rect.left(),
                row_rect.top(),
                row_rect.width() * 0.30,
                row_rect.height(),
            )
            painter.setPen(parse_color(THEME_COLORS.text_secondary))
            painter.drawText(
                label_rect,
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                summary.label,
            )

            bar_rect = QRectF(
                row_rect.left() + (row_rect.width() * 0.34),
                row_rect.top() + GEOMETRY.unit,
                row_rect.width() * 0.48,
                row_rect.height() - (GEOMETRY.unit * 2),
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(translucent(THEME_COLORS.text_primary, 0.06))
            painter.drawRoundedRect(bar_rect, GEOMETRY.radius_inner, GEOMETRY.radius_inner)

            fill_ratio = summary.total_magnitude / max(max_total, 1e-6)
            segment_count = 6
            segment_gap = GEOMETRY.unit // 2
            segment_width = (bar_rect.width() - (segment_gap * (segment_count - 1))) / segment_count
            filled_segments = max(1, round(fill_ratio * segment_count))
            for index in range(segment_count):
                segment_rect = QRectF(
                    bar_rect.left() + (index * (segment_width + segment_gap)),
                    bar_rect.top(),
                    segment_width,
                    bar_rect.height(),
                )
                active = index < filled_segments
                color = summary.color if active else THEME_COLORS.text_muted
                painter.setBrush(translucent(color, 0.18 if active else 0.06))
                radius = capsule_radius(int(segment_rect.height()))
                painter.drawRoundedRect(segment_rect, radius, radius)
                if active:
                    glow_pen = QPen(translucent(summary.color, 0.18), GEOMETRY.unit)
                    painter.setPen(glow_pen)
                    painter.drawRoundedRect(segment_rect, radius, radius)
                    painter.setPen(Qt.PenStyle.NoPen)

            value_rect = QRectF(
                row_rect.right() - (row_rect.width() * 0.16),
                row_rect.top(),
                row_rect.width() * 0.16,
                row_rect.height(),
            )
            value_color = (
                summary.color
                if summary.region_id == self._selected_region_id
                else THEME_COLORS.text_primary
            )
            painter.setPen(parse_color(value_color))
            painter.drawText(
                value_rect,
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                f"{summary.total_magnitude:.1f}",
            )


class RadialSummaryWidget(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ReportChartCard")
        self.setMinimumHeight(GEOMETRY.viewport_min)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._summaries: tuple[RegionalSummaryData, ...] = ()
        self._title = "Regional Motion"

    def set_summaries(self, summaries: tuple[RegionalSummaryData, ...]) -> None:
        self._summaries = summaries
        self.update()

    def axis_labels(self) -> tuple[str, str]:
        return ("Regional Distribution (region)", "Motion Magnitude (mm)")

    def paintEvent(self, event) -> None:  # pragma: no cover - paint path
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(0, 0, -1, -1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(parse_color(THEME_COLORS.viewport_overlay))
        painter.drawRoundedRect(rect, GEOMETRY.radius_inner, GEOMETRY.radius_inner)

        chart_rect = QRectF(
            GEOMETRY.unit * 6,
            GEOMETRY.unit * 3,
            max(self.width() - (GEOMETRY.unit * 8), 1),
            max(self.height() - (GEOMETRY.unit * 9), 1),
        )
        x_label, y_label = self.axis_labels()
        draw_chart_axis_labels(painter, chart_rect, x_label=x_label, y_label=y_label)

        if not self._summaries:
            draw_empty_chart_state(painter, QRectF(rect), "No regional balance yet")
            return

        center = QPointF(chart_rect.center())
        outer_radius = min(chart_rect.width(), chart_rect.height()) * 0.24
        inner_radius = outer_radius * 0.66
        total_magnitude = sum(summary.total_magnitude for summary in self._summaries)
        dot_count = 28

        painter.setPen(QPen(translucent(THEME_COLORS.text_primary, 0.08), 1))
        painter.drawLine(
            QPointF(chart_rect.left(), center.y()),
            QPointF(chart_rect.right(), center.y()),
        )
        painter.drawLine(
            QPointF(center.x(), chart_rect.top()),
            QPointF(center.x(), chart_rect.bottom()),
        )

        for ring_index, radius in enumerate((outer_radius, inner_radius)):
            summaries = self._summaries if ring_index == 0 else tuple(reversed(self._summaries))
            running_angle = -pi / 2
            for summary in summaries:
                proportion = summary.total_magnitude / max(total_magnitude, 1e-6)
                steps = max(2, round(proportion * dot_count))
                angle_step = (2 * pi) / dot_count
                for step_index in range(steps):
                    angle = running_angle + (step_index * angle_step)
                    point = QPointF(
                        center.x() + cos(angle) * radius,
                        center.y() + sin(angle) * radius,
                    )
                    fill = parse_color(summary.color)
                    fill.setAlphaF(0.86 if ring_index == 0 else 0.52)
                    painter.setBrush(fill)
                    painter.drawEllipse(point, GEOMETRY.unit // 1.6, GEOMETRY.unit // 1.6)
                running_angle += steps * angle_step

        painter.setPen(parse_color(THEME_COLORS.text_primary))
        painter.setFont(TYPOGRAPHY.create_font(18, TYPOGRAPHY.weight_light, display=True))
        painter.drawText(
            QRectF(
                center.x() - (GEOMETRY.unit * 10),
                center.y() - (GEOMETRY.unit * 4),
                GEOMETRY.unit * 20,
                GEOMETRY.unit * 4,
            ),
            int(Qt.AlignmentFlag.AlignCenter),
            f"{total_magnitude:.1f}",
        )
        painter.setFont(TYPOGRAPHY.create_font(12, TYPOGRAPHY.weight_regular))
        painter.setPen(parse_color(THEME_COLORS.text_muted))
        painter.drawText(
            QRectF(
                center.x() - (GEOMETRY.unit * 10),
                center.y() + GEOMETRY.unit,
                GEOMETRY.unit * 20,
                GEOMETRY.unit * 3,
            ),
            int(Qt.AlignmentFlag.AlignCenter),
            self._title,
        )


def draw_empty_chart_state(painter: QPainter, rect: QRectF, text: str) -> None:
    painter.setFont(TYPOGRAPHY.create_font(12, TYPOGRAPHY.weight_regular))
    painter.setPen(parse_color(THEME_COLORS.text_muted))
    painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)
