from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from spinelab.ui.theme import THEME_COLORS

Point3D = tuple[float, float, float]

_SEGMENT_LABEL_PATTERN = re.compile(
    r"^(?:(?P<range>[CTLS]\d+-[CTLS]\d+)\s+)?(?P<label>.+)$",
    re.IGNORECASE,
)
_AUTO_MEASUREMENT_LABELS = {
    "disc height",
    "listhesis",
    "segmental lordosis/kyphosis",
    "lumbar lordosis",
    "thoracic kyphosis",
}
_LINE_COLOR = THEME_COLORS.danger
_POINT_COLOR = THEME_COLORS.danger


@dataclass(frozen=True)
class OverlayGeometry:
    overlay_id: str
    label: str
    line_segments: tuple[tuple[Point3D, Point3D], ...] = ()
    anchor_points: tuple[Point3D, ...] = ()
    line_color: str = _LINE_COLOR
    point_color: str = _POINT_COLOR
    line_width: int = 4
    point_size: int = 18


class MeasurementOverlayController:
    def __init__(
        self,
        viewport: Any,
        landmarks_payload_getter: Callable[[], dict[str, Any] | None],
    ) -> None:
        self._viewport = viewport
        self._landmarks_payload_getter = landmarks_payload_getter
        self._current_measurement: str | None = None

    def refresh(self, measurement_name: str | None) -> OverlayGeometry | None:
        self._current_measurement = measurement_name
        payload = self._landmarks_payload_getter()
        geometry = build_measurement_overlay_geometry(measurement_name, payload)
        set_geometry = getattr(self._viewport, "set_overlay_geometry", None)
        if callable(set_geometry):
            set_geometry("automatic-measurement", geometry)
        return geometry

    def clear(self) -> None:
        clear_geometry = getattr(self._viewport, "clear_overlay_geometry", None)
        if callable(clear_geometry):
            clear_geometry("automatic-measurement")
        self._current_measurement = None


def build_measurement_overlay_geometry(
    measurement_name: str | None,
    payload: dict[str, Any] | None,
) -> OverlayGeometry | None:
    if measurement_name is None or payload is None:
        return None
    normalized_name = measurement_name.strip().lower()
    is_disc_height = (
        "disc height" in normalized_name
        or "disc midpoint height" in normalized_name
    )
    if (
        not is_disc_height
        and "listhesis" not in normalized_name
        and "segmental lordosis/kyphosis" not in normalized_name
        and normalized_name not in _AUTO_MEASUREMENT_LABELS
    ):
        return None

    landmark_lookup = _landmark_lookup(payload)
    if not landmark_lookup:
        return None

    if normalized_name == "lumbar lordosis":
        return _build_global_angle_overlay(
            measurement_name,
            landmark_lookup,
            cranial_level="L1",
            cranial_endplate="superior",
            caudal_level="S1",
            caudal_endplate="superior",
        )
    if normalized_name == "thoracic kyphosis":
        return _build_global_angle_overlay(
            measurement_name,
            landmark_lookup,
            cranial_level="T4",
            cranial_endplate="superior",
            caudal_level="T12",
            caudal_endplate="inferior",
        )

    segment = _segment_levels(measurement_name)
    if segment is None and "disc height" in normalized_name:
        return None
    if segment is None:
        return None
    cranial_level, caudal_level = segment

    if is_disc_height:
        return _build_disc_height_overlay(
            measurement_name,
            landmark_lookup,
            cranial_level,
            caudal_level,
        )
    if "listhesis" in normalized_name:
        return _build_listhesis_overlay(
            measurement_name,
            landmark_lookup,
            cranial_level,
            caudal_level,
        )
    if "segmental lordosis/kyphosis" in normalized_name:
        return _build_global_angle_overlay(
            measurement_name,
            landmark_lookup,
            cranial_level=cranial_level,
            cranial_endplate="inferior",
            caudal_level=caudal_level,
            caudal_endplate="superior",
        )
    return None


def _build_disc_height_overlay(
    measurement_name: str,
    landmark_lookup: dict[str, dict[str, Any]],
    cranial_level: str,
    caudal_level: str,
) -> OverlayGeometry | None:
    cranial = landmark_lookup.get(cranial_level)
    caudal = landmark_lookup.get(caudal_level)
    if cranial is None or caudal is None:
        return None

    cranial_midpoint = _primitive_point(cranial, "inferior_endplate_midpoint")
    caudal_midpoint = _primitive_point(caudal, "superior_endplate_midpoint")
    if cranial_midpoint is None or caudal_midpoint is None:
        return None

    line_segments = ((cranial_midpoint, caudal_midpoint),)
    anchor_points = (cranial_midpoint, caudal_midpoint)
    return OverlayGeometry(
        overlay_id="automatic-measurement",
        label=measurement_name,
        line_segments=line_segments,
        anchor_points=anchor_points,
    )


def _build_listhesis_overlay(
    measurement_name: str,
    landmark_lookup: dict[str, dict[str, Any]],
    cranial_level: str,
    caudal_level: str,
) -> OverlayGeometry | None:
    cranial = landmark_lookup.get(cranial_level)
    caudal = landmark_lookup.get(caudal_level)
    if cranial is None or caudal is None:
        return None

    cranial_wall = _primitive_line(cranial, "posterior_wall_line")
    caudal_wall = _primitive_line(caudal, "posterior_wall_line")
    cranial_midpoint = _primitive_point(cranial, "posterior_superior_corner")
    caudal_midpoint = _primitive_point(caudal, "posterior_superior_corner")
    if (
        cranial_wall is None
        or caudal_wall is None
        or cranial_midpoint is None
        or caudal_midpoint is None
    ):
        return None

    line_segments = (
        cranial_wall,
        caudal_wall,
        (cranial_midpoint, caudal_midpoint),
    )
    anchor_points = (
        cranial_wall[0],
        cranial_wall[1],
        caudal_wall[0],
        caudal_wall[1],
        cranial_midpoint,
        caudal_midpoint,
    )
    return OverlayGeometry(
        overlay_id="automatic-measurement",
        label=measurement_name,
        line_segments=line_segments,
        anchor_points=anchor_points,
    )


