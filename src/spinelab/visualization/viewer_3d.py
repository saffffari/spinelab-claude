from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path
from typing import Any, cast

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QSize, Qt, Signal
from PySide6.QtGui import QHideEvent, QMouseEvent, QPixmap, QShowEvent, QWheelEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from spinelab.services import BoundedCache, performance_coordinator
from spinelab.ui.svg_icons import build_svg_icon
from spinelab.ui.theme import GEOMETRY, TEXT_STYLES, THEME_COLORS
from spinelab.ui.widgets import CapsuleButton, apply_text_role
from spinelab.visualization.measurement_overlays import OverlayGeometry
from spinelab.visualization.viewport_gnomon import (
    ViewportGnomonOverlay,
    position_gnomon_overlay,
)
from spinelab.visualization.viewport_theme import (
    VIEWPORT_BACKGROUND,
    VIEWPORT_GRID_MAJOR_COLOR,
    VIEWPORT_GRID_MINOR_COLOR,
    VIEWPORT_MODES,
    ViewportMode,
    ViewportRenderMode,
    resolve_mesh_visual_colors,
    resolve_mode_edge_color,
)

pv: Any = None
trimesh: Any = None
QtInteractor: Any = None
SelectableQtInteractor: Any = None
PanOnlyQtInteractor: Any = None
PanZoomQtInteractor: Any = None

VIEWPORT_MODE_ICON_PATHS = {
    ViewportMode.WIRE: Path(__file__).resolve().parents[1]
    / "ui"
    / "assets"
    / "fluent-table-simple-regular-48.svg",
    ViewportMode.SOLID: Path(__file__).resolve().parents[1]
    / "ui"
    / "assets"
    / "fluent-table-simple-filled-48.svg",
    ViewportMode.TRANSPARENT: Path(__file__).resolve().parents[1]
    / "ui"
    / "assets"
    / "fluent-table-simple-filled-soft-48.svg",
    ViewportMode.POINTS: Path(__file__).resolve().parents[1]
    / "ui"
    / "assets"
    / "viewport-points-48.svg",
}

def _import_optional_viewer_backends() -> tuple[Any, Any, Any]:
    pv_module: Any = None
    trimesh_module: Any = None
    qt_interactor: Any = None
    try:
        import pyvista as imported_pyvista
    except ImportError:  # pragma: no cover - local runtime guard
        pass
    else:
        pv_module = imported_pyvista
    try:
        import trimesh as imported_trimesh
    except ImportError:  # pragma: no cover - local runtime guard
        pass
    else:
        trimesh_module = imported_trimesh
    try:
        from pyvistaqt import QtInteractor as imported_qt_interactor
    except ImportError:  # pragma: no cover - local runtime guard
        pass
    else:
        qt_interactor = imported_qt_interactor
    return pv_module, trimesh_module, qt_interactor


pv, trimesh, QtInteractor = _import_optional_viewer_backends()

if QtInteractor is not None:

    class _SelectableQtInteractor(QtInteractor):
        background_clicked = Signal()

        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self._press_position = QPoint()
            self._pick_handled = False
            self._dragged = False
            self._remove_requested = False
            self._set_primary_requested = False
            self._middle_dragging = False
            self._last_middle_position = QPointF()
            self._right_dragging = False
            self._last_right_position = QPointF()

        def mark_pick_handled(self) -> None:
            self._pick_handled = True

        def remove_requested(self) -> bool:
            return self._remove_requested

        def set_primary_requested(self) -> bool:
            return self._set_primary_requested

        def mousePressEvent(self, event: QMouseEvent) -> None:
            if event.button() == Qt.MouseButton.MiddleButton:
                self._middle_dragging = True
                self._last_middle_position = event.position()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
            if event.button() == Qt.MouseButton.RightButton:
                self._right_dragging = True
                self._last_right_position = event.position()
                self.setCursor(Qt.CursorShape.SizeHorCursor)
                event.accept()
                return
            if event.button() == Qt.MouseButton.LeftButton:
                self._press_position = event.position().toPoint()
                self._pick_handled = False
                self._dragged = False
                self._remove_requested = bool(
                    event.modifiers() & Qt.KeyboardModifier.ControlModifier
                )
                self._set_primary_requested = bool(
                    event.modifiers() & Qt.KeyboardModifier.AltModifier
                )
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event: QMouseEvent) -> None:
            if self._middle_dragging and event.buttons() & Qt.MouseButton.MiddleButton:
                delta = event.position() - self._last_middle_position
                self._last_middle_position = event.position()
                if abs(delta.x()) > 0.0 or abs(delta.y()) > 0.0:
                    pan_camera_from_screen_delta(self, delta.x(), delta.y())
                    self.render()
                event.accept()
                return
            if self._right_dragging and event.buttons() & Qt.MouseButton.RightButton:
                delta = event.position() - self._last_right_position
                self._last_right_position = event.position()
                if abs(delta.x()) > 0.0:
                    orbit_camera_about_up_axis(self, delta.x())
                    self.render()
                event.accept()
                return
            if (
                event.buttons() & Qt.MouseButton.LeftButton
                and (event.position().toPoint() - self._press_position).manhattanLength() > 4
            ):
                self._dragged = True
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event: QMouseEvent) -> None:
            if event.button() == Qt.MouseButton.MiddleButton and self._middle_dragging:
                self._middle_dragging = False
                self.unsetCursor()
                event.accept()
                return
            if event.button() == Qt.MouseButton.RightButton and self._right_dragging:
                self._right_dragging = False
                self.unsetCursor()
                event.accept()
                return
            super().mouseReleaseEvent(event)
            if (
                event.button() == Qt.MouseButton.LeftButton
                and not self._pick_handled
                and not self._dragged
            ):
                self.background_clicked.emit()

    class _PanOnlyQtInteractor(_SelectableQtInteractor):
        def wheelEvent(self, event: QWheelEvent) -> None:
            event.ignore()

        def mousePressEvent(self, event: QMouseEvent) -> None:
            if event.button() == Qt.MouseButton.RightButton:
                event.ignore()
                return
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event: QMouseEvent) -> None:
            if event.buttons() & Qt.MouseButton.RightButton:
                event.ignore()
                return
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event: QMouseEvent) -> None:
            if event.button() == Qt.MouseButton.RightButton:
                event.ignore()
                return
            super().mouseReleaseEvent(event)

    class _PanZoomQtInteractor(_SelectableQtInteractor):
        def wheelEvent(self, event: QWheelEvent) -> None:
            delta_y = event.angleDelta().y()
            if delta_y == 0:
                event.ignore()
                return
            current_scale = float(getattr(self.camera, "parallel_scale", 1.0))
            self.camera.parallel_scale = orthographic_zoom_scale(current_scale, delta_y)
            self.render()
            event.accept()

        def mousePressEvent(self, event: QMouseEvent) -> None:
            if event.button() == Qt.MouseButton.RightButton:
                event.ignore()
                return
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event: QMouseEvent) -> None:
            if event.buttons() & Qt.MouseButton.RightButton:
                event.ignore()
                return
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event: QMouseEvent) -> None:
            if event.button() == Qt.MouseButton.RightButton:
                event.ignore()
                return
            super().mouseReleaseEvent(event)

    SelectableQtInteractor = _SelectableQtInteractor
    PanOnlyQtInteractor = _PanOnlyQtInteractor
    PanZoomQtInteractor = _PanZoomQtInteractor


@dataclass(frozen=True)
class MockVertebra:
    vertebra_id: str
    label: str
    center: tuple[float, float, float]
    extents: tuple[float, float, float]
    mesh_path: str | None = None
    selectable: bool = True
    render_id: str | None = None
    selection_id: str | None = None
    pose_name: str = "baseline"
    mesh_data: Any | None = None
    mesh_transform: tuple[tuple[float, float, float, float], ...] | None = None

    @property
    def actor_id(self) -> str:
        return self.render_id or self.vertebra_id

    @property
    def selection_key(self) -> str | None:
        if self.selection_id is not None:
            return self.selection_id
        if self.selectable:
            return self.vertebra_id
        return None


DEMO_VERTEBRAE = [
    MockVertebra("L1", "L1", (0.0, 0.0, 2.6), (1.8, 1.2, 0.8)),
    MockVertebra("L2", "L2", (0.0, 0.0, 1.4), (2.0, 1.3, 0.85)),
    MockVertebra("L3", "L3", (0.0, 0.0, 0.1), (2.1, 1.4, 0.9)),
    MockVertebra("L4", "L4", (0.0, 0.0, -1.3), (2.2, 1.45, 0.95)),
    MockVertebra("L5", "L5", (0.0, 0.0, -2.8), (2.3, 1.55, 1.0)),
]

VERTEBRA_INDEX = {spec.vertebra_id: spec for spec in DEMO_VERTEBRAE}
REFERENCE_AXIS_LENGTH = max(max(spec.extents) for spec in DEMO_VERTEBRAE) * 0.8
STANDING_SUFFIX = "_STANDING"
GLB_TO_VIEWPORT_TRANSFORM = np.array(
    [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, -1.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ],
    dtype=float,
)

def _estimate_mesh_bytes(mesh: Any) -> int:
    if mesh is None:
        return 0
    try:
        return int(mesh.GetActualMemorySize()) * 1024
    except Exception:
        pass
    try:
        points = np.asarray(mesh.points)
        return int(points.nbytes)
    except Exception:
        return 0



def _mesh_cache() -> BoundedCache[str, Any]:
    policy = performance_coordinator().active_policy
    return performance_coordinator().get_cache(
        "viewer-3d-mesh",
        max_bytes=policy.raw_mesh_cache_budget_bytes,
        estimate_size=_estimate_mesh_bytes,
    )


def _lod_mesh_cache() -> BoundedCache[tuple[str, int], Any]:
    policy = performance_coordinator().active_policy
    return performance_coordinator().get_cache(
        "viewer-3d-lod-mesh",
        max_bytes=policy.lod_mesh_cache_budget_bytes,
        estimate_size=_estimate_mesh_bytes,
    )
DETAIL_LEVEL_REDUCTIONS: dict[int, float] = {
    0: 0.94,
    1: 0.82,
    2: 0.58,
    3: 0.0,
}
DEFAULT_DETAIL_LEVEL = 2
DETAIL_PRESET_LEVELS: tuple[tuple[str, int], ...] = (
    ("Low", 0),
    ("Med", DEFAULT_DETAIL_LEVEL),
    ("High", max(DETAIL_LEVEL_REDUCTIONS)),
)
VIEWPORT_CAMERA_MODES = ("perspective", "front", "side", "top")


def coerce_selected_ids(candidate_ids: Iterable[str], valid_ids: set[str]) -> tuple[str, ...]:
    ordered_ids: list[str] = []
    seen: set[str] = set()
    for vertebra_id in candidate_ids:
        if vertebra_id in valid_ids and vertebra_id not in seen:
            seen.add(vertebra_id)
            ordered_ids.append(vertebra_id)
    return tuple(ordered_ids)


def normalize_camera_mode(mode: str) -> str:
    normalized = mode.strip().lower()
    return normalized if normalized in VIEWPORT_CAMERA_MODES else "perspective"


def pose_visible_for_name(
    pose_name: str,
    *,
    baseline_visible: bool,
    standing_visible: bool,
) -> bool:
    return standing_visible if pose_name == "standing" else baseline_visible


def resolve_viewport_fallback_message(
    *,
    interactive_enabled: bool,
    fallback_message: str | None,
    offscreen: bool,
    backend_available: bool,
) -> str:
    if fallback_message:
        return fallback_message
    if not interactive_enabled:
        return "Interactive 3D disabled."
    if offscreen:
        return "Interactive 3D unavailable in offscreen mode."
    if not backend_available:
        return "Interactive 3D backend is unavailable in this environment."
    return "Interactive 3D is unavailable."


def load_cached_mesh(mesh_path: Path):
    if pv is None or not mesh_path.is_file():
        return None
    cache_key = str(mesh_path.resolve())
    cached_mesh = _mesh_cache().get(cache_key)
    if cached_mesh is None:
        try:
            cached_mesh = pv.read(mesh_path)
        except Exception:
            return None
        _mesh_cache().put(cache_key, cached_mesh)
    try:
        return cached_mesh.copy(deep=True)
    except Exception:
        return cached_mesh.copy()


def copy_mesh_data(mesh: Any):
    if mesh is None:
        return None
    try:
        return mesh.copy(deep=True)
    except Exception:
        return mesh.copy()


def coerce_detail_level(level: int) -> int:
    return max(min(int(level), max(DETAIL_LEVEL_REDUCTIONS)), min(DETAIL_LEVEL_REDUCTIONS))


def mesh_detail_reduction(level: int) -> float:
    return DETAIL_LEVEL_REDUCTIONS[coerce_detail_level(level)]


def detail_preset_level(level: int) -> int:
    normalized_level = coerce_detail_level(level)
    if normalized_level >= DETAIL_PRESET_LEVELS[-1][1]:
        return DETAIL_PRESET_LEVELS[-1][1]
    if normalized_level >= DETAIL_PRESET_LEVELS[1][1]:
        return DETAIL_PRESET_LEVELS[1][1]
    return DETAIL_PRESET_LEVELS[0][1]


