from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import SimpleITK as sitk

from spinelab.ontology import CoordinateSystem

_SEGMENT_NAME_PATTERN = re.compile(r"^Segment(\d+)_Name$")


@dataclass(frozen=True, slots=True)
class LoadedVolume:
    path: Path
    image: sitk.Image
    coordinate_system: CoordinateSystem

    @property
    def spacing_mm(self) -> tuple[float, float, float]:
        spacing = self.image.GetSpacing()
        return (float(spacing[0]), float(spacing[1]), float(spacing[2]))

    @property
    def origin_mm(self) -> tuple[float, float, float]:
        origin = self.image.GetOrigin()
        return (float(origin[0]), float(origin[1]), float(origin[2]))

    @property
    def size_xyz(self) -> tuple[int, int, int]:
        size = self.image.GetSize()
        return (int(size[0]), int(size[1]), int(size[2]))


@dataclass(frozen=True, slots=True)
class LoadedSegmentation:
    path: Path
    image: sitk.Image
    coordinate_system: CoordinateSystem
    masks: dict[str, np.ndarray]
    label_values: dict[str, int]
    layers: dict[str, int]
    raw_metadata: dict[str, str]

    @property
    def spacing_mm(self) -> tuple[float, float, float]:
        spacing = self.image.GetSpacing()
        return (float(spacing[0]), float(spacing[1]), float(spacing[2]))


@dataclass(frozen=True, slots=True)
class LoadedMarkups:
    path: Path
    coordinate_system: CoordinateSystem
    points: dict[str, np.ndarray]


def _normalize_coordinate_system(value: str | None) -> CoordinateSystem:
    normalized = (value or "").strip().upper()
    if normalized == CoordinateSystem.RAS.value:
        return CoordinateSystem.RAS
    if normalized == CoordinateSystem.LPS.value:
        return CoordinateSystem.LPS
    lowered = normalized.lower()
    if lowered == "right-anterior-superior":
        return CoordinateSystem.RAS
    if lowered == "left-posterior-superior":
        return CoordinateSystem.LPS
    return CoordinateSystem.LPS


def convert_point_coordinates(
    point_xyz: tuple[float, float, float] | list[float] | np.ndarray,
    source: CoordinateSystem,
    target: CoordinateSystem,
) -> np.ndarray:
    point = np.asarray(point_xyz, dtype=float).reshape(3)
    if source == target:
        return point
    return np.asarray((-point[0], -point[1], point[2]), dtype=float)


def convert_points_coordinates(
    points_xyz: np.ndarray,
    source: CoordinateSystem,
    target: CoordinateSystem,
) -> np.ndarray:
    points = np.asarray(points_xyz, dtype=float)
    if source == target:
        return points
    converted = points.copy()
    converted[..., 0] *= -1.0
    converted[..., 1] *= -1.0
    return converted


def load_volume(path: Path) -> LoadedVolume:
    image = sitk.ReadImage(str(path))
    coordinate_system = _normalize_coordinate_system(
        image.GetMetaData("space") if image.HasMetaDataKey("space") else None
    )
    return LoadedVolume(path=path, image=image, coordinate_system=coordinate_system)


def load_segmentation(path: Path) -> LoadedSegmentation:
    image = sitk.ReadImage(str(path))
    coordinate_system = _normalize_coordinate_system(
        image.GetMetaData("space") if image.HasMetaDataKey("space") else None
    )
    raw_metadata = {key: image.GetMetaData(key) for key in image.GetMetaDataKeys()}
    array = sitk.GetArrayFromImage(image)
    masks: dict[str, np.ndarray] = {}
    label_values: dict[str, int] = {}
    layers: dict[str, int] = {}
    segment_indices = sorted(
        int(match.group(1))
        for key in raw_metadata
        if (match := _SEGMENT_NAME_PATTERN.match(key)) is not None
    )
    for segment_index in segment_indices:
        name = raw_metadata.get(f"Segment{segment_index}_Name")
        if not name:
            continue
        label_value = int(raw_metadata.get(f"Segment{segment_index}_LabelValue", "1"))
        layer = int(raw_metadata.get(f"Segment{segment_index}_Layer", "0"))
        if array.ndim == 4:
            if layer < 0 or layer >= array.shape[0]:
                continue
            segment_array = array[layer]
        else:
            segment_array = array
        mask = np.asarray(segment_array == label_value, dtype=bool)
        if not mask.any():
            continue
        masks[name] = mask
        label_values[name] = label_value
        layers[name] = layer
    return LoadedSegmentation(
        path=path,
        image=image,
        coordinate_system=coordinate_system,
        masks=masks,
        label_values=label_values,
        layers=layers,
        raw_metadata=raw_metadata,
    )


def load_markups(path: Path) -> LoadedMarkups:
    payload = json.loads(path.read_text(encoding="utf-8"))
    markup_entries = payload.get("markups", [])
    coordinate_system = CoordinateSystem.LPS
    points: dict[str, np.ndarray] = {}
    for markup in markup_entries:
        coordinate_system = _normalize_coordinate_system(markup.get("coordinateSystem"))
        for control_point in markup.get("controlPoints", []):
            label = str(control_point.get("label", "")).strip()
            position = control_point.get("position", [])
            if not label or not isinstance(position, list) or len(position) != 3:
                continue
            if label in points:
                raise ValueError(f"Duplicate markup label: {label}")
            points[label] = np.asarray(position, dtype=float)
    return LoadedMarkups(path=path, coordinate_system=coordinate_system, points=points)
