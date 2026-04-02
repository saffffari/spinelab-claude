"""Anatomy Explorer tree widget for per-structure visibility control.

Displays segmentation labels grouped by organ system in a collapsible tree.
Each row has an eye toggle button aligned right.  Toggling a folder hides
all children regardless of their individual visibility state.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QStyle,
    QStyleOptionViewItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
)

from spinelab.segmentation.anatomy_groups import (
    AnatomyGroup,
    display_name_for_label,
)
from spinelab.ui.theme import GEOMETRY, THEME_COLORS, qcolor_from_css


# ---------------------------------------------------------------------------
# Eye toggle button
# ---------------------------------------------------------------------------


class AnatomyVisibilityButton(QToolButton):
    """Small eye-glyph toggle for anatomy label visibility."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("AnatomyEyeButton")
        self.setCheckable(True)
        self.setChecked(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        size = GEOMETRY.control_height_sm - 8
        self.setFixedSize(size, size)
        self.setText("")
        self.toggled.connect(lambda _checked: self.update())

    def paintEvent(self, event) -> None:  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if not self.isChecked():
            painter.end()
            return

        w = float(self.width())
        h = float(self.height())
        cx, cy = w / 2.0, h / 2.0
        eye_w = w * 0.72
        eye_h = h * 0.36

        color = (
            qcolor_from_css(THEME_COLORS.focus)
            if self.isChecked()
            else qcolor_from_css(THEME_COLORS.text_muted)
        )

        # Draw eye outline (two arcs)
        path = QPainterPath()
        path.moveTo(cx - eye_w / 2, cy)
        path.quadTo(cx, cy - eye_h, cx + eye_w / 2, cy)
        path.quadTo(cx, cy + eye_h, cx - eye_w / 2, cy)

        pen = QPen(color)
        pen.setWidthF(1.2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Draw pupil
        pupil_r = min(eye_w, eye_h) * 0.28
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(cx - pupil_r, cy - pupil_r, pupil_r * 2, pupil_r * 2)

        painter.end()


# ---------------------------------------------------------------------------
# Anatomy explorer tree
# ---------------------------------------------------------------------------

_ROLE_LABEL_NAME = Qt.ItemDataRole.UserRole + 1
_ROLE_GROUP_NAME = Qt.ItemDataRole.UserRole + 2


class AnatomyExplorerTree(QTreeWidget):
    """Collapsible organ-system tree with per-label eye toggles."""

    visibility_changed = Signal(set)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("AnatomyExplorerTree")
        self.setHeaderHidden(True)
        self.setColumnCount(2)
        self.setIndentation(GEOMETRY.unit * 2)
        self.setRootIsDecorated(True)
        self.setAllColumnsShowFocus(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setUniformRowHeights(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._label_visible: dict[str, bool] = {}
        self._folder_visible: dict[str, bool] = {}
        self._groups: list[AnatomyGroup] = []
        self._folder_buttons: dict[str, AnatomyVisibilityButton] = {}
        self._label_buttons: dict[str, AnatomyVisibilityButton] = {}

    # -- public API ---------------------------------------------------------

    def populate(self, groups: list[AnatomyGroup]) -> None:
        self.clear()
        self._groups = groups
        self._label_visible.clear()
        self._folder_visible.clear()
        self._folder_buttons.clear()
        self._label_buttons.clear()

        for group in groups:
            self._folder_visible[group.display_name] = True

            folder_item = QTreeWidgetItem(self)
            folder_item.setText(0, group.display_name)
            folder_item.setData(0, _ROLE_GROUP_NAME, group.display_name)
            folder_item.setFlags(Qt.ItemFlag.ItemIsEnabled)

            folder_btn = AnatomyVisibilityButton()
            folder_btn.setChecked(True)
            folder_btn.toggled.connect(
                lambda checked, name=group.display_name: self._handle_folder_toggled(
                    name, checked
                )
            )
            self.setItemWidget(folder_item, 1, folder_btn)
            self._folder_buttons[group.display_name] = folder_btn

            for label_name in group.label_names:
                self._label_visible[label_name] = True

                child_item = QTreeWidgetItem(folder_item)
                child_item.setText(0, display_name_for_label(label_name))
                child_item.setData(0, _ROLE_LABEL_NAME, label_name)

                label_btn = AnatomyVisibilityButton()
                label_btn.setChecked(True)
                label_btn.toggled.connect(
                    lambda checked, name=label_name: self._handle_label_toggled(
                        name, checked
                    )
                )
                self.setItemWidget(child_item, 1, label_btn)
                self._label_buttons[label_name] = label_btn

        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, self.header().ResizeMode.Stretch)
        self.header().setSectionResizeMode(1, self.header().ResizeMode.ResizeToContents)

    def visible_labels(self) -> set[str]:
        result: set[str] = set()
        for group in self._groups:
            if not self._folder_visible.get(group.display_name, True):
                continue
            for label_name in group.label_names:
                if self._label_visible.get(label_name, True):
                    result.add(label_name)
        return result

    # -- handlers -----------------------------------------------------------

    def _handle_label_toggled(self, label_name: str, visible: bool) -> None:
        self._label_visible[label_name] = visible
        self._sync_folder_button_for_label(label_name)
        self.visibility_changed.emit(self.visible_labels())

    def _handle_folder_toggled(self, group_name: str, visible: bool) -> None:
        self._folder_visible[group_name] = visible
        self.visibility_changed.emit(self.visible_labels())

    def _sync_folder_button_for_label(self, label_name: str) -> None:
        """Update folder eye icon to reflect children state."""
        for group in self._groups:
            if label_name not in group.label_names:
                continue
            any_visible = any(
                self._label_visible.get(name, True) for name in group.label_names
            )
            btn = self._folder_buttons.get(group.display_name)
            if btn is not None:
                btn.blockSignals(True)
                btn.setChecked(any_visible)
                btn.blockSignals(False)
            break

    # -- custom painting ----------------------------------------------------

    def drawRow(
        self, painter: QPainter, options: QStyleOptionViewItem, index
    ) -> None:
        option = QStyleOptionViewItem(options)
        option.showDecorationSelected = False
        option.state &= ~QStyle.StateFlag.State_Selected
        option.state &= ~QStyle.StateFlag.State_HasFocus
        super().drawRow(painter, option, index)