def mesh_cache_key_for_spec(spec: MockVertebra) -> str:
    if spec.mesh_path:
        try:
            resolved = str(Path(spec.mesh_path).resolve())
        except Exception:
            resolved = spec.mesh_path
        return f"{resolved}::{spec.actor_id}::{spec.pose_name}"
    return (
        f"{spec.pose_name}::{spec.actor_id}::"
        f"{spec.center[0]:.4f},{spec.center[1]:.4f},{spec.center[2]:.4f}::"
        f"{spec.extents[0]:.4f},{spec.extents[1]:.4f},{spec.extents[2]:.4f}"
    )


def build_detail_mesh(mesh: Any, level: int):
    if pv is None or mesh is None:
        return None
    reduction = mesh_detail_reduction(level)
    base_mesh = copy_mesh_data(mesh)
    if base_mesh is None:
        return None
    if reduction <= 0:
        return base_mesh
    try:
        if not isinstance(base_mesh, pv.PolyData):
            base_mesh = base_mesh.extract_surface()
        base_mesh = base_mesh.triangulate().clean()
        if getattr(base_mesh, "n_cells", 0) <= 8:
            return base_mesh
        reduced_mesh = base_mesh.decimate(
            reduction,
            volume_preservation=True,
            inplace=False,
        )
        if reduced_mesh is not None and getattr(reduced_mesh, "n_cells", 0) > 0:
            return reduced_mesh.clean()
    except Exception:
        return base_mesh
    return base_mesh


def load_lod_mesh(spec: MockVertebra, base_mesh: Any, detail_level: int):
    if base_mesh is None:
        return None
    normalized_level = coerce_detail_level(detail_level)
    cache_key = (mesh_cache_key_for_spec(spec), normalized_level)
    cached_mesh = _lod_mesh_cache().get(cache_key)
    if cached_mesh is None:
        cached_mesh = build_detail_mesh(base_mesh, normalized_level)
        if cached_mesh is None:
            return None
        _lod_mesh_cache().put(cache_key, cached_mesh)
    return copy_mesh_data(cached_mesh)


def prewarm_lod_mesh_cache(
    models: Iterable[MockVertebra],
    *,
    detail_levels: Iterable[int] | None = None,
    max_workers: int | None = None,
) -> None:
    if pv is None:
        return
    resolved_levels = tuple(
        dict.fromkeys(
            coerce_detail_level(level)
            for level in (
                detail_levels
                if detail_levels is not None
                else tuple(level for _label, level in DETAIL_PRESET_LEVELS)
            )
        )
    )
    if not resolved_levels:
        return

    model_specs = list(models)
    if not model_specs:
        return

    def prewarm_spec(spec: MockVertebra) -> None:
        base_mesh = build_mock_mesh(spec)
        if base_mesh is None:
            return
        for level in resolved_levels:
            load_lod_mesh(spec, base_mesh, level)
    
    resolved_workers = max(1, int(max_workers or 1))
    if resolved_workers <= 1 or len(model_specs) <= 1:
        for spec in model_specs:
            prewarm_spec(spec)
        return

    executor = performance_coordinator().lod_prewarm_executor()
    futures = [executor.submit(prewarm_spec, spec) for spec in model_specs]
    for future in futures:
        future.result()


def build_spec_from_mesh(
    mesh: Any,
    *,
    vertebra_id: str,
    label: str,
    mesh_path: str | None = None,
    selectable: bool = True,
    render_id: str | None = None,
    selection_id: str | None = None,
    pose_name: str = "baseline",
) -> MockVertebra | None:
    if mesh is None:
        return None
    bounds = tuple(float(value) for value in mesh.bounds)
    return MockVertebra(
        vertebra_id=vertebra_id,
        label=label,
        center=(
            float(mesh.center[0]),
            float(mesh.center[1]),
            float(mesh.center[2]),
        ),
        extents=(
            max(0.1, bounds[1] - bounds[0]),
            max(0.1, bounds[3] - bounds[2]),
            max(0.1, bounds[5] - bounds[4]),
        ),
        mesh_path=mesh_path,
        selectable=selectable,
        render_id=render_id,
        selection_id=selection_id,
        pose_name=pose_name,
        mesh_data=copy_mesh_data(mesh),
    )


def build_mock_mesh(spec: MockVertebra):
    if pv is None:
        return None
    mesh = None
    if spec.mesh_data is not None:
        mesh = copy_mesh_data(spec.mesh_data)
    elif spec.mesh_path is not None:
        mesh_path = Path(spec.mesh_path)
        if mesh_path.is_file():
            cached_mesh = load_cached_mesh(mesh_path)
            if cached_mesh is not None:
                mesh = cached_mesh
    if mesh is None:
        mesh = pv.Box(
            bounds=(
                spec.center[0] - spec.extents[0] / 2,
                spec.center[0] + spec.extents[0] / 2,
                spec.center[1] - spec.extents[1] / 2,
                spec.center[1] + spec.extents[1] / 2,
                spec.center[2] - spec.extents[2] / 2,
                spec.center[2] + spec.extents[2] / 2,
            )
        )
    if spec.mesh_transform is not None:
        try:
            mesh.transform(np.asarray(spec.mesh_transform, dtype=float), inplace=True)
        except Exception:
            pass
    return mesh


def build_mesh_spec_from_path(mesh_path: Path) -> MockVertebra | None:
    if pv is None or not mesh_path.is_file():
        return None
    mesh = load_cached_mesh(mesh_path)
    if mesh is None:
        return None
    return build_spec_from_mesh(
        mesh,
        vertebra_id=mesh_path.stem.upper(),
        label=mesh_path.stem.replace("_", " ").title(),
        mesh_path=str(mesh_path),
        selectable=is_selectable_vertebra_id(mesh_path.stem.upper()),
    )


def build_mesh_specs_from_glb_path(
    mesh_path: Path,
    *,
    include_structure: Callable[[str], bool] | None = None,
) -> list[MockVertebra]:
    if pv is None or trimesh is None or not mesh_path.is_file():
        return []
    try:
        scene = trimesh.load(mesh_path, force="scene")
    except Exception:
        return []

    if not isinstance(scene, trimesh.Scene):
        return []

    scene_models: list[MockVertebra] = []
    for node_name in sorted(scene.graph.nodes_geometry):
        if include_structure is not None and not include_structure(node_name):
            continue
        transform, geometry_name = scene.graph[node_name]
        geometry = scene.geometry.get(geometry_name)
        if geometry is None:
            continue
        mesh = geometry.copy()
        mesh.apply_transform(transform)
        mesh.apply_transform(GLB_TO_VIEWPORT_TRANSFORM)
        poly_data = trimesh_to_pyvista(mesh)
        vertebra_id = node_name.upper()
        spec = build_spec_from_mesh(
            poly_data,
            vertebra_id=vertebra_id,
            label=f"{node_name.replace('_', ' ').title()} Standing",
            mesh_path=str(mesh_path),
            selectable=is_selectable_vertebra_id(vertebra_id),
            render_id=f"{vertebra_id}{STANDING_SUFFIX}",
            selection_id=vertebra_id,
            pose_name="standing",
        )
        if spec is not None:
            scene_models.append(spec)
    return scene_models


def trimesh_to_pyvista(mesh: Any):
    if pv is None:
        return None
    vertices = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    if vertices.size == 0 or faces.size == 0:
        return None
    face_cells = np.hstack(
        [
            np.full((faces.shape[0], 1), 3, dtype=np.int64),
            faces,
        ]
    ).ravel()
    return pv.PolyData(vertices, face_cells)


def is_selectable_vertebra_id(vertebra_id: str) -> bool:
    normalized = vertebra_id.strip().upper()
    if normalized == "PELVIS":
        return True
    if len(normalized) < 2:
        return False
    prefix = normalized[0]
    suffix = normalized[1:]
    return prefix in {"C", "T", "L", "S"} and suffix.isdigit()


def scene_bounds(models: Iterable[MockVertebra]) -> tuple[float, float, float, float, float, float]:
    bounds: list[tuple[float, ...]] = []
    for model in models:
        mesh = model.mesh_data
        if mesh is not None:
            bounds.append(tuple(float(value) for value in mesh.bounds))
            continue
        half_x, half_y, half_z = (extent / 2 for extent in model.extents)
        bounds.append(
            (
                model.center[0] - half_x,
                model.center[0] + half_x,
                model.center[1] - half_y,
                model.center[1] + half_y,
                model.center[2] - half_z,
                model.center[2] + half_z,
            )
        )
    if not bounds:
        return (-1.0, 1.0, -1.0, 1.0, -1.0, 1.0)
    return (
        min(bound[0] for bound in bounds),
        max(bound[1] for bound in bounds),
        min(bound[2] for bound in bounds),
        max(bound[3] for bound in bounds),
        min(bound[4] for bound in bounds),
        max(bound[5] for bound in bounds),
    )


def model_lookup_by_id(models: Iterable[MockVertebra]) -> dict[str, MockVertebra]:
    return {model.vertebra_id.upper(): model for model in models}


def normalize_vector(vector: np.ndarray) -> np.ndarray | None:
    magnitude = float(np.linalg.norm(vector))
    if magnitude <= 1e-8:
        return None
    return vector / magnitude


def projected_direction(vector: np.ndarray, *axes: np.ndarray) -> np.ndarray | None:
    projected = np.asarray(vector, dtype=float)
    for axis in axes:
        projected = projected - np.dot(projected, axis) * axis
    return normalize_vector(projected)


def first_anchor_offset(
    lookup: dict[str, MockVertebra],
    origin: np.ndarray,
    candidates: Iterable[str],
) -> np.ndarray | None:
    for candidate in candidates:
        model = lookup.get(candidate.upper())
        if model is None:
            continue
        offset = normalize_vector(np.asarray(model.center, dtype=float) - origin)
        if offset is not None:
            return offset
    return None


def paired_anchor_offset(
    lookup: dict[str, MockVertebra],
    pairs: Iterable[tuple[str, str]],
) -> np.ndarray | None:
    for right_name, left_name in pairs:
        right_model = lookup.get(right_name.upper())
        left_model = lookup.get(left_name.upper())
        if right_model is None or left_model is None:
            continue
        offset = normalize_vector(
            np.asarray(right_model.center, dtype=float) - np.asarray(left_model.center, dtype=float)
        )
        if offset is not None:
            return offset
    return None


def principal_axes_for_model(model: MockVertebra) -> np.ndarray | None:
    mesh = build_mock_mesh(model)
    if mesh is None:
        return None
    points = np.asarray(mesh.points, dtype=float)
    if points.ndim != 2 or len(points) < 3:
        return None
    centered = points - points.mean(axis=0)
    covariance = np.cov(centered.T)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    order = np.argsort(eigenvalues)[::-1]
    return np.asarray(eigenvectors[:, order], dtype=float)


def default_reference_id_for_models(models: Iterable[MockVertebra]) -> str | None:
    lookup = model_lookup_by_id(models)
    if "PELVIS" in lookup:
        return "PELVIS"
    for model in models:
        return model.vertebra_id.upper()
    return None


def build_pose_model_lookup(
    models: Iterable[MockVertebra],
    *,
    pose_name: str | None = None,
) -> dict[str, MockVertebra]:
    lookup: dict[str, MockVertebra] = {}
    for model in models:
        if pose_name is not None and model.pose_name != pose_name:
            continue
        lookup.setdefault(model.vertebra_id.upper(), model)
    return lookup


def scene_span_along_axis(
    models: Iterable[MockVertebra],
    axis: np.ndarray,
) -> tuple[float, float]:
    normalized_axis = normalize_vector(np.asarray(axis, dtype=float))
    if normalized_axis is None:
        return (-1.0, 1.0)

    minimum = float("inf")
    maximum = float("-inf")
    for model in models:
        mesh = build_mock_mesh(model)
        if mesh is not None:
            points = np.asarray(mesh.points, dtype=float)
            if points.ndim == 2 and len(points):
                projections = points @ normalized_axis
                minimum = min(minimum, float(np.min(projections)))
                maximum = max(maximum, float(np.max(projections)))
                continue
        center_projection = float(np.dot(np.asarray(model.center, dtype=float), normalized_axis))
        radius = float(np.linalg.norm(np.asarray(model.extents, dtype=float))) / 2.0
        minimum = min(minimum, center_projection - radius)
        maximum = max(maximum, center_projection + radius)
    if minimum == float("inf") or maximum == float("-inf"):
        return (-1.0, 1.0)
    return (minimum, maximum)


def reference_basis_for_model(model: MockVertebra | None) -> np.ndarray:
    if model is None:
        return np.eye(3, dtype=float)
    if model.vertebra_id.upper() == "PELVIS":
        return np.eye(3, dtype=float)

    principal_axes = principal_axes_for_model(model)
    if principal_axes is None:
        return np.eye(3, dtype=float)

    world_up = np.array((0.0, 0.0, 1.0), dtype=float)
    world_right = np.array((1.0, 0.0, 0.0), dtype=float)
    axes = [np.asarray(principal_axes[:, index], dtype=float) for index in range(3)]
    z_axis_seed = max(axes, key=lambda candidate: abs(float(np.dot(candidate, world_up))))
    if float(np.dot(z_axis_seed, world_up)) < 0:
        z_axis_seed = -z_axis_seed
    z_axis = normalize_vector(z_axis_seed)
    if z_axis is None:
        return np.eye(3, dtype=float)

    x_candidates: list[np.ndarray] = []
    for candidate in axes:
        projected = projected_direction(candidate, z_axis)
        if projected is not None:
            x_candidates.append(projected)
    x_axis_seed: np.ndarray | None
    if x_candidates:
        x_axis_seed = max(
            x_candidates,
            key=lambda candidate: abs(float(np.dot(candidate, world_right))),
        )
        if float(np.dot(x_axis_seed, world_right)) < 0:
            x_axis_seed = -x_axis_seed
    else:
        x_axis_seed = projected_direction(world_right, z_axis)
    if x_axis_seed is None:
        return np.eye(3, dtype=float)
    x_axis = x_axis_seed

    y_axis_seed = normalize_vector(np.cross(z_axis, x_axis))
    if y_axis_seed is None:
        return np.eye(3, dtype=float)
    y_axis = y_axis_seed
    x_axis_refined = normalize_vector(np.cross(y_axis, z_axis))
    if x_axis_refined is None:
        return np.eye(3, dtype=float)
    x_axis = x_axis_refined

    basis = np.column_stack((x_axis, y_axis, z_axis))
    if np.linalg.det(basis) < 0:
        basis[:, 1] *= -1.0
    return basis


