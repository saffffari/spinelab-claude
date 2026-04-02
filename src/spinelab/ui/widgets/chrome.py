from __future__ import annotations

import math

from PySide6.QtCore import QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
    QStyleOptionToolButton,
    QStylePainter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from spinelab.services import SettingsService
from spinelab.ui.theme import (
    GEOMETRY,
    TEXT_STYLES,
    THEME_COLORS,
    TYPOGRAPHY,
    capsule_radius,
    qcolor_from_css,
)
from spinelab.ui.widgets.splitters import TransparentSplitter


def apply_text_role(
    widget: QLabel | QPushButton | QToolButton,
    role: str,
    *,
    display: bool = False,
) -> None:
    style = TEXT_STYLES[role]
    font = TYPOGRAPHY.create_font(style.point_size, style.weight, display=display)
    widget.setFont(font)
    widget.setProperty("role", role)


def major_button_icon_size() -> QSize:
    line_height = TEXT_STYLES["major-button"].line_height
    return QSize(line_height, line_height)


class CapsuleButton(QPushButton):
    def __init__(
        self,
        text: str,
        *,
        variant: str = "ghost",
        checkable: bool = False,
        major: bool = False,
    ) -> None:
        super().__init__(text)
        self._major = major
        self._pop_progress = 0.0
        self._busy = False
        self._busy_phase = 0
        self._busy_tint: str | None = None
        self._updating_busy_icon = False
        self._base_icon = QIcon()
        self._base_icon_size = QSize()

        self._pop_animation = QVariantAnimation(self)
        self._pop_animation.setDuration(180)
        self._pop_animation.setStartValue(0.0)
        self._pop_animation.setEndValue(1.0)
        self._pop_animation.valueChanged.connect(self._handle_pop_value_changed)
        self._pop_animation.finished.connect(self._finish_pop_animation)

        self._busy_timer = QTimer(self)
        self._busy_timer.setInterval(90)
        self._busy_timer.timeout.connect(self._advance_busy_spinner)

        self.setCheckable(checkable)
        self.setProperty("variant", variant)
        self.setProperty("majorButton", major)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(
            GEOMETRY.major_button_height if major else GEOMETRY.control_height_md
        )
        apply_text_role(self, "major-button" if major else "body-emphasis")
        if major:
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.pressed.connect(self._play_pop_animation)

    def setIcon(self, icon: QIcon | QPixmap) -> None:  # noqa: N802
        if not self._updating_busy_icon:
            self._base_icon = icon if isinstance(icon, QIcon) else QIcon(icon)
        super().setIcon(icon)

    def setIconSize(self, size: QSize) -> None:  # noqa: N802
        if not self._updating_busy_icon:
            self._base_icon_size = QSize(size)
        super().setIconSize(size)

    def is_busy(self) -> bool:
        return self._busy

    def set_busy(self, busy: bool, *, tint: str | None = None) -> None:
        if self._busy == busy and (not busy or tint == self._busy_tint):
            return
        self._busy = busy
        self._busy_tint = tint or self._default_icon_tint()
        self.setProperty("busy", busy)
        if busy:
            self._busy_phase = 0
            self._busy_timer.start()
            self._refresh_busy_icon()
        else:
            self._busy_timer.stop()
            self._restore_base_icon()
        self.update()

    def paintEvent(self, event) -> None:
        if self._pop_progress <= 1e-3:
            super().paintEvent(event)
            return
        painter = QStylePainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        option = QStyleOptionButton()
        self.initStyleOption(option)

        center = self.rect().center()
        scale = 1.0 + (0.045 * math.sin(self._pop_progress * math.pi))
        painter.translate(center)
        painter.scale(scale, scale)
        painter.translate(-center)
        painter.drawControl(QStyle.ControlElement.CE_PushButton, option)
        del event

    def _play_pop_animation(self) -> None:
        self._pop_animation.stop()
        self._pop_animation.start()

    def _handle_pop_value_changed(self, value) -> None:
        self._pop_progress = float(value)
        self.update()

    def _finish_pop_animation(self) -> None:
        self._pop_progress = 0.0
        self.update()

    def _advance_busy_spinner(self) -> None:
        self._busy_phase = (self._busy_phase + 1) % 8
        self._refresh_busy_icon()

    def _refresh_busy_icon(self) -> None:
        if not self._busy:
            return
        icon_size = self._resolved_icon_size()
        pixel_ratio = self.devicePixelRatioF()
        pixel_width = max(1, int(round(icon_size.width() * pixel_ratio)))
        pixel_height = max(1, int(round(icon_size.height() * pixel_ratio)))
        pixmap = QPixmap(pixel_width, pixel_height)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = qcolor_from_css(self._busy_tint or self._default_icon_tint())
        center_x = pixel_width / 2
        center_y = pixel_height / 2
        radius = max(1.0, min(pixel_width, pixel_height) * 0.12)
        orbit = max(2.0, min(pixel_width, pixel_height) * 0.34)
        for index in range(8):
            phase_offset = (index - self._busy_phase) % 8
            alpha = 0.22 + (0.68 * (1.0 - (phase_offset / 7.0)))
            dot_color = color
            dot_color.setAlphaF(alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dot_color)
            angle = (-math.pi / 2.0) + ((2.0 * math.pi * index) / 8.0)
            painter.drawEllipse(
                int(round(center_x + (math.cos(angle) * orbit) - radius)),
                int(round(center_y + (math.sin(angle) * orbit) - radius)),
                int(round(radius * 2.0)),
                int(round(radius * 2.0)),
            )
        painter.end()
        pixmap.setDevicePixelRatio(pixel_ratio)

        self._updating_busy_icon = True
        try:
            super().setIcon(QIcon(pixmap))
            super().setIconSize(icon_size)
        finally:
            self._updating_busy_icon = False

    def _restore_base_icon(self) -> None:
        self._updating_busy_icon = True
        try:
            super().setIcon(self._base_icon)
            if self._base_icon_size.isValid():
                super().setIconSize(self._base_icon_size)
        finally:
            self._updating_busy_icon = False

    def _resolved_icon_size(self) -> QSize:
        if self._base_icon_size.isValid():
            return QSize(self._base_icon_size)
        if self._major:
            return major_button_icon_size()
        line_height = TEXT_STYLES["body-emphasis"].line_height
        return QSize(line_height, line_height)

    def _default_icon_tint(self) -> str:
        variant = str(self.property("variant") or "ghost")
        if variant == "primary":
            return THEME_COLORS.focus
        if variant == "info":
            return THEME_COLORS.info
        if variant == "success":
            return THEME_COLORS.success
        if variant == "warning":
            return THEME_COLORS.warning
        if variant == "danger":
            return THEME_COLORS.danger
        return THEME_COLORS.text_primary


