from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import nibabel as nib
import numpy as np
import pydicom
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QDragEnterEvent,
    QDropEvent,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    qRgb,
)
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from spinelab.models import StudyAsset
from spinelab.services import BoundedCache, performance_coordinator
from spinelab.ui.svg_icons import build_svg_pixmap, centered_square_rect
from spinelab.ui.theme import GEOMETRY, THEME_COLORS, qcolor_from_css
from spinelab.ui.widgets import apply_text_role
from spinelab.visualization.viewport_gnomon import (
    ViewportGnomonOverlay,
    position_gnomon_overlay,
)

SPINELAB_ASSET_MIME = "application/x-spinelab-asset-id"


def _estimate_qimage_bytes(image: QImage) -> int:
    return int(image.sizeInBytes()) if image is not None else 0


def _estimate_stack_descriptor_bytes(descriptor: DisplayStackDescriptor) -> int:
    return max(256, len(descriptor.slice_paths) * 96)


def _estimate_volume_array_bytes(volume: np.ndarray) -> int:
    return int(volume.nbytes)



def _raster_image_cache() -> BoundedCache[str, QImage]:
    policy = performance_coordinator().active_policy
    return performance_coordinator().get_cache(
        "viewer-2d-raster-images",
        max_bytes=policy.image_cache_budget_bytes,
        estimate_size=_estimate_qimage_bytes,
    )