def build_pelvis_world_transform(
    models: list[MockVertebra],
    *,
    anchor_id: str = "PELVIS",
) -> np.ndarray | None:
    lookup = model_lookup_by_id(models)
    pelvis = lookup.get(anchor_id.upper())
    if pelvis is None:
        return None

    pelvis_center = np.asarray(pelvis.center, dtype=float)
    right_hint = paired_anchor_offset(
        lookup,
        [
            ("RIGHT_FEMUR", "LEFT_FEMUR"),
            ("RIGHT_HUMERUS", "LEFT_HUMERUS"),
            ("RIGHT_CLAVICLE", "LEFT_CLAVICLE"),
            ("RIGHT_RIBS", "LEFT_RIBS"),
            ("RIGHT_SCAPULA", "LEFT_SCAPULA"),
        ],
    )
    up_hint = first_anchor_offset(
        lookup,
        pelvis_center,
        ["L5", "L4", "L3", "L2", "L1", "T12", "T11", "T10", "STERNUM", "T1", "C7"],
    )
    anterior_hint = first_anchor_offset(
        lookup,
        pelvis_center,
        ["STERNUM", "T1", "C7", "RIGHT_RIBS", "LEFT_RIBS"],
    )

    principal_axes = principal_axes_for_model(pelvis)
    if up_hint is None and principal_axes is not None:
        up_hint = np.asarray(principal_axes[:, 1], dtype=float)
    up_axis = normalize_vector(up_hint if up_hint is not None else np.array((0.0, 0.0, 1.0)))
    if up_axis is None:
        return None

    if right_hint is None and principal_axes is not None:
        for column in principal_axes.T:
            candidate = projected_direction(np.asarray(column, dtype=float), up_axis)
            if candidate is not None:
                right_hint = candidate
                break
    right_axis = projected_direction(
        right_hint if right_hint is not None else np.array((1.0, 0.0, 0.0)),
        up_axis,
    )
    if right_axis is None:
        return None

    anterior_axis = normalize_vector(np.cross(up_axis, right_axis))
    if anterior_axis is None:
        return None
    if anterior_hint is not None:
        projected_anterior = projected_direction(anterior_hint, up_axis, right_axis)
        if projected_anterior is not None and np.dot(anterior_axis, projected_anterior) < 0:
            anterior_axis = -anterior_axis
            right_axis = normalize_vector(np.cross(anterior_axis, up_axis))
            if right_axis is None:
                return None

    basis = np.column_stack((right_axis, anterior_axis, up_axis))
    if np.linalg.det(basis) < 0:
        basis[:, 1] *= -1.0
    rotation = basis.T

    transform = np.eye(4, dtype=float)
    transform[:3, :3] = rotation
    transform[:3, 3] = -(rotation @ pelvis_center)
    return transform


def apply_group_transform(
    models: list[MockVertebra],
    transform: np.ndarray | None,
) -> list[MockVertebra]:
    if transform is None:
        return list(models)
    transformed_models: list[MockVertebra] = []
    linear = transform[:3, :3]
    offset = transform[:3, 3]
    for model in models:
        transformed_center = (
            float(linear[0] @ np.asarray(model.center, dtype=float) + offset[0]),
            float(linear[1] @ np.asarray(model.center, dtype=float) + offset[1]),
            float(linear[2] @ np.asarray(model.center, dtype=float) + offset[2]),
        )
        transformed_mesh = build_mock_mesh(model)
        if transformed_mesh is not None:
            transformed_points = (
                np.asarray(transformed_mesh.points, dtype=float) @ linear.T
            ) + offset
            transformed_mesh.points = transformed_points
            bounds = tuple(float(value) for value in transformed_mesh.bounds)
            transformed_models.append(
                replace(
                    model,
                    center=transformed_center,
                    extents=(
                        max(0.1, bounds[1] - bounds[0]),
                        max(0.1, bounds[3] - bounds[2]),
                        max(0.1, bounds[5] - bounds[4]),
                    ),
                    mesh_data=transformed_mesh,
                )
            )
            continue
        transformed_models.append(replace(model, center=transformed_center))
    return transformed_models


def apply_flat_shading(actor: Any) -> None:
    prop = getattr(actor, "prop", None)
    if prop is None:
        return
    try:
        prop.interpolation = "flat"
        return
    except Exception:
        pass
    try:
        prop.SetInterpolationToFlat()
    except Exception:
        pass


def apply_point_rendering(actor: Any, enabled: bool) -> None:
    prop = getattr(actor, "prop", None)
    if prop is None:
        return
    try:
        prop.render_points_as_spheres = bool(enabled)
        return
    except Exception:
        pass
    try:
        prop.SetRenderPointsAsSpheres(bool(enabled))
    except Exception:
        pass


def apply_surface_material(actor: Any, render_mode: ViewportRenderMode) -> None:
    prop = getattr(actor, "prop", None)
    if prop is None:
        return
    try:
        prop.lighting = bool(render_mode.lighting)
    except Exception:
        pass
    try:
        prop.specular = 0.12 if render_mode.lighting else 0.0
    except Exception:
        pass
    try:
        prop.specular_power = 18.0 if render_mode.lighting else 1.0
    except Exception:
        pass
    try:
        prop.diffuse = 0.92 if render_mode.lighting else 1.0
    except Exception:
        pass
    try:
        prop.ambient = 0.22 if render_mode.lighting else 0.0
    except Exception:
        pass
    if render_mode.smooth_shading:
        try:
            prop.interpolation = "phong"
            return
        except Exception:
            pass
        try:
            prop.SetInterpolationToPhong()
        except Exception:
            pass
        return
    apply_flat_shading(actor)


def nice_grid_step(span: float, target_divisions: int = 8) -> float:
    if span <= 0:
        return 1.0
    raw_step = span / max(target_divisions, 1)
    exponent = float(np.floor(np.log10(raw_step)))
    fraction = raw_step / (10.0 ** exponent)
    if fraction <= 1.0:
        nice_fraction = 1.0
    elif fraction <= 2.0:
        nice_fraction = 2.0
    elif fraction <= 5.0:
        nice_fraction = 5.0
    else:
        nice_fraction = 10.0
    return float(nice_fraction * (10.0 ** exponent))


