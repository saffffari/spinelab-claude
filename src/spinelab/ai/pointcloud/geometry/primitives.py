from __future__ import annotations

from typing import Any

import numpy as np

from spinelab.ontology import GlobalStructureId, PrimitiveId

from .fitting import normalize_vector, point_average, weighted_line_fit, weighted_plane_fit


def _select_extreme_points(
    points_xyz: np.ndarray,
    axis: int,
    *,
    keep_high: bool,
    quantile: float,
) -> np.ndarray:
    points = np.asarray(points_xyz, dtype=float)
    if len(points) == 0:
        raise ValueError("Point cloud is empty.")
    threshold = np.quantile(points[:, axis], quantile if keep_high else 1.0 - quantile)
    if keep_high:
        selected = np.asarray(points[points[:, axis] >= threshold], dtype=float)
    else:
        selected = np.asarray(points[points[:, axis] <= threshold], dtype=float)
    if len(selected) == 0:
        return points
    return np.asarray(selected, dtype=float)


def _extreme_point(points_xyz: np.ndarray, axis: int, *, keep_high: bool) -> np.ndarray:
    points = np.asarray(points_xyz, dtype=float)
    index = int(np.argmax(points[:, axis]) if keep_high else np.argmin(points[:, axis]))
    return np.array(
        (
            float(points[index, 0]),
            float(points[index, 1]),
            float(points[index, 2]),
        ),
        dtype=float,
    )


def _point_payload(point_xyz: np.ndarray) -> dict[str, Any]:
    return {"point_mm": [float(value) for value in point_xyz.tolist()]}


def _plane_payload(point_xyz: np.ndarray, normal_xyz: np.ndarray) -> dict[str, Any]:
    return {
        "point_mm": [float(value) for value in point_xyz.tolist()],
        "normal": [float(value) for value in normal_xyz.tolist()],
    }


def _line_payload(
    point_xyz: np.ndarray,
    direction_xyz: np.ndarray,
    end_points_xyz: tuple[np.ndarray, np.ndarray],
) -> dict[str, Any]:
    return {
        "point_mm": [float(value) for value in point_xyz.tolist()],
        "direction": [float(value) for value in direction_xyz.tolist()],
        "points_mm": [[float(value) for value in point.tolist()] for point in end_points_xyz],
    }