def _stack_descriptor_cache() -> BoundedCache[str, DisplayStackDescriptor]:
    policy = performance_coordinator().active_policy
    return performance_coordinator().get_cache(
        "viewer-2d-stack-descriptors",
        max_bytes=max(32 * 1024 * 1024, policy.image_cache_budget_bytes // 16),
        estimate_size=_estimate_stack_descriptor_bytes,
    )


def _volume_array_cache() -> BoundedCache[str, np.ndarray]:
    policy = performance_coordinator().active_policy
    return performance_coordinator().get_cache(
        "viewer-2d-volume-arrays",
        max_bytes=policy.active_volume_cache_budget_bytes,
        estimate_size=_estimate_volume_array_bytes,
    )
EMPTY_STATE_ICON_PATH = (
    Path(__file__).resolve().parents[1] / "ui" / "assets" / "fluent-document-add-48.svg"
)
MIN_VIEWPORT_ZOOM = 0.5
MAX_VIEWPORT_ZOOM = 12.0


class XrayProjection(StrEnum):
    AP = "AP"
    LAT = "LAT"


@dataclass(frozen=True)
class DisplayStackDescriptor:
    kind: str
    source_path: Path
    slice_paths: list[Path]
    slice_count: int


def path_cache_key(source_path: Path) -> str:
    try:
        return str(source_path.resolve())
    except Exception:
        return str(source_path)


def wheel_uses_slice_navigation(
    render_mode: str,
    modifiers: Any,
) -> bool:
    return render_mode == "ct" and not bool(
        modifiers & Qt.KeyboardModifier.ControlModifier
    )


def stack_preview_slice_index(slice_count: int) -> int:
    normalized_count = max(1, slice_count)
    preview_slice_number = int((normalized_count / 2.0) + 0.5)
    return max(0, min(normalized_count - 1, preview_slice_number - 1))


class SliceCanvas(QFrame):
    slice_changed = Signal(int, int)
    files_dropped = Signal(list)
    asset_dropped = Signal(str)
    browse_requested = Signal()
    activated = Signal()

    def __init__(
        self,
        render_mode: str,
        slot_title: str,
        empty_subtitle: str,
        *,
        projection: XrayProjection | None = None,
        allow_drop: bool = True,
    ) -> None:
        super().__init__()
        self.setObjectName("ImageViewportCanvas")
        self.setAcceptDrops(allow_drop)
        self._render_mode = render_mode
        self._slot_title = slot_title
        self._empty_subtitle = empty_subtitle
        self._projection = projection
        self._allow_drop = allow_drop
        self._source_root: Path | None = None
        self._stack_descriptor: DisplayStackDescriptor | None = None
        self._slice_paths: list[Path] = []
        self._slice_index = 0
        self._slice_count = 1
        self._zoom = 1.0
        self._pan_offset = QPointF()
        self._middle_dragging = False
        self._last_drag_position = QPointF()
        self.setMouseTracking(True)
        self.update()

    @property
    def slice_count(self) -> int:
        return self._slice_count

    @property
    def slice_index(self) -> int:
        return self._slice_index

    @property
    def is_empty(self) -> bool:
        return self._source_root is None

    def set_source(self, source_root: Path | None) -> None:
        self._source_root = source_root
        self._stack_descriptor = describe_display_stack(source_root, render_mode=self._render_mode)
        self._slice_paths = (
            list(self._stack_descriptor.slice_paths) if self._stack_descriptor is not None else []
        )
        self._slice_count = (
            max(1, self._stack_descriptor.slice_count)
            if self._stack_descriptor is not None
            else 1
        )
        if self._render_mode == "ct" and self._slice_count > 0:
            self._slice_index = stack_preview_slice_index(self._slice_count)
        else:
            self._slice_index = min(self._slice_index, self._slice_count - 1)
        self._reset_view_transform()
        self.update()
        self.slice_changed.emit(self._slice_index + 1, self._slice_count)

    def set_slice_index(self, slice_index: int) -> None:
        if self._render_mode != "ct":
            return
        next_index = max(0, min(self._slice_count - 1, slice_index))
        if next_index == self._slice_index:
            return
        self._slice_index = next_index
        self.update()
        self.slice_changed.emit(self._slice_index + 1, self._slice_count)

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        viewport_bg = qcolor_from_css(THEME_COLORS.viewport_bg)
        painter.fillRect(self.rect(), viewport_bg)

        if self._source_root is None:
            painter.drawImage(0, 0, render_empty_placeholder(
                self.width(),
                self.height(),
                self._slot_title,
                self._empty_subtitle,
            ))
            painter.end()
            return

        content_rect = self._content_rect()
        painter.fillRect(content_rect, viewport_bg)
        image = self._current_loaded_image()
        if image is None:
            fallback = self._render_fallback_image()
            painter.drawImage(0, 0, fallback)
            painter.end()
            return

        target_rect = self._image_target_rect(image, content_rect)
        painter.setClipRect(content_rect)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(target_rect, image)
        painter.end()

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        if wheel_uses_slice_navigation(self._render_mode, event.modifiers()):
            if self._slice_count <= 1:
                event.ignore()
                return
            direction = 1 if delta > 0 else -1
            self.set_slice_index(self._slice_index + direction)
            event.accept()
            return
        if self._apply_zoom(delta, event.position()):
            event.accept()
            return
        event.ignore()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
        elif (
            event.button() == Qt.MouseButton.MiddleButton
            and self._source_root is not None
            and self._current_loaded_image() is not None
        ):
            self._middle_dragging = True
            self._last_drag_position = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._middle_dragging and event.buttons() & Qt.MouseButton.MiddleButton:
            delta = event.position() - self._last_drag_position
            self._last_drag_position = event.position()
            self._pan_offset = QPointF(
                self._pan_offset.x() + delta.x(),
                self._pan_offset.y() + delta.y(),
            )
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton and self._middle_dragging:
            self._middle_dragging = False
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if not self._allow_drop:
            super().dragEnterEvent(event)
            return
        mime_data = event.mimeData()
        if mime_data.hasFormat(SPINELAB_ASSET_MIME):
            event.acceptProposedAction()
            return
        if mime_data.hasUrls():
            local_paths = [
                Path(url.toLocalFile()) for url in mime_data.urls() if url.isLocalFile()
            ]
            if local_paths:
                event.acceptProposedAction()
                return
        super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if not self._allow_drop:
            super().dropEvent(event)
            return
        mime_data = event.mimeData()
        if mime_data.hasFormat(SPINELAB_ASSET_MIME):
            asset_id = mime_data.data(SPINELAB_ASSET_MIME).toStdString()
            if asset_id:
                self.asset_dropped.emit(asset_id)
                event.acceptProposedAction()
                return
        if mime_data.hasUrls():
            local_paths = [
                Path(url.toLocalFile()) for url in mime_data.urls() if url.isLocalFile()
            ]
            if local_paths:
                self.files_dropped.emit(local_paths)
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def _reset_view_transform(self) -> None:
        self._zoom = 1.0
        self._pan_offset = QPointF()
        self._middle_dragging = False
        self.unsetCursor()

    def _content_rect(self) -> QRectF:
        return QRectF(
            0.0,
            0.0,
            max(1.0, float(self.width())),
            max(1.0, float(self.height())),
        )

    def _current_loaded_image(self) -> QImage | None:
        if self._stack_descriptor is None:
            return None
        index = 0 if self._render_mode == "xray" else self._slice_index
        return load_display_slice(self._stack_descriptor, index)

    def _image_target_rect(self, image: QImage, content_rect: QRectF) -> QRectF:
        width = max(float(image.width()), 1.0)
        height = max(float(image.height()), 1.0)
        fit_scale = min(content_rect.width() / width, content_rect.height() / height)
        draw_scale = fit_scale * self._zoom
        draw_width = width * draw_scale
        draw_height = height * draw_scale
        center = QPointF(
            content_rect.center().x() + self._pan_offset.x(),
            content_rect.center().y() + self._pan_offset.y(),
        )
        return QRectF(
            center.x() - draw_width / 2.0,
            center.y() - draw_height / 2.0,
            draw_width,
            draw_height,
        )

    def _render_fallback_image(self) -> QImage:
        width = max(320, self.width())
        height = max(240, self.height())
        if self._render_mode == "xray":
            return render_loaded_xray(
                width,
                height,
                self._source_root or Path(),
                self._projection,
                loaded_image=None,
            )
        current_path = (
            self._slice_paths[self._slice_index]
            if self._slice_paths
            else self._source_root or Path()
        )
        return render_loaded_ct_slice(
            width,
            height,
            current_path,
            self._slice_index,
            self._slice_count,
            loaded_image=None,
        )

    def _apply_zoom(self, delta_y: int, anchor: QPointF) -> bool:
        image = self._current_loaded_image()
        if image is None or image.isNull():
            return False
        zoom_factor = pow(1.12, delta_y / 120.0)
        next_zoom = max(
            MIN_VIEWPORT_ZOOM,
            min(MAX_VIEWPORT_ZOOM, self._zoom * zoom_factor),
        )
        if abs(next_zoom - self._zoom) < 1e-6:
            return False

        content_rect = self._content_rect()
        center_before = QPointF(
            content_rect.center().x() + self._pan_offset.x(),
            content_rect.center().y() + self._pan_offset.y(),
        )
        offset_x = anchor.x() - center_before.x()
        offset_y = anchor.y() - center_before.y()
        scale_ratio = next_zoom / max(self._zoom, 1e-6)
        center_after = QPointF(
            anchor.x() - offset_x * scale_ratio,
            anchor.y() - offset_y * scale_ratio,
        )
        self._pan_offset = QPointF(
            center_after.x() - content_rect.center().x(),
            center_after.y() - content_rect.center().y(),
        )
        self._zoom = next_zoom
        self.update()
        return True


class ImageViewport2D(QWidget):
    files_dropped = Signal(list)
    asset_dropped = Signal(str)
    browse_requested = Signal()
    activated = Signal()

    def __init__(
        self,
        title: str,
        projection: XrayProjection,
        *,
        empty_subtitle: str = "",
        empty_status: str = "Unassigned",
        allow_drop: bool = True,
    ) -> None:
        super().__init__()
        self._title = title
        self._empty_status = empty_status
        self._surface: QFrame | None = None
        self._transition_overlay: QLabel | None = None
        self._overlay_widgets: list[QWidget] = []
        self._gnomon_overlay: ViewportGnomonOverlay | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("ViewportOverlayChip")
        apply_text_role(self.title_label, "panel-title")

        self.status_label = QLabel(self._empty_status)
        self.status_label.setObjectName("ViewportOverlayStatus")
        apply_text_role(self.status_label, "meta")

        self.canvas = SliceCanvas(
            "xray",
            title,
            empty_subtitle,
            projection=projection,
            allow_drop=allow_drop,
        )
        self.canvas.files_dropped.connect(self.files_dropped.emit)
        self.canvas.asset_dropped.connect(self.asset_dropped.emit)
        self.canvas.browse_requested.connect(self.browse_requested.emit)
        self.canvas.activated.connect(self.activated.emit)

        surface = QFrame()
        surface.setObjectName("ViewportCardFrame")
        self._surface = surface
        surface_layout = QGridLayout(surface)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        surface_layout.setSpacing(0)
        surface_layout.addWidget(self.canvas, 0, 0)

        overlay = QFrame()
        overlay.setObjectName("ViewportOverlayBar")
        overlay_layout = QHBoxLayout(overlay)
        overlay_layout.setContentsMargins(
            GEOMETRY.overlay_padding,
            GEOMETRY.overlay_padding,
            GEOMETRY.overlay_padding,
            0,
        )
        overlay_layout.setSpacing(GEOMETRY.overlay_gap)
        overlay_layout.addWidget(self.title_label)
        overlay_layout.addStretch(1)
        overlay_layout.addWidget(self.status_label)
        surface_layout.addWidget(
            overlay,
            0,
            0,
            alignment=Qt.AlignmentFlag.AlignTop,
        )
        self._overlay_widgets.append(overlay)
        initial_view_kind = "lat" if projection == XrayProjection.LAT else "ap"
        self._gnomon_overlay = ViewportGnomonOverlay(self, view_kind=initial_view_kind)

        layout.addWidget(surface, stretch=1)

    def set_layout_transition_active(self, active: bool) -> None:
        surface = self._surface
        if surface is None:
            return
        if active:
            if self._transition_overlay is not None:
                return
            snapshot = self._capture_surface_snapshot()
            if snapshot.isNull():
                return
            overlay = QLabel(surface)
            overlay.setObjectName("ViewportTransitionOverlay")
            overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            overlay.setScaledContents(True)
            overlay.setPixmap(snapshot)
            overlay.setGeometry(surface.rect())
            self._transition_overlay = overlay
            self.canvas.hide()
            overlay.show()
            overlay.raise_()
            self._raise_overlay_widgets()
            return
        if self._transition_overlay is None:
            return
        self.canvas.show()
        self._transition_overlay.deleteLater()
        self._transition_overlay = None
        self._raise_overlay_widgets()
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._transition_overlay is not None and self._surface is not None:
            self._transition_overlay.setGeometry(self._surface.rect())
        if self._gnomon_overlay is not None:
            position_gnomon_overlay(self._gnomon_overlay, self._surface)
            self._gnomon_overlay.raise_()

    def set_asset(self, asset: StudyAsset | None) -> None:
        self.canvas.set_source(Path(asset.managed_path) if asset is not None else None)
        status_text = (
            Path(asset.managed_path).name if asset is not None else self._empty_status
        )
        self.status_label.setText(status_text)

    def _capture_surface_snapshot(self) -> QPixmap:
        surface = self._surface
        if surface is None:
            return QPixmap()
        for overlay_widget in self._overlay_widgets:
            overlay_widget.hide()
        try:
            return surface.grab()
        finally:
            self._raise_overlay_widgets()

    def _raise_overlay_widgets(self) -> None:
        for overlay_widget in self._overlay_widgets:
            overlay_widget.show()
            overlay_widget.raise_()
        if self._gnomon_overlay is not None:
            self._gnomon_overlay.show()
            self._gnomon_overlay.raise_()


class ZStackViewport2D(QWidget):
    slice_changed = Signal(int, int)
    files_dropped = Signal(list)
    asset_dropped = Signal(str)
    browse_requested = Signal()
    activated = Signal()

    def __init__(
        self,
        title: str,
        *,
        empty_subtitle: str = "",
        empty_status: str = "Unassigned",
        allow_drop: bool = True,
        use_external_slice_toolbar: bool = False,
    ) -> None:
        super().__init__()
        self._title = title
        self._empty_status = empty_status
        self._use_external_slice_toolbar = use_external_slice_toolbar
        self._surface: QFrame | None = None
        self._transition_overlay: QLabel | None = None
        self._overlay_widgets: list[QWidget] = []
        self._gnomon_overlay: ViewportGnomonOverlay | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("ViewportOverlayChip")
        apply_text_role(self.title_label, "panel-title")

        self.status_label = QLabel(self._empty_status)
        self.status_label.setObjectName("ViewportOverlayStatus")
        apply_text_role(self.status_label, "meta")

        self.canvas = SliceCanvas(
            "ct",
            title,
            empty_subtitle,
            allow_drop=allow_drop,
        )
        self.canvas.slice_changed.connect(self._handle_slice_changed)
        self.canvas.files_dropped.connect(self.files_dropped.emit)
        self.canvas.asset_dropped.connect(self.asset_dropped.emit)
        self.canvas.browse_requested.connect(self.browse_requested.emit)
        self.canvas.activated.connect(self.activated.emit)

        self._slice_slider = QSlider(Qt.Orientation.Horizontal)
        self._slice_slider.setObjectName("ViewportSliceSlider")
        self._slice_slider.setMinimum(1)
        self._slice_slider.setMaximum(1)
        self._slice_slider.setValue(1)
        self._slice_slider.setEnabled(False)
        self._slice_slider.valueChanged.connect(self._handle_slider_changed)
        self._slice_toolbar_group = self._build_slice_toolbar_group()

        surface = QFrame()
        surface.setObjectName("ViewportCardFrame")
        self._surface = surface
        surface_layout = QGridLayout(surface)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        surface_layout.setSpacing(0)
        surface_layout.addWidget(self.canvas, 0, 0)

        header_overlay = QFrame()
        header_overlay.setObjectName("ViewportOverlayBar")
        header_layout = QHBoxLayout(header_overlay)
        header_layout.setContentsMargins(
            GEOMETRY.overlay_padding,
            GEOMETRY.overlay_padding,
            GEOMETRY.overlay_padding,
            0,
        )
        header_layout.setSpacing(GEOMETRY.overlay_gap)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.status_label)
        surface_layout.addWidget(
            header_overlay,
            0,
            0,
            alignment=Qt.AlignmentFlag.AlignTop,
        )
        self._overlay_widgets.append(header_overlay)

        if not self._use_external_slice_toolbar:
            footer_overlay = QFrame()
            footer_overlay.setObjectName("ViewportOverlayFooter")
            footer_layout = QHBoxLayout(footer_overlay)
            footer_layout.setContentsMargins(
                GEOMETRY.overlay_padding,
                0,
                GEOMETRY.overlay_padding,
                GEOMETRY.overlay_padding,
            )
            footer_layout.setSpacing(0)
            footer_layout.addWidget(self._slice_toolbar_group, stretch=1)
            surface_layout.addWidget(
                footer_overlay,
                0,
                0,
                alignment=Qt.AlignmentFlag.AlignBottom,
            )
            self._overlay_widgets.append(footer_overlay)

        self._gnomon_overlay = ViewportGnomonOverlay(self, view_kind="axial")
        layout.addWidget(surface, stretch=1)

        self._handle_slice_changed(self.canvas.slice_index + 1, self.canvas.slice_count)

    def slice_toolbar_group(self) -> QFrame:
        return self._slice_toolbar_group

    def _build_slice_toolbar_group(self) -> QFrame:
        group = QFrame()
        group.setObjectName("CenterToolbarGroup")
        group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(group)
        layout.setContentsMargins(
            GEOMETRY.default_padding,
            GEOMETRY.inspector_row_gap,
            GEOMETRY.default_padding,
            GEOMETRY.inspector_row_gap,
        )
        layout.setSpacing(GEOMETRY.inspector_row_gap)
        layout.addWidget(self._slice_slider)
        return group

    def set_layout_transition_active(self, active: bool) -> None:
        surface = self._surface
        if surface is None:
            return
        if active:
            if self._transition_overlay is not None:
                return
            snapshot = self._capture_surface_snapshot()
            if snapshot.isNull():
                return
            overlay = QLabel(surface)
            overlay.setObjectName("ViewportTransitionOverlay")
            overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            overlay.setScaledContents(True)
            overlay.setPixmap(snapshot)
            overlay.setGeometry(surface.rect())
            self._transition_overlay = overlay
            self.canvas.hide()
            overlay.show()
            overlay.raise_()
            self._raise_overlay_widgets()
            return
        if self._transition_overlay is None:
            return
        self.canvas.show()
        self._transition_overlay.deleteLater()
        self._transition_overlay = None
        self._raise_overlay_widgets()
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._transition_overlay is not None and self._surface is not None:
            self._transition_overlay.setGeometry(self._surface.rect())
        if self._gnomon_overlay is not None:
            position_gnomon_overlay(self._gnomon_overlay, self._surface)
            self._gnomon_overlay.raise_()

    def set_asset(self, asset: StudyAsset | None) -> None:
        self.canvas.set_source(Path(asset.managed_path) if asset is not None else None)
        if asset is None:
            self.status_label.setText(self._empty_status)
            return
        self._handle_slice_changed(self.canvas.slice_index + 1, self.canvas.slice_count)

    def _handle_slice_changed(self, current_slice: int, slice_count: int) -> None:
        self._slice_slider.blockSignals(True)
        self._slice_slider.setMinimum(1)
        self._slice_slider.setMaximum(max(1, slice_count))
        self._slice_slider.setValue(max(1, current_slice))
        self._slice_slider.setEnabled(not self.canvas.is_empty and slice_count > 1)
        self._slice_slider.blockSignals(False)
        if self.canvas.is_empty:
            self.status_label.setText(self._empty_status)
        elif self._slice_name():
            self.status_label.setText(f"{self._slice_name()}  {current_slice}/{slice_count}")
        else:
            self.status_label.setText(f"Slice {current_slice}/{slice_count}")
        self.slice_changed.emit(current_slice, slice_count)

    def _handle_slider_changed(self, value: int) -> None:
        self.canvas.set_slice_index(value - 1)

    def _slice_name(self) -> str:
        if self.canvas.is_empty:
            return ""
        if self.canvas._slice_paths:
            return self.canvas._slice_paths[self.canvas.slice_index].name
        source_root = self.canvas._source_root
        return source_root.name if source_root is not None else ""

    def _capture_surface_snapshot(self) -> QPixmap:
        surface = self._surface
        if surface is None:
            return QPixmap()
        for overlay_widget in self._overlay_widgets:
            overlay_widget.hide()
        try:
            return surface.grab()
        finally:
            self._raise_overlay_widgets()

    def _raise_overlay_widgets(self) -> None:
        for overlay_widget in self._overlay_widgets:
            overlay_widget.show()
            overlay_widget.raise_()
        if self._gnomon_overlay is not None:
            self._gnomon_overlay.show()
            self._gnomon_overlay.raise_()


