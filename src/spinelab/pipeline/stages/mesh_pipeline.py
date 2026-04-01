from __future__ import annotations

import binascii
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import nibabel as nib
import numpy as np
import vtk
from scipy import ndimage
from vtkmodules.util.numpy_support import (
    numpy_to_vtk,
    numpy_to_vtkIdTypeArray,
    vtk_to_numpy,
)

from spinelab.ontology import (
    Modality,
    VariantTag,
    build_structure_instance_context,
)

MESH_PIPELINE_VERSION = "mesh-pipeline.v1"
DEFAULT_EXTRACTION_ALGORITHM = "vtk_discrete_flying_edges"
SURFACE_NETS_ALGORITHM = "vtk_surface_nets"
BENCHMARK_EXTRACTION_ALGORITHMS = (
    DEFAULT_EXTRACTION_ALGORITHM,
    SURFACE_NETS_ALGORITHM,
)


@dataclass(frozen=True, slots=True)
class MeshPipelineConfig:
    crop_margin_voxels: int = 2
    measurement_smoothing_iterations: int = 8
    measurement_smoothing_pass_band: float = 0.12
    measurement_min_cells_for_smoothing: int = 128
    inference_target_reduction: float = 0.55
    inference_min_cells_for_decimation: int = 256
    point_cloud_size: int = 8192
    surface_nets_iterations: int = 12
    surface_nets_relaxation_factor: float = 0.35


@dataclass(frozen=True, slots=True)
class VertebraSegmentationEntry:
    vertebra_id: str
    label_value: int
    structure_instance_id: str = ""
    display_label: str = ""
    standard_level_id: str | None = None
    region_id: str = "other"
    structure_type: str = "other"
    order_index: int | None = None
    numbering_confidence: float = 1.0
    variant_tags: tuple[str, ...] = ()
    supports_standard_measurements: bool = False
    superior_neighbor_instance_id: str | None = None
    inferior_neighbor_instance_id: str | None = None
    voxel_count: int | None = None
    ijk_bounds: tuple[tuple[int, int], tuple[int, int], tuple[int, int]] | None = None
    center_hint_ijk: tuple[int, int, int] | None = None
    center_hint_patient_frame_mm: tuple[float, float, float] | None = None


@dataclass(slots=True)
class ExtractedMeshResult:
    vertebra_id: str
    label_value: int
    status: str
    extraction_algorithm: str
    roi_bounds_ijk: tuple[tuple[int, int], tuple[int, int], tuple[int, int]]
    roi_affine: np.ndarray
    roi_mask: np.ndarray
    elapsed_seconds: float
    raw_mesh: Any | None = None
    measurement_mesh: Any | None = None
    inference_mesh: Any | None = None
    point_cloud: np.ndarray | None = None
    point_normals: np.ndarray | None = None
    mesh_stats: dict[str, Any] | None = None
    qc_summary: dict[str, Any] | None = None


def _coerce_int_triplet(payload: Any) -> tuple[int, int, int] | None:
    if not isinstance(payload, (list, tuple)) or len(payload) != 3:
        return None
    try:
        return cast(tuple[int, int, int], tuple(int(value) for value in payload))
    except (TypeError, ValueError):
        return None


def _coerce_float_triplet(payload: Any) -> tuple[float, float, float] | None:
    if not isinstance(payload, (list, tuple)) or len(payload) != 3:
        return None
    try:
        return cast(tuple[float, float, float], tuple(float(value) for value in payload))
    except (TypeError, ValueError):
        return None


def _coerce_bounds(
    payload: Any,
) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]] | None:
    if not isinstance(payload, (list, tuple)) or len(payload) != 3:
        return None
    bounds: list[tuple[int, int]] = []
    for axis_payload in payload:
        if not isinstance(axis_payload, (list, tuple)) or len(axis_payload) != 2:
            return None
        try:
            start, stop = int(axis_payload[0]), int(axis_payload[1])
        except (TypeError, ValueError):
            return None
        if stop < start:
            return None
        bounds.append((start, stop))
    return cast(tuple[tuple[int, int], tuple[int, int], tuple[int, int]], tuple(bounds))


