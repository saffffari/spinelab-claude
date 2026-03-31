from __future__ import annotations

from typing import Protocol, cast

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPaintEvent
from PySide6.QtWidgets import QSplitter, QSplitterHandle, QWidget

from spinelab.ui.theme import GEOMETRY


class LayoutTransitionWidget(Protocol):
    def set_layout_transition_active(self, active: bool) -> None:
        ...


class TransparentSplitterHandle(QSplitterHandle):
    def __init__(self, orientation: Qt.Orientation, parent: QSplitter) -> None:
        super().__init__(orientation, parent)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        cursor = (
            Qt.CursorShape.SplitHCursor
            if orientation == Qt.Orientation.Horizontal
            else Qt.CursorShape.SplitVCursor
        )
        self.setCursor(cursor)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: ARG002
        return

    def mousePressEvent(self, event) -> None:
        splitter = self.splitter()
        if (
            event.button() == Qt.MouseButton.LeftButton
            and isinstance(splitter, TransparentSplitter)
        ):
            splitter._begin_layout_transition()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        splitter = self.splitter()
        super().mouseReleaseEvent(event)
        if isinstance(splitter, TransparentSplitter):
            splitter._end_layout_transition()


class TransparentSplitter(QSplitter):
    def __init__(self, orientation: Qt.Orientation, parent=None) -> None:
        super().__init__(orientation, parent)
        self.setHandleWidth(GEOMETRY.splitter_handle)
        self.setChildrenCollapsible(True)
        self.setOpaqueResize(True)
        self._layout_transition_active = False
        self.splitterMoved.connect(self._schedule_repaint)

    def createHandle(self) -> QSplitterHandle:
        return TransparentSplitterHandle(self.orientation(), self)

    def _begin_layout_transition(self) -> None:
        if self._layout_transition_active:
            return
        self._layout_transition_active = True
        for widget in self._transition_widgets():
            widget.set_layout_transition_active(True)

    def _end_layout_transition(self) -> None:
        if not self._layout_transition_active:
            return
        self._layout_transition_active = False
        QTimer.singleShot(0, self._restore_layout_transition)

    def _restore_layout_transition(self) -> None:
        for widget in self._transition_widgets():
            widget.set_layout_transition_active(False)
        self._repaint_shell()

    def _transition_widgets(self) -> list[LayoutTransitionWidget]:
        widgets: list[LayoutTransitionWidget] = []
        seen: set[int] = set()
        for index in range(self.count()):
            root = self.widget(index)
            if root is None:
                continue
            for candidate in [root, *root.findChildren(QWidget)]:
                callback = getattr(candidate, "set_layout_transition_active", None)
                if not callable(callback):
                    continue
                key = id(candidate)
                if key in seen:
                    continue
                seen.add(key)
                widgets.append(cast(LayoutTransitionWidget, candidate))
        return widgets

    def _schedule_repaint(self, *_args) -> None:
        QTimer.singleShot(0, self._repaint_shell)

    def _repaint_shell(self) -> None:
        self.update()
        parent = self.parentWidget()
        if parent is not None:
            parent.update()
        for index in range(self.count()):
            widget = self.widget(index)
            if widget is not None:
                widget.update()


def schedule_splitter_midpoint(
    splitter: QSplitter,
    *,
    middle_extent: int | None = None,
) -> None:
    def apply_midpoint() -> None:
        count = splitter.count()
        if count not in {2, 3}:
            return

        sizes = splitter.sizes()
        total_extent = sum(sizes)
        if total_extent <= 0:
            total_extent = (
                splitter.width()
                if splitter.orientation() == Qt.Orientation.Horizontal
                else splitter.height()
            )
        if total_extent <= 1:
            return

        if count == 2:
            leading_extent = total_extent // 2
            splitter.setSizes([leading_extent, total_extent - leading_extent])
            return

        if middle_extent is None:
            return

        fixed_middle_extent = min(max(0, middle_extent), max(0, total_extent - 2))
        remaining_extent = max(2, total_extent - fixed_middle_extent)
        leading_extent = remaining_extent // 2
        splitter.setSizes(
            [
                leading_extent,
                fixed_middle_extent,
                remaining_extent - leading_extent,
            ]
        )

    QTimer.singleShot(0, apply_midpoint)
