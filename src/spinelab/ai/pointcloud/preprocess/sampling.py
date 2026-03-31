from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from spinelab.ai.pointcloud.io.slicer import LoadedSegmentation, convert_points_coordinates
from spinelab.ontology import CoordinateSystem


@dataclass(frozen=True, slots=True)
class SurfaceSample:
    points_xyz: np.ndarray
    normals_xyz: np.ndarray
    indices_zyx: np.ndarray


def _estimate_outward_normals(indices_zyx: np.ndarray) -> np.ndarray:
    centroid = np.mean(indices_zyx[:, ::-1], axis=0)
    vectors = indices_zyx[:, ::-1] - centroid[np.newaxis, :]
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return np.asarray(vectors / norms, dtype=float)


def sample_structure_surface_points(
    segmentation: LoadedSegmentation,
    structure_name: str,
    *,
    max_points: int,
    seed: int,
    target_coordinate_system: CoordinateSystem = CoordinateSystem.LPS,
) -> SurfaceSample:
    if structure_name not in segmentation.masks:
        raise KeyError(f"Missing structure segment: {structure_name}")
    mask = segmentation.masks[structure_name]
    if not np.any(mask):
        raise ValueError(f"Structure segment has no voxels: {structure_name}")

    eroded = ndimage.binary_erosion(mask, border_value=0)
    surface_mask = np.logical_and(mask, np.logical_not(eroded))
    indices_zyx = np.argwhere(surface_mask)
    if len(indices_zyx) == 0:
        indices_zyx = np.argwhere(mask)
    if len(indices_zyx) == 0:
        raise ValueError(f"Structure segment has no valid sample points: {structure_name}")

    if len(indices_zyx) > max_points:
        rng = np.random.default_rng(seed)
        chosen = np.sort(rng.choice(len(indices_zyx), size=max_points, replace=False))
        indices_zyx = indices_zyx[chosen]

    physical_points = np.asarray(
        [
            segmentation.image.TransformIndexToPhysicalPoint(
                (int(index[2]), int(index[1]), int(index[0]))
            )
            for index in indices_zyx
        ],
        dtype=float,
    )
    points_xyz = convert_points_coordinates(
        physical_points,
        segmentation.coordinate_system,
        target_coordinate_system,
    )
    normals_xyz = _estimate_outward_normals(indices_zyx)
    return SurfaceSample(points_xyz=points_xyz, normals_xyz=normals_xyz, indices_zyx=indices_zyx)