def _build_global_angle_overlay(
    measurement_name: str,
    landmark_lookup: dict[str, dict[str, Any]],
    *,
    cranial_level: str,
    cranial_endplate: str,
    caudal_level: str,
    caudal_endplate: str,
) -> OverlayGeometry | None:
    cranial = landmark_lookup.get(cranial_level)
    caudal = landmark_lookup.get(caudal_level)
    if cranial is None or caudal is None:
        return None

    cranial_segment = _endplate_segment(cranial, cranial_endplate)
    caudal_segment = _endplate_segment(caudal, caudal_endplate)
    cranial_midpoint = _endplate_midpoint(cranial, cranial_endplate)
    caudal_midpoint = _endplate_midpoint(caudal, caudal_endplate)
    if (
        cranial_segment is None
        or caudal_segment is None
        or cranial_midpoint is None
        or caudal_midpoint is None
    ):
        return None

    line_segments = (
        cranial_segment,
        caudal_segment,
        (cranial_midpoint, caudal_midpoint),
    )
    anchor_points = (
        cranial_segment[0],
        cranial_segment[1],
        caudal_segment[0],
        caudal_segment[1],
        cranial_midpoint,
        caudal_midpoint,
    )
    return OverlayGeometry(
        overlay_id="automatic-measurement",
        label=measurement_name,
        line_segments=line_segments,
        anchor_points=anchor_points,
    )


def _landmark_lookup(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for entry in payload.get("vertebrae", []):
        if not isinstance(entry, dict):
            continue
        vertebra_id = str(entry.get("vertebra_id", "")).strip().upper()
        primitives = entry.get("primitives")
        if vertebra_id and isinstance(primitives, dict):
            lookup[vertebra_id] = entry
    return lookup


def _segment_levels(measurement_name: str) -> tuple[str, str] | None:
    match = _SEGMENT_LABEL_PATTERN.match(measurement_name.strip())
    if match is None:
        return None
    range_text = match.group("range")
    if not range_text:
        return None
    cranial, caudal = range_text.upper().split("-", 1)
    if not cranial or not caudal:
        return None
    return cranial, caudal


def _primitive_point(entry: dict[str, Any], primitive_id: str) -> Point3D | None:
    primitive = _primitive(entry, primitive_id)
    if primitive is None:
        return None
    point = primitive.get("point_mm")
    if isinstance(point, (list, tuple)) and len(point) == 3:
        try:
            return cast(
                Point3D,
                tuple(float(value) for value in point),
            )
        except (TypeError, ValueError):
            return None
    points = primitive.get("points_mm")
    if isinstance(points, (list, tuple)) and points:
        try:
            coords = [tuple(float(value) for value in point) for point in points]
        except (TypeError, ValueError):
            return None
        if not coords:
            return None
        count = float(len(coords))
        return cast(
            Point3D,
            (
            sum(point[0] for point in coords) / count,
            sum(point[1] for point in coords) / count,
            sum(point[2] for point in coords) / count,
            ),
        )
    return None


def _primitive_line(
    entry: dict[str, Any],
    primitive_id: str,
) -> tuple[Point3D, Point3D] | None:
    primitive = _primitive(entry, primitive_id)
    if primitive is None:
        return None
    points = primitive.get("points_mm")
    if not isinstance(points, (list, tuple)) or len(points) < 2:
        return None
    try:
        first = cast(Point3D, tuple(float(value) for value in points[0]))
        second = cast(Point3D, tuple(float(value) for value in points[1]))
    except (TypeError, ValueError):
        return None
    return first, second


def _endplate_segment(entry: dict[str, Any], endplate: str) -> tuple[Point3D, Point3D] | None:
    if endplate == "superior":
        return _primitive_line(entry, "superior_endplate_line") or _corner_segment(
            entry,
            "anterior_superior_corner",
            "posterior_superior_corner",
        )
    if endplate == "inferior":
        return _primitive_line(entry, "inferior_endplate_line") or _corner_segment(
            entry,
            "anterior_inferior_corner",
            "posterior_inferior_corner",
        )
    return None


def _endplate_midpoint(entry: dict[str, Any], endplate: str) -> Point3D | None:
    if endplate == "superior":
        return _primitive_point(entry, "superior_endplate_midpoint")
    if endplate == "inferior":
        return _primitive_point(entry, "inferior_endplate_midpoint")
    return None


def _corner_segment(
    entry: dict[str, Any],
    first_corner: str,
    second_corner: str,
) -> tuple[Point3D, Point3D] | None:
    first = _primitive_point(entry, first_corner)
    second = _primitive_point(entry, second_corner)
    if first is None or second is None:
        return None
    return first, second


def _primitive(entry: dict[str, Any], primitive_id: str) -> dict[str, Any] | None:
    primitives = entry.get("primitives")
    if not isinstance(primitives, dict):
        return None
    primitive = primitives.get(primitive_id)
    return primitive if isinstance(primitive, dict) else None