def parse_segmentation_entries(payload: dict[str, Any]) -> list[VertebraSegmentationEntry]:
    entries: list[VertebraSegmentationEntry] = []
    raw_vertebrae = payload.get("vertebrae")
    if isinstance(raw_vertebrae, list):
        for item in raw_vertebrae:
            if not isinstance(item, dict):
                continue
            vertebra_id = str(item.get("vertebra_id", "")).upper().strip()
            try:
                label_value = int(item.get("label_value", 0))
            except (TypeError, ValueError):
                continue
            if vertebra_id and label_value > 0:
                context = build_structure_instance_context(
                    structure_instance_id=str(
                        item.get("structure_instance_id") or item.get("structure_id") or ""
                    )
                    or None,
                    display_label=str(item.get("display_label") or vertebra_id),
                    modality=Modality.CT,
                    numbering_confidence=float(item.get("numbering_confidence", 1.0)),
                    variant_tags=tuple(
                        VariantTag(str(tag))
                        for tag in item.get("variant_tags", [])
                        if str(tag) in {variant.value for variant in VariantTag}
                    ),
                    superior_neighbor_instance_id=(
                        str(item.get("superior_neighbor_instance_id"))
                        if item.get("superior_neighbor_instance_id")
                        else None
                    ),
                    inferior_neighbor_instance_id=(
                        str(item.get("inferior_neighbor_instance_id"))
                        if item.get("inferior_neighbor_instance_id")
                        else None
                    ),
                )
                entries.append(
                    VertebraSegmentationEntry(
                        vertebra_id=vertebra_id,
                        label_value=label_value,
                        structure_instance_id=context.structure_instance_id,
                        display_label=context.display_label,
                        standard_level_id=context.standard_level_id,
                        region_id=str(
                            item.get("region_id") or context.region_id.value
                        ),
                        structure_type=str(
                            item.get("structure_type") or context.structure_type.value
                        ),
                        order_index=(
                            int(item["order_index"])
                            if item.get("order_index") is not None
                            else context.order_index
                        ),
                        numbering_confidence=float(
                            item.get("numbering_confidence", context.numbering_confidence)
                        ),
                        variant_tags=tuple(tag.value for tag in context.variant_tags),
                        supports_standard_measurements=bool(
                            item.get(
                                "supports_standard_measurements",
                                context.supports_standard_measurements,
                            )
                        ),
                        superior_neighbor_instance_id=context.superior_neighbor_instance_id,
                        inferior_neighbor_instance_id=context.inferior_neighbor_instance_id,
                        voxel_count=(
                            int(item["voxel_count"])
                            if item.get("voxel_count") is not None
                            else None
                        ),
                        ijk_bounds=_coerce_bounds(item.get("ijk_bounds")),
                        center_hint_ijk=cast(
                            tuple[int, int, int] | None,
                            _coerce_int_triplet(item.get("center_hint_ijk")),
                        ),
                        center_hint_patient_frame_mm=cast(
                            tuple[float, float, float] | None,
                            _coerce_float_triplet(item.get("center_hint_patient_frame_mm")),
                        ),
                    )
                )
    if entries:
        return entries

    raw_level_map = payload.get("level_map")
    if not isinstance(raw_level_map, dict):
        return []
    for vertebra_id, label_value in sorted(raw_level_map.items()):
        try:
            parsed_label = int(label_value)
        except (TypeError, ValueError):
            continue
        normalized_id = str(vertebra_id).upper().strip()
        if normalized_id and parsed_label > 0:
            context = build_structure_instance_context(
                display_label=normalized_id,
                modality=Modality.CT,
            )
            entries.append(
                VertebraSegmentationEntry(
                    vertebra_id=normalized_id,
                    label_value=parsed_label,
                    structure_instance_id=context.structure_instance_id,
                    display_label=context.display_label,
                    standard_level_id=context.standard_level_id,
                    region_id=context.region_id.value,
                    structure_type=context.structure_type.value,
                    order_index=context.order_index,
                    numbering_confidence=context.numbering_confidence,
                    variant_tags=tuple(tag.value for tag in context.variant_tags),
                    supports_standard_measurements=context.supports_standard_measurements,
                    superior_neighbor_instance_id=context.superior_neighbor_instance_id,
                    inferior_neighbor_instance_id=context.inferior_neighbor_instance_id,
                )
            )
    return entries


def load_label_map(label_map_path: Path) -> tuple[np.ndarray, np.ndarray]:
    image_any: Any = nib.load(str(label_map_path))
    data = np.asarray(image_any.dataobj)
    if data.ndim != 3:
        raise ValueError(f"Expected a 3D label map, got shape {tuple(data.shape)}")
    return np.asarray(data, dtype=np.int16), np.asarray(image_any.affine, dtype=float)