def resolve_slice_sources(source_root: Path | None) -> list[Path]:
    if source_root is None:
        return []
    if source_root.is_dir():
        return sorted(
            [path for path in source_root.iterdir() if path.is_file()],
            key=lambda path: path.name.lower(),
        )
    return [source_root]


def render_empty_placeholder(width: int, height: int, title: str, subtitle: str) -> QImage:
    del title
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    empty_bg = qcolor_from_css(THEME_COLORS.viewport_empty_bg)
    image.fill(empty_bg)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillRect(image.rect(), empty_bg)

    icon_rect = empty_placeholder_icon_rect(width, height)
    if EMPTY_STATE_ICON_PATH.exists():
        icon_pixmap = build_svg_pixmap(
            EMPTY_STATE_ICON_PATH,
            icon_rect.size(),
            device_pixel_ratio=1.0,
        )
        if not icon_pixmap.isNull():
            painter.drawPixmap(icon_rect, icon_pixmap)

    if subtitle:
        subtitle_font = painter.font()
        subtitle_font.setPointSize(11)
        painter.setFont(subtitle_font)
        painter.setPen(QPen(Qt.GlobalColor.gray))
        painter.drawText(
            empty_placeholder_subtitle_rect(width, height),
            Qt.AlignmentFlag.AlignCenter,
            subtitle,
        )
    painter.end()
    return image


