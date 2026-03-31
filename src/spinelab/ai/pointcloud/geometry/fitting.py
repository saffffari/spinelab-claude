from __future__ import annotations

import math

import numpy as np


def normalize_vector(vector: np.ndarray | tuple[float, float, float]) -> np.ndarray:
    array = np.asarray(vector, dtype=float).reshape(3)
    norm = float(np.linalg.norm(array))
    if norm == 0.0:
        return np.asarray((0.0, 0.0, 1.0), dtype=float)
    return np.asarray(array / norm, dtype=float)


def point_average(points_xyz: np.ndarray) -> np.ndarray:
    points = np.asarray(points_xyz, dtype=float)
    if points.size == 0:
        return np.zeros(3, dtype=float)
    return np.asarray(np.mean(points, axis=0), dtype=float)


def weighted_plane_fit(
    points_xyz: np.ndarray,
    weights: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(points_xyz, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) == 0:
        raise ValueError("weighted_plane_fit requires an (N, 3) point array.")
    if weights is None:
        weight_array = np.ones(len(points), dtype=float)
    else:
        weight_array = np.asarray(weights, dtype=float).reshape(len(points))
    total_weight = float(np.sum(weight_array))
    if total_weight <= 0.0:
        raise ValueError("weighted_plane_fit requires positive weights.")
    centroid = np.average(points, axis=0, weights=weight_array)
    centered = points - centroid
    covariance = (centered * weight_array[:, np.newaxis]).T @ centered / total_weight
    _, _, vh = np.linalg.svd(covariance, full_matrices=False)
    normal = normalize_vector(vh[-1])
    if normal[2] < 0.0:
        normal *= -1.0
    return centroid, normal


def weighted_line_fit(
    points_xyz: np.ndarray,
    weights: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(points_xyz, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) == 0:
        raise ValueError("weighted_line_fit requires an (N, 3) point array.")
    if weights is None:
        weight_array = np.ones(len(points), dtype=float)
    else:
        weight_array = np.asarray(weights, dtype=float).reshape(len(points))
    total_weight = float(np.sum(weight_array))
    if total_weight <= 0.0:
        raise ValueError("weighted_line_fit requires positive weights.")
    centroid = np.average(points, axis=0, weights=weight_array)
    centered = points - centroid
    covariance = (centered * weight_array[:, np.newaxis]).T @ centered / total_weight
    _, _, vh = np.linalg.svd(covariance, full_matrices=False)
    direction = normalize_vector(vh[0])
    return centroid, direction


def principal_axes_frame(points_xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(points_xyz, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) == 0:
        raise ValueError("principal_axes_frame requires an (N, 3) point array.")
    centroid = point_average(points)
    centered = points - centroid
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    axes = np.asarray(vh, dtype=float)
    if np.linalg.det(axes) < 0.0:
        axes[-1] *= -1.0
    return centroid, axes


def angle_in_plane_degrees(
    first_vector: np.ndarray | tuple[float, float, float],
    second_vector: np.ndarray | tuple[float, float, float],
    *,
    plane: str = "sagittal",
) -> float:
    axis_lookup = {
        "sagittal": (1, 2),
        "coronal": (0, 2),
        "axial": (0, 1),
    }
    if plane not in axis_lookup:
        raise ValueError(f"Unsupported plane: {plane}")
    first = np.asarray(first_vector, dtype=float)
    second = np.asarray(second_vector, dtype=float)
    first_2d = np.asarray([first[axis_lookup[plane][0]], first[axis_lookup[plane][1]]], dtype=float)
    second_2d = np.asarray(
        [second[axis_lookup[plane][0]], second[axis_lookup[plane][1]]],
        dtype=float,
    )
    if np.linalg.norm(first_2d) == 0.0 or np.linalg.norm(second_2d) == 0.0:
        return 0.0
    first_angle = math.atan2(first_2d[1], first_2d[0])
    second_angle = math.atan2(second_2d[1], second_2d[0])
    return math.degrees(second_angle - first_angle)