def label_statistics_for_entries(
    label_map: np.ndarray,
    entries: list[VertebraSegmentationEntry],
) -> dict[int, dict[str, Any]]:
    label_values = [entry.label_value for entry in entries if entry.label_value > 0]
    if not label_values:
        return {}
    max_label = max(label_values)
    label_counts = np.bincount(label_map.reshape(-1), minlength=max_label + 1)
    object_slices = ndimage.find_objects(label_map, max_label=max_label)
    statistics: dict[int, dict[str, Any]] = {}
    for label_value in label_values:
        if label_value >= len(label_counts) or int(label_counts[label_value]) <= 0:
            continue
        slices = object_slices[label_value - 1] if label_value - 1 < len(object_slices) else None
        if slices is None:
            continue
        bounds = cast(
            tuple[tuple[int, int], tuple[int, int], tuple[int, int]],
            tuple((int(axis_slice.start), int(axis_slice.stop)) for axis_slice in slices),
        )
        roi = label_map[slices] == label_value
        coordinates = np.argwhere(roi)
        center_ijk = None
        if coordinates.size > 0:
            center_local = coordinates.mean(axis=0)
            center_ijk = tuple(
                int(round(float(center_local[axis]) + float(slices[axis].start)))
                for axis in range(3)
            )
        statistics[label_value] = {
            "voxel_count": int(label_counts[label_value]),
            "ijk_bounds": bounds,
            "center_hint_ijk": center_ijk,
        }
    return statistics


def hydrate_segmentation_entries(
    entries: list[VertebraSegmentationEntry],
    label_statistics: dict[int, dict[str, Any]],
    affine: np.ndarray,
) -> list[VertebraSegmentationEntry]:
    hydrated_entries: list[VertebraSegmentationEntry] = []
    for entry in entries:
        stats = label_statistics.get(entry.label_value, {})
        center_hint_ijk = (
            entry.center_hint_ijk
            if entry.center_hint_ijk is not None
            else stats.get("center_hint_ijk")
        )
        center_hint_patient_frame_mm = entry.center_hint_patient_frame_mm
        if center_hint_patient_frame_mm is None and center_hint_ijk is not None:
            center_hint_patient_frame_mm = cast(
                tuple[float, float, float],
                tuple(
                    float(value)
                    for value in (affine @ np.array([*center_hint_ijk, 1.0], dtype=float))[:3]
                ),
            )
        hydrated_entries.append(
            VertebraSegmentationEntry(
                vertebra_id=entry.vertebra_id,
                label_value=entry.label_value,
                structure_instance_id=entry.structure_instance_id,
                display_label=entry.display_label,
                standard_level_id=entry.standard_level_id,
                region_id=entry.region_id,
                structure_type=entry.structure_type,
                order_index=entry.order_index,
                numbering_confidence=entry.numbering_confidence,
                variant_tags=entry.variant_tags,
                supports_standard_measurements=entry.supports_standard_measurements,
                superior_neighbor_instance_id=entry.superior_neighbor_instance_id,
                inferior_neighbor_instance_id=entry.inferior_neighbor_instance_id,
                voxel_count=entry.voxel_count or stats.get("voxel_count"),
                ijk_bounds=entry.ijk_bounds or stats.get("ijk_bounds"),
                center_hint_ijk=center_hint_ijk,
                center_hint_patient_frame_mm=center_hint_patient_frame_mm,
            )
        )
    return hydrated_entries


def extract_vertebra_mesh(
    label_map: np.ndarray,
    affine: np.ndarray,
    entry: VertebraSegmentationEntry,
    *,
    algorithm: str = DEFAULT_EXTRACTION_ALGORITHM,
    config: MeshPipelineConfig | None = None,
    point_cloud_seed_key: str = "",
) -> ExtractedMeshResult:
    resolved_config = config or MeshPipelineConfig()
    started_at = time.perf_counter()
    roi_mask, roi_bounds_ijk, roi_affine = crop_label_mask(
        label_map,
        affine,
        entry.label_value,
        margin_voxels=resolved_config.crop_margin_voxels,
        bounds_ijk=entry.ijk_bounds,
    )
    if roi_mask is None or roi_affine is None:
        elapsed = time.perf_counter() - started_at
        qc_summary: dict[str, Any] = {
            "status": "missing-label",
            "message": f"Label {entry.label_value} not present in the segmentation volume.",
        }
        return ExtractedMeshResult(
            vertebra_id=entry.vertebra_id,
            label_value=entry.label_value,
            status="missing-label",
            extraction_algorithm=algorithm,
            roi_bounds_ijk=roi_bounds_ijk,
            roi_affine=np.eye(4, dtype=float),
            roi_mask=np.zeros((0, 0, 0), dtype=np.uint8),
            elapsed_seconds=elapsed,
            mesh_stats={"triangle_count": 0, "point_count": 0},
            qc_summary=qc_summary,
        )

    vtk_image = vtk_image_from_mask(roi_mask, roi_affine)
    extracted_polydata = extract_polydata(vtk_image, algorithm=algorithm, config=resolved_config)
    prepared_polydata = prepare_polydata(extracted_polydata)
    if prepared_polydata is None:
        elapsed = time.perf_counter() - started_at
        qc_summary = {
            "status": "empty-mesh",
            "message": "Surface extraction produced no triangles for this vertebra label.",
        }
        return ExtractedMeshResult(
            vertebra_id=entry.vertebra_id,
            label_value=entry.label_value,
            status="empty-mesh",
            extraction_algorithm=algorithm,
            roi_bounds_ijk=roi_bounds_ijk,
            roi_affine=roi_affine,
            roi_mask=roi_mask,
            elapsed_seconds=elapsed,
            mesh_stats={"triangle_count": 0, "point_count": 0},
            qc_summary=qc_summary,
        )

    component_mesh, component_summary = extract_largest_component(prepared_polydata)
    measurement_mesh, smoothing_summary = build_measurement_mesh(
        component_mesh,
        config=resolved_config,
    )
    inference_mesh, decimation_summary = build_inference_mesh(
        measurement_mesh,
        config=resolved_config,
    )
    point_cloud, point_normals = sample_point_cloud(
        measurement_mesh,
        sample_count=resolved_config.point_cloud_size,
        seed_key=f"{point_cloud_seed_key}:{entry.vertebra_id}:{entry.label_value}",
    )

    elapsed = time.perf_counter() - started_at
    mesh_stats = collect_mesh_statistics(measurement_mesh, inference_mesh, point_cloud)
    qc_summary = {
        "status": "complete",
        "component_summary": component_summary,
        "measurement_smoothing": smoothing_summary,
        "inference_decimation": decimation_summary,
        "point_cloud_size": int(point_cloud.shape[0]),
    }
    return ExtractedMeshResult(
        vertebra_id=entry.vertebra_id,
        label_value=entry.label_value,
        status="complete",
        extraction_algorithm=algorithm,
        roi_bounds_ijk=roi_bounds_ijk,
        roi_affine=roi_affine,
        roi_mask=roi_mask,
        elapsed_seconds=elapsed,
        raw_mesh=component_mesh,
        measurement_mesh=measurement_mesh,
        inference_mesh=inference_mesh,
        point_cloud=point_cloud,
        point_normals=point_normals,
        mesh_stats=mesh_stats,
        qc_summary=qc_summary,
    )