class MenuButton(QToolButton):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.setObjectName("HeaderMenuButton")
        self.setText(text)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(GEOMETRY.header_control_height)
        self.setProperty("variant", "ghost")
        apply_text_role(self, "header-text")

    def initStyleOption(self, option: QStyleOptionToolButton) -> None:
        super().initStyleOption(option)
        option.features = option.features & ~QStyleOptionToolButton.ToolButtonFeature.HasMenu
        option.features = (
            option.features
            & ~QStyleOptionToolButton.ToolButtonFeature.MenuButtonPopup
        )
        option.arrowType = Qt.ArrowType.NoArrow


class CornerIconButton(QToolButton):
    def __init__(self, glyph: str) -> None:
        super().__init__()
        self.setObjectName("SidebarToggleButton")
        self.setText(glyph)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoRaise(True)
        icon_size = TEXT_STYLES["panel-title"].line_height
        self.setFixedSize(icon_size, icon_size)
        apply_text_role(self, "panel-title")


class PanelSectionDisclosureButton(CornerIconButton):
    def __init__(self) -> None:
        super().__init__("⌄")
        self.setObjectName("PanelSectionDisclosureButton")


class CollapsiblePanelSection(QFrame):
    expanded_changed = Signal(bool)

    def __init__(
        self,
        title: str,
        content: QWidget,
        *,
        disclosure_side: str,
    ) -> None:
        super().__init__()
        self._content = content
        self._expanded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._surface = QFrame()
        self._surface.setObjectName("PanelInner")
        surface_layout = QVBoxLayout(self._surface)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        surface_layout.setSpacing(0)

        self._header = QWidget()
        self._header.setObjectName("PanelSectionHeader")
        self.header_layout = QHBoxLayout(self._header)
        self.header_layout.setContentsMargins(
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding // 2,
            GEOMETRY.panel_padding,
            0,
        )
        self.header_layout.setSpacing(GEOMETRY.inspector_row_gap)

        self.title_label = QLabel("")
        apply_text_role(self.title_label, "section-label")

        self.disclosure_button = PanelSectionDisclosureButton()
        self.disclosure_button.clicked.connect(self._toggle_expanded)

        if disclosure_side == "leading":
            self.header_layout.addWidget(
                self.disclosure_button,
                alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            )
            self.header_layout.addWidget(self.title_label)
            self.header_layout.addStretch(1)
        else:
            self.header_layout.addWidget(self.title_label)
            self.header_layout.addStretch(1)
            self.header_layout.addWidget(
                self.disclosure_button,
                alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )

        object_name = self._content.objectName()
        if object_name in {
            "PanelInner",
            "InspectorPreviewFrame",
            "InspectorActionCard",
            "InspectorSummaryCard",
            "ManualMeasurementToolbar",
        }:
            self._content.setProperty("embeddedSectionBody", True)

        surface_layout.addWidget(self._header)
        surface_layout.addWidget(self._content, stretch=1)
        layout.addWidget(self._surface)
        self.set_title(title)
        self.set_expanded(True, emit=False)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title.upper())

    def is_expanded(self) -> bool:
        return self._expanded

    def content_widget(self) -> QWidget:
        return self._content

    def collapsed_height(self) -> int:
        return int(
            max(
                self._header.sizeHint().height(),
                self.disclosure_button.sizeHint().height(),
            )
        )

    def set_expanded(self, expanded: bool, *, emit: bool = True) -> None:
        if self._expanded == expanded:
            return
        self._expanded = expanded
        self._content.setVisible(expanded)
        self.disclosure_button.setText("⌄" if expanded else "⌃")
        self.setMinimumHeight(self.collapsed_height())
        self.updateGeometry()
        if emit:
            self.expanded_changed.emit(expanded)

    def _toggle_expanded(self) -> None:
        self.set_expanded(not self._expanded)


