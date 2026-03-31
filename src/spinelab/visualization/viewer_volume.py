from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np
import pydicom
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImageReader
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from spinelab.models import VolumeMetadata
from spinelab.services import BoundedCache, performance_coordinator
from spinelab.ui.theme import GEOMETRY, THEME_COLORS
from spinelab.ui.widgets import CapsuleButton, apply_text_role
from spinelab.visualization.viewer_2d import load_cached_volume_array, resolve_slice_sources
from spinelab.visualization.viewer_3d import SelectableQtInteractor, ViewportMode, pv
from spinelab.visualization.viewport_theme import VIEWPORT_BACKGROUND

VOLUME_RENDER_MODES = ("slice", "volume", "isosurface")
VOLUME_PRESETS = ("bone", "soft")


def _estimate_stack_volume_bytes(volume: np.ndarray) -> int:
    return int(volume.nbytes)


def _stack_volume_cache() -> BoundedCache[str, np.ndarray]:
    policy = performance_coordinator().active_policy
    return performance_coordinator().get_cache(
        "viewer-volume-stack",
        max_bytes=policy.active_volume_cache_budget_bytes,
        estimate_size=_estimate_stack_volume_bytes,
    )


def _read_qimage_array(path: Path) -> np.ndarray | None:
    reader = QImageReader(str(path))
    image = reader.read()
    if image.isNull():
        return None
    converted = image.convertToFormat(image.Format.Format_Grayscale8)
    buffer_any: Any = converted.bits()
    buffer_any.setsize(converted.sizeInBytes())
    array = np.frombuffer(buffer_any, dtype=np.uint8).reshape(
        converted.height(),
        converted.bytesPerLine(),
    )
    return array[:, : converted.width()].copy()


def _read_slice_array(path: Path) -> np.ndarray | None:
    if path.suffix.lower() == ".dcm":
        try:
            dataset = pydicom.dcmread(str(path))
        except Exception:
            return None
        try:
            return np.asarray(dataset.pixel_array)
        except Exception:
            return None
    return _read_qimage_array(path)


def _load_stack_volume(path: Path) -> np.ndarray | None:
    cache_key = str(path.resolve())
    cached_volume = _stack_volume_cache().get(cache_key)
    if cached_volume is not None:
        return cached_volume
    slice_paths = resolve_slice_sources(path)
    if not slice_paths:
        return None
    slices = [
        slice_array
        for file_path in slice_paths
        if (slice_array := _read_slice_array(file_path)) is not None
    ]
    if not slices:
        return None
    return _stack_volume_cache().put(cache_key, np.stack(slices, axis=-1))


def _load_volume_array(volume: VolumeMetadata | None) -> np.ndarray | None:
    if volume is None:
        return None
    source_path = Path(volume.canonical_path)
    suffix = "".join(source_path.suffixes).lower()
    if source_path.is_file() and suffix in {".nii", ".nii.gz"}:
        return load_cached_volume_array(source_path)
    if source_path.is_file() and suffix == ".dcm":
        return load_cached_volume_array(source_path)
    if source_path.is_dir():
        return _load_stack_volume(source_path)
    if source_path.is_file():
        return _read_slice_array(source_path)
    return None