def crop_label_mask(
    label_map: np.ndarray,
    affine: np.ndarray,
    label_value: int,
    *,
    margin_voxels: int,
    bounds_ijk: tuple[tuple[int, int], tuple[int, int], tuple[int, int]] | None = None,
) -> tuple[
    np.ndarray | None,
    tuple[tuple[int, int], tuple[int, int], tuple[int, int]],
    np.ndarray | None,
]:
    if bounds_ijk is not None:
        bounds = expand_bounds(bounds_ijk, margin_voxels=margin_voxels, shape=label_map.shape)
    else:
        coordinates = np.argwhere(label_map == label_value)
        if coordinates.size == 0:
            zero_bounds = ((0, 0), (0, 0), (0, 0))
            return None, zero_bounds, None

        min_corner = np.maximum(coordinates.min(axis=0) - margin_voxels, 0)
        max_corner = np.minimum(
            coordinates.max(axis=0) + margin_voxels + 1,
            np.asarray(label_map.shape, dtype=int),
        )
        bounds = (
            (int(min_corner[0]), int(max_corner[0])),
            (int(min_corner[1]), int(max_corner[1])),
            (int(min_corner[2]), int(max_corner[2])),
        )
    cropped = label_map[
        bounds[0][0] : bounds[0][1],
        bounds[1][0] : bounds[1][1],
        bounds[2][0] : bounds[2][1],
    ]
    if not np.any(cropped == label_value):
        zero_bounds = ((0, 0), (0, 0), (0, 0))
        return None, zero_bounds, None
    roi_affine = cropped_affine(affine, (bounds[0][0], bounds[1][0], bounds[2][0]))
    return np.asarray(cropped == label_value, dtype=np.uint8), bounds, roi_affine


def expand_bounds(
    bounds_ijk: tuple[tuple[int, int], tuple[int, int], tuple[int, int]],
    *,
    margin_voxels: int,
    shape: tuple[int, int, int],
) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    expanded: list[tuple[int, int]] = []
    for axis, (start, stop) in enumerate(bounds_ijk):
        expanded_start = max(int(start) - margin_voxels, 0)
        expanded_stop = min(int(stop) + margin_voxels, int(shape[axis]))
        expanded.append((expanded_start, expanded_stop))
    return cast(tuple[tuple[int, int], tuple[int, int], tuple[int, int]], tuple(expanded))


def cropped_affine(affine: np.ndarray, offset_ijk: tuple[int, int, int]) -> np.ndarray:
    offset_vector = np.array(
        [float(offset_ijk[0]), float(offset_ijk[1]), float(offset_ijk[2]), 1.0],
        dtype=float,
    )
    cropped = np.asarray(affine, dtype=float).copy()
    cropped[:3, 3] = (affine @ offset_vector)[:3]
    return cropped


