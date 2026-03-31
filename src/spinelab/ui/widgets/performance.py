from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QPushButton, QSizePolicy

from spinelab.services.performance import PerformanceMode, canonical_performance_mode
from spinelab.ui.theme import GEOMETRY, THEME_COLORS, capsule_radius, qcolor_from_css
from spinelab.ui.widgets.chrome import CapsuleButton, apply_text_role, major_button_icon_size


class TurboModeButton(CapsuleButton):
    mode_changed = Signal(str)

    _ARM_TIMEOUT_MS = 2000

    def __init__(self, mode: PerformanceMode | str = PerformanceMode.ADAPTIVE) -> None:
        super().__init__("", major=True)
        self.setObjectName("TurboModeButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._mode = canonical_performance_mode(mode)
        self._state = ""
        self._arm_timer = QTimer(self)
        self._arm_timer.setInterval(self._ARM_TIMEOUT_MS)
        self._arm_timer.setSingleShot(True)
        self._arm_timer.timeout.connect(self._handle_arm_timeout)
        self.clicked.connect(self._handle_clicked)
        self.set_mode(self._mode)

    def mode(self) -> PerformanceMode:
        return self._mode

    def state(self) -> str:
        return self._state

    def is_armed(self) -> bool:
        return self._state == "armed"

    def set_mode(self, mode: PerformanceMode | str) -> None:
        normalized = canonical_performance_mode(mode)
        if normalized == self._mode and self._state == self._state_for_mode(normalized):
            return
        self._mode = normalized
        self._cancel_armed(reset_from_mode=False)
        self._apply_state(self._state_for_mode(normalized))

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        if not enabled:
            self._cancel_armed(reset_from_mode=True)
        super().setEnabled(enabled)

    def _handle_clicked(self) -> None:
        if self._state == "idle":
            self._apply_state("armed")
            self._arm_timer.start()
            return
        if self._state == "armed":
            self._arm_timer.stop()
            self._mode = PerformanceMode.TURBO
            self._apply_state("active")
            self.mode_changed.emit(self._mode.value)
            return
        self._mode = PerformanceMode.ADAPTIVE
        self._apply_state("idle")
        self.mode_changed.emit(self._mode.value)

    def _handle_arm_timeout(self) -> None:
        if self._state != "armed":
            return
        self._apply_state(self._state_for_mode(self._mode))

    def _cancel_armed(self, *, reset_from_mode: bool) -> None:
        if self._arm_timer.isActive():
            self._arm_timer.stop()
        if reset_from_mode and self._state == "armed":
            self._apply_state(self._state_for_mode(self._mode))

    def _state_for_mode(self, mode: PerformanceMode) -> str:
        return "active" if mode == PerformanceMode.TURBO else "idle"

    def _apply_state(self, state: str) -> None:
        self._state = state
        self.setProperty("turboState", state)
        if state == "idle":
            self.setText("Arm Turbo")
            self.setToolTip(
                "First click arms Turbo. Click again within 2 seconds to activate it."
            )
            self.setAccessibleDescription(
                "Turbo performance control. First click arms Turbo. "
                "Second click within 2 seconds activates it."
            )
        elif state == "armed":
            self.setText("Activate Turbo")
            self.setToolTip("Turbo is armed. Click again within 2 seconds to activate it.")
            self.setAccessibleDescription(
                "Turbo performance control armed. Click again within 2 seconds to activate Turbo."
            )
        else:
            self.setText("Turbo Active")
            self.setToolTip("Turbo is active. Click to restore Adaptive mode.")
            self.setAccessibleDescription(
                "Turbo performance control active. Click to restore Adaptive mode."
            )
        self._refresh_style()

    def _refresh_style(self) -> None:
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self.update()


class AnalyzeProgressButton(QPushButton):
    _SPINNER_INTERVAL_MS = 16
    _SPINNER_CYCLE_MS = 1400.0
    _SPINNER_ARC_SPAN_DEGREES = 104.0
    _SPINNER_PHASE_WARP = 0.12

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self._base_text = text
        self._progress_active = False
        self._progress_fraction = 0.0
        self._progress_percent = 0
        self._spinner_visible = False
        self._spinner_active = False
        self._spinner_phase = 0.0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(self._SPINNER_INTERVAL_MS)
        self._spinner_timer.timeout.connect(self._advance_spinner)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(GEOMETRY.analyze_button_height)
        apply_text_role(self, "major-button")

    def is_busy(self) -> bool:
        return self._progress_active

    def is_spinner_active(self) -> bool:
        return self._spinner_active

    def shows_spinner(self) -> bool:
        return self._spinner_visible

    def display_text(self) -> str:
        return self._base_text

    def set_busy(self, busy: bool, *, tint: str | None = None) -> None:
        del tint
        self.set_progress(active=busy, percent=0.0 if busy else None)

    def set_progress(
        self,
        *,
        active: bool,
        percent: float | None,
        spinner_active: bool | None = None,
    ) -> None:
        self._progress_active = bool(active)
        if percent is not None:
            normalized_percent = max(0.0, min(100.0, float(percent)))
            self._progress_percent = int(round(normalized_percent))
            self._progress_fraction = normalized_percent / 100.0
        elif not active:
            self._progress_percent = 0
            self._progress_fraction = 0.0
        self._spinner_visible = self._progress_active
        self.set_spinner_active(self._progress_active if spinner_active is None else spinner_active)
        if not self._progress_active:
            self._spinner_phase = 0.0
        self.update()

    def set_spinner_active(self, active: bool) -> None:
        should_spin = bool(active) and self._spinner_visible
        if self._spinner_active == should_spin:
            return
        self._spinner_active = should_spin
        if should_spin:
            self._spinner_timer.start()
        else:
            self._spinner_timer.stop()
        self.update()

    def reset_progress(self) -> None:
        self._progress_active = False
        self._progress_percent = 0
        self._progress_fraction = 0.0
        self._spinner_visible = False
        self._spinner_active = False
        self._spinner_phase = 0.0
        self._spinner_timer.stop()
        self.update()

    def set_progress_percent(
        self,
        percent: float,
        *,
        active: bool,
        spinner_active: bool | None = None,
    ) -> None:
        self.set_progress(active=active, percent=percent, spinner_active=spinner_active)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect().adjusted(0, 0, -1, -1))
        radius = float(capsule_radius(int(rect.height())))

        show_active_palette = self.isEnabled() or self._progress_active
        track_color = qcolor_from_css(
            THEME_COLORS.info_soft if show_active_palette else THEME_COLORS.viewport_overlay
        )
        fill_color = qcolor_from_css(
            THEME_COLORS.info if show_active_palette else THEME_COLORS.text_muted
        )
        if self._progress_active:
            text_color = qcolor_from_css(THEME_COLORS.text_primary)
        elif self.isEnabled():
            text_color = qcolor_from_css(THEME_COLORS.info)
        else:
            text_color = qcolor_from_css(THEME_COLORS.text_muted)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(rect, radius, radius)

        if self._progress_active:
            fill_rect = QRectF(
                rect.left(),
                rect.top(),
                max(rect.height(), rect.width() * self._progress_fraction),
                rect.height(),
            )
            painter.setBrush(fill_color)
            painter.drawRoundedRect(fill_rect, radius, radius)

        if self.isDown():
            pressed_overlay = qcolor_from_css(THEME_COLORS.viewport_overlay)
            painter.setBrush(pressed_overlay)
            painter.drawRoundedRect(rect, radius, radius)

        painter.setPen(text_color)
        painter.setFont(self.font())

        content_rect = rect.adjusted(16.0, 0.0, -16.0, 0.0)
        icon_size = self.iconSize() if self.iconSize().isValid() else major_button_icon_size()
        show_gutter_visual = self._spinner_visible or not self.icon().isNull()
        if show_gutter_visual:
            icon_rect = QRectF(
                rect.right() - 16.0 - icon_size.width(),
                rect.center().y() - (icon_size.height() / 2.0),
                icon_size.width(),
                icon_size.height(),
            )
            if self._spinner_visible:
                self._paint_spinner(painter, icon_rect, text_color)
            else:
                self.icon().paint(
                    painter,
                    icon_rect.toRect(),
                    Qt.AlignmentFlag.AlignCenter,
                    mode=QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled,
                )
            content_rect = QRectF(
                content_rect.left(),
                content_rect.top(),
                max(0.0, icon_rect.left() - content_rect.left() - 8.0),
                content_rect.height(),
            )

        painter.drawText(
            content_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.display_text(),
        )

    def _advance_spinner(self) -> None:
        self._spinner_phase = (
            self._spinner_phase + (self._SPINNER_INTERVAL_MS / self._SPINNER_CYCLE_MS)
        ) % 1.0
        self.update()

    def _paint_spinner(self, painter: QPainter, rect: QRectF, color) -> None:
        stroke_width = max(1.75, rect.width() * 0.11)
        spinner_rect = rect.adjusted(
            stroke_width / 2.0,
            stroke_width / 2.0,
            -stroke_width / 2.0,
            -stroke_width / 2.0,
        )
        ring_color = color
        ring_color.setAlphaF(0.18)
        ring_pen = QPen(ring_color, stroke_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(ring_pen)
        painter.drawEllipse(spinner_rect)

        arc_color = color
        arc_color.setAlphaF(0.92 if self._spinner_active else 0.58)
        arc_pen = QPen(arc_color, stroke_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        start_degrees = 90.0 - (self._spinner_angle_progress(self._spinner_phase) * 360.0)
        painter.drawArc(
            spinner_rect.toRect(),
            int(round(start_degrees * 16.0)),
            int(round(-self._SPINNER_ARC_SPAN_DEGREES * 16.0)),
        )

    @classmethod
    def _spinner_angle_progress(cls, phase: float) -> float:
        normalized = max(0.0, min(1.0, float(phase)))
        return normalized - (cls._SPINNER_PHASE_WARP * math.sin(normalized * math.tau))
