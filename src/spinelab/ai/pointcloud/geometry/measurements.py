from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .fitting import angle_in_plane_degrees, normalize_vector


@dataclass(frozen=True, slots=True)
class MetricComputation:
    key: str
    label: str
    value: float | None
    unit: str
    valid: bool
    invalid_reason: str
    required_primitives: tuple[str, ...]


def _point(payload: dict[str, Any]) -> np.ndarray:
    return np.array(payload["point_mm"], dtype=float, copy=True)


def _normal(payload: dict[str, Any]) -> np.ndarray:
    return np.asarray(normalize_vector(np.asarray(payload["normal"], dtype=float)), dtype=float)


def _axis(primitives: dict[str, Any], axis_name: str) -> np.ndarray:
    return np.asarray(
        normalize_vector(
            np.asarray(primitives["vertebra_local_frame"]["axes"][axis_name], dtype=float)
        ),
        dtype=float,
    )


def _posterior_wall_midpoint(primitives: dict[str, Any]) -> np.ndarray:
    return np.asarray(
        np.mean(np.asarray(primitives["posterior_wall_line"]["points_mm"], dtype=float), axis=0),
        dtype=float,
    )


def _project_distance(first_point: np.ndarray, second_point: np.ndarray, axis: np.ndarray) -> float:
    return float(np.dot(second_point - first_point, normalize_vector(axis)))


def compute_disc_heights(
    cranial_primitives: dict[str, Any],
    caudal_primitives: dict[str, Any],
) -> dict[str, float]:
    disc_axis = normalize_vector(
        _normal(cranial_primitives["inferior_endplate_plane"])
        + _normal(caudal_primitives["superior_endplate_plane"])
    )
    anterior = abs(
        _project_distance(
            _point(cranial_primitives["anterior_inferior_corner"]),
            _point(caudal_primitives["anterior_superior_corner"]),
            disc_axis,
        )
    )
    middle = abs(
        _project_distance(
            _point(cranial_primitives["inferior_endplate_midpoint"]),
            _point(caudal_primitives["superior_endplate_midpoint"]),
            disc_axis,
        )
    )
    posterior = abs(
        _project_distance(
            _point(cranial_primitives["posterior_inferior_corner"]),
            _point(caudal_primitives["posterior_superior_corner"]),
            disc_axis,
        )
    )
    return {
        "anterior": anterior,
        "middle": middle,
        "posterior": posterior,
        "midpoint": middle,
    }


def compute_disc_space_angle(
    cranial_primitives: dict[str, Any],
    caudal_primitives: dict[str, Any],
) -> float:
    return abs(
        angle_in_plane_degrees(
            _normal(cranial_primitives["inferior_endplate_plane"]),
            _normal(caudal_primitives["superior_endplate_plane"]),
            plane="sagittal",
        )
    )


def compute_segmental_lordosis(
    cranial_primitives: dict[str, Any],
    caudal_primitives: dict[str, Any],
) -> float:
    return compute_disc_space_angle(cranial_primitives, caudal_primitives)


def compute_listhesis(
    cranial_primitives: dict[str, Any],
    caudal_primitives: dict[str, Any],
) -> float:
    ap_axis = _axis(caudal_primitives, "anterior_posterior")
    cranial_midpoint = _posterior_wall_midpoint(cranial_primitives)
    caudal_midpoint = _posterior_wall_midpoint(caudal_primitives)
    return _project_distance(caudal_midpoint, cranial_midpoint, ap_axis)


def compute_lumbar_lordosis(
    l1_primitives: dict[str, Any],
    s1_primitives: dict[str, Any],
) -> float:
    return abs(
        angle_in_plane_degrees(
            _normal(l1_primitives["superior_endplate_plane"]),
            _normal(s1_primitives["superior_endplate_plane"]),
            plane="sagittal",
        )
    )


def compute_thoracic_kyphosis(
    t4_primitives: dict[str, Any],
    t12_primitives: dict[str, Any],
) -> float:
    return abs(
        angle_in_plane_degrees(
            _normal(t4_primitives["superior_endplate_plane"]),
            _normal(t12_primitives["inferior_endplate_plane"]),
            plane="sagittal",
        )
    )


def compute_sagittal_vertical_axis(
    c7_primitives: dict[str, Any],
    s1_primitives: dict[str, Any],
) -> float:
    ap_axis = _axis(s1_primitives, "anterior_posterior")
    c7_centroid = _point(c7_primitives["vertebral_centroid"])
    s1_corner = _point(s1_primitives["posterior_superior_corner"])
    return abs(_project_distance(s1_corner, c7_centroid, ap_axis))


def compute_coronal_balance(
    c7_primitives: dict[str, Any],
    sacral_center_payload: dict[str, Any],
) -> float:
    c7_centroid = _point(c7_primitives["vertebral_centroid"])
    sacral_center = _point(sacral_center_payload)
    return abs(float(c7_centroid[0] - sacral_center[0]))


def compute_sacral_slope(s1_primitives: dict[str, Any]) -> float:
    superior_axis = np.asarray((0.0, 0.0, 1.0), dtype=float)
    return abs(
        angle_in_plane_degrees(
            superior_axis,
            _normal(s1_primitives["superior_endplate_plane"]),
            plane="sagittal",
        )
    )


def compute_pelvic_tilt(
    s1_midpoint_payload: dict[str, Any],
    hip_axis_midpoint_payload: dict[str, Any],
) -> float:
    vertical_axis = np.asarray((0.0, 0.0, 1.0), dtype=float)
    pelvis_vector = _point(hip_axis_midpoint_payload) - _point(s1_midpoint_payload)
    return abs(angle_in_plane_degrees(vertical_axis, pelvis_vector, plane="sagittal"))


def compute_pelvic_incidence(
    s1_primitives: dict[str, Any],
    hip_axis_midpoint_payload: dict[str, Any],
) -> float:
    pelvis_vector = _point(hip_axis_midpoint_payload) - _point(
        s1_primitives["superior_endplate_midpoint"]
    )
    return abs(
        angle_in_plane_degrees(
            _normal(s1_primitives["superior_endplate_plane"]),
            pelvis_vector,
            plane="sagittal",
        )
    )