def affine_components(
    affine: np.ndarray,
) -> tuple[tuple[float, float, float], np.ndarray, tuple[float, float, float]]:
    axes = np.asarray(affine[:3, :3], dtype=float)
    spacing_values = tuple(float(np.linalg.norm(axes[:, axis])) for axis in range(3))
    spacing = cast(tuple[float, float, float], spacing_values)
    direction = np.eye(3, dtype=float)
    for axis, component_spacing in enumerate(spacing):
        if component_spacing > 0.0:
            direction[:, axis] = axes[:, axis] / component_spacing
    origin = (
        float(affine[0, 3]),
        float(affine[1, 3]),
        float(affine[2, 3]),
    )
    return origin, direction, spacing


def vtk_image_from_mask(mask: np.ndarray, affine: np.ndarray) -> Any:
    image = vtk.vtkImageData()
    dimensions = tuple(int(dimension) for dimension in mask.shape)
    image.SetDimensions(*dimensions)
    origin, direction, spacing = affine_components(affine)
    image.SetOrigin(origin)
    image.SetSpacing(spacing)
    direction_matrix = vtk.vtkMatrix3x3()
    for row in range(3):
        for column in range(3):
            direction_matrix.SetElement(row, column, float(direction[row, column]))
    image.SetDirectionMatrix(direction_matrix)

    scalars = numpy_to_vtk(
        np.ascontiguousarray(mask.ravel(order="F")),
        deep=True,
        array_type=vtk.VTK_UNSIGNED_CHAR,
    )
    scalars.SetName("labels")
    image.GetPointData().SetScalars(scalars)
    return image


def extract_polydata(image: Any, *, algorithm: str, config: MeshPipelineConfig) -> Any:
    if algorithm == DEFAULT_EXTRACTION_ALGORITHM:
        extractor = vtk.vtkDiscreteFlyingEdges3D()
        extractor.SetInputData(image)
        extractor.SetNumberOfContours(1)
        extractor.SetValue(0, 1)
        extractor.ComputeNormalsOff()
        extractor.ComputeGradientsOff()
        extractor.ComputeScalarsOff()
        extractor.Update()
        output = vtk.vtkPolyData()
        output.ShallowCopy(extractor.GetOutput())
        return output

    if algorithm == SURFACE_NETS_ALGORITHM:
        extractor = vtk.vtkSurfaceNets3D()
        extractor.SetInputData(image)
        extractor.SetNumberOfLabels(1)
        extractor.SetLabel(0, 1)
        extractor.SetBackgroundLabel(0)
        extractor.SetOutputStyleToBoundary()
        extractor.SetOutputMeshTypeToTriangles()
        extractor.SmoothingOn()
        extractor.SetNumberOfIterations(config.surface_nets_iterations)
        extractor.SetRelaxationFactor(config.surface_nets_relaxation_factor)
        extractor.SetAutomaticSmoothingConstraints(True)
        extractor.Update()
        output = vtk.vtkPolyData()
        output.ShallowCopy(extractor.GetOutput())
        return output

    raise ValueError(f"Unsupported mesh extraction algorithm: {algorithm}")


def prepare_polydata(polydata: Any) -> Any | None:
    if polydata is None or polydata.GetNumberOfCells() == 0:
        return None

    triangle_filter = vtk.vtkTriangleFilter()
    triangle_filter.SetInputData(polydata)
    triangle_filter.Update()

    clean_filter = vtk.vtkStaticCleanPolyData()
    clean_filter.SetInputConnection(triangle_filter.GetOutputPort())
    clean_filter.Update()
    cleaned = clean_filter.GetOutput()

    vertices, faces = polydata_to_arrays(cleaned)
    if vertices.size == 0 or faces.size == 0:
        return None
    filtered_faces = filter_degenerate_triangles(vertices, faces)
    if filtered_faces.size == 0:
        return None
    return polydata_from_arrays(vertices, filtered_faces)


def polydata_to_arrays(polydata: Any) -> tuple[np.ndarray, np.ndarray]:
    if polydata is None or polydata.GetNumberOfPoints() == 0 or polydata.GetNumberOfPolys() == 0:
        return np.empty((0, 3), dtype=float), np.empty((0, 3), dtype=np.int64)
    vertices = vtk_to_numpy(polydata.GetPoints().GetData()).astype(np.float64, copy=False)
    vtk_polys = polydata.GetPolys()
    connectivity = vtk_to_numpy(vtk_polys.GetConnectivityArray())
    offsets = vtk_to_numpy(vtk_polys.GetOffsetsArray())
    if connectivity.size == 0 or offsets.size <= 1:
        return vertices, np.empty((0, 3), dtype=np.int64)
    face_sizes = np.diff(offsets)
    if not np.all(face_sizes == 3):
        raise ValueError("Expected triangulated polydata before converting to arrays.")
    faces = connectivity.reshape((-1, 3)).astype(np.int64, copy=False)
    return vertices, faces