def empty_placeholder_icon_rect(width: int, height: int) -> QRect:
    icon_size = min(72.0, max(40.0, min(width, height) * 0.22))
    return centered_square_rect(
        width,
        height,
        int(round(icon_size)),
    )


def empty_placeholder_subtitle_rect(width: int, height: int) -> QRectF:
    subtitle_height = GEOMETRY.control_height_sm
    subtitle_y = max(
        0,
        height - subtitle_height - (GEOMETRY.unit * 2),
    )
    return QRectF(
        0.0,
        float(subtitle_y),
        float(width),
        float(subtitle_height),
    )


def render_loaded_xray(
    width: int,
    height: int,
    source_path: Path,
    projection: XrayProjection | None,
    *,
    loaded_image: QImage | None = None,
) -> QImage:
    loaded = compose_loaded_raster(width, height, loaded_image or load_raster_image(source_path))
    if loaded is not None:
        return loaded
    return render_xray_image(width, height, projection or XrayProjection.AP, source_path.name)


def render_loaded_ct_slice(
    width: int,
    height: int,
    source_path: Path,
    slice_index: int,
    slice_count: int,
    *,
    loaded_image: QImage | None = None,
) -> QImage:
    loaded = compose_loaded_raster(
        width,
        height,
        loaded_image or load_ct_preview_image(source_path, slice_index),
    )
    if loaded is not None:
        return loaded
    return render_empty_placeholder(width, height, "CT", "Preview unavailable")


