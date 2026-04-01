from __future__ import annotations

import binascii
import time
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from vtkmodules.util.numpy_support import vtk_to_numpy

from spinelab.pipeline.stages.mesh_pipeline import (
    MeshPipelineConfig,
    VertebraSegmentationEntry,
    compute_normals,
    crop_label_mask,
    extract_largest_component,
    extract_polydata,
    mesh_center_and_extents,
    polydata_to_arrays,
    prepare_polydata,
    vtk_image_from_mask,
)

POINT_CLOUD_PIPELINE_VERSION = "point-cloud-pipeline.v1"
SURFACE_NETS_ALGORITHM = "vtk_surface_nets"


@dataclass(frozen=True, slots=True)
class PointCloudPipelineConfig:
    crop_margin_voxels: int = 2
    surface_nets_iterations: int = 12
    surface_nets_relaxation_factor: float = 0.35
    point_cloud_size: int = 8192


@dataclass(slots=True)
class ExtractedPointCloudResult:
    vertebra_id: str
    label_value: int
    status: str
    roi_bounds_ijk: tuple[tuple[int, int], tuple[int, int], tuple[int, int]]
    roi_affine: np.ndarray
    elapsed_seconds: float
    points: np.ndarray | None = None
    normals: np.ndarray | None = None
    center_mm: tuple[float, float, float] | None = None
    extents_mm: tuple[float, float, float] | None = None
    surface_nets_vertex_count: int = 0


def _to_mesh_config(config: PointCloudPipelineConfig) -> MeshPipelineConfig:
    return MeshPipelineConfig(
        crop_margin_voxels=config.crop_margin_voxels,
        surface_nets_iterations=config.surface_nets_iterations,
        surface_nets_relaxation_factor=config.surface_nets_relaxation_factor,
        point_cloud_size=config.point_cloud_size,
    )


def extract_vertebra_point_cloud(
    label_map: np.ndarray,
    affine: np.ndarray,
    entry: VertebraSegmentationEntry,
    *,
    config: PointCloudPipelineConfig | None = None,
    seed_key: str = "",
) -> ExtractedPointCloudResult:
    resolved_config = config or PointCloudPipelineConfig()
    mesh_config = _to_mesh_config(resolved_config)
    started_at = time.perf_counter()

    zero_bounds: tuple[tuple[int, int], tuple[int, int], tuple[int, int]] = (
        (0, 0),
        (0, 0),
        (0, 0),
    )
    zero_affine = np.eye(4, dtype=float)

    mask, bounds, roi_affine = crop_label_mask(
        label_map,
        affine,
        entry.label_value,
        margin_voxels=resolved_config.crop_margin_voxels,
        bounds_ijk=entry.ijk_bounds,
    )
    if mask is None or roi_affine is None:
        return ExtractedPointCloudResult(
            vertebra_id=entry.vertebra_id,
            label_value=entry.label_value,
            status="missing-label",
            roi_bounds_ijk=bounds,
            roi_affine=zero_affine,
            elapsed_seconds=time.perf_counter() - started_at,
        )

    image = vtk_image_from_mask(mask, roi_affine)
    polydata = extract_polydata(image, algorithm=SURFACE_NETS_ALGORITHM, config=mesh_config)
    polydata = prepare_polydata(polydata)
    if polydata is None:
        return ExtractedPointCloudResult(
            vertebra_id=entry.vertebra_id,
            label_value=entry.label_value,
            status="empty-surface",
            roi_bounds_ijk=bounds,
            roi_affine=roi_affine,
            elapsed_seconds=time.perf_counter() - started_at,
        )

    polydata, _component_summary = extract_largest_component(polydata)
    center, extents = mesh_center_and_extents(polydata)

    polydata_with_normals = compute_normals(polydata)
    vertices, _faces = polydata_to_arrays(polydata_with_normals)
    normal_data = polydata_with_normals.GetPointData().GetNormals()
    if normal_data is not None:
        vertex_normals = np.asarray(vtk_to_numpy(normal_data), dtype=np.float64)
    else:
        vertex_normals = np.zeros_like(vertices)

    surface_nets_vertex_count = vertices.shape[0]

    seed = binascii.crc32(
        f"{seed_key}:{entry.vertebra_id}:{entry.label_value}".encode("utf-8")
    ) & 0xFFFFFFFF
    target = resolved_config.point_cloud_size

    if surface_nets_vertex_count == 0:
        points = np.zeros((target, 3), dtype=np.float32)
        normals = np.tile(
            np.array([[0.0, 0.0, 1.0]], dtype=np.float32), (target, 1)
        )
    elif surface_nets_vertex_count > target:
        indices = farthest_point_sampling(vertices, target, seed)
        points = np.asarray(vertices[indices], dtype=np.float32)
        normals = np.asarray(vertex_normals[indices], dtype=np.float32)
    elif surface_nets_vertex_count < target:
        pad_count = target - surface_nets_vertex_count
        rng = np.random.default_rng(seed)
        pad_indices = rng.choice(surface_nets_vertex_count, size=pad_count)
        points = np.empty((target, 3), dtype=np.float32)
        points[:surface_nets_vertex_count] = vertices
        points[surface_nets_vertex_count:] = vertices[pad_indices]
        normals = np.empty((target, 3), dtype=np.float32)
        normals[:surface_nets_vertex_count] = vertex_normals
        normals[surface_nets_vertex_count:] = vertex_normals[pad_indices]
    else:
        points = np.asarray(vertices, dtype=np.float32)
        normals = np.asarray(vertex_normals, dtype=np.float32)

    return ExtractedPointCloudResult(
        vertebra_id=entry.vertebra_id,
        label_value=entry.label_value,
        status="complete",
        roi_bounds_ijk=bounds,
        roi_affine=roi_affine,
        elapsed_seconds=time.perf_counter() - started_at,
        points=points,
        normals=normals,
        center_mm=center,
        extents_mm=extents,
        surface_nets_vertex_count=surface_nets_vertex_count,
    )


def farthest_point_sampling(
    points: np.ndarray,
    target_count: int,
    seed: int,
) -> np.ndarray:
    n = points.shape[0]
    if n <= target_count:
        return np.arange(n, dtype=np.int64)

    rng = np.random.default_rng(seed)
    selected = np.empty(target_count, dtype=np.int64)
    selected[0] = rng.integers(n)

    distances = np.full(n, np.inf, dtype=np.float64)
    for i in range(1, target_count):
        last = points[selected[i - 1]]
        dist_to_last = np.sum((points - last) ** 2, axis=1)
        np.minimum(distances, dist_to_last, out=distances)
        selected[i] = np.argmax(distances)

    return selected


def write_point_cloud(
    path: Path,
    *,
    points: np.ndarray,
    normals: np.ndarray,
    vertebra_id: str,
    structure_instance_id: str,
    standard_level_id: str | None,
    display_label: str,
    coordinate_frame: str,
) -> None:
    """Write point cloud NPZ with pickle-safe string metadata."""
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        points=np.asarray(points, dtype=np.float32),
        normals=np.asarray(normals, dtype=np.float32),
        vertebra_id=np.array(vertebra_id.encode("utf-8")),
        structure_instance_id=np.array(structure_instance_id.encode("utf-8")),
        display_label=np.array(display_label.encode("utf-8")),
        standard_level_id=np.array((standard_level_id or "").encode("utf-8")),
        coordinate_frame=np.array(coordinate_frame.encode("utf-8")),
    )