def polydata_from_arrays(vertices: np.ndarray, faces: np.ndarray) -> Any:
    polydata = vtk.vtkPolyData()
    vtk_points = vtk.vtkPoints()
    vtk_points.SetData(numpy_to_vtk(np.ascontiguousarray(vertices), deep=True))
    polydata.SetPoints(vtk_points)

    if faces.size == 0:
        return polydata
    offsets = np.arange(0, faces.shape[0] * 3 + 1, 3, dtype=np.int64)
    connectivity = faces.astype(np.int64, copy=False).ravel()
    vtk_cells = vtk.vtkCellArray()
    vtk_cells.SetData(
        numpy_to_vtkIdTypeArray(np.ascontiguousarray(offsets), deep=True),
        numpy_to_vtkIdTypeArray(np.ascontiguousarray(connectivity), deep=True),
    )
    polydata.SetPolys(vtk_cells)
    return polydata


def filter_degenerate_triangles(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    first = vertices[faces[:, 0]]
    second = vertices[faces[:, 1]]
    third = vertices[faces[:, 2]]
    twice_area = np.linalg.norm(np.cross(second - first, third - first), axis=1)
    valid = twice_area > 1e-8
    return np.asarray(faces[valid], dtype=np.int64)


def extract_largest_component(polydata: Any) -> tuple[Any, dict[str, Any]]:
    connectivity_probe = vtk.vtkPolyDataConnectivityFilter()
    connectivity_probe.SetInputData(polydata)
    connectivity_probe.SetExtractionModeToAllRegions()
    connectivity_probe.ColorRegionsOff()
    connectivity_probe.Update()
    component_count = int(connectivity_probe.GetNumberOfExtractedRegions())
    if component_count <= 0:
        raise ValueError("No connected mesh components available after cleanup.")
    largest_region = vtk.vtkPolyDataConnectivityFilter()
    largest_region.SetInputData(polydata)
    largest_region.SetExtractionModeToLargestRegion()
    largest_region.ColorRegionsOff()
    largest_region.Update()
    primary = prepare_polydata(largest_region.GetOutput())
    if primary is None:
        raise ValueError("No connected mesh components available after cleanup.")

    kept_triangles = int(primary.GetNumberOfCells())
    total_triangles = int(polydata.GetNumberOfCells())
    boundary_edge_count = count_feature_edges(primary, boundary_edges=True)
    non_manifold_edge_count = count_feature_edges(primary, non_manifold_edges=True)
    watertight = boundary_edge_count == 0 and non_manifold_edge_count == 0
    component_summary = {
        "component_count": component_count,
        "kept_triangle_count": kept_triangles,
        "dropped_component_count": max(component_count - 1, 0),
        "largest_component_ratio": (
            float(kept_triangles / total_triangles) if total_triangles else 0.0
        ),
        "watertight": watertight,
        "winding_consistent": watertight,
        "boundary_edge_count": boundary_edge_count,
        "non_manifold_edge_count": non_manifold_edge_count,
    }
    return primary, component_summary


def count_feature_edges(
    polydata: Any,
    *,
    boundary_edges: bool = False,
    non_manifold_edges: bool = False,
) -> int:
    feature_edges = vtk.vtkFeatureEdges()
    feature_edges.SetInputData(polydata)
    feature_edges.FeatureEdgesOff()
    feature_edges.ManifoldEdgesOff()
    if boundary_edges:
        feature_edges.BoundaryEdgesOn()
    else:
        feature_edges.BoundaryEdgesOff()
    if non_manifold_edges:
        feature_edges.NonManifoldEdgesOn()
    else:
        feature_edges.NonManifoldEdgesOff()
    feature_edges.Update()
    return int(feature_edges.GetOutput().GetNumberOfCells())


def build_measurement_mesh(
    polydata: Any,
    *,
    config: MeshPipelineConfig,
) -> tuple[Any, dict[str, Any]]:
    if polydata.GetNumberOfCells() < config.measurement_min_cells_for_smoothing:
        mesh = compute_normals(polydata)
        return mesh, {"applied": False, "reason": "triangle-count-below-threshold"}

    smoother = vtk.vtkWindowedSincPolyDataFilter()
    smoother.SetInputData(polydata)
    smoother.SetNumberOfIterations(config.measurement_smoothing_iterations)
    smoother.SetPassBand(config.measurement_smoothing_pass_band)
    smoother.NormalizeCoordinatesOn()
    smoother.BoundarySmoothingOff()
    smoother.FeatureEdgeSmoothingOff()
    smoother.NonManifoldSmoothingOff()
    smoother.Update()
    smoothed = prepare_polydata(smoother.GetOutput())
    if smoothed is None:
        smoothed = polydata
    return compute_normals(smoothed), {
        "applied": True,
        "iterations": config.measurement_smoothing_iterations,
        "pass_band": config.measurement_smoothing_pass_band,
    }


def build_inference_mesh(
    polydata: Any,
    *,
    config: MeshPipelineConfig,
) -> tuple[Any, dict[str, Any]]:
    if polydata.GetNumberOfCells() < config.inference_min_cells_for_decimation:
        mesh = compute_normals(polydata)
        return mesh, {"applied": False, "reason": "triangle-count-below-threshold"}

    decimator = vtk.vtkQuadricDecimation()
    decimator.SetInputData(strip_normals(polydata))
    decimator.SetTargetReduction(config.inference_target_reduction)
    decimator.VolumePreservationOn()
    decimator.Update()
    decimated = prepare_polydata(decimator.GetOutput())
    if decimated is None:
        decimated = strip_normals(polydata)
    return compute_normals(decimated), {
        "applied": True,
        "target_reduction": config.inference_target_reduction,
    }


def strip_normals(polydata: Any) -> Any:
    clone = vtk.vtkPolyData()
    clone.DeepCopy(polydata)
    if clone.GetPointData() is not None:
        clone.GetPointData().SetNormals(None)
    if clone.GetCellData() is not None:
        clone.GetCellData().SetNormals(None)
    return clone


def compute_normals(polydata: Any) -> Any:
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputData(polydata)
    normals.AutoOrientNormalsOn()
    normals.ConsistencyOn()
    normals.SplittingOff()
    normals.ComputeCellNormalsOff()
    normals.ComputePointNormalsOn()
    normals.Update()
    output = vtk.vtkPolyData()
    output.ShallowCopy(normals.GetOutput())
    return output


def sample_point_cloud(
    polydata: Any,
    *,
    sample_count: int,
    seed_key: str,
) -> tuple[np.ndarray, np.ndarray]:
    vertices, faces = polydata_to_arrays(strip_normals(polydata))
    if vertices.size == 0 or faces.size == 0:
        return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.float32)

    first = vertices[faces[:, 0]]
    second = vertices[faces[:, 1]]
    third = vertices[faces[:, 2]]
    cross = np.cross(second - first, third - first)
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    valid = areas > 0.0
    if not np.any(valid):
        repeated_vertices = np.resize(vertices, (sample_count, 3)).astype(np.float32, copy=False)
        default_normals = np.tile(
            np.array([[0.0, 0.0, 1.0]], dtype=np.float32),
            (sample_count, 1),
        )
        return repeated_vertices, default_normals

    normalized_areas = areas[valid] / np.sum(areas[valid])
    valid_faces = faces[valid]
    valid_cross = cross[valid]
    face_normals = valid_cross / np.linalg.norm(valid_cross, axis=1, keepdims=True)
    seed = binascii.crc32(seed_key.encode("utf-8")) & 0xFFFFFFFF
    rng = np.random.default_rng(seed)
    sampled_face_indices = rng.choice(valid_faces.shape[0], size=sample_count, p=normalized_areas)

    barycentric_u = rng.random(sample_count)
    barycentric_v = rng.random(sample_count)
    reflected = barycentric_u + barycentric_v > 1.0
    barycentric_u[reflected] = 1.0 - barycentric_u[reflected]
    barycentric_v[reflected] = 1.0 - barycentric_v[reflected]

    sampled_faces = valid_faces[sampled_face_indices]
    origin = vertices[sampled_faces[:, 0]]
    edge_u = vertices[sampled_faces[:, 1]] - origin
    edge_v = vertices[sampled_faces[:, 2]] - origin
    points = origin + edge_u * barycentric_u[:, None] + edge_v * barycentric_v[:, None]
    normals = face_normals[sampled_face_indices]
    return (
        np.asarray(points, dtype=np.float32),
        np.asarray(normals, dtype=np.float32),
    )