def derive_primitives_from_point_cloud(
    points_xyz: np.ndarray,
) -> tuple[dict[str, Any], dict[str, Any]]:
    points = np.asarray(points_xyz, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 8:
        raise ValueError("derive_primitives_from_point_cloud requires at least 8 (x, y, z) points.")

    superior_points = _select_extreme_points(points, 2, keep_high=True, quantile=0.85)
    inferior_points = _select_extreme_points(points, 2, keep_high=False, quantile=0.85)
    posterior_points = _select_extreme_points(points, 1, keep_high=True, quantile=0.85)
    anterior_points = _select_extreme_points(points, 1, keep_high=False, quantile=0.85)

    superior_point, superior_normal = weighted_plane_fit(superior_points)
    inferior_point, inferior_normal = weighted_plane_fit(inferior_points)
    posterior_line_point, posterior_direction = weighted_line_fit(posterior_points)
    if posterior_direction[2] < 0.0:
        posterior_direction *= -1.0

    anterior_superior = _extreme_point(superior_points, 1, keep_high=False)
    posterior_superior = _extreme_point(superior_points, 1, keep_high=True)
    anterior_inferior = _extreme_point(inferior_points, 1, keep_high=False)
    posterior_inferior = _extreme_point(inferior_points, 1, keep_high=True)

    superior_midpoint = point_average(np.vstack((anterior_superior, posterior_superior)))
    inferior_midpoint = point_average(np.vstack((anterior_inferior, posterior_inferior)))
    centroid = point_average(points)
    posterior_midpoint = point_average(posterior_points)
    anterior_midpoint = point_average(anterior_points)

    superior_inferior_axis = normalize_vector(superior_normal + inferior_normal)
    if superior_inferior_axis[2] < 0.0:
        superior_inferior_axis *= -1.0
    anterior_posterior_axis = normalize_vector(anterior_midpoint - posterior_midpoint)
    left_right_axis = normalize_vector(np.cross(anterior_posterior_axis, superior_inferior_axis))
    anterior_posterior_axis = normalize_vector(np.cross(superior_inferior_axis, left_right_axis))

    primitives = {
        PrimitiveId.VERTEBRAL_CENTROID.value: _point_payload(centroid),
        PrimitiveId.SUPERIOR_ENDPLATE_PLANE.value: _plane_payload(superior_point, superior_normal),
        PrimitiveId.INFERIOR_ENDPLATE_PLANE.value: _plane_payload(inferior_point, inferior_normal),
        PrimitiveId.ANTERIOR_SUPERIOR_CORNER.value: _point_payload(anterior_superior),
        PrimitiveId.POSTERIOR_SUPERIOR_CORNER.value: _point_payload(posterior_superior),
        PrimitiveId.ANTERIOR_INFERIOR_CORNER.value: _point_payload(anterior_inferior),
        PrimitiveId.POSTERIOR_INFERIOR_CORNER.value: _point_payload(posterior_inferior),
        PrimitiveId.POSTERIOR_WALL_LINE.value: _line_payload(
            posterior_line_point,
            posterior_direction,
            (posterior_superior, posterior_inferior),
        ),
        PrimitiveId.SUPERIOR_ENDPLATE_MIDPOINT.value: _point_payload(superior_midpoint),
        PrimitiveId.INFERIOR_ENDPLATE_MIDPOINT.value: _point_payload(inferior_midpoint),
        PrimitiveId.VERTEBRA_LOCAL_FRAME.value: {
            "origin_mm": [float(value) for value in centroid.tolist()],
            "axes": {
                "left_right": [float(value) for value in left_right_axis.tolist()],
                "anterior_posterior": [float(value) for value in anterior_posterior_axis.tolist()],
                "superior_inferior": [float(value) for value in superior_inferior_axis.tolist()],
            },
        },
    }
    qc = {
        "point_count": int(len(points)),
        "superior_support_count": int(len(superior_points)),
        "inferior_support_count": int(len(inferior_points)),
        "posterior_support_count": int(len(posterior_points)),
    }
    return primitives, qc


def derive_global_structures(vertebrae: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {
        str(vertebra.get("standard_level_id", vertebra.get("vertebra_id", ""))).upper(): vertebra
        for vertebra in vertebrae
    }
    global_structures: list[dict[str, Any]] = []
    c7 = lookup.get("C7")
    if c7 is not None:
        centroid_payload = c7["primitives"][PrimitiveId.VERTEBRAL_CENTROID.value]
        global_structures.append(
            {
                "structure_id": GlobalStructureId.C7_CENTROID.value,
                "point_mm": list(centroid_payload["point_mm"]),
                "source_level_id": "C7",
            }
        )
    s1 = lookup.get("S1")
    if s1 is not None:
        global_structures.extend(
            [
                {
                    "structure_id": GlobalStructureId.S1_SUPERIOR_MIDPOINT.value,
                    "point_mm": list(
                        s1["primitives"][PrimitiveId.SUPERIOR_ENDPLATE_MIDPOINT.value]["point_mm"]
                    ),
                    "source_level_id": "S1",
                },
                {
                    "structure_id": GlobalStructureId.SACRAL_CENTER.value,
                    "point_mm": list(
                        s1["primitives"][PrimitiveId.VERTEBRAL_CENTROID.value]["point_mm"]
                    ),
                    "source_level_id": "S1",
                },
                {
                    "structure_id": GlobalStructureId.POSTERIOR_SUPERIOR_S1_CORNER.value,
                    "point_mm": list(
                        s1["primitives"][PrimitiveId.POSTERIOR_SUPERIOR_CORNER.value]["point_mm"]
                    ),
                    "source_level_id": "S1",
                },
                {
                    "structure_id": GlobalStructureId.S1_SUPERIOR_ENDPLATE_PLANE.value,
                    "point_mm": list(
                        s1["primitives"][PrimitiveId.SUPERIOR_ENDPLATE_PLANE.value]["point_mm"]
                    ),
                    "normal": list(
                        s1["primitives"][PrimitiveId.SUPERIOR_ENDPLATE_PLANE.value]["normal"]
                    ),
                    "source_level_id": "S1",
                },
            ]
        )
    return global_structures