def orthographic_zoom_scale(current_scale: float, wheel_delta_y: int) -> float:
    base_scale = max(float(current_scale), 0.25)
    step_count = max(1, abs(int(wheel_delta_y)) // 120)
    zoom_factor = 0.88**step_count if wheel_delta_y > 0 else (1.0 / 0.88) ** step_count
    return max(base_scale * zoom_factor, 0.25)


def configure_viewport_render_widget(widget: QWidget) -> None:
    widget.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
    widget.setAutoFillBackground(True)


def configure_plotter_studio_lighting(plotter: Any) -> None:
    try:
        plotter.enable_lightkit()
    except Exception:
        pass
    renderer = getattr(plotter, "renderer", None)
    if renderer is not None:
        try:
            renderer.use_fxaa = True
        except Exception:
            pass


def pan_camera_from_screen_delta(
    plotter: Any,
    delta_x: float,
    delta_y: float,
) -> None:
    camera = getattr(plotter, "camera", None)
    if camera is None:
        return

    width = max(int(plotter.width()), 1)
    height = max(int(plotter.height()), 1)
    position = np.asarray(camera.position[:3], dtype=float)
    focal_point = np.asarray(camera.focal_point[:3], dtype=float)
    view_direction = normalize_vector(focal_point - position)
    if view_direction is None:
        return

    up_vector = normalize_vector(np.asarray(camera.up[:3], dtype=float))
    if up_vector is None:
        up_vector = np.array((0.0, 0.0, 1.0), dtype=float)

    right_vector = normalize_vector(np.cross(view_direction, up_vector))
    if right_vector is None:
        return
    true_up = normalize_vector(np.cross(right_vector, view_direction))
    if true_up is None:
        return

    aspect_ratio = width / max(height, 1)
    parallel_projection = bool(getattr(camera, "parallel_projection", False))
    if parallel_projection:
        visible_height = max(float(getattr(camera, "parallel_scale", 1.0)) * 2.0, 1e-6)
    else:
        focal_distance = max(float(np.linalg.norm(focal_point - position)), 1e-6)
        view_angle = float(getattr(camera, "view_angle", 30.0) or 30.0)
        visible_height = max(
            2.0 * focal_distance * np.tan(np.deg2rad(view_angle) / 2.0),
            1e-6,
        )

    units_per_pixel_y = visible_height / max(height, 1)
    units_per_pixel_x = (visible_height * aspect_ratio) / max(width, 1)
    translation = (
        right_vector * (-delta_x * units_per_pixel_x)
        + true_up * (delta_y * units_per_pixel_y)
    )
    camera.position = tuple(float(value) for value in (position + translation))
    camera.focal_point = tuple(float(value) for value in (focal_point + translation))


def orbit_camera_about_up_axis(plotter: Any, delta_x: float) -> None:
    camera = getattr(plotter, "camera", None)
    if camera is None:
        return
    position = np.asarray(camera.position[:3], dtype=float)
    focal_point = np.asarray(camera.focal_point[:3], dtype=float)
    up_axis = normalize_vector(np.asarray(camera.up[:3], dtype=float))
    offset = position - focal_point
    radius = float(np.linalg.norm(offset))
    if up_axis is None or radius <= 1e-8:
        return
    angle = np.deg2rad(float(delta_x) * 0.45)
    cos_angle = float(np.cos(angle))
    sin_angle = float(np.sin(angle))
    rotated_offset = (
        offset * cos_angle
        + np.cross(up_axis, offset) * sin_angle
        + up_axis * np.dot(up_axis, offset) * (1.0 - cos_angle)
    )
    camera.position = tuple(float(value) for value in (focal_point + rotated_offset))
    camera.up = tuple(float(value) for value in up_axis)


def visible_world_size(plotter: Any) -> tuple[float, float]:
    camera = getattr(plotter, "camera", None)
    if camera is None:
        return (2.0, 2.0)
    width = max(int(plotter.width()), 1)
    height = max(int(plotter.height()), 1)
    aspect_ratio = width / max(height, 1)
    if bool(getattr(camera, "parallel_projection", False)):
        visible_height = max(float(getattr(camera, "parallel_scale", 1.0)) * 2.0, 1.0)
    else:
        position = np.asarray(camera.position[:3], dtype=float)
        focal_point = np.asarray(camera.focal_point[:3], dtype=float)
        focal_distance = max(float(np.linalg.norm(focal_point - position)), 1.0)
        view_angle = float(getattr(camera, "view_angle", 30.0) or 30.0)
        visible_height = max(
            2.0 * focal_distance * np.tan(np.deg2rad(view_angle) / 2.0),
            1.0,
        )
    return (visible_height * aspect_ratio, visible_height)


def build_grid_line_positions(
    minimum: float,
    maximum: float,
    step: float,
    *,
    major_frequency: int = 5,
) -> list[tuple[float, bool]]:
    if step <= 0 or maximum <= minimum:
        return []
    start_index = int(np.floor(minimum / step)) - 1
    end_index = int(np.ceil(maximum / step)) + 1
    line_positions: list[tuple[float, bool]] = []
    for index in range(start_index, end_index + 1):
        position = index * step
        if position < minimum - step or position > maximum + step:
            continue
        line_positions.append((position, index % major_frequency == 0))
    return line_positions


def build_line_segment_mesh(
    segments: Iterable[
        tuple[tuple[float, float, float], tuple[float, float, float]]
    ],
):
    if pv is None:
        return None
    segment_list = list(segments)
    if not segment_list:
        return None
    points = np.asarray(
        [point for segment in segment_list for point in segment],
        dtype=float,
    )
    lines = np.empty(len(segment_list) * 3, dtype=np.int64)
    for index in range(len(segment_list)):
        point_index = index * 2
        lines[index * 3 : index * 3 + 3] = (2, point_index, point_index + 1)
    return pv.PolyData(points, lines=lines)


class SpineViewport3D(QWidget):
    selection_changed = Signal(str, bool, bool)
    mode_changed = Signal(object)
    detail_level_changed = Signal(int)
    point_size_changed = Signal(int)
    camera_mode_changed = Signal(str)

    def __init__(
        self,
        title: str,
        *,
        show_demo_scene: bool = True,
        models: list[MockVertebra] | None = None,
        show_toolbar: bool = True,
        show_display_controls: bool = True,
        track_selection_pivot: bool = True,
        interactive_enabled: bool = True,
        fallback_message: str | None = None,
    ) -> None:
        super().__init__()
        self._title = title
        self._show_toolbar = show_toolbar
        self._show_display_controls = show_display_controls
        self._track_selection_pivot = track_selection_pivot
        self._interactive_enabled = interactive_enabled
        self._fallback_message = fallback_message
        self._models = list(models) if models is not None else (
            list(DEMO_VERTEBRAE) if show_demo_scene else []
        )
        self._reference_model_lookup = build_pose_model_lookup(self._models, pose_name="baseline")
        if not self._reference_model_lookup:
            self._reference_model_lookup = build_pose_model_lookup(self._models)
        self._standing_reference_model_lookup = build_pose_model_lookup(
            self._models,
            pose_name="standing",
        )
        self._selectable_index: dict[str, MockVertebra] = {}
        for model in self._models:
            selection_key = model.selection_key
            if selection_key is None or not model.selectable:
                continue
            self._selectable_index.setdefault(selection_key, model)
        self._show_demo_scene = bool(self._models)
        self._mode = ViewportMode.SOLID
        self._detail_level = DEFAULT_DETAIL_LEVEL
        self._point_size = VIEWPORT_MODES[ViewportMode.POINTS].point_size
        self._camera_mode = "perspective"
        self._selected_ids: tuple[str, ...] = ()
        self._active_id: str | None = None
        self._reference_id: str | None = None
        self._isolate_selection = False
        self._show_reference_axes = True
        self._baseline_pose_visible = True
        self._standing_pose_visible = True
        self._pose_delta_glyphs: tuple[Any, ...] = ()
        self._plotter = None
        self._surface: QFrame | None = None
        self._transition_overlay: QLabel | None = None
        self._toolbar_overlay: QWidget | None = None
        self._gnomon_overlay: ViewportGnomonOverlay | None = None
        self._floating_toolbar = self._show_toolbar and not self._show_display_controls
        self._actor_map: dict[str, Any] = {}
        self._render_model_map: dict[str, MockVertebra] = {}
        self._mesh_map: dict[str, Any] = {}
        self._display_mesh_map: dict[str, Any] = {}
        self._base_mesh_by_actor_id: dict[str, Any] = {}
        self._reference_axis_actors: list[Any] = []
        self._pose_delta_actors: list[Any] = []
        self._grid_actors: dict[str, Any] = {}
        self._overlay_actors: dict[str, list[Any]] = {}
        self._grid_refreshing = False
        self._last_grid_signature: tuple[float, ...] | None = None
        self._mode_buttons: dict[ViewportMode, CapsuleButton] = {}
        self._detail_buttons: dict[int, CapsuleButton] = {}
        self._surface_point_pick_callback: Callable[
            [tuple[float, float, float]], None
        ] | None = None
        self._surface_point_picking_enabled = False
        self._disposed = False
        self._reference_axis_length = max(
            (max(model.extents) for model in self._models),
            default=REFERENCE_AXIS_LENGTH,
        ) * 0.8

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        toolbar: QWidget | None = None
        if self._show_toolbar:
            if self._floating_toolbar:
                title_label = QLabel(title, self)
                title_label.setObjectName("ViewportOverlayChip")
                title_label.setAttribute(
                    Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
                )
                apply_text_role(title_label, "panel-title")
                toolbar = title_label
                self._toolbar_overlay = title_label
            else:
                toolbar = QFrame(self)
                toolbar.setObjectName("ViewportToolbar")
                self._toolbar_overlay = toolbar
                toolbar_layout = QVBoxLayout(toolbar)
                toolbar_layout.setContentsMargins(
                    GEOMETRY.overlay_padding,
                    GEOMETRY.overlay_padding,
                    GEOMETRY.overlay_padding,
                    0,
                )
                toolbar_layout.setSpacing(GEOMETRY.overlay_gap)

                title_row = QHBoxLayout()
                title_row.setContentsMargins(0, 0, 0, 0)
                title_row.setSpacing(GEOMETRY.overlay_gap)
                toolbar_layout.addLayout(title_row)

                title_label = QLabel(title)
                title_label.setObjectName("ViewportOverlayChip")
                apply_text_role(title_label, "panel-title")
                title_row.addWidget(title_label)
                title_row.addStretch(1)

                mode_icon_size = QSize(
                    TEXT_STYLES["body-emphasis"].line_height,
                    TEXT_STYLES["body-emphasis"].line_height,
                )
                for mode in ViewportMode:
                    button = CapsuleButton("", checkable=True)
                    button.setObjectName("ViewportModeButton")
                    button.setChecked(mode == self._mode)
                    button.setToolTip(mode.value.title())
                    button.setAccessibleName(mode.value.title())
                    button.setFixedWidth(GEOMETRY.control_height_sm)
                    button.setIconSize(mode_icon_size)
                    button.setEnabled(self._interactive_enabled)
                    button.clicked.connect(
                        lambda checked=False, selected_mode=mode: self.set_mode(selected_mode)
                    )
                    title_row.addWidget(button)
                    self._mode_buttons[mode] = button
        self._refresh_mode_button_icons()
        if toolbar is not None and self._show_display_controls:
            detail_row = QHBoxLayout()
            detail_row.setContentsMargins(0, 0, 0, 0)
            detail_row.setSpacing(GEOMETRY.overlay_gap)
            detail_row.addStretch(1)
            toolbar_layout.addLayout(detail_row)

            detail_group = QFrame(toolbar)
            detail_group.setObjectName("ViewportOverlayGroup")
            detail_layout = QHBoxLayout(detail_group)
            detail_layout.setContentsMargins(
                GEOMETRY.unit * 2,
                GEOMETRY.unit,
                GEOMETRY.unit * 2,
                GEOMETRY.unit,
            )
            detail_layout.setSpacing(GEOMETRY.unit)
            detail_label = QLabel("Detail")
            detail_label.setObjectName("ViewportOverlayHint")
            apply_text_role(detail_label, "meta")
            detail_layout.addWidget(detail_label)
            for button_label, button_level in DETAIL_PRESET_LEVELS:
                button = CapsuleButton(button_label, checkable=True)
                button.setObjectName("ViewportAxisButton")
                button.setFixedHeight(GEOMETRY.control_height_sm)
                button.setEnabled(self._interactive_enabled)
                button.clicked.connect(
                    partial(self._handle_detail_preset_selected, button_level)
                )
                detail_layout.addWidget(button)
                self._detail_buttons[button_level] = button
            self._refresh_detail_button_states()
            detail_row.addWidget(detail_group)
            root_layout.addWidget(toolbar)
        elif toolbar is not None and not self._floating_toolbar:
            root_layout.addWidget(toolbar)

        surface = QFrame(self)
        surface.setObjectName("ViewportCardFrame")
        self._surface = surface
        self._gnomon_overlay = ViewportGnomonOverlay(self, view_kind="3d")
        surface_layout = QGridLayout(surface)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        surface_layout.setSpacing(0)
        root_layout.addWidget(surface, stretch=1)

        offscreen = os.environ.get("QT_QPA_PLATFORM", "").lower() in {"offscreen", "minimal"}
        backend_available = SelectableQtInteractor is not None and pv is not None
        if not self._interactive_enabled or not backend_available or offscreen:
            self._build_fallback(
                surface_layout,
                resolve_viewport_fallback_message(
                    interactive_enabled=self._interactive_enabled,
                    fallback_message=self._fallback_message,
                    offscreen=offscreen,
                    backend_available=backend_available,
                ),
            )
            return

        self._plotter = SelectableQtInteractor(surface)
        configure_viewport_render_widget(self._plotter)
        self._plotter.set_background(VIEWPORT_BACKGROUND)
        configure_plotter_studio_lighting(self._plotter)
        self._plotter.enable_trackball_style()
        self._plotter.background_clicked.connect(self._handle_background_click)
        self._plotter.camera.AddObserver("ModifiedEvent", self._handle_camera_modified)
        surface_layout.addWidget(self._plotter, 0, 0)
        if toolbar is not None:
            toolbar.raise_()
        if self._show_demo_scene:
            self._build_scene()
            self._enable_selection_picking()

    def _build_fallback(self, surface_layout: QGridLayout, message: str) -> None:
        fallback = QFrame()
        fallback.setObjectName("ViewportFallback")
        fallback_layout = QVBoxLayout(fallback)
        fallback_layout.setContentsMargins(
            GEOMETRY.unit * 2,
            GEOMETRY.unit * 2,
            GEOMETRY.unit * 2,
            GEOMETRY.unit * 2,
        )
        fallback_layout.setSpacing(GEOMETRY.unit)
        fallback_layout.addStretch(1)
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_text_role(message_label, "body")
        fallback_layout.addWidget(message_label)
        surface_layout.addWidget(fallback, 0, 0)

    def closeEvent(self, event) -> None:
        self.dispose()
        super().closeEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.set_render_widget_visible(True)
        self._raise_overlay_widgets()

    def hideEvent(self, event: QHideEvent) -> None:
        self.set_render_widget_visible(False)
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._transition_overlay is not None and self._surface is not None:
            self._transition_overlay.setGeometry(self._surface.rect())
        self._position_toolbar_overlay()
        if self._gnomon_overlay is not None:
            position_gnomon_overlay(self._gnomon_overlay, self._surface)
            self._gnomon_overlay.raise_()

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        plotter = self._plotter
        self._plotter = None
        if plotter is not None:
            try:
                plotter._suppress_rendering = True
            except Exception:
                pass
            render_timer = getattr(plotter, "render_timer", None)
            if render_timer is not None:
                try:
                    render_timer.stop()
                except Exception:
                    pass
                try:
                    render_timer.timeout.disconnect()
                except Exception:
                    pass
            try:
                plotter.close()
            except Exception:
                pass
            try:
                plotter.Finalize()
            except Exception:
                pass
            for actor in self._grid_actors.values():
                try:
                    plotter.remove_actor(actor, reset_camera=False, render=False)
                except Exception:
                    pass
            for overlay_actors in self._overlay_actors.values():
                for actor in overlay_actors:
                    try:
                        plotter.remove_actor(actor, reset_camera=False, render=False)
                    except Exception:
                        pass
        self._actor_map.clear()
        self._render_model_map.clear()
        self._mesh_map.clear()
        self._display_mesh_map.clear()
        self._base_mesh_by_actor_id.clear()
        self._reference_axis_actors.clear()
        self._pose_delta_actors.clear()
        self._grid_actors.clear()
        self._overlay_actors.clear()
        self._last_grid_signature = None
        self._surface = None
        if self._transition_overlay is not None:
            self._transition_overlay.deleteLater()
            self._transition_overlay = None
        self._toolbar_overlay = None
        self._gnomon_overlay = None

    def set_render_widget_visible(self, visible: bool) -> None:
        if self._disposed or self._plotter is None:
            return
        self._plotter.setVisible(visible)
        self._plotter.setUpdatesEnabled(visible)
        if not visible:
            return
        try:
            self._raise_overlay_widgets()
        except Exception:
            pass
        try:
            self._plotter.render()
        except Exception:
            pass

    def set_layout_transition_active(self, active: bool) -> None:
        surface = self._surface
        if self._disposed or surface is None:
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
            if self._plotter is not None:
                self._plotter.hide()
            overlay.show()
            overlay.raise_()
            self._raise_overlay_widgets()
            return
        if self._transition_overlay is None:
            return
        if self._plotter is not None:
            self._plotter.show()
        self._transition_overlay.deleteLater()
        self._transition_overlay = None
        self._raise_overlay_widgets()
        if self._plotter is not None:
            try:
                self._plotter.render()
            except Exception:
                pass
        self.update()

    def _capture_surface_snapshot(self) -> QPixmap:
        surface = self._surface
        if surface is None:
            return QPixmap()
        return surface.grab()

    def _raise_toolbar_overlay(self) -> None:
        if self._toolbar_overlay is None:
            return
        self._toolbar_overlay.show()
        self._position_toolbar_overlay()
        self._toolbar_overlay.raise_()

    def _raise_overlay_widgets(self) -> None:
        self._raise_toolbar_overlay()
        if self._gnomon_overlay is not None:
            self._gnomon_overlay.show()
            position_gnomon_overlay(self._gnomon_overlay, self._surface)
            self._gnomon_overlay.raise_()

    def _position_toolbar_overlay(self) -> None:
        if not self._floating_toolbar:
            return
        toolbar = self._toolbar_overlay
        surface = self._surface
        if toolbar is None or surface is None:
            return
        toolbar.adjustSize()
        size = toolbar.sizeHint().expandedTo(toolbar.minimumSizeHint())
        toolbar.setGeometry(
            surface.x() + GEOMETRY.overlay_padding,
            surface.y() + GEOMETRY.overlay_padding,
            size.width(),
            size.height(),
        )

    def _build_scene(self) -> None:
        if self._disposed or self._plotter is None or pv is None:
            return
        render_mode = VIEWPORT_MODES[self._mode]
        for spec in self._models:
            base_mesh = build_mock_mesh(spec)
            if base_mesh is None:
                continue
            mesh = load_lod_mesh(spec, base_mesh, self._detail_level)
            if mesh is None:
                continue
            actor_id = spec.actor_id
            initial_colors = resolve_mesh_visual_colors(
                spec.pose_name,
                selected=False,
                reference=False,
            )
            actor = self._plotter.add_mesh(
                mesh,
                color=initial_colors.fill,
                opacity=render_mode.opacity,
                lighting=render_mode.lighting,
                smooth_shading=render_mode.smooth_shading,
                show_edges=render_mode.show_edges,
                name=f"review-{actor_id}",
                pickable=spec.selectable,
            )
            apply_surface_material(actor, render_mode)
            actor.prop.edge_color = initial_colors.edge
            actor._selection_id = spec.selection_key if spec.selectable else None
            self._actor_map[actor_id] = actor
            self._render_model_map[actor_id] = spec
            self._display_mesh_map[actor_id] = mesh
            self._base_mesh_by_actor_id[actor_id] = base_mesh
            selection_key = spec.selection_key
            if selection_key is not None and (
                selection_key not in self._mesh_map or spec.pose_name == "baseline"
            ):
                self._mesh_map[selection_key] = base_mesh
            reference_key = spec.vertebra_id.upper()
            if reference_key not in self._mesh_map or spec.pose_name == "baseline":
                self._mesh_map[reference_key] = base_mesh
        self._apply_camera_mode(reset_scale=True)
        self._apply_scene_state()

    def _current_reference_model(self) -> MockVertebra | None:
        if self._reference_id is None:
            return None
        reference_key = self._reference_id.upper()
        return self._reference_model_lookup.get(
            reference_key
        ) or self._standing_reference_model_lookup.get(
            reference_key
        )

    def _current_reference_center(self) -> np.ndarray:
        reference_model = self._current_reference_model()
        if reference_model is not None:
            return np.asarray(reference_model.center, dtype=float)
        return np.array((0.0, 0.0, 0.0), dtype=float)

    def _current_reference_basis(self) -> np.ndarray:
        return reference_basis_for_model(self._current_reference_model())

    def _current_standing_alignment_offset(self) -> np.ndarray:
        if self._reference_id is None:
            return np.zeros(3, dtype=float)
        reference_key = self._reference_id.upper()
        baseline_model = self._reference_model_lookup.get(reference_key)
        standing_model = self._standing_reference_model_lookup.get(reference_key)
        if baseline_model is None or standing_model is None:
            return np.zeros(3, dtype=float)
        return np.array(
            (
                baseline_model.center[0] - standing_model.center[0],
                baseline_model.center[1] - standing_model.center[1],
                baseline_model.center[2] - standing_model.center[2],
            ),
            dtype=float,
        )

    def _set_actor_translation(self, actor: Any, translation: np.ndarray) -> None:
        offset = tuple(float(value) for value in translation)
        try:
            actor.position = offset
            return
        except Exception:
            pass
        try:
            actor.SetPosition(*offset)
        except Exception:
            pass

    def _spec_matches_reference(self, spec: MockVertebra) -> bool:
        if self._reference_id is None:
            return False
        reference_key = self._reference_id.upper()
        selection_key = spec.selection_key.upper() if spec.selection_key is not None else None
        return selection_key == reference_key or spec.vertebra_id.upper() == reference_key

    def _center_camera_on_origin(self) -> None:
        if self._disposed or self._plotter is None or not self._models:
            return
        camera = self._plotter.camera
        position = np.asarray(camera.position, dtype=float)
        focal_point = np.asarray(camera.focal_point, dtype=float)
        direction = position - focal_point
        direction = normalize_vector(direction)
        if direction is None:
            direction = normalize_vector(np.array((1.6, -1.3, 1.1), dtype=float))
        bounds = scene_bounds(self._models)
        radius = max(abs(value) for value in bounds)
        distance = max(radius * 2.8, 1.0)
        focus = self._current_reference_center()
        camera.focal_point = tuple(float(value) for value in focus)
        camera.position = tuple(float(value) for value in (focus + direction * distance))
        camera.up = tuple(float(value) for value in self._current_reference_basis()[:, 2])

    def _center_orthographic_camera_on_origin(self, *, reset_scale: bool) -> None:
        if self._disposed or self._plotter is None:
            return
        camera = self._plotter.camera
        basis = self._current_reference_basis()
        focus = self._current_reference_center()
        width = max(self._plotter.width(), 1)
        height = max(self._plotter.height(), 1)
        aspect_ratio = width / max(height, 1)

        if self._camera_mode == "front":
            direction = basis[:, 0]
            horizontal_axis = basis[:, 1]
            vertical_axis = basis[:, 2]
            camera.up = tuple(float(value) for value in basis[:, 2])
        elif self._camera_mode == "side":
            direction = basis[:, 1]
            horizontal_axis = basis[:, 0]
            vertical_axis = basis[:, 2]
            camera.up = tuple(float(value) for value in basis[:, 2])
        else:
            direction = basis[:, 2]
            horizontal_axis = basis[:, 0]
            vertical_axis = basis[:, 1]
            camera.up = tuple(float(value) for value in basis[:, 1])

        bounds = scene_bounds(self._models)
        radius = max(max(abs(value) for value in bounds), 1.0)
        distance = max(radius * 3.0, 1.0)
        camera.focal_point = tuple(float(value) for value in focus)
        camera.position = tuple(float(value) for value in (focus + direction * distance))
        camera.parallel_projection = True
        if not reset_scale:
            return

        horizontal_min, horizontal_max = scene_span_along_axis(self._models, horizontal_axis)
        vertical_min, vertical_max = scene_span_along_axis(self._models, vertical_axis)
        horizontal_span = max(horizontal_max - horizontal_min, 1.0)
        vertical_span = max(vertical_max - vertical_min, 1.0)
        camera.parallel_scale = max(
            vertical_span / 2.0,
            horizontal_span / max(2.0 * aspect_ratio, 1e-6),
            1.0,
        ) * 1.08

    def _handle_mesh_pick(self, actor) -> None:
        if self._disposed:
            return
        if self._plotter is not None:
            self._plotter.mark_pick_handled()
        vertebra_id = getattr(actor, "_selection_id", None)
        if isinstance(vertebra_id, str):
            remove_requested = (
                self._plotter.remove_requested()
                if self._plotter is not None
                else False
            )
            set_primary_requested = (
                self._plotter.set_primary_requested()
                if self._plotter is not None
                else False
            )
            self.selection_changed.emit(vertebra_id, remove_requested, set_primary_requested)

    def _handle_surface_point_pick(self, point) -> None:
        if self._disposed:
            return
        if self._plotter is not None:
            try:
                self._plotter.mark_pick_handled()
            except Exception:
                pass
        callback = self._surface_point_pick_callback
        if callback is None:
            return
        try:
            snapped_point = tuple(float(value) for value in point[:3])
        except Exception:
            return
        callback(cast(tuple[float, float, float], snapped_point))

    def set_surface_point_pick_callback(
        self,
        callback: Callable[[tuple[float, float, float]], None] | None,
    ) -> None:
        self._surface_point_pick_callback = callback
        self._refresh_pick_mode()

    def set_surface_point_picking_enabled(self, enabled: bool) -> None:
        if self._surface_point_picking_enabled == bool(enabled):
            return
        self._surface_point_picking_enabled = bool(enabled)
        self._refresh_pick_mode()

    def _refresh_pick_mode(self) -> None:
        if self._disposed or self._plotter is None:
            return
        try:
            self._plotter.disable_picking()
        except Exception:
            pass
        if self._surface_point_picking_enabled and self._surface_point_pick_callback is not None:
            self._plotter.enable_surface_point_picking(
                callback=self._handle_surface_point_pick,
                left_clicking=True,
                show_message=False,
                show_point=False,
                clear_on_no_selection=False,
                use_picker=True,
            )
            return
        self._enable_selection_picking()

    def _enable_selection_picking(self) -> None:
        if self._disposed or self._plotter is None:
            return
        self._plotter.enable_mesh_picking(
            callback=self._handle_mesh_pick,
            use_actor=True,
            left_clicking=True,
            show=False,
            show_message=False,
        )

    def set_overlay_geometry(
        self,
        overlay_id: str,
        overlay: OverlayGeometry | None,
    ) -> None:
        if self._disposed or self._plotter is None:
            return
        self.clear_overlay_geometry(overlay_id)
        if overlay is None:
            return
        overlay_actors: list[Any] = []
        if overlay.line_segments:
            line_mesh = build_line_segment_mesh(overlay.line_segments)
            if line_mesh is not None:
                line_actor = self._plotter.add_mesh(
                    line_mesh,
                    color=overlay.line_color,
                    line_width=overlay.line_width,
                    lighting=False,
                    pickable=False,
                    reset_camera=False,
                    render=False,
                )
                overlay_actors.append(line_actor)
        if overlay.anchor_points:
            point_mesh = pv.PolyData(np.asarray(overlay.anchor_points, dtype=float))
            point_actor = self._plotter.add_mesh(
                point_mesh,
                color=overlay.point_color,
                point_size=overlay.point_size,
                render_points_as_spheres=True,
                lighting=False,
                pickable=False,
                reset_camera=False,
                render=False,
            )
            overlay_actors.append(point_actor)
        if overlay_actors:
            self._overlay_actors[overlay_id] = overlay_actors

    def clear_overlay_geometry(self, overlay_id: str) -> None:
        if self._disposed or self._plotter is None:
            self._overlay_actors.pop(overlay_id, None)
            return
        overlay_actors = self._overlay_actors.pop(overlay_id, [])
        for actor in overlay_actors:
            try:
                self._plotter.remove_actor(actor, reset_camera=False, render=False)
            except Exception:
                pass

    def _handle_background_click(self) -> None:
        if self._selected_ids or self._active_id is not None or self._reference_id is not None:
            self.selection_changed.emit("", False, False)

    def set_mode(self, mode: ViewportMode) -> None:
        if self._mode == mode:
            return
        self._mode = mode
        for button_mode, button in self._mode_buttons.items():
            button.setChecked(button_mode == mode)
        self._refresh_mode_button_icons()
        self._apply_scene_state()
        self.mode_changed.emit(mode)

    def current_mode(self) -> ViewportMode:
        return self._mode

    @property
    def mode_buttons(self) -> dict[ViewportMode, CapsuleButton]:
        return self._mode_buttons

    @property
    def detail_buttons(self) -> dict[int, CapsuleButton]:
        return self._detail_buttons

    def set_camera_mode(self, mode: str) -> None:
        normalized = normalize_camera_mode(mode)
        if self._camera_mode == normalized and self._plotter is not None:
            return
        self._camera_mode = normalized
        self._apply_camera_mode(reset_scale=True)
        self.camera_mode_changed.emit(normalized)

    def current_camera_mode(self) -> str:
        return self._camera_mode

    def set_reference_axes_visible(self, visible: bool) -> None:
        self._show_reference_axes = bool(visible)
        self._refresh_reference_axes()
        if self._plotter is not None:
            self._plotter.render()

    def set_pose_visibility(self, *, baseline_visible: bool, standing_visible: bool) -> None:
        next_baseline_visible = bool(baseline_visible)
        next_standing_visible = bool(standing_visible)
        if (
            self._baseline_pose_visible == next_baseline_visible
            and self._standing_pose_visible == next_standing_visible
        ):
            return
        self._baseline_pose_visible = next_baseline_visible
        self._standing_pose_visible = next_standing_visible
        self._apply_scene_state()

    def current_pose_visibility(self) -> tuple[bool, bool]:
        return self._baseline_pose_visible, self._standing_pose_visible

    def set_track_selection_pivot(self, enabled: bool) -> None:
        self._track_selection_pivot = bool(enabled)

    def set_pose_delta_glyphs(self, glyphs: Iterable[Any]) -> None:
        self._pose_delta_glyphs = tuple(glyphs)
        self._refresh_pose_delta_glyphs()
        if self._plotter is not None:
            self._plotter.render()

    def _handle_detail_preset_selected(self, level: int, _checked: bool = False) -> None:
        if detail_preset_level(self._detail_level) == level:
            self._refresh_detail_button_states()
            return
        self.set_detail_level(level)

    def set_detail_level(self, level: int) -> None:
        normalized_level = coerce_detail_level(level)
        if normalized_level == self._detail_level:
            self._refresh_detail_button_states()
            return
        self._detail_level = normalized_level
        self._refresh_detail_button_states()
        self._apply_detail_level()
        self.detail_level_changed.emit(normalized_level)

    def set_point_size(self, point_size: int) -> None:
        normalized_size = max(2, min(int(point_size), 24))
        if normalized_size == self._point_size:
            return
        self._point_size = normalized_size
        self._apply_scene_state()
        self.point_size_changed.emit(normalized_size)

    def current_point_size(self) -> int:
        return self._point_size

    def fit_scene_to_reference(self) -> None:
        self._apply_camera_mode(reset_scale=True)

    def _refresh_mode_button_icons(self) -> None:
        icon_size = QSize(
            TEXT_STYLES["body-emphasis"].line_height,
            TEXT_STYLES["body-emphasis"].line_height,
        )
        for mode, button in self._mode_buttons.items():
            tint = THEME_COLORS.focus if mode == self._mode else THEME_COLORS.text_secondary
            button.setIcon(
                build_svg_icon(
                    VIEWPORT_MODE_ICON_PATHS[mode],
                    icon_size,
                    device_pixel_ratio=button.devicePixelRatioF(),
                    tint=tint,
                )
            )

    def current_detail_level(self) -> int:
        return self._detail_level

    def _refresh_detail_button_states(self) -> None:
        selected_level = detail_preset_level(self._detail_level)
        for button_level, button in self._detail_buttons.items():
            button.setChecked(button_level == selected_level)

    def _apply_detail_level(self) -> None:
        if self._plotter is None:
            return
        for actor_id, actor in self._actor_map.items():
            spec = self._render_model_map[actor_id]
            base_mesh = self._base_mesh_by_actor_id.get(actor_id)
            if base_mesh is None:
                continue
            detail_mesh = load_lod_mesh(spec, base_mesh, self._detail_level)
            if detail_mesh is None:
                continue
            dataset = actor.mapper.dataset
            try:
                dataset.copy_from(detail_mesh, deep=True)
            except Exception:
                actor.mapper.dataset = detail_mesh
            self._display_mesh_map[actor_id] = dataset
        self._apply_scene_state()

    def set_selection(
        self,
        selected_ids: Iterable[str],
        *,
        active_id: str | None,
        reference_id: str | None,
        isolate_selection: bool,
        emit_signal: bool = False,
    ) -> None:
        if not self._show_demo_scene:
            return
        valid_ids = set(self._selectable_index)
        reference_valid_ids = set(self._reference_model_lookup) | set(
            self._standing_reference_model_lookup
        )
        self._selected_ids = coerce_selected_ids(selected_ids, valid_ids)
        self._active_id = active_id if active_id in valid_ids else None
        self._reference_id = (
            reference_id.upper()
            if isinstance(reference_id, str) and reference_id.upper() in reference_valid_ids
            else None
        )
        self._isolate_selection = isolate_selection and bool(self._selected_ids)
        if self._active_id is None and self._selected_ids:
            self._active_id = self._selected_ids[-1]
        self._apply_scene_state()
        if emit_signal and self._active_id is not None:
            self.selection_changed.emit(self._active_id, False, False)

    def select_model(self, vertebra_id: str, *, emit_signal: bool = True) -> None:
        if not self._show_demo_scene or vertebra_id not in self._selectable_index:
            return
        selected_ids = self._selected_ids or (vertebra_id,)
        if vertebra_id not in selected_ids:
            selected_ids = (*selected_ids, vertebra_id)
        self.set_selection(
            selected_ids,
            active_id=vertebra_id,
            reference_id=self._reference_id,
            isolate_selection=self._isolate_selection,
            emit_signal=emit_signal,
        )

    def _apply_scene_state(self) -> None:
        if self._plotter is None:
            return
        render_mode = VIEWPORT_MODES[self._mode]
        alignment_offset = self._current_standing_alignment_offset()
        for render_id, actor in self._actor_map.items():
            spec = self._render_model_map[render_id]
            selection_key = spec.selection_key
            selected = selection_key in self._selected_ids if selection_key is not None else False
            active = selection_key == self._active_id if selection_key is not None else False
            reference = self._spec_matches_reference(spec)
            pose_visible = pose_visible_for_name(
                spec.pose_name,
                baseline_visible=self._baseline_pose_visible,
                standing_visible=self._standing_pose_visible,
            )
            visible = pose_visible and (
                not self._isolate_selection or not self._selected_ids or selected
            )

            actor.visibility = visible
            self._set_actor_translation(
                actor,
                alignment_offset if spec.pose_name == "standing" else np.zeros(3, dtype=float),
            )
            actor.prop.style = render_mode.style
            actor.prop.opacity = render_mode.opacity
            actor.prop.show_edges = render_mode.show_edges
            actor.prop.point_size = (
                self._point_size if self._mode == ViewportMode.POINTS else render_mode.point_size
            )
            actor.prop.line_width = 3 if reference or active else render_mode.edge_width
            apply_surface_material(actor, render_mode)
            apply_point_rendering(actor, render_mode.style == "points")

            display_colors = resolve_mesh_visual_colors(
                spec.pose_name,
                selected=selected,
                reference=reference,
            )

            actor.prop.edge_color = resolve_mode_edge_color(
                self._mode,
                display_colors.edge,
                active=active,
                reference=reference,
            )
            actor.prop.color = display_colors.fill

        self._refresh_reference_axes()
        if self._camera_mode == "perspective":
            self._update_orbit_reference()
        else:
            self._center_orthographic_camera_on_origin(reset_scale=False)
        self._refresh_grid()
        self._refresh_pose_delta_glyphs()
        self._plotter.render()

    def _update_orbit_reference(self) -> None:
        if (
            self._plotter is None
            or not self._track_selection_pivot
        ):
            return
        focus = self._current_reference_center()
        up_axis = self._current_reference_basis()[:, 2]
        self._plotter.camera.focal_point = tuple(float(value) for value in focus)
        self._plotter.camera.up = tuple(float(value) for value in up_axis)

    def _refresh_reference_axes(self) -> None:
        if self._disposed or self._plotter is None or pv is None:
            return
        for actor in self._reference_axis_actors:
            self._plotter.remove_actor(actor, reset_camera=False, render=False)
        self._reference_axis_actors.clear()
        if not self._show_reference_axes or self._reference_id is None:
            return

        center = self._current_reference_center()
        basis = self._current_reference_basis()
        axis_specs = [
            (basis[:, 0] * self._reference_axis_length, THEME_COLORS.axis_x),
            (basis[:, 1] * self._reference_axis_length, THEME_COLORS.axis_y),
            (basis[:, 2] * self._reference_axis_length, THEME_COLORS.axis_z),
        ]
        for direction, color in axis_specs:
            start = (
                float(center[0] - direction[0]),
                float(center[1] - direction[1]),
                float(center[2] - direction[2]),
            )
            end = (
                float(center[0] + direction[0]),
                float(center[1] + direction[1]),
                float(center[2] + direction[2]),
            )
            line = pv.Line(start, end)
            actor = self._plotter.add_mesh(
                line,
                color=color,
                line_width=4,
                pickable=False,
                reset_camera=False,
                render=False,
            )
            self._reference_axis_actors.append(actor)

    def _refresh_pose_delta_glyphs(self) -> None:
        if self._disposed or self._plotter is None or pv is None:
            return
        for actor in self._pose_delta_actors:
            self._plotter.remove_actor(actor, reset_camera=False, render=False)
        self._pose_delta_actors.clear()
        if not self._pose_delta_glyphs:
            return

        selected_lookup = set(self._selected_ids)
        endpoint_radius = max(self._reference_axis_length * 0.045, 0.28)
        alignment_offset = self._current_standing_alignment_offset()
        for glyph in self._pose_delta_glyphs:
            vertebra_id = getattr(glyph, "vertebra_id", None)
            if not isinstance(vertebra_id, str):
                continue
            start = tuple(float(value) for value in getattr(glyph, "start", (0.0, 0.0, 0.0)))
            delta = tuple(float(value) for value in getattr(glyph, "delta", (0.0, 0.0, 0.0)))
            color = getattr(glyph, "color", THEME_COLORS.focus)
            endpoint = (
                start[0] + delta[0] + float(alignment_offset[0]),
                start[1] + delta[1] + float(alignment_offset[1]),
                start[2] + delta[2] + float(alignment_offset[2]),
            )
            magnitude = float(getattr(glyph, "magnitude", 0.0))
            selected = not selected_lookup or vertebra_id in selected_lookup
            active = vertebra_id == self._active_id
            reference = vertebra_id == self._reference_id
            opacity = 0.88 if selected else 0.18
            line_width = 7 if active or reference else 4
            point_radius = endpoint_radius * (1.28 if active or reference else 1.0)

            if magnitude > 1e-5:
                line = pv.Line(start, endpoint)
                actor = self._plotter.add_mesh(
                    line,
                    color=color,
                    opacity=opacity,
                    line_width=line_width,
                    pickable=False,
                    lighting=False,
                    reset_camera=False,
                    render=False,
                )
                self._pose_delta_actors.append(actor)

            point = pv.Sphere(
                radius=point_radius,
                center=endpoint,
                theta_resolution=14,
                phi_resolution=14,
            )
            actor = self._plotter.add_mesh(
                point,
                color=color,
                opacity=0.96 if selected else 0.26,
                smooth_shading=False,
                pickable=False,
                reset_camera=False,
                render=False,
            )
            apply_flat_shading(actor)
            self._pose_delta_actors.append(actor)

    def _apply_camera_mode(self, *, reset_scale: bool) -> None:
        if self._disposed or self._plotter is None:
            return
        if self._camera_mode == "perspective":
            self._plotter.camera.parallel_projection = False
            if reset_scale:
                self._plotter.reset_camera()
            self._center_camera_on_origin()
        else:
            if self._camera_mode == "front":
                self._plotter.view_yz()
            elif self._camera_mode == "side":
                self._plotter.view_xz()
            else:
                self._plotter.view_xy()
            if reset_scale:
                self._plotter.reset_camera()
            self._center_orthographic_camera_on_origin(reset_scale=reset_scale)
        self._refresh_grid()
        self._refresh_pose_delta_glyphs()
        self._plotter.render()

    def _handle_camera_modified(self, *_args) -> None:
        if self._disposed:
            return
        self._refresh_grid()

    def _refresh_grid(self) -> None:
        if self._disposed or self._plotter is None or pv is None or self._grid_refreshing:
            return
        if not self._models:
            return

        plotter = self._plotter
        width = max(plotter.width(), 1)
        height = max(plotter.height(), 1)
        focal_values = tuple(float(value) for value in plotter.camera.focal_point[:3])
        if len(focal_values) < 3:
            focal_values = focal_values + (0.0,) * (3 - len(focal_values))
        visible_width, visible_height = visible_world_size(plotter)
        minor_step = nice_grid_step(min(visible_width, visible_height))
        if minor_step <= 0:
            return

        # Camera orbit changes the position continuously while keeping the same
        # focal point, visible extent, and reference basis. Including camera
        # position in the grid signature forces a full floor grid rebuild on
        # every orbit mouse move, which makes the 3D viewport feel like a CPU
        # fallback even on native hardware rendering.
        grid_signature = (
            round(focal_values[0], 3),
            round(focal_values[1], 3),
            round(focal_values[2], 3),
            round(visible_width, 3),
            round(visible_height, 3),
            float(width),
            float(height),
            float(self._camera_mode != "perspective"),
            *tuple(round(float(value), 3) for value in self._current_reference_basis().reshape(-1)),
        )
        if self._last_grid_signature == grid_signature:
            return

        basis = self._current_reference_basis()
        fixed_axis = basis[:, 2]
        horizontal_axis = basis[:, 0]
        depth_axis = basis[:, 1]
        center_horizontal = float(np.dot(np.asarray(focal_values, dtype=float), horizontal_axis))
        center_depth = float(np.dot(np.asarray(focal_values, dtype=float), depth_axis))
        horizontal_min, horizontal_max = scene_span_along_axis(self._models, horizontal_axis)
        depth_min, depth_max = scene_span_along_axis(self._models, depth_axis)
        plane_min, _plane_max = scene_span_along_axis(self._models, fixed_axis)
        left = min(horizontal_min, center_horizontal - visible_width / 2.0)
        right = max(horizontal_max, center_horizontal + visible_width / 2.0)
        back = min(depth_min, center_depth - visible_height / 2.0)
        front = max(depth_max, center_depth + visible_height / 2.0)
        plane_coordinate = float(plane_min)

        self._grid_refreshing = True
        try:
            minor_segments: list[
                tuple[tuple[float, float, float], tuple[float, float, float]]
            ] = []
            major_segments: list[
                tuple[tuple[float, float, float], tuple[float, float, float]]
            ] = []

            def add_grid_line(
                start_horizontal: float,
                start_depth: float,
                end_horizontal: float,
                end_depth: float,
                *,
                major: bool,
            ) -> None:
                start = (
                    fixed_axis * plane_coordinate
                    + horizontal_axis * start_horizontal
                    + depth_axis * start_depth
                )
                end = (
                    fixed_axis * plane_coordinate
                    + horizontal_axis * end_horizontal
                    + depth_axis * end_depth
                )
                segment = (
                    (
                        float(start[0]),
                        float(start[1]),
                        float(start[2]),
                    ),
                    (
                        float(end[0]),
                        float(end[1]),
                        float(end[2]),
                    ),
                )
                if major:
                    major_segments.append(segment)
                else:
                    minor_segments.append(segment)

            for position, major in build_grid_line_positions(left, right, minor_step):
                add_grid_line(position, back, position, front, major=major)

            for position, major in build_grid_line_positions(back, front, minor_step):
                add_grid_line(left, position, right, position, major=major)

            self._update_grid_actor(
                "floor-minor",
                build_line_segment_mesh(minor_segments),
                color=VIEWPORT_GRID_MINOR_COLOR,
                line_width=1,
            )
            self._update_grid_actor(
                "floor-major",
                build_line_segment_mesh(major_segments),
                color=VIEWPORT_GRID_MAJOR_COLOR,
                line_width=2,
            )
        finally:
            self._grid_refreshing = False

        self._last_grid_signature = grid_signature

    def _update_grid_actor(
        self,
        grid_key: str,
        mesh: Any,
        *,
        color: str,
        line_width: int,
    ) -> None:
        if self._plotter is None:
            return
        existing_actor = self._grid_actors.get(grid_key)
        if mesh is None:
            if existing_actor is None:
                return
            self._plotter.remove_actor(existing_actor, reset_camera=False, render=False)
            del self._grid_actors[grid_key]
            return
        if existing_actor is None:
            actor = self._plotter.add_mesh(
                mesh,
                color=color,
                opacity=1.0,
                line_width=line_width,
                pickable=False,
                lighting=False,
                reset_camera=False,
                render=False,
            )
            self._grid_actors[grid_key] = actor
            return

        existing_actor.prop.color = color
        existing_actor.prop.line_width = line_width
        dataset = existing_actor.mapper.dataset
        try:
            dataset.copy_from(mesh, deep=True)
        except Exception:
            existing_actor.mapper.dataset = mesh


class OrthographicMeshViewport(QWidget):
    selection_changed = Signal(str, bool, bool)
    point_size_changed = Signal(int)

    def __init__(
        self,
        title: str,
        view_axis: str,
        *,
        show_demo_scene: bool = True,
        models: list[MockVertebra] | None = None,
        interactive_enabled: bool = True,
        fallback_message: str | None = None,
    ) -> None:
        super().__init__()
        self._title = title
        self._view_axis = view_axis
        self._interactive_enabled = interactive_enabled
        self._fallback_message = fallback_message
        self._models = list(models) if models is not None else (
            list(DEMO_VERTEBRAE) if show_demo_scene else []
        )
        self._reference_model_lookup = build_pose_model_lookup(self._models, pose_name="baseline")
        if not self._reference_model_lookup:
            self._reference_model_lookup = build_pose_model_lookup(self._models)
        self._standing_reference_model_lookup = build_pose_model_lookup(
            self._models,
            pose_name="standing",
        )
        self._selectable_index: dict[str, MockVertebra] = {}
        for model in self._models:
            selection_key = model.selection_key
            if selection_key is None or not model.selectable:
                continue
            self._selectable_index.setdefault(selection_key, model)
        self._show_demo_scene = bool(self._models)
        self._mode = ViewportMode.SOLID
        self._detail_level = DEFAULT_DETAIL_LEVEL
        self._point_size = VIEWPORT_MODES[ViewportMode.POINTS].point_size
        self._baseline_pose_visible = True
        self._standing_pose_visible = True
        self._selected_ids: tuple[str, ...] = ()
        self._active_id: str | None = None
        self._reference_id: str | None = None
        self._isolate_selection = False
        self._plotter = None
        self._surface: QFrame | None = None
        self._transition_overlay: QLabel | None = None
        self._toolbar_overlay: QWidget | None = None
        self._gnomon_overlay: ViewportGnomonOverlay | None = None
        self._floating_toolbar = True
        self._grid_actors: dict[str, Any] = {}
        self._grid_refreshing = False
        self._last_grid_signature: tuple[float, ...] | None = None
        self._actor_map: dict[str, Any] = {}
        self._render_model_map: dict[str, MockVertebra] = {}
        self._mesh_map: dict[str, Any] = {}
        self._display_mesh_map: dict[str, Any] = {}
        self._base_mesh_by_actor_id: dict[str, Any] = {}
        self._reference_axis_actors: list[Any] = []
        self._disposed = False
        self._reference_axis_length = max(
            (max(model.extents) for model in self._models),
            default=REFERENCE_AXIS_LENGTH,
        ) * 0.8

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        title_label = QLabel(title, self)
        title_label.setObjectName("ViewportOverlayChip")
        title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        apply_text_role(title_label, "panel-title")
        self._toolbar_overlay = title_label
        view_kind = "ap" if view_axis == "front" else "lat" if view_axis == "side" else "axial"
        self._gnomon_overlay = ViewportGnomonOverlay(self, view_kind=view_kind)

        surface = QFrame(self)
        surface.setObjectName("ViewportCardFrame")
        self._surface = surface
        surface_layout = QGridLayout(surface)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        surface_layout.setSpacing(0)
        root_layout.addWidget(surface, stretch=1)

        offscreen = os.environ.get("QT_QPA_PLATFORM", "").lower() in {"offscreen", "minimal"}
        backend_available = (
            QtInteractor is not None
            and pv is not None
            and PanZoomQtInteractor is not None
        )
        if not self._interactive_enabled or not backend_available or offscreen:
            self._build_fallback(
                surface_layout,
                resolve_viewport_fallback_message(
                    interactive_enabled=self._interactive_enabled,
                    fallback_message=self._fallback_message,
                    offscreen=offscreen,
                    backend_available=backend_available,
                ),
            )
            return

        self._plotter = PanZoomQtInteractor(surface)
        configure_viewport_render_widget(self._plotter)
        self._plotter.set_background(VIEWPORT_BACKGROUND)
        configure_plotter_studio_lighting(self._plotter)
        self._plotter.enable_parallel_projection()
        surface_layout.addWidget(self._plotter, 0, 0)
        title_label.raise_()
        self._set_camera_view(reset=False)
        self._plotter.camera.AddObserver("ModifiedEvent", self._handle_camera_modified)
        if self._show_demo_scene:
            self._plotter.enable_rubber_band_2d_style()
            self._build_scene()
            self._plotter.enable_mesh_picking(
                callback=self._handle_mesh_pick,
                use_actor=True,
                left_clicking=True,
                show=False,
                show_message=False,
            )

    def _build_fallback(self, surface_layout: QGridLayout, message: str) -> None:
        fallback = QFrame()
        fallback.setObjectName("ViewportFallback")
        fallback_layout = QVBoxLayout(fallback)
        fallback_layout.setContentsMargins(
            GEOMETRY.unit * 2,
            GEOMETRY.unit * 2,
            GEOMETRY.unit * 2,
            GEOMETRY.unit * 2,
        )
        fallback_layout.setSpacing(GEOMETRY.unit)
        fallback_layout.addStretch(1)
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_text_role(message_label, "body")
        fallback_layout.addWidget(message_label)
        surface_layout.addWidget(fallback, 0, 0)

    def closeEvent(self, event) -> None:
        self.dispose()
        super().closeEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.set_render_widget_visible(True)
        self._raise_overlay_widgets()

    def hideEvent(self, event: QHideEvent) -> None:
        self.set_render_widget_visible(False)
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._transition_overlay is not None and self._surface is not None:
            self._transition_overlay.setGeometry(self._surface.rect())
        self._position_toolbar_overlay()
        if self._gnomon_overlay is not None:
            position_gnomon_overlay(self._gnomon_overlay, self._surface)
            self._gnomon_overlay.raise_()

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        plotter = self._plotter
        self._plotter = None
        if plotter is not None:
            try:
                plotter._suppress_rendering = True
            except Exception:
                pass
            render_timer = getattr(plotter, "render_timer", None)
            if render_timer is not None:
                try:
                    render_timer.stop()
                except Exception:
                    pass
                try:
                    render_timer.timeout.disconnect()
                except Exception:
                    pass
            try:
                plotter.close()
            except Exception:
                pass
            try:
                plotter.Finalize()
            except Exception:
                pass
        if plotter is not None:
            for actor in self._grid_actors.values():
                try:
                    plotter.remove_actor(actor, reset_camera=False, render=False)
                except Exception:
                    pass
        self._grid_actors.clear()
        self._actor_map.clear()
        self._render_model_map.clear()
        self._mesh_map.clear()
        self._display_mesh_map.clear()
        self._base_mesh_by_actor_id.clear()
        self._reference_axis_actors.clear()
        self._last_grid_signature = None
        self._surface = None
        if self._transition_overlay is not None:
            self._transition_overlay.deleteLater()
            self._transition_overlay = None
        self._toolbar_overlay = None
        self._gnomon_overlay = None

    def set_render_widget_visible(self, visible: bool) -> None:
        if self._disposed or self._plotter is None:
            return
        self._plotter.setVisible(visible)
        self._plotter.setUpdatesEnabled(visible)
        if not visible:
            return
        try:
            self._raise_overlay_widgets()
        except Exception:
            pass
        try:
            self._plotter.render()
        except Exception:
            pass

    def set_layout_transition_active(self, active: bool) -> None:
        surface = self._surface
        if self._disposed or surface is None:
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
            if self._plotter is not None:
                self._plotter.hide()
            overlay.show()
            overlay.raise_()
            self._raise_overlay_widgets()
            return
        if self._transition_overlay is None:
            return
        if self._plotter is not None:
            self._plotter.show()
        self._transition_overlay.deleteLater()
        self._transition_overlay = None
        self._raise_overlay_widgets()
        if self._plotter is not None:
            try:
                self._plotter.render()
            except Exception:
                pass
        self.update()

    def _capture_surface_snapshot(self) -> QPixmap:
        surface = self._surface
        if surface is None:
            return QPixmap()
        return surface.grab()

    def _raise_toolbar_overlay(self) -> None:
        if self._toolbar_overlay is None:
            return
        self._toolbar_overlay.show()
        self._position_toolbar_overlay()
        self._toolbar_overlay.raise_()

    def _raise_overlay_widgets(self) -> None:
        self._raise_toolbar_overlay()
        if self._gnomon_overlay is not None:
            self._gnomon_overlay.show()
            position_gnomon_overlay(self._gnomon_overlay, self._surface)
            self._gnomon_overlay.raise_()

    def _position_toolbar_overlay(self) -> None:
        toolbar = self._toolbar_overlay
        surface = self._surface
        if toolbar is None or surface is None:
            return
        toolbar.adjustSize()
        size = toolbar.sizeHint().expandedTo(toolbar.minimumSizeHint())
        toolbar.setGeometry(
            surface.x() + GEOMETRY.overlay_padding,
            surface.y() + GEOMETRY.overlay_padding,
            size.width(),
            size.height(),
        )

    def _build_scene(self) -> None:
        if self._disposed or self._plotter is None or pv is None:
            return
        render_mode = VIEWPORT_MODES[self._mode]
        for spec in self._models:
            base_mesh = build_mock_mesh(spec)
            if base_mesh is None:
                continue
            mesh = load_lod_mesh(spec, base_mesh, self._detail_level)
            if mesh is None:
                continue
            actor_id = spec.actor_id
            initial_colors = resolve_mesh_visual_colors(
                spec.pose_name,
                selected=False,
                reference=False,
            )
            actor = self._plotter.add_mesh(
                mesh,
                color=initial_colors.fill,
                opacity=render_mode.opacity,
                lighting=render_mode.lighting,
                smooth_shading=render_mode.smooth_shading,
                show_edges=render_mode.show_edges,
                name=f"{self._title}-{actor_id}",
                pickable=spec.selectable,
            )
            apply_surface_material(actor, render_mode)
            actor.prop.edge_color = initial_colors.edge
            actor._selection_id = spec.selection_key if spec.selectable else None
            self._actor_map[actor_id] = actor
            self._render_model_map[actor_id] = spec
            self._display_mesh_map[actor_id] = mesh
            self._base_mesh_by_actor_id[actor_id] = base_mesh
            selection_key = spec.selection_key
            if selection_key is not None and (
                selection_key not in self._mesh_map or spec.pose_name == "baseline"
            ):
                self._mesh_map[selection_key] = base_mesh
            reference_key = spec.vertebra_id.upper()
            if reference_key not in self._mesh_map or spec.pose_name == "baseline":
                self._mesh_map[reference_key] = base_mesh
        self._set_camera_view(reset=True)
        self._apply_scene_state()

    def _current_reference_model(self) -> MockVertebra | None:
        if self._reference_id is None:
            return None
        reference_key = self._reference_id.upper()
        return self._reference_model_lookup.get(
            reference_key
        ) or self._standing_reference_model_lookup.get(
            reference_key
        )

    def _current_reference_center(self) -> np.ndarray:
        reference_model = self._current_reference_model()
        if reference_model is not None:
            return np.asarray(reference_model.center, dtype=float)
        return np.array((0.0, 0.0, 0.0), dtype=float)

    def _current_reference_basis(self) -> np.ndarray:
        return reference_basis_for_model(self._current_reference_model())

    def _current_standing_alignment_offset(self) -> np.ndarray:
        if self._reference_id is None:
            return np.zeros(3, dtype=float)
        reference_key = self._reference_id.upper()
        baseline_model = self._reference_model_lookup.get(reference_key)
        standing_model = self._standing_reference_model_lookup.get(reference_key)
        if baseline_model is None or standing_model is None:
            return np.zeros(3, dtype=float)
        return np.array(
            (
                baseline_model.center[0] - standing_model.center[0],
                baseline_model.center[1] - standing_model.center[1],
                baseline_model.center[2] - standing_model.center[2],
            ),
            dtype=float,
        )

    def _set_actor_translation(self, actor: Any, translation: np.ndarray) -> None:
        offset = tuple(float(value) for value in translation)
        try:
            actor.position = offset
            return
        except Exception:
            pass
        try:
            actor.SetPosition(*offset)
        except Exception:
            pass

    def _spec_matches_reference(self, spec: MockVertebra) -> bool:
        if self._reference_id is None:
            return False
        reference_key = self._reference_id.upper()
        selection_key = spec.selection_key.upper() if spec.selection_key is not None else None
        return selection_key == reference_key or spec.vertebra_id.upper() == reference_key

    def _set_camera_view(self, *, reset: bool = False) -> None:
        if self._disposed or self._plotter is None:
            return
        self._plotter.camera.parallel_projection = True
        if reset:
            self._plotter.reset_camera()
        self._center_camera_on_origin(reset_scale=reset)
        self._refresh_grid()
        self._plotter.render()

    def _center_camera_on_origin(self, *, reset_scale: bool) -> None:
        if self._disposed or self._plotter is None:
            return
        camera = self._plotter.camera
        basis = self._current_reference_basis()
        focus = self._current_reference_center()
        position = np.asarray(camera.position, dtype=float)
        focal_point = np.asarray(camera.focal_point, dtype=float)
        direction = position - focal_point
        direction = normalize_vector(direction)
        if direction is None:
            direction = (
                basis[:, 0]
                if self._view_axis == "front"
                else basis[:, 1]
            )
        if self._view_axis == "front":
            direction = basis[:, 0]
            horizontal_axis = basis[:, 1]
            vertical_axis = basis[:, 2]
            camera.up = tuple(float(value) for value in basis[:, 2])
        else:
            direction = basis[:, 1]
            horizontal_axis = basis[:, 0]
            vertical_axis = basis[:, 2]
            camera.up = tuple(float(value) for value in basis[:, 2])
        distance = max(float(np.linalg.norm(position - focal_point)), 1.0)
        camera.focal_point = tuple(float(value) for value in focus)
        camera.position = tuple(float(value) for value in (focus + direction * distance))
        if reset_scale:
            width = max(self._plotter.width(), 1)
            height = max(self._plotter.height(), 1)
            aspect_ratio = width / max(height, 1)
            horizontal_min, horizontal_max = scene_span_along_axis(self._models, horizontal_axis)
            vertical_min, vertical_max = scene_span_along_axis(self._models, vertical_axis)
            horizontal_span = max(horizontal_max - horizontal_min, 1.0)
            vertical_span = max(vertical_max - vertical_min, 1.0)
            camera.parallel_scale = max(
                vertical_span / 2.0,
                horizontal_span / max(2.0 * aspect_ratio, 1e-6),
                1.0,
            ) * 1.08

    def _handle_camera_modified(self, *_args) -> None:
        if self._disposed:
            return
        self._refresh_grid()

    def _refresh_grid(self) -> None:
        if self._disposed or self._plotter is None or pv is None or self._grid_refreshing:
            return
        plotter = self._plotter
        width = max(self._plotter.width(), 1)
        height = max(self._plotter.height(), 1)
        focal_values = tuple(float(value) for value in plotter.camera.focal_point[:3])
        if len(focal_values) < 3:
            focal_values = focal_values + (0.0,) * (3 - len(focal_values))
        parallel_scale = float(plotter.camera.parallel_scale)
        if parallel_scale <= 0:
            return

        grid_signature = (
            round(focal_values[0], 3),
            round(focal_values[1], 3),
            round(focal_values[2], 3),
            round(parallel_scale, 3),
            float(width),
            float(height),
            *tuple(round(float(value), 3) for value in self._current_reference_basis().reshape(-1)),
        )
        if self._last_grid_signature == grid_signature:
            return

        aspect_ratio = width / max(height, 1)
        visible_height = parallel_scale * 2.0
        visible_width = visible_height * aspect_ratio
        minor_step = nice_grid_step(min(visible_width, visible_height))
        if minor_step <= 0:
            return

        basis = self._current_reference_basis()
        if self._view_axis == "front":
            fixed_axis = basis[:, 0]
            horizontal_axis = basis[:, 1]
        else:
            fixed_axis = basis[:, 1]
            horizontal_axis = basis[:, 0]
        vertical_axis = basis[:, 2]

        center_horizontal = float(np.dot(np.asarray(focal_values, dtype=float), horizontal_axis))
        center_vertical = float(np.dot(np.asarray(focal_values, dtype=float), vertical_axis))
        left = center_horizontal - visible_width / 2.0
        right = center_horizontal + visible_width / 2.0
        bottom = center_vertical - visible_height / 2.0
        top = center_vertical + visible_height / 2.0
        plane_coordinate = float(np.dot(np.asarray(focal_values, dtype=float), fixed_axis))

        self._grid_refreshing = True
        try:
            minor_segments: list[tuple[tuple[float, float, float], tuple[float, float, float]]] = []
            major_segments: list[tuple[tuple[float, float, float], tuple[float, float, float]]] = []

            def add_grid_line(
                start_horizontal: float,
                start_vertical: float,
                end_horizontal: float,
                end_vertical: float,
                *,
                major: bool,
            ) -> None:
                start = (
                    fixed_axis * plane_coordinate
                    + horizontal_axis * start_horizontal
                    + vertical_axis * start_vertical
                )
                end = (
                    fixed_axis * plane_coordinate
                    + horizontal_axis * end_horizontal
                    + vertical_axis * end_vertical
                )
                segment = (
                    (
                        float(start[0]),
                        float(start[1]),
                        float(start[2]),
                    ),
                    (
                        float(end[0]),
                        float(end[1]),
                        float(end[2]),
                    ),
                )
                if major:
                    major_segments.append(segment)
                else:
                    minor_segments.append(segment)

            for position, major in build_grid_line_positions(left, right, minor_step):
                add_grid_line(
                    position,
                    bottom,
                    position,
                    top,
                    major=major,
                )

            for position, major in build_grid_line_positions(bottom, top, minor_step):
                add_grid_line(
                    left,
                    position,
                    right,
                    position,
                    major=major,
                )

            self._update_grid_actor(
                "minor",
                build_line_segment_mesh(minor_segments),
                color=VIEWPORT_GRID_MINOR_COLOR,
                line_width=1,
            )
            self._update_grid_actor(
                "major",
                build_line_segment_mesh(major_segments),
                color=VIEWPORT_GRID_MAJOR_COLOR,
                line_width=2,
            )
        finally:
            self._grid_refreshing = False

        self._last_grid_signature = grid_signature

    def _update_grid_actor(
        self,
        grid_key: str,
        mesh: Any,
        *,
        color: str,
        line_width: int,
    ) -> None:
        if self._plotter is None:
            return
        existing_actor = self._grid_actors.get(grid_key)
        if mesh is None:
            if existing_actor is None:
                return
            self._plotter.remove_actor(existing_actor, reset_camera=False, render=False)
            del self._grid_actors[grid_key]
            return
        if existing_actor is None:
            actor = self._plotter.add_mesh(
                mesh,
                color=color,
                opacity=1.0,
                line_width=line_width,
                pickable=False,
                lighting=False,
                reset_camera=False,
                render=False,
            )
            self._grid_actors[grid_key] = actor
            return

        existing_actor.prop.color = color
        existing_actor.prop.line_width = line_width
        dataset = existing_actor.mapper.dataset
        try:
            dataset.copy_from(mesh, deep=True)
        except Exception:
            existing_actor.mapper.dataset = mesh

    def _handle_mesh_pick(self, actor) -> None:
        if self._disposed:
            return
        if self._plotter is not None:
            self._plotter.mark_pick_handled()
        vertebra_id = getattr(actor, "_selection_id", None)
        if isinstance(vertebra_id, str):
            remove_requested = (
                self._plotter.remove_requested()
                if self._plotter is not None
                else False
            )
            set_primary_requested = (
                self._plotter.set_primary_requested()
                if self._plotter is not None
                else False
            )
            self.selection_changed.emit(vertebra_id, remove_requested, set_primary_requested)

    def set_selection(
        self,
        selected_ids: Iterable[str],
        *,
        active_id: str | None,
        reference_id: str | None,
        isolate_selection: bool,
        emit_signal: bool = False,
    ) -> None:
        if not self._show_demo_scene:
            return
        valid_ids = set(self._selectable_index)
        reference_valid_ids = set(self._reference_model_lookup) | set(
            self._standing_reference_model_lookup
        )
        self._selected_ids = coerce_selected_ids(selected_ids, valid_ids)
        self._active_id = active_id if active_id in valid_ids else None
        self._reference_id = (
            reference_id.upper()
            if isinstance(reference_id, str) and reference_id.upper() in reference_valid_ids
            else None
        )
        self._isolate_selection = isolate_selection and bool(self._selected_ids)
        if self._active_id is None and self._selected_ids:
            self._active_id = self._selected_ids[-1]
        self._apply_scene_state()
        if emit_signal and self._active_id is not None:
            self.selection_changed.emit(self._active_id, False, False)

    def select_model(self, vertebra_id: str, *, emit_signal: bool = True) -> None:
        if not self._show_demo_scene or vertebra_id not in self._selectable_index:
            return
        selected_ids = self._selected_ids or (vertebra_id,)
        if vertebra_id not in selected_ids:
            selected_ids = (*selected_ids, vertebra_id)
        self.set_selection(
            selected_ids,
            active_id=vertebra_id,
            reference_id=self._reference_id,
            isolate_selection=self._isolate_selection,
            emit_signal=emit_signal,
        )

    def set_mode(self, mode: ViewportMode) -> None:
        if self._mode == mode:
            return
        self._mode = mode
        self._apply_scene_state()

    def current_mode(self) -> ViewportMode:
        return self._mode

    def set_detail_level(self, level: int) -> None:
        normalized_level = coerce_detail_level(level)
        if normalized_level == self._detail_level:
            return
        self._detail_level = normalized_level
        self._apply_detail_level()

    def current_detail_level(self) -> int:
        return self._detail_level

    def set_point_size(self, point_size: int) -> None:
        normalized_size = max(2, min(int(point_size), 24))
        if normalized_size == self._point_size:
            return
        self._point_size = normalized_size
        self._apply_scene_state()
        self.point_size_changed.emit(normalized_size)

    def current_point_size(self) -> int:
        return self._point_size

    def fit_scene_to_reference(self) -> None:
        self._set_camera_view(reset=True)

    def set_pose_visibility(self, *, baseline_visible: bool, standing_visible: bool) -> None:
        next_baseline_visible = bool(baseline_visible)
        next_standing_visible = bool(standing_visible)
        if (
            self._baseline_pose_visible == next_baseline_visible
            and self._standing_pose_visible == next_standing_visible
        ):
            return
        self._baseline_pose_visible = next_baseline_visible
        self._standing_pose_visible = next_standing_visible
        self._apply_scene_state()

    def current_pose_visibility(self) -> tuple[bool, bool]:
        return self._baseline_pose_visible, self._standing_pose_visible

    def _apply_detail_level(self) -> None:
        if self._disposed or self._plotter is None:
            return
        for actor_id, actor in self._actor_map.items():
            spec = self._render_model_map[actor_id]
            base_mesh = self._base_mesh_by_actor_id.get(actor_id)
            if base_mesh is None:
                continue
            detail_mesh = load_lod_mesh(spec, base_mesh, self._detail_level)
            if detail_mesh is None:
                continue
            dataset = actor.mapper.dataset
            try:
                dataset.copy_from(detail_mesh, deep=True)
            except Exception:
                actor.mapper.dataset = detail_mesh
            self._display_mesh_map[actor_id] = dataset
        self._apply_scene_state()

    def _apply_scene_state(self) -> None:
        if self._disposed or self._plotter is None:
            return
        render_mode = VIEWPORT_MODES[self._mode]
        alignment_offset = self._current_standing_alignment_offset()
        for render_id, actor in self._actor_map.items():
            spec = self._render_model_map[render_id]
            selection_key = spec.selection_key
            selected = selection_key in self._selected_ids if selection_key is not None else False
            active = selection_key == self._active_id if selection_key is not None else False
            reference = self._spec_matches_reference(spec)
            pose_visible = pose_visible_for_name(
                spec.pose_name,
                baseline_visible=self._baseline_pose_visible,
                standing_visible=self._standing_pose_visible,
            )
            visible = pose_visible and (
                not self._isolate_selection or not self._selected_ids or selected
            )

            actor.visibility = visible
            self._set_actor_translation(
                actor,
                alignment_offset if spec.pose_name == "standing" else np.zeros(3, dtype=float),
            )
            actor.prop.style = render_mode.style
            actor.prop.opacity = render_mode.opacity
            actor.prop.show_edges = render_mode.show_edges
            actor.prop.point_size = (
                self._point_size if self._mode == ViewportMode.POINTS else render_mode.point_size
            )
            actor.prop.line_width = 3 if reference or active else render_mode.edge_width
            apply_surface_material(actor, render_mode)
            apply_point_rendering(actor, render_mode.style == "points")

            display_colors = resolve_mesh_visual_colors(
                spec.pose_name,
                selected=selected,
                reference=reference,
            )

            actor.prop.edge_color = resolve_mode_edge_color(
                self._mode,
                display_colors.edge,
                active=active,
                reference=reference,
            )
            actor.prop.color = display_colors.fill

        self._center_camera_on_origin(reset_scale=False)
        self._refresh_reference_axes()
        self._refresh_grid()
        self._plotter.render()

    def _refresh_reference_axes(self) -> None:
        if self._disposed or self._plotter is None or pv is None:
            return
        for actor in self._reference_axis_actors:
            self._plotter.remove_actor(actor, reset_camera=False, render=False)
        self._reference_axis_actors.clear()
        if self._reference_id is None:
            return

        center = self._current_reference_center()
        basis = self._current_reference_basis()
        axis_specs = [
            (basis[:, 0] * self._reference_axis_length, THEME_COLORS.axis_x),
            (basis[:, 1] * self._reference_axis_length, THEME_COLORS.axis_y),
            (basis[:, 2] * self._reference_axis_length, THEME_COLORS.axis_z),
        ]
        for direction, color in axis_specs:
            start = (
                float(center[0] - direction[0]),
                float(center[1] - direction[1]),
                float(center[2] - direction[2]),
            )
            end = (
                float(center[0] + direction[0]),
                float(center[1] + direction[1]),
                float(center[2] + direction[2]),
            )
            line = pv.Line(start, end)
            actor = self._plotter.add_mesh(
                line,
                color=color,
                line_width=4,
                pickable=False,
                reset_camera=False,
                render=False,
            )
            self._reference_axis_actors.append(actor)