def collect_mesh_statistics(
    measurement_mesh: Any,
    inference_mesh: Any,
    point_cloud: np.ndarray,
) -> dict[str, Any]:
    measurement_points, measurement_faces = polydata_to_arrays(strip_normals(measurement_mesh))
    inference_points, inference_faces = polydata_to_arrays(strip_normals(inference_mesh))
    return {
        "point_count": int(measurement_points.shape[0]),
        "triangle_count": int(measurement_faces.shape[0]),
        "inference_point_count": int(inference_points.shape[0]),
        "inference_triangle_count": int(inference_faces.shape[0]),
        "point_cloud_count": int(point_cloud.shape[0]),
    }


def mesh_center_and_extents(
    polydata: Any,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    bounds = polydata.GetBounds()
    center = (
        float((bounds[0] + bounds[1]) / 2.0),
        float((bounds[2] + bounds[3]) / 2.0),
        float((bounds[4] + bounds[5]) / 2.0),
    )
    extents = (
        max(0.1, float(bounds[1] - bounds[0])),
        max(0.1, float(bounds[3] - bounds[2])),
        max(0.1, float(bounds[5] - bounds[4])),
    )
    return center, extents


def write_polydata(path: Path, polydata: Any) -> None:
    writer = vtk.vtkPLYWriter()
    writer.SetInputData(strip_normals(polydata))
    writer.SetFileName(str(path))
    writer.SetFileTypeToBinary()
    path.parent.mkdir(parents=True, exist_ok=True)
    if writer.Write() != 1:
        raise ValueError(f"Unable to write mesh to {path}")


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
    source_mesh_path: Path,
) -> None:
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
        source_mesh_path=np.array(str(source_mesh_path).encode("utf-8")),
    )


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rasterize_polydata(
    polydata: Any,
    *,
    shape: tuple[int, int, int],
    affine: np.ndarray,
) -> np.ndarray:
    vertices, faces = polydata_to_arrays(strip_normals(polydata))
    if vertices.size == 0 or faces.size == 0:
        return np.zeros(shape, dtype=np.uint8)

    inverse_affine = np.linalg.inv(np.asarray(affine, dtype=float))
    homogeneous_vertices = np.column_stack(
        (vertices, np.ones(vertices.shape[0], dtype=np.float64))
    )
    index_vertices = (inverse_affine @ homogeneous_vertices.T).T[:, :3]
    index_polydata = polydata_from_arrays(index_vertices, faces)

    reference = vtk.vtkImageData()
    reference.SetDimensions(*(int(dimension) for dimension in shape))
    reference.SetOrigin(0.0, 0.0, 0.0)
    reference.SetSpacing(1.0, 1.0, 1.0)
    reference.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)
    reference.GetPointData().GetScalars().Fill(1)

    stencil_source = vtk.vtkPolyDataToImageStencil()
    stencil_source.SetInputData(index_polydata)
    stencil_source.SetOutputOrigin(reference.GetOrigin())
    stencil_source.SetOutputSpacing(reference.GetSpacing())
    stencil_source.SetOutputWholeExtent(reference.GetExtent())
    stencil_source.Update()

    stencil = vtk.vtkImageStencil()
    stencil.SetInputData(reference)
    stencil.SetStencilConnection(stencil_source.GetOutputPort())
    stencil.ReverseStencilOff()
    stencil.SetBackgroundValue(0)
    stencil.Update()
    output = stencil.GetOutput()
    data = vtk_to_numpy(output.GetPointData().GetScalars())
    return np.asarray(data.reshape(shape, order="F"), dtype=np.uint8)