def load_ct_preview_image(source_path: Path, slice_index: int) -> QImage | None:
    descriptor = describe_display_stack(source_path, render_mode="ct")
    if descriptor is None:
        return None
    return load_display_slice(descriptor, slice_index)


def compose_loaded_raster(width: int, height: int, image: QImage | None) -> QImage | None:
    if image is None or image.isNull():
        return None
    canvas = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(qcolor_from_css(THEME_COLORS.viewport_bg))

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    fitted = image.scaled(
        width - GEOMETRY.unit * 4,
        height - GEOMETRY.unit * 4,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = (width - fitted.width()) // 2
    y = (height - fitted.height()) // 2
    painter.drawImage(x, y, fitted)
    painter.end()
    return canvas


def describe_display_stack(
    source_root: Path | None,
    *,
    render_mode: str,
) -> DisplayStackDescriptor | None:
    if source_root is None:
        return None
    cache_key = f"{render_mode}:{path_cache_key(source_root)}"
    cached_descriptor = _stack_descriptor_cache().get(cache_key)
    if cached_descriptor is not None:
        return cached_descriptor

    if render_mode == "xray":
        descriptor = DisplayStackDescriptor(
            kind="xray",
            source_path=source_root,
            slice_paths=[source_root],
            slice_count=1,
        )
        return _stack_descriptor_cache().put(cache_key, descriptor)

    if source_root.is_dir():
        slice_paths = resolve_slice_sources(source_root)
        if not slice_paths:
            return None
        descriptor = DisplayStackDescriptor(
            kind="directory",
            source_path=source_root,
            slice_paths=slice_paths,
            slice_count=len(slice_paths),
        )
        return _stack_descriptor_cache().put(cache_key, descriptor)

    suffix = normalized_suffix(source_root)
    if suffix in {".nii", ".nii.gz"}:
        volume_shape = nifti_stack_shape(source_root)
        if volume_shape is None:
            return None
        descriptor = DisplayStackDescriptor(
            kind="nifti",
            source_path=source_root,
            slice_paths=[source_root for _ in range(volume_shape[2])],
            slice_count=volume_shape[2],
        )
        return _stack_descriptor_cache().put(cache_key, descriptor)

    if suffix == ".dcm":
        slice_count = dicom_stack_depth(source_root)
        descriptor = DisplayStackDescriptor(
            kind="dicom-volume" if slice_count > 1 else "dicom-raster",
            source_path=source_root,
            slice_paths=[source_root for _ in range(slice_count)],
            slice_count=slice_count,
        )
        return _stack_descriptor_cache().put(cache_key, descriptor)

    descriptor = DisplayStackDescriptor(
        kind="raster",
        source_path=source_root,
        slice_paths=[source_root],
        slice_count=1,
    )
    return _stack_descriptor_cache().put(cache_key, descriptor)


def nifti_stack_shape(source_path: Path) -> tuple[int, int, int] | None:
    try:
        volume_image = cast(Any, nib.load(str(source_path)))
    except Exception:
        return None
    shape = tuple(int(value) for value in volume_image.shape[:3])
    if len(shape) != 3:
        return None
    return cast(tuple[int, int, int], shape)


def dicom_stack_depth(source_path: Path) -> int:
    try:
        dataset = pydicom.dcmread(
            str(source_path),
            stop_before_pixels=True,
            specific_tags=["NumberOfFrames"],
        )
    except Exception:
        return 1
    try:
        return max(1, int(getattr(dataset, "NumberOfFrames", 1) or 1))
    except Exception:
        return 1


def load_display_slice(
    descriptor: DisplayStackDescriptor,
    slice_index: int,
) -> QImage | None:
    if descriptor.kind in {"xray", "raster", "dicom-raster"}:
        return load_raster_image(descriptor.source_path)
    if descriptor.kind == "directory":
        if not descriptor.slice_paths:
            return None
        index = max(0, min(slice_index, len(descriptor.slice_paths) - 1))
        return load_raster_image(descriptor.slice_paths[index])
    if descriptor.kind == "nifti":
        return load_nifti_slice(descriptor.source_path, slice_index, descriptor.slice_count)
    if descriptor.kind == "dicom-volume":
        return load_dicom_volume_slice(
            descriptor.source_path,
            slice_index,
            descriptor.slice_count,
        )
    return None


def load_nifti_slice(
    source_path: Path,
    slice_index: int,
    slice_count: int,
) -> QImage | None:
    volume = load_cached_volume_array(source_path)
    if volume is None or volume.ndim != 3:
        return None
    index = max(0, min(slice_index, min(slice_count, volume.shape[2]) - 1))
    return qimage_from_array(np.rot90(volume[:, :, index]))


def load_dicom_volume_slice(
    source_path: Path,
    slice_index: int,
    slice_count: int,
) -> QImage | None:
    volume = load_cached_volume_array(source_path)
    if volume is None:
        return None
    if volume.ndim == 2:
        return qimage_from_array(volume)
    if volume.ndim != 3:
        return None
    index = max(0, min(slice_index, min(slice_count, volume.shape[0]) - 1))
    return qimage_from_array(volume[index])


def load_cached_volume_array(source_path: Path) -> np.ndarray | None:
    cache_key = path_cache_key(source_path)
    cached_volume = _volume_array_cache().get(cache_key)
    if cached_volume is not None:
        return cached_volume

    suffix = normalized_suffix(source_path)
    volume: np.ndarray | None
    if suffix in {".nii", ".nii.gz"}:
        try:
            volume_image = cast(Any, nib.load(str(source_path)))
            volume = np.asarray(volume_image.dataobj, dtype=np.float32)
        except Exception:
            return None
        if volume.ndim == 4:
            volume = volume[..., 0]
    elif suffix == ".dcm":
        try:
            dataset = pydicom.dcmread(str(source_path))
            volume = np.asarray(dataset.pixel_array, dtype=np.float32)
        except Exception:
            return None
    else:
        return None
    return _volume_array_cache().put(cache_key, volume)


def load_ct_stack_images(source_root: Path) -> tuple[list[Path], list[QImage]]:
    descriptor = describe_display_stack(source_root, render_mode="ct")
    if descriptor is None:
        return [], []
    loaded_slices = [
        image
        for slice_index in range(descriptor.slice_count)
        if (image := load_display_slice(descriptor, slice_index)) is not None
    ]
    return list(descriptor.slice_paths[: len(loaded_slices)]), loaded_slices


def load_raster_image(source_path: Path) -> QImage | None:
    if not source_path.is_file():
        return None
    cache_key = path_cache_key(source_path)
    cached_image = _raster_image_cache().get(cache_key)
    if cached_image is not None:
        return QImage(cached_image)
    suffix = normalized_suffix(source_path)
    if suffix == ".dcm":
        try:
            dataset = pydicom.dcmread(str(source_path))
            image = qimage_from_array(np.asarray(dataset.pixel_array, dtype=np.float32))
            _raster_image_cache().put(cache_key, QImage(image))
            return QImage(image)
        except Exception:
            return None

    image = QImage(str(source_path))
    if image.isNull():
        return None
    _raster_image_cache().put(cache_key, QImage(image))
    return image


def normalized_suffix(source_path: Path) -> str:
    return "".join(source_path.suffixes).lower()


def qimage_from_array(array: np.ndarray) -> QImage:
    pixel_data = np.nan_to_num(np.asarray(array, dtype=np.float32), nan=0.0)
    if pixel_data.ndim == 3:
        pixel_data = pixel_data[:, :, 0]

    if pixel_data.size == 0:
        normalized = np.zeros((1, 1), dtype=np.uint8)
    else:
        min_value = float(np.min(pixel_data))
        max_value = float(np.max(pixel_data))
        if max_value <= min_value:
            normalized = np.zeros(pixel_data.shape, dtype=np.uint8)
        else:
            normalized = np.clip(
                ((pixel_data - min_value) / (max_value - min_value)) * 255.0,
                0.0,
                255.0,
            ).astype(np.uint8)

    contiguous = np.ascontiguousarray(normalized)
    height, width = contiguous.shape
    image = QImage(
        contiguous.data,
        width,
        height,
        contiguous.strides[0],
        QImage.Format.Format_Grayscale8,
    )
    return image.copy()


def render_xray_image(
    width: int,
    height: int,
    projection: XrayProjection,
    file_name: str = "",
) -> QImage:
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(qRgb(10, 10, 10))

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    painter.fillRect(image.rect(), qRgb(18, 18, 18))
    painter.setPen(QPen(Qt.GlobalColor.gray, 2))
    painter.drawRoundedRect(18, 18, width - 36, height - 36, 18, 18)

    if projection == XrayProjection.AP:
        center_x = width / 2
        painter.setPen(QPen(Qt.GlobalColor.lightGray, 6))
        points = [
            QPointF(center_x, height * 0.12),
            QPointF(center_x - 12, height * 0.28),
            QPointF(center_x + 10, height * 0.44),
            QPointF(center_x - 8, height * 0.62),
            QPointF(center_x, height * 0.92),
        ]
        painter.drawPolyline(points)
        painter.setPen(QPen(Qt.GlobalColor.darkGray, 2))
        for row in range(9):
            top = height * (0.18 + row * 0.07)
            rect = QRectF(center_x - 42, top, 84, 18)
            painter.drawRoundedRect(rect, 8, 8)
        painter.drawEllipse(QRectF(center_x - 92, height * 0.16, 64, 120))
        painter.drawEllipse(QRectF(center_x + 28, height * 0.16, 64, 120))
    else:
        center_x = width * 0.56
        painter.setPen(QPen(Qt.GlobalColor.lightGray, 6))
        points = [
            QPointF(center_x - 10, height * 0.12),
            QPointF(center_x + 16, height * 0.30),
            QPointF(center_x - 20, height * 0.46),
            QPointF(center_x + 8, height * 0.62),
            QPointF(center_x - 4, height * 0.92),
        ]
        painter.drawPolyline(points)
        painter.setPen(QPen(Qt.GlobalColor.darkGray, 2))
        for row in range(9):
            top = height * (0.18 + row * 0.07)
            rect = QRectF(center_x - 64, top, 92, 16)
            painter.drawRoundedRect(rect, 8, 8)

    if file_name:
        painter.setPen(QPen(Qt.GlobalColor.gray))
        painter.drawText(
            QRectF(24, height - 40, width - 48, 24),
            Qt.AlignmentFlag.AlignCenter,
            file_name,
        )

    painter.end()
    return image