class LoadingCapsule(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("LoadingCapsule")
        self.setFixedHeight(GEOMETRY.control_height_sm - 8)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._active = False
        self._phase = 0.0
        self._percent = 0.0
        self._preferred_width = GEOMETRY.sidebar_min
        self._timer = QTimer(self)
        self._timer.setInterval(22)
        self._timer.timeout.connect(self._advance_phase)

    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        if active:
            self._timer.start()
        else:
            self._timer.stop()
            self._phase = 0.0
            self._percent = 0.0
        self.update()

    def set_percent(self, percent: float) -> None:
        self._percent = max(0.0, min(100.0, float(percent)))
        self.update()

    def _advance_phase(self) -> None:
        self._phase = (self._phase + 0.035) % 1.35
        if self._percent <= 0:
            self.update()

    def track_color_css(self) -> str:
        return THEME_COLORS.info_soft

    def fill_color_css(self) -> str:
        return THEME_COLORS.info

    def preferred_width(self) -> int:
        return self._preferred_width

    def set_preferred_width(self, width: int) -> None:
        self._preferred_width = max(0, int(width))

    def paintEvent(self, event) -> None:  # pragma: no cover - paint path
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        rect = self.rect().adjusted(0, 0, -1, -1)
        radius = capsule_radius(rect.height())
        painter.setBrush(qcolor_from_css(self.track_color_css()))
        painter.drawRoundedRect(rect, radius, radius)

        if not self._active:
            return

        if self._percent > 0:
            fill_width = max(1, int(round(rect.width() * (self._percent / 100.0))))
            fill_rect = rect.adjusted(0, 0, fill_width - rect.width(), 0)
            painter.setBrush(qcolor_from_css(self.fill_color_css()))
            painter.drawRoundedRect(fill_rect, radius, radius)
            return

        segment_width = max(42, min(96, int(rect.width() * 0.28)))
        travel = rect.width() + segment_width
        segment_x = int(round((self._phase * travel) - segment_width))
        segment_rect = rect.adjusted(segment_x, 0, segment_x - rect.width() + segment_width, 0)
        painter.setBrush(qcolor_from_css(self.fill_color_css()))
        painter.drawRoundedRect(segment_rect, radius, radius)


class HeaderStatusStrip(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("HeaderStatusStrip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        layout.setSpacing(GEOMETRY.unit)
        self._layout = layout
        self._progress_target_width = GEOMETRY.sidebar_min

        self._progress_capsule = LoadingCapsule()
        self._progress_capsule.hide()
        layout.addWidget(self._progress_capsule)

        self._status_label = QLabel("Idle")
        self._status_label.setObjectName("HeaderStatusLabel")
        apply_text_role(self._status_label, "meta")
        layout.addWidget(self._status_label)

        self._eta_label = QLabel("")
        self._eta_label.setObjectName("HeaderEtaLabel")
        apply_text_role(self._eta_label, "meta")
        self._eta_label.hide()
        layout.addWidget(self._eta_label)

        self._update_progress_capsule_width()

    def set_status(self, text: str, *, active: bool) -> None:
        self._status_label.setText(text)
        self._progress_capsule.set_active(active)

    def set_progress(self, percent: float, *, active: bool) -> None:
        self._progress_capsule.set_active(active)
        self._progress_capsule.set_percent(percent)
        if active and percent > 0:
            self._progress_capsule.show()
        elif not active:
            self._progress_capsule.hide()
        self._update_progress_capsule_width()

    def set_eta(self, text: str) -> None:
        self._eta_label.setText(text)
        self._eta_label.setVisible(bool(text))

    def set_progress_target_width(self, width: int) -> None:
        self._progress_target_width = max(0, int(width))
        self._progress_capsule.set_preferred_width(self._progress_target_width)
        self._update_progress_capsule_width()

    def progress_target_width(self) -> int:
        return self._progress_target_width

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_progress_capsule_width()

    def _update_progress_capsule_width(self) -> None:
        if self._layout is None:
            return
        if not self._progress_capsule.isVisible():
            self._progress_capsule.setFixedWidth(0)
            return
        desired_width = self._progress_target_width
        if self.width() <= 0:
            self._progress_capsule.setFixedWidth(desired_width)
            return
        margins = self._layout.contentsMargins()
        spacing = self._layout.spacing()
        status_reserve = max(120, self._status_label.sizeHint().width())
        reserved_width = (
            margins.left()
            + margins.right()
            + (spacing * 2)
            + status_reserve
        )
        available_width = max(0, self.width() - reserved_width)
        self._progress_capsule.setFixedWidth(min(desired_width, available_width))


class FooterStatusBar(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("FooterBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            GEOMETRY.unit * 2,
            GEOMETRY.footer_padding_y,
            GEOMETRY.unit * 2,
            GEOMETRY.footer_padding_y,
        )
        layout.setSpacing(GEOMETRY.unit)
        self._layout = layout
        self._progress_target_width = GEOMETRY.sidebar_min

        self._progress_capsule = LoadingCapsule()
        layout.addWidget(self._progress_capsule)

        self._status_label = QLabel("Idle")
        self._status_label.setObjectName("FooterStatusLabel")
        apply_text_role(self._status_label, "meta")
        layout.addWidget(self._status_label)
        layout.addStretch(1)

        self._renderer_label = QLabel("Renderer: pending")
        self._renderer_label.setObjectName("FooterRendererLabel")
        self._renderer_label.setProperty("renderState", "unknown")
        apply_text_role(self._renderer_label, "meta")
        layout.addWidget(self._renderer_label)
        self._update_progress_capsule_width()

    def set_status(self, text: str, *, active: bool) -> None:
        self._status_label.setText(text)
        self._progress_capsule.set_active(active)

    def set_renderer_status(self, text: str, *, state: str) -> None:
        self._renderer_label.setText(text)
        self._renderer_label.setProperty("renderState", state)
        self._renderer_label.style().unpolish(self._renderer_label)
        self._renderer_label.style().polish(self._renderer_label)
        self._renderer_label.update()
        self._update_progress_capsule_width()

    def set_progress_target_width(self, width: int) -> None:
        self._progress_target_width = max(0, int(width))
        self._progress_capsule.set_preferred_width(self._progress_target_width)
        self._update_progress_capsule_width()

    def progress_target_width(self) -> int:
        return self._progress_target_width

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_progress_capsule_width()

    def _update_progress_capsule_width(self) -> None:
        if self._layout is None:
            return
        desired_width = self._progress_target_width
        if self.width() <= 0:
            self._progress_capsule.setFixedWidth(desired_width)
            return
        margins = self._layout.contentsMargins()
        spacing = self._layout.spacing()
        status_reserve = max(120, self._status_label.sizeHint().width())
        renderer_reserve = self._renderer_label.sizeHint().width()
        reserved_width = (
            margins.left()
            + margins.right()
            + (spacing * 3)
            + status_reserve
            + renderer_reserve
        )
        available_width = max(0, self.width() - reserved_width)
        self._progress_capsule.setFixedWidth(min(desired_width, available_width))


class PanelFrame(QFrame):
    def __init__(
        self,
        title: str,
        subtitle: str = "",
        *,
        settings: SettingsService | None = None,
        workspace_id: str | None = None,
        panel_id: str | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("PanelFrame")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._settings = settings
        self._workspace_id = workspace_id
        self._panel_id = panel_id
        self._section_stretches: list[int] = []
        self._sections: list[CollapsiblePanelSection] = []
        self._section_restore_pending = True
        self._header_title_visible = True
        self._header_has_actions = False

        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(0, 0, 0, 0)
        self.outer_layout.setSpacing(0)

        self.header_row = QHBoxLayout()
        self.header_row.setContentsMargins(0, 0, 0, 0)
        self.header_row.setSpacing(GEOMETRY.unit)
        self.title_label = QLabel(title)
        apply_text_role(self.title_label, "panel-title")
        self.header_row.addWidget(self.title_label)
        self.header_row.addStretch(1)
        self.outer_layout.addLayout(self.header_row)
        del subtitle

        self.inner = QFrame()
        self.inner.setObjectName("PanelSectionHost")
        self.inner_layout = QVBoxLayout(self.inner)
        self.inner_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        self.inner_layout.setSpacing(0)
        self.section_splitter = TransparentSplitter(Qt.Orientation.Vertical)
        self.section_splitter.setHandleWidth(GEOMETRY.sidebar_section_gap)
        self.section_splitter.setChildrenCollapsible(False)
        self.section_splitter.splitterMoved.connect(self._save_section_sizes)
        self.inner_layout.addWidget(self.section_splitter)
        self.outer_layout.addWidget(self.inner, stretch=1)
        self._refresh_header_chrome()
        QTimer.singleShot(0, self._restore_section_sizes)

    def add_widget(
        self,
        widget: QWidget,
        *,
        stretch: int = 0,
        title: str | None = None,
        expanded: bool = True,
    ) -> CollapsiblePanelSection:
        section_index = self.section_splitter.count()
        content = self._normalize_section_widget(widget)
        set_title_visible = getattr(content, "set_title_visible", None)
        if callable(set_title_visible):
            set_title_visible(False)
        section = CollapsiblePanelSection(
            title or self._infer_section_title(content, section_index),
            content,
            disclosure_side="leading" if self._panel_id == "right" else "trailing",
        )
        stored_expanded = expanded
        flag_key = self._section_flag_key(section_index)
        if self._settings is not None and flag_key is not None:
            assert self._workspace_id is not None
            stored_expanded = self._settings.load_flag(
                self._workspace_id,
                flag_key,
                expanded,
            )
        section.set_expanded(stored_expanded, emit=False)
        section.expanded_changed.connect(
            lambda is_expanded, index=section_index: self._handle_section_expanded_changed(
                index,
                is_expanded,
            )
        )
        self.section_splitter.addWidget(section)
        self.section_splitter.setStretchFactor(
            section_index,
            max(1, stretch or 1),
        )
        self._section_stretches.append(max(1, stretch or 1))
        self._sections.append(section)
        self._section_restore_pending = True
        QTimer.singleShot(0, self._restore_section_sizes)
        return section

    def set_header_title_visible(self, visible: bool) -> None:
        self._header_title_visible = visible
        self.title_label.setVisible(visible)
        self._refresh_header_chrome()
        self.updateGeometry()

    def set_header_action(self, widget: QWidget) -> None:
        self._header_has_actions = True
        self.header_row.addWidget(
            widget,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        self._refresh_header_chrome()

    def set_header_leading_action(self, widget: QWidget) -> None:
        self._header_has_actions = True
        self.header_row.insertWidget(
            0,
            widget,
            alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        self._refresh_header_chrome()

    def _refresh_header_chrome(self) -> None:
        top_padding = GEOMETRY.panel_padding if self._header_title_visible else 0
        self.outer_layout.setContentsMargins(
            GEOMETRY.panel_padding,
            top_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
        )
        self.outer_layout.setSpacing(
            GEOMETRY.inspector_row_gap if self._header_title_visible else 0
        )

    def _normalize_section_widget(self, widget: QWidget) -> QWidget:
        object_name = widget.objectName()
        if object_name in {
            "PanelInner",
            "InspectorPreviewFrame",
            "InspectorActionCard",
            "InspectorSummaryCard",
            "ManualMeasurementToolbar",
        }:
            return widget
        return NestedBubbleFrame(widget)

    def _default_section_sizes(self) -> list[int]:
        sizes: list[int] = []
        for index in range(self.section_splitter.count()):
            widget = self.section_splitter.widget(index)
            stretch = (
                self._section_stretches[index]
                if index < len(self._section_stretches)
                else 1
            )
            if index < len(self._sections) and not self._sections[index].is_expanded():
                sizes.append(self._sections[index].collapsed_height())
                continue
            hint = (
                widget.sizeHint().height()
                if widget is not None
                else GEOMETRY.sidebar_section_min
            )
            sizes.append(max(GEOMETRY.sidebar_section_min, hint) * max(1, stretch))
        return sizes

    def _settings_key(self) -> str | None:
        if self._workspace_id is None or self._panel_id is None:
            return None
        return f"{self._panel_id}_sections"

    def _section_flag_key(self, index: int) -> str | None:
        if self._panel_id is None:
            return None
        return f"{self._panel_id}_section_{index}_expanded"

    def _infer_section_title(self, widget: QWidget, index: int) -> str:
        title_label = getattr(widget, "title_label", None)
        if isinstance(title_label, QLabel):
            text = str(title_label.text()).strip()
            if text:
                return text
        return f"Section {index + 1}"

    def _section_floor_height(self, index: int) -> int:
        if index < len(self._sections) and not self._sections[index].is_expanded():
            return self._sections[index].collapsed_height()
        widget = self.section_splitter.widget(index)
        hint = widget.sizeHint().height() if widget is not None else GEOMETRY.sidebar_section_min
        return max(GEOMETRY.sidebar_section_min, hint)

    def _normalized_section_sizes(self, sizes: list[int]) -> list[int]:
        count = self.section_splitter.count()
        if count == 0:
            return []
        resolved_sizes = list(sizes[:count])
        if len(resolved_sizes) < count:
            resolved_sizes.extend([0] * (count - len(resolved_sizes)))
        floors = [self._section_floor_height(index) for index in range(count)]
        total = max(
            sum(resolved_sizes),
            self.section_splitter.size().height(),
            sum(floors),
        )
        result = list(floors)
        extra = max(total - sum(floors), 0)
        recipients = [
            index
            for index, section in enumerate(self._sections)
            if section.is_expanded()
        ]
        if not recipients:
            recipients = [count - 1]
        weights: list[int] = []
        for index in recipients:
            current_extra = max(0, resolved_sizes[index] - floors[index])
            if current_extra == 0:
                current_extra = (
                    self._section_stretches[index]
                    if index < len(self._section_stretches)
                    else 1
                )
            weights.append(max(1, current_extra))
        weight_total = sum(weights)
        remaining = extra
        for position, index in enumerate(recipients):
            if position == len(recipients) - 1:
                share = remaining
            else:
                share = int(round(extra * (weights[position] / weight_total)))
                share = min(share, remaining)
            result[index] += share
            remaining -= share
        return result

    def _save_section_sizes(self) -> None:
        key = self._settings_key()
        if self._settings is None or key is None or self.section_splitter.count() == 0:
            return
        assert self._workspace_id is not None
        self._settings.save_sizes(
            self._workspace_id,
            key,
            self.section_splitter.sizes(),
        )

    def _restore_section_sizes(self) -> None:
        if not self._section_restore_pending or self.section_splitter.count() == 0:
            return
        self._section_restore_pending = False
        sizes: list[int] | None = None
        key = self._settings_key()
        if self._settings is not None and key is not None:
            assert self._workspace_id is not None
            loaded_sizes = self._settings.load_sizes(self._workspace_id, key)
            if loaded_sizes is not None and len(loaded_sizes) == self.section_splitter.count():
                sizes = loaded_sizes
        if sizes is None:
            sizes = self._default_section_sizes()
        if sizes:
            self.section_splitter.setSizes(self._normalized_section_sizes(sizes))

    def _handle_section_expanded_changed(self, index: int, expanded: bool) -> None:
        flag_key = self._section_flag_key(index)
        if self._settings is not None and flag_key is not None:
            assert self._workspace_id is not None
            self._settings.save_flag(self._workspace_id, flag_key, expanded)
        self.section_splitter.setSizes(
            self._normalized_section_sizes(self.section_splitter.sizes())
        )
        self._save_section_sizes()


class NestedBubbleFrame(QFrame):
    def __init__(self, child: QWidget, *, padding: int | None = None) -> None:
        super().__init__()
        self.setObjectName("NestedPanelInner")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        inset = GEOMETRY.panel_padding if padding is None else padding
        layout.setContentsMargins(inset, inset, inset, inset)
        layout.setSpacing(0)
        layout.addWidget(child)


class ViewportCard(QFrame):
    def __init__(self, title: str, subtitle: str, footer: str = "") -> None:
        super().__init__()
        self.setObjectName("ViewportCardFrame")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
        )
        layout.setSpacing(GEOMETRY.unit)

        title_label = QLabel(title)
        apply_text_role(title_label, "panel-title")
        layout.addWidget(title_label)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setWordWrap(True)
        apply_text_role(subtitle_label, "body")
        layout.addWidget(subtitle_label, stretch=1)

        if footer:
            footer_label = QLabel(footer)
            footer_label.setWordWrap(True)
            apply_text_role(footer_label, "meta")
            layout.addWidget(footer_label)