def dice_score(reference: np.ndarray, candidate: np.ndarray) -> float:
    reference_sum = int(reference.sum())
    candidate_sum = int(candidate.sum())
    if reference_sum == 0 and candidate_sum == 0:
        return 1.0
    if reference_sum == 0 or candidate_sum == 0:
        return 0.0
    overlap = int(np.logical_and(reference > 0, candidate > 0).sum())
    return float((2.0 * overlap) / (reference_sum + candidate_sum))


def binary_surface_distance_metrics(
    reference: np.ndarray,
    candidate: np.ndarray,
    *,
    spacing: tuple[float, float, float],
) -> dict[str, float | None]:
    if not np.any(reference) or not np.any(candidate):
        return {"assd_mm": None, "hd95_mm": None, "max_hd_mm": None}

    structure = np.ones((3, 3, 3), dtype=bool)
    reference_surface = np.logical_and(
        reference > 0,
        np.logical_not(ndimage.binary_erosion(reference > 0, structure=structure, border_value=0)),
    )
    candidate_surface = np.logical_and(
        candidate > 0,
        np.logical_not(ndimage.binary_erosion(candidate > 0, structure=structure, border_value=0)),
    )
    if not np.any(reference_surface) or not np.any(candidate_surface):
        return {"assd_mm": None, "hd95_mm": None, "max_hd_mm": None}

    reference_distance = ndimage.distance_transform_edt(
        np.logical_not(reference_surface),
        sampling=spacing,
    )
    candidate_distance = ndimage.distance_transform_edt(
        np.logical_not(candidate_surface),
        sampling=spacing,
    )
    candidate_to_reference = reference_distance[candidate_surface]
    reference_to_candidate = candidate_distance[reference_surface]
    distances = np.concatenate((candidate_to_reference, reference_to_candidate))
    if distances.size == 0:
        return {"assd_mm": None, "hd95_mm": None, "max_hd_mm": None}
    return {
        "assd_mm": float(distances.mean()),
        "hd95_mm": float(np.quantile(distances, 0.95)),
        "max_hd_mm": float(distances.max()),
    }
