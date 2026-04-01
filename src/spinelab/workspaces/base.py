from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QShowEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from spinelab.services import SettingsService
from spinelab.ui.theme import GEOMETRY
from spinelab.ui.widgets import (
    CornerIconButton,
    PanelFrame,
    TransparentSplitter,
)


class WorkspacePage(QWidget):
    sidebar_widths_changed = Signal(int, int)

    def __init__(
        self,
        workspace_id: str,
        title: str,
        subtitle: str,
        settings: SettingsService,
        left_panel: PanelFrame,
        center_widget: QWidget,
        right_panel: PanelFrame,
        *,
        center_surface_padding: int | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("WorkspacePage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.workspace_id = workspace_id
        self._settings = settings
        self._saved_left_width = GEOMETRY.sidebar_min
        self._saved_right_width = GEOMETRY.inspector_min
        self._left_visible = True
        self._right_visible = True
        self._left_panel = left_panel
        self._right_panel = right_panel
        self._post_show_sync_pending = True

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
        )
        root_layout.setSpacing(GEOMETRY.unit)

        self.left_toggle = CornerIconButton("‹")
        self.left_toggle.clicked.connect(self._toggle_left)
        left_panel.set_header_action(self.left_toggle)
        left_panel.set_header_title_visible(False)

        self.right_toggle = CornerIconButton("›")
        self.right_toggle.clicked.connect(self._toggle_right)
        right_panel.set_header_leading_action(self.right_toggle)
        right_panel.set_header_title_visible(False)

        self.left_reveal = CornerIconButton("›")
        self.left_reveal.clicked.connect(self._toggle_left)

        self.right_reveal = CornerIconButton("‹")
        self.right_reveal.clicked.connect(self._toggle_right)

        body_row = QHBoxLayout()
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(0)
        root_layout.addLayout(body_row, stretch=1)

        self.outer_splitter = TransparentSplitter(Qt.Orientation.Horizontal)
        self.outer_splitter.splitterMoved.connect(self._persist_splitter)
        body_row.addWidget(self.left_reveal, alignment=Qt.AlignmentFlag.AlignTop)
        body_row.addWidget(self.outer_splitter, stretch=1)
        body_row.addWidget(self.right_reveal, alignment=Qt.AlignmentFlag.AlignTop)

        left_panel.setMinimumWidth(0)
        right_panel.setMinimumWidth(0)

        center_surface = QFrame()
        center_surface.setObjectName("SurfaceFrame")
        center_layout = QVBoxLayout(center_surface)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(GEOMETRY.viewport_gap)
        center_layout.addWidget(center_widget, stretch=1)

        self.outer_splitter.addWidget(left_panel)
        self.outer_splitter.addWidget(center_surface)
        self.outer_splitter.addWidget(right_panel)
        self.outer_splitter.setStretchFactor(1, 1)

        QTimer.singleShot(0, self.restore_layout)

    def restore_layout(self) -> None:
        self.sync_shell_layout()

    def dispose(self) -> None:
        return None

    def on_workspace_activated(self) -> None:
        return None

    def on_workspace_deactivated(self) -> None:
        return None

    def closeEvent(self, event: QCloseEvent) -> None:
        self.dispose()
        super().closeEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._post_show_sync_pending:
            self._post_show_sync_pending = False
            QTimer.singleShot(0, self.sync_shell_layout)

    def sync_shell_layout(self) -> None:
        left_width, right_width = self._settings.load_shell_sidebar_widths()
        shared_sidebar_width = max(GEOMETRY.sidebar_min, GEOMETRY.inspector_min)
        self._saved_left_width = max(left_width or shared_sidebar_width, GEOMETRY.sidebar_min)
        self._saved_right_width = max(right_width or shared_sidebar_width, GEOMETRY.inspector_min)
        self._left_visible, self._right_visible = self._settings.load_shell_sidebar_visibility(
            True,
            True,
        )
        self._normalize_sidebar_widths()
        self._settings.save_shell_sidebar_widths(
            self._saved_left_width,
            self._saved_right_width,
        )
        self._apply_shell_layout()
        self._refresh_toggle_icons()

    def shell_sidebar_width_targets(self) -> tuple[int | None, int | None]:
        return (
            self._sidebar_target_width(
                self._left_panel,
                GEOMETRY.sidebar_min,
            ),
            self._sidebar_target_width(
                self._right_panel,
                GEOMETRY.inspector_min,
            ),
        )

    def _normalize_sidebar_widths(self) -> None:
        left_target_width = self._sidebar_target_width(
            self._left_panel,
            GEOMETRY.sidebar_min,
        )
        right_target_width = self._sidebar_target_width(
            self._right_panel,
            GEOMETRY.inspector_min,
        )
        if not (self._left_visible and self._right_visible):
            if self._left_visible:
                self._saved_left_width = max(self._saved_left_width, left_target_width)
            if self._right_visible:
                self._saved_right_width = max(self._saved_right_width, right_target_width)
            return
        minimum_shared_width = max(
            left_target_width,
            right_target_width,
        )
        shared_width = max(
            minimum_shared_width,
            self._saved_left_width,
            self._saved_right_width,
        )
        self._saved_left_width = shared_width
        self._saved_right_width = shared_width

    def _sidebar_target_width(self, panel: PanelFrame, minimum_width: int) -> int:
        minimum_hint_width = max(panel.minimumSizeHint().width(), minimum_width)
        preferred_hint_width = max(panel.sizeHint().width(), minimum_hint_width)
        return int(
            max(
                minimum_width,
                minimum_hint_width,
                math.ceil(preferred_hint_width / 2.0),
            )
        )

    def _persist_splitter(self) -> None:
        sizes = self.outer_splitter.sizes()
        if sizes[0] > 0:
            self._saved_left_width = sizes[0]
        if sizes[2] > 0:
            self._saved_right_width = sizes[2]
        self._settings.save_shell_sidebar_widths(
            self._saved_left_width,
            self._saved_right_width,
        )
        self._settings.save_shell_sidebar_visibility(
            self._left_visible,
            self._right_visible,
        )
        self._emit_sidebar_widths_changed()

    def _refresh_toggle_icons(self) -> None:
        self.left_toggle.setVisible(self._left_visible)
        self.right_toggle.setVisible(self._right_visible)
        self.left_reveal.setVisible(not self._left_visible)
        self.right_reveal.setVisible(not self._right_visible)

    def _toggle_left(self) -> None:
        self._left_visible = not self._left_visible
        self._restore_left() if self._left_visible else self._collapse_left()
        self._refresh_toggle_icons()

    def _toggle_right(self) -> None:
        self._right_visible = not self._right_visible
        self._restore_right() if self._right_visible else self._collapse_right()
        self._refresh_toggle_icons()

    def _collapse_left(self, *, persist: bool = True) -> None:
        sizes = self.outer_splitter.sizes()
        if sizes[0] > 0:
            self._saved_left_width = sizes[0]
        self._left_panel.hide()
        self.outer_splitter.setSizes([0, sizes[1] + sizes[0], sizes[2]])
        if persist:
            self._persist_splitter()

    def _restore_left(self) -> None:
        self._left_panel.show()
        sizes = self.outer_splitter.sizes()
        total_width = max(sum(sizes), 1)
        right_width = sizes[2]
        left_width = min(
            max(self._saved_left_width, GEOMETRY.sidebar_min),
            max(total_width - right_width - 1, 0),
        )
        center_width = max(1, total_width - left_width - right_width)
        self.outer_splitter.setSizes([left_width, center_width, sizes[2]])
        self._persist_splitter()

    def _collapse_right(self, *, persist: bool = True) -> None:
        sizes = self.outer_splitter.sizes()
        if sizes[2] > 0:
            self._saved_right_width = sizes[2]
        self._right_panel.hide()
        self.outer_splitter.setSizes([sizes[0], sizes[1] + sizes[2], 0])
        if persist:
            self._persist_splitter()

    def _restore_right(self) -> None:
        self._right_panel.show()
        sizes = self.outer_splitter.sizes()
        total_width = max(sum(sizes), 1)
        left_width = sizes[0]
        right_width = min(
            max(self._saved_right_width, GEOMETRY.inspector_min),
            max(total_width - left_width - 1, 0),
        )
        center_width = max(1, total_width - left_width - right_width)
        self.outer_splitter.setSizes([sizes[0], center_width, right_width])
        self._persist_splitter()

    def _apply_shell_layout(self) -> None:
        current_sizes = self.outer_splitter.sizes()
        total_width = sum(current_sizes)
        if total_width <= 0:
            current_sizes = [
                GEOMETRY.sidebar_min,
                GEOMETRY.viewport_min * 3,
                GEOMETRY.inspector_min,
            ]
            total_width = sum(current_sizes)
        left_width = self._saved_left_width if self._left_visible else 0
        right_width = self._saved_right_width if self._right_visible else 0
        self._left_panel.setVisible(self._left_visible)
        self._right_panel.setVisible(self._right_visible)
        available_for_sidebars = max(total_width - 1, 0)
        if left_width + right_width > available_for_sidebars and available_for_sidebars > 0:
            scale = available_for_sidebars / (left_width + right_width)
            left_width = int(left_width * scale)
            right_width = int(right_width * scale)
        center_width = max(1, total_width - left_width - right_width)
        self.outer_splitter.setSizes([left_width, center_width, right_width])
        self._emit_sidebar_widths_changed()

    def _emit_sidebar_widths_changed(self) -> None:
        sizes = self.outer_splitter.sizes()
        left_width = sizes[0] if len(sizes) >= 1 else 0
        right_width = sizes[2] if len(sizes) >= 3 else 0
        self.sidebar_widths_changed.emit(left_width, right_width)
