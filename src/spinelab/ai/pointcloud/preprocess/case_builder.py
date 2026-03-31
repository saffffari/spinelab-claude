from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from spinelab.ai.pointcloud.contracts import (
    POINTCLOUD_SCHEMA_VERSION,
    CaseAnnotationPaths,
    CaseContext,
    StructureContext,
    StructurePackageMetadata,
    json_ready_path_map,
)
from spinelab.ai.pointcloud.geometry import principal_axes_frame
from spinelab.ai.pointcloud.io import load_markups, load_segmentation, load_volume
from spinelab.ai.pointcloud.preprocess.sampling import sample_structure_surface_points
from spinelab.ontology import (
    PRIMITIVE_IDS,
    STANDARD_LEVEL_IDS,
    STANDARD_LEVEL_INDEX,
    STANDARD_STRUCTURES,
    SURFACE_PATCH_CLASS_INDEX,
    SURFACE_PATCH_IDS,
    CaseOntologyContext,
    CoordinateSystem,
    Modality,
    SurfacePatchId,
    build_structure_instance_context,
    level_from_structure_instance_id,
    level_token_index,
    standard_neighbors,
    structure_instance_id_for_level,
    structure_type_token,
    surface_patch_segment_name,
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object at {path}")
    return payload


def _resolve_case_annotation_paths(
    *,
    image_path: Path | None,
    structures_path: Path | None,
    surface_patches_path: Path | None,
    landmarks_path: Path | None,
    metadata_path: Path,
) -> CaseAnnotationPaths:
    metadata = _load_json(metadata_path)
    root = metadata_path.parent
    return CaseAnnotationPaths(
        image_path=image_path or (root / str(metadata["image"])).resolve(),
        structures_segmentation_path=structures_path
        or (root / str(metadata["structures_segmentation"])).resolve(),
        surface_patches_segmentation_path=surface_patches_path
        or (root / str(metadata["surface_patches_segmentation"])).resolve(),
        landmark_markup_path=landmarks_path or (root / str(metadata["landmarks"])).resolve(),
        metadata_path=metadata_path.resolve(),
    )


def _patch_lookup_for_level(level_id: str) -> dict[str, SurfacePatchId]:
    normalized = level_id.upper()
    mapping = {
        surface_patch_segment_name(normalized, SurfacePatchId.SUPERIOR_ENDPLATE): (
            SurfacePatchId.SUPERIOR_ENDPLATE
        ),
        surface_patch_segment_name(normalized, SurfacePatchId.INFERIOR_ENDPLATE): (
            SurfacePatchId.INFERIOR_ENDPLATE
        ),
        surface_patch_segment_name(normalized, SurfacePatchId.POSTERIOR_BODY_WALL): (
            SurfacePatchId.POSTERIOR_BODY_WALL
        ),
    }
    if normalized == "S1":
        mapping["S1_posterior_wall"] = SurfacePatchId.POSTERIOR_BODY_WALL
    return mapping


def _semantic_and_boundary_labels(
    *,
    indices_zyx: np.ndarray,
    patch_masks: dict[str, np.ndarray],
    level_id: str,
) -> tuple[np.ndarray, np.ndarray]:
    semantic_labels = np.full(
        len(indices_zyx),
        SURFACE_PATCH_CLASS_INDEX[SurfacePatchId.VERTEBRAL_BODY_SURFACE],
        dtype=np.int32,
    )
    lookup = _patch_lookup_for_level(level_id)
    dense_labels: np.ndarray | None = None
    for segment_name, patch_id in lookup.items():
        mask = patch_masks.get(segment_name)
        if mask is None:
            continue
        if dense_labels is None:
            dense_labels = np.full(
                mask.shape,
                SURFACE_PATCH_CLASS_INDEX[SurfacePatchId.VERTEBRAL_BODY_SURFACE],
                dtype=np.int32,
            )
        dense_labels[mask] = SURFACE_PATCH_CLASS_INDEX[patch_id]
    if dense_labels is None:
        return semantic_labels, np.zeros(len(indices_zyx), dtype=np.int32)

    for index, voxel_index in enumerate(indices_zyx):
        z_index, y_index, x_index = int(voxel_index[0]), int(voxel_index[1]), int(voxel_index[2])
        semantic_labels[index] = int(dense_labels[z_index, y_index, x_index])

    boundary_labels = np.zeros(len(indices_zyx), dtype=np.int32)
    offsets = (
        (-1, 0, 0),
        (1, 0, 0),
        (0, -1, 0),
        (0, 1, 0),
        (0, 0, -1),
        (0, 0, 1),
    )
    shape = dense_labels.shape
    for index, voxel_index in enumerate(indices_zyx):
        label_value = int(semantic_labels[index])
        if label_value == 0:
            continue
        z_index, y_index, x_index = int(voxel_index[0]), int(voxel_index[1]), int(voxel_index[2])
        for z_offset, y_offset, x_offset in offsets:
            neighbor = (z_index + z_offset, y_index + y_offset, x_index + x_offset)
            if (
                neighbor[0] < 0
                or neighbor[1] < 0
                or neighbor[2] < 0
                or neighbor[0] >= shape[0]
                or neighbor[1] >= shape[1]
                or neighbor[2] >= shape[2]
            ):
                boundary_labels[index] = 1
                break
            if int(dense_labels[neighbor]) != label_value:
                boundary_labels[index] = 1
                break
    return semantic_labels, boundary_labels


def _landmark_tensors(
    *,
    level_id: str,
    markups: dict[str, np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    landmark_names = tuple(primitive_id.value for primitive_id in PRIMITIVE_IDS)
    landmark_xyz = np.zeros((len(landmark_names), 3), dtype=np.float32)
    landmark_mask = np.zeros((len(landmark_names),), dtype=np.int32)
    label_lookup = {
        "anterior_superior_corner": f"{level_id}_ASC",
        "posterior_superior_corner": f"{level_id}_PSC",
        "anterior_inferior_corner": f"{level_id}_AIC",
        "posterior_inferior_corner": f"{level_id}_PIC",
        "vertebral_centroid": f"{level_id}_centroid",
        "superior_endplate_midpoint": f"{level_id}_superior_endplate_midpoint",
        "inferior_endplate_midpoint": f"{level_id}_inferior_endplate_midpoint",
    }
    for index, landmark_name in enumerate(landmark_names):
        label = label_lookup.get(landmark_name)
        if label is None:
            continue
        if label not in markups:
            continue
        landmark_xyz[index] = np.asarray(markups[label], dtype=np.float32)
        landmark_mask[index] = 1
    return landmark_xyz, landmark_mask


def _context_from_case_metadata(
    metadata: dict[str, Any],
    *,
    levels_present: tuple[str, ...],
    unsupported_levels: tuple[str, ...],
) -> CaseOntologyContext:
    modality = Modality(str(metadata.get("modality", Modality.CT.value)).upper())
    source_coordinate_system = CoordinateSystem(
        str(metadata.get("source_coordinate_system", CoordinateSystem.LPS.value)).upper()
    )
    numbering_review_flags = tuple(str(item) for item in metadata.get("numbering_review_flags", []))
    field_of_view_start = levels_present[0] if levels_present else None
    field_of_view_end = levels_present[-1] if levels_present else None
    pelvis_present = bool(
        metadata.get("pelvis_present")
        or metadata.get("femoral_heads_present")
        or any(level == "S1" for level in levels_present)
    )
    return CaseContext(
        case_id=str(metadata["case_id"]),
        modality=modality,
        source_coordinate_system=source_coordinate_system,
        canonical_coordinate_system=CoordinateSystem.LPS,
        levels_present=levels_present,
        unsupported_levels_present=unsupported_levels,
        pelvis_present=pelvis_present,
        field_of_view_start=field_of_view_start,
        field_of_view_end=field_of_view_end,
        numbering_review_flags=numbering_review_flags,
    )


def _structure_contexts(
    *,
    levels_present: tuple[str, ...],
    unsupported_levels: tuple[str, ...],
    case_context: CaseContext,
) -> dict[str, StructureContext]:
    neighbors = standard_neighbors(levels_present)
    result: dict[str, StructureContext] = {}
    for definition in STANDARD_STRUCTURES:
        if definition.standard_level_id not in levels_present:
            continue
        superior, inferior = neighbors.get(definition.standard_level_id, (None, None))
        result[definition.structure_instance_id] = build_structure_instance_context(
            structure_instance_id=definition.structure_instance_id,
            display_label=definition.standard_level_id,
            modality=case_context.modality,
            numbering_confidence=1.0,
            superior_neighbor_instance_id=(
                structure_instance_id_for_level(superior) if superior is not None else None
            ),
            inferior_neighbor_instance_id=(
                structure_instance_id_for_level(inferior) if inferior is not None else None
            ),
        )
    for unsupported_level in unsupported_levels:
        structure_context = build_structure_instance_context(
            display_label=unsupported_level,
            modality=case_context.modality,
            numbering_confidence=0.25,
        )
        result[structure_context.structure_instance_id] = structure_context
    return result


def build_case_npz(
    *,
    metadata_path: Path,
    output_dir: Path,
    image_path: Path | None = None,
    structures_path: Path | None = None,
    surface_patches_path: Path | None = None,
    landmarks_path: Path | None = None,
    max_points: int = 4096,
    seed: int = 7,
) -> list[Path]:
    annotation_paths = _resolve_case_annotation_paths(
        image_path=image_path,
        structures_path=structures_path,
        surface_patches_path=surface_patches_path,
        landmarks_path=landmarks_path,
        metadata_path=metadata_path,
    )
    metadata = _load_json(annotation_paths.metadata_path)
    _ = load_volume(annotation_paths.image_path)
    structures = load_segmentation(annotation_paths.structures_segmentation_path)
    surface_patches = load_segmentation(annotation_paths.surface_patches_segmentation_path)
    markups = load_markups(annotation_paths.landmark_markup_path)

    if markups.coordinate_system != CoordinateSystem.LPS:
        converted_markups = {
            label: np.asarray((-point[0], -point[1], point[2]), dtype=float)
            for label, point in markups.points.items()
        }
    else:
        converted_markups = markups.points

    levels_present = tuple(
        sorted(
            {
                level_id
                for structure_name in structures.masks
                if (level_id := level_from_structure_instance_id(structure_name)) is not None
                and level_id in STANDARD_LEVEL_IDS
            },
            key=lambda level_id: STANDARD_LEVEL_INDEX[level_id],
        )
    )
    unsupported_levels = tuple(
        sorted(
            {
                level_id
                for structure_name in structures.masks
                if (level_id := level_from_structure_instance_id(structure_name)) is not None
                and level_id not in STANDARD_LEVEL_IDS
            }
        )
    )
    case_context = _context_from_case_metadata(
        metadata,
        levels_present=levels_present,
        unsupported_levels=unsupported_levels,
    )
    structure_context_lookup = _structure_contexts(
        levels_present=levels_present,
        unsupported_levels=unsupported_levels,
        case_context=case_context,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []
    for structure_name, context in structure_context_lookup.items():
        if structure_name not in structures.masks:
            continue
        sample = sample_structure_surface_points(
            structures,
            structure_name,
            max_points=max_points,
            seed=seed + len(written_paths),
        )
        if context.standard_level_id is None:
            semantic_labels = np.zeros(len(sample.indices_zyx), dtype=np.int32)
            boundary_labels = np.zeros(len(sample.indices_zyx), dtype=np.int32)
            landmark_xyz = np.zeros((len(PRIMITIVE_IDS), 3), dtype=np.float32)
            landmark_mask = np.zeros((len(PRIMITIVE_IDS),), dtype=np.int32)
        else:
            semantic_labels, boundary_labels = _semantic_and_boundary_labels(
                indices_zyx=sample.indices_zyx,
                patch_masks=surface_patches.masks,
                level_id=context.standard_level_id,
            )
            landmark_xyz, landmark_mask = _landmark_tensors(
                level_id=context.standard_level_id,
                markups=converted_markups,
            )

        centroid, axes = principal_axes_frame(sample.points_xyz)
        local_coords = (sample.points_xyz - centroid) @ axes.T
        features = np.column_stack(
            (
                local_coords,
                np.full(
                    (len(sample.points_xyz), 1),
                    level_token_index(context.standard_level_id),
                    dtype=float,
                ),
                np.full(
                    (len(sample.points_xyz), 1),
                    structure_type_token(context.structure_type),
                    dtype=float,
                ),
            )
        ).astype(np.float32)

        npz_path = output_dir / f"{metadata['case_id']}_{structure_name}.npz"
        np.savez_compressed(
            npz_path,
            points=sample.points_xyz.astype(np.float32),
            normals=sample.normals_xyz.astype(np.float32),
            features=features,
            semantic_labels=semantic_labels.astype(np.int32),
            boundary_labels=boundary_labels.astype(np.int32),
            landmark_xyz=landmark_xyz.astype(np.float32),
            landmark_mask=landmark_mask.astype(np.int32),
            structure_instance_id=np.asarray(structure_name),
            vertebral_level=np.asarray(context.standard_level_id or "unsupported"),
            case_id=np.asarray(metadata["case_id"]),
            modality=np.asarray(case_context.modality.value),
            numbering_confidence=np.asarray(context.numbering_confidence, dtype=np.float32),
            supports_standard_measurements=np.asarray(
                1 if context.supports_standard_measurements else 0,
                dtype=np.int32,
            ),
        )
        metadata_path_sidecar = npz_path.with_suffix(".json")
        package_metadata = StructurePackageMetadata(
            schema_version=POINTCLOUD_SCHEMA_VERSION,
            case_context=case_context,
            structure_context=context,
            image_path=str(annotation_paths.image_path),
            source_paths=json_ready_path_map(
                structures_segmentation=annotation_paths.structures_segmentation_path,
                surface_patches_segmentation=annotation_paths.surface_patches_segmentation_path,
                landmark_markup=annotation_paths.landmark_markup_path,
                metadata=annotation_paths.metadata_path,
            ),
            landmark_names=tuple(primitive_id.value for primitive_id in PRIMITIVE_IDS),
            surface_patch_names=tuple(patch_id.value for patch_id in SURFACE_PATCH_IDS),
            point_count=int(len(sample.points_xyz)),
            preprocessing_notes=(
                "Points are sampled from segmentation boundary voxels in canonical LPS space.",
                "Normals are heuristic outward estimates until mesh-native normals are available.",
                (
                    "Local coordinates use a PCA frame during preprocessing; anatomical frames are "
                    "derived later."
                ),
            ),
        )
        metadata_path_sidecar.write_text(
            json.dumps(package_metadata.to_dict(), indent=2),
            encoding="utf-8",
        )
        written_paths.extend([npz_path, metadata_path_sidecar])
    return written_paths


def build_dataset_from_root(
    *,
    cases_root: Path,
    output_dir: Path,
    max_points: int = 4096,
    seed: int = 7,
) -> list[Path]:
    written_paths: list[Path] = []
    for metadata_path in sorted(cases_root.rglob("case_metadata.json")):
        case_output_dir = output_dir / metadata_path.parent.name
        written_paths.extend(
            build_case_npz(
                metadata_path=metadata_path,
                output_dir=case_output_dir,
                max_points=max_points,
                seed=seed,
            )
        )
    return written_paths