class VolumeViewport3D(QWidget):
    selection_changed = Signal(str, bool)
    mode_changed = Signal(object)
    detail_level_changed = Signal(int)

    def __init__(self, title: str, volume: VolumeMetadata | None = None) -> None:
        super().__init__()
        self._title = title
        self._volume_metadata = volume
        self._mode = ViewportMode.SOLID
        self._detail_level = 2
        self._render_mode = "volume"
        self._preset = "bone"
        self._slab_percent = 100
        self._disposed = False
        self._plotter = None
        self._volume_grid = self._build_volume_grid(volume)
        self._slab_rebuild_timer = self._build_slab_rebuild_timer()

        self._mode_buttons: dict[str, CapsuleButton] = {}
        self._preset_buttons: dict[str, CapsuleButton] = {}
        self._slab_slider = QSlider(Qt.Orientation.Horizontal)
        self._slab_slider.setRange(20, 100)
        self._slab_slider.setValue(self._slab_percent)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        surface = QFrame(self)
        surface.setObjectName("ViewportCardFrame")
        surface_layout = QGridLayout(surface)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        surface_layout.setSpacing(0)
        root_layout.addWidget(surface, stretch=1)

        toolbar = self._build_toolbar()
        slider_bar = self._build_slider_bar()
        self._slab_slider.valueChanged.connect(self._handle_slab_value_changed)
        self._refresh_button_states()

        offscreen = os.environ.get("QT_QPA_PLATFORM", "").lower() in {"offscreen", "minimal"}
        if SelectableQtInteractor is None or pv is None or offscreen:
            self._build_fallback(surface_layout)
            surface_layout.addWidget(toolbar, 0, 0, alignment=Qt.AlignmentFlag.AlignTop)
            surface_layout.addWidget(slider_bar, 0, 0, alignment=Qt.AlignmentFlag.AlignBottom)
            return

        self._plotter = SelectableQtInteractor(self)
        self._plotter.set_background(VIEWPORT_BACKGROUND)
        self._plotter.enable_trackball_style()
        surface_layout.addWidget(self._plotter, 0, 0)
        surface_layout.addWidget(toolbar, 0, 0, alignment=Qt.AlignmentFlag.AlignTop)
        surface_layout.addWidget(slider_bar, 0, 0, alignment=Qt.AlignmentFlag.AlignBottom)
        toolbar.raise_()
        slider_bar.raise_()
        self._rebuild_scene()

    def _build_toolbar(self) -> QFrame:
        toolbar = QFrame()
        toolbar.setObjectName("ViewportOverlayBar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(
            GEOMETRY.overlay_padding,
            GEOMETRY.overlay_padding,
            GEOMETRY.overlay_padding,
            0,
        )
        toolbar_layout.setSpacing(GEOMETRY.overlay_gap)

        title_label = QLabel(self._title)
        title_label.setObjectName("ViewportOverlayChip")
        apply_text_role(title_label, "panel-title")
        toolbar_layout.addWidget(title_label)

        for mode in VOLUME_RENDER_MODES:
            button = CapsuleButton(mode.title(), checkable=True)
            button.clicked.connect(
                lambda checked=False, selected_mode=mode: self.set_render_mode(
                    selected_mode
                )
            )
            self._mode_buttons[mode] = button
            toolbar_layout.addWidget(button)

        toolbar_layout.addStretch(1)

        for preset in VOLUME_PRESETS:
            button = CapsuleButton(preset.title(), checkable=True)
            button.clicked.connect(
                lambda checked=False, selected_preset=preset: self.set_intensity_preset(
                    selected_preset
                )
            )
            self._preset_buttons[preset] = button
            toolbar_layout.addWidget(button)

        return toolbar

    def _build_slider_bar(self) -> QFrame:
        slider_bar = QFrame()
        slider_bar.setObjectName("ViewportOverlayBar")
        slider_layout = QHBoxLayout(slider_bar)
        slider_layout.setContentsMargins(
            GEOMETRY.overlay_padding,
            0,
            GEOMETRY.overlay_padding,
            GEOMETRY.overlay_padding,
        )
        slider_layout.setSpacing(GEOMETRY.overlay_gap)

        slab_label = QLabel("Slab")
        slab_label.setObjectName("ViewportOverlayChip")
        apply_text_role(slab_label, "micro")
        slider_layout.addWidget(slab_label)
        slider_layout.addWidget(self._slab_slider, stretch=1)
        return slider_bar

    def _build_slab_rebuild_timer(self):
        from PySide6.QtCore import QTimer

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(40)
        timer.timeout.connect(self._rebuild_scene)
        return timer

    def _build_fallback(self, surface_layout: QGridLayout) -> None:
        fallback = QFrame()
        fallback.setObjectName("ViewportFallback")
        fallback_layout = QVBoxLayout(fallback)
        fallback_layout.setContentsMargins(
            GEOMETRY.unit * 2,
            GEOMETRY.unit * 2,
            GEOMETRY.unit * 2,
            GEOMETRY.unit * 2,
        )
        fallback_layout.addStretch(1)
        label = QLabel("Volume rendering unavailable")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_text_role(label, "body")
        fallback_layout.addWidget(label)
        fallback_layout.addStretch(1)
        surface_layout.addWidget(fallback, 0, 0)

    def _build_volume_grid(self, volume: VolumeMetadata | None):
        if pv is None:
            return None
        volume_array = _load_volume_array(volume)
        if volume_array is None:
            return None
        normalized = np.asarray(volume_array)
        if normalized.ndim == 2:
            normalized = normalized[:, :, np.newaxis]
        grid = pv.wrap(normalized)
        spacing = (
            volume.voxel_spacing
            if volume is not None and volume.voxel_spacing
            else (1.0, 1.0, 1.0)
        )
        grid.spacing = spacing
        return grid

    def _window_range(self) -> tuple[float, float]:
        volume = self._volume_metadata
        if volume is not None and volume.value_range is not None:
            low, high = volume.value_range
        elif self._volume_grid is not None:
            values = np.asarray(self._volume_grid["values"])
            low, high = float(values.min()), float(values.max())
        else:
            low, high = 0.0, 1.0
        if high <= low:
            high = low + 1.0
        span = high - low
        if self._preset == "soft":
            return low, low + (span * 0.55)
        return low + (span * 0.20), high

    def _prepared_grid(self):
        if self._volume_grid is None or pv is None:
            return None
        dimensions = self._volume_grid.dimensions
        if len(dimensions) < 3 or dimensions[2] <= 1 or self._slab_percent >= 100:
            return self._volume_grid
        z_max = max(int(dimensions[2]) - 1, 1)
        upper_index = max(1, int(round(z_max * (self._slab_percent / 100.0))))
        return self._volume_grid.extract_subset(
            (
                0,
                int(dimensions[0]) - 1,
                0,
                int(dimensions[1]) - 1,
                0,
                upper_index,
            )
        )

    def _isosurface_value(self, low: float, high: float) -> float:
        return low + ((high - low) * (0.72 if self._preset == "bone" else 0.40))

    def _refresh_button_states(self) -> None:
        for mode, button in self._mode_buttons.items():
            button.setChecked(mode == self._render_mode)
        for preset, button in self._preset_buttons.items():
            button.setChecked(preset == self._preset)

    def _rebuild_scene(self) -> None:
        if self._disposed or self._plotter is None or pv is None:
            return
        self._plotter.clear()
        self._plotter.set_background(VIEWPORT_BACKGROUND)
        dataset = self._prepared_grid()
        if dataset is None:
            self._plotter.render()
            return

        low, high = self._window_range()
        if self._render_mode == "slice":
            slice_mesh = dataset.slice_orthogonal(
                x=float(dataset.center[0]),
                y=float(dataset.center[1]),
                z=float(dataset.center[2]),
            ).combine()
            self._plotter.add_mesh(
                slice_mesh,
                scalars="values",
                cmap="bone" if self._preset == "bone" else "gray",
                clim=(low, high),
                show_scalar_bar=False,
                lighting=False,
                reset_camera=False,
            )
        elif self._render_mode == "isosurface":
            contour = dataset.contour(isosurfaces=[self._isosurface_value(low, high)])
            self._plotter.add_mesh(
                contour,
                color=(
                    THEME_COLORS.text_primary
                    if self._preset == "bone"
                    else THEME_COLORS.info
                ),
                opacity=1.0,
                smooth_shading=False,
                show_edges=False,
                reset_camera=False,
            )
        else:
            self._plotter.add_volume(
                dataset,
                scalars="values",
                cmap="bone" if self._preset == "bone" else "gray",
                clim=(low, high),
                opacity="sigmoid_6" if self._preset == "bone" else "linear",
                shade=False,
                reset_camera=False,
            )

        self._plotter.reset_camera()
        self._plotter.render()

    def _handle_slab_value_changed(self, value: int) -> None:
        self._slab_percent = int(value)
        self._slab_rebuild_timer.start()

    def set_render_mode(self, render_mode: str) -> None:
        if render_mode not in VOLUME_RENDER_MODES or render_mode == self._render_mode:
            return
        self._render_mode = render_mode
        self._refresh_button_states()
        self._rebuild_scene()

    def current_render_mode(self) -> str:
        return self._render_mode

    def set_intensity_preset(self, preset: str) -> None:
        if preset not in VOLUME_PRESETS or preset == self._preset:
            return
        self._preset = preset
        self._refresh_button_states()
        self._rebuild_scene()

    def current_intensity_preset(self) -> str:
        return self._preset

    def set_selection(
        self,
        selected_ids,
        *,
        active_id: str | None,
        reference_id: str | None,
        isolate_selection: bool,
        emit_signal: bool = False,
    ) -> None:
        del selected_ids
        del active_id
        del reference_id
        del isolate_selection
        del emit_signal

    def select_model(self, vertebra_id: str, *, emit_signal: bool = True) -> None:
        del vertebra_id
        del emit_signal

    def set_mode(self, mode: ViewportMode) -> None:
        self._mode = mode

    def current_mode(self) -> ViewportMode:
        return self._mode

    def set_detail_level(self, level: int) -> None:
        self._detail_level = int(level)

    def current_detail_level(self) -> int:
        return self._detail_level

    def set_volume(self, volume: VolumeMetadata | None) -> None:
        self._volume_metadata = volume
        self._volume_grid = self._build_volume_grid(volume)
        self._rebuild_scene()

    def export_screenshot(self, output_path: Path) -> None:
        if self._plotter is not None:
            self._plotter.screenshot(str(output_path))

    def closeEvent(self, event) -> None:
        self.dispose()
        super().closeEvent(event)

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        plotter = self._plotter
        self._plotter = None
        if plotter is not None:
            try:
                plotter.close()
            except Exception:
                pass
            try:
                plotter.Finalize()
            except Exception:
                pass
