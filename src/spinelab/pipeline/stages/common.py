from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np

from spinelab.models import CaseManifest, PipelineArtifact, VolumeMetadata
from spinelab.ontology import STANDARD_STRUCTURES, standard_level_sort_key

SEGMENTATION_MODEL_NAME = "nnunetv2-resenc-l"
SEGMENTATION_MODEL_VERSION = "cads-foundation"
PTV3_MODEL_NAME = "point-transformer-v3"
PTV3_MODEL_VERSION = "vertex-groups-foundation-plan"
REGISTRATION_MODEL_NAME = "polypose"
REGISTRATION_MODEL_VERSION = "gui-foundation-plan"

VERTEBRA_LEVELS = tuple(definition.standard_level_id for definition in STANDARD_STRUCTURES)

VERTEBRA_LABELS = {vertebra_id: index + 1 for index, vertebra_id in enumerate(VERTEBRA_LEVELS)}


@dataclass(frozen=True, slots=True)
class VertebraGeometry:
    vertebra_id: str
    label_value: int
    center: tuple[float, float, float]
    extents: tuple[float, float, float]


def analysis_generated_asset_id(stage: str, name: str) -> str:
    return f"generated-{stage}-{name}"


def generated_asset_prefix(stage: str) -> str:
    return f"generated-{stage}-"


def primary_ct_volume(manifest: CaseManifest) -> VolumeMetadata | None:
    ct_asset = manifest.get_asset_for_role("ct_stack")
    if ct_asset is not None:
        volume = manifest.get_volume(ct_asset.asset_id)
        if volume is not None:
            return volume
    for volume in manifest.volumes:
        if volume.modality == "ct":
            return volume
    return manifest.volumes[0] if manifest.volumes else None


def artifact_for_type(manifest: CaseManifest, artifact_type: str) -> PipelineArtifact | None:
    for artifact in reversed(manifest.artifacts):
        if artifact.artifact_type == artifact_type:
            return artifact
    return None


def read_json_payload(manifest: CaseManifest, artifact_type: str) -> dict[str, Any] | None:
    artifact = artifact_for_type(manifest, artifact_type)
    if artifact is None:
        return None
    path = Path(artifact.path)
    if not path.exists() or path.suffix.lower() not in {".json"}:
        return None
    return cast_json_dict(path)


def cast_json_dict(path: Path) -> dict[str, Any]:
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    return {}


def synthetic_vertebrae() -> list[VertebraGeometry]:
    def center_for_level(level_id: str, order_index: int) -> tuple[float, float, float]:
        if level_id == "C7":
            z_position = 168.0
        elif level_id.startswith("T"):
            z_position = 156.0 - ((int(level_id[1:]) - 1) * 10.5)
        elif level_id.startswith("L"):
            z_position = 34.0 - ((int(level_id[1:]) - 1) * 12.5)
        else:
            z_position = -36.0
        x_position = math.sin(order_index / 2.6) * 4.0
        y_position = 14.0 - (order_index * 1.6)
        return (x_position, y_position, z_position)

    def extents_for_level(level_id: str) -> tuple[float, float, float]:
        if level_id == "C7":
            return (18.0, 13.0, 11.0)
        if level_id.startswith("T"):
            thoracic_index = int(level_id[1:])
            return (
                22.0 + (thoracic_index * 0.65),
                15.0 + (thoracic_index * 0.35),
                12.0 + (thoracic_index * 0.15),
            )
        if level_id.startswith("L"):
            lumbar_index = int(level_id[1:])
            return (
                28.0 + (lumbar_index * 1.4),
                18.5 + (lumbar_index * 0.9),
                15.0 + (lumbar_index * 0.5),
            )
        return (36.0, 26.0, 14.0)

    return [
        VertebraGeometry(
            vertebra_id=vertebra_id,
            label_value=VERTEBRA_LABELS[vertebra_id],
            center=center_for_level(vertebra_id, index),
            extents=extents_for_level(vertebra_id),
        )
        for index, vertebra_id in enumerate(sorted(VERTEBRA_LEVELS, key=standard_level_sort_key))
    ]


def load_or_placeholder_volume(volume: VolumeMetadata) -> np.ndarray:
    path = Path(volume.canonical_path)
    suffix = "".join(path.suffixes).lower()
    if path.is_file() and suffix in {".nii", ".nii.gz"}:
        image_any: Any = nib.load(str(path))
        data = np.asarray(image_any.dataobj)
        if data.ndim == 2:
            data = data[:, :, np.newaxis]
        return np.asarray(data)
    fallback_shape = tuple(max(1, int(dimension)) for dimension in volume.dimensions)
    return np.zeros(fallback_shape, dtype=np.int16)


def write_label_map(path: Path, label_map: np.ndarray, volume: VolumeMetadata) -> None:
    spacing = volume.voxel_spacing or (1.0, 1.0, 1.0)
    affine = np.diag([spacing[0], spacing[1], spacing[2], 1.0])
    canonical_path = Path(volume.canonical_path)
    suffix = "".join(canonical_path.suffixes).lower()
    if canonical_path.is_file() and suffix in {".nii", ".nii.gz"}:
        try:
            image_any: Any = nib.load(str(canonical_path))
        except Exception:
            image_any = None
        if image_any is not None:
            affine = np.asarray(image_any.affine, dtype=float)
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(nib.Nifti1Image(label_map.astype(np.int16), affine), str(path))


def populate_label_map(shape: tuple[int, int, int]) -> np.ndarray:
    normalized_shape = tuple(max(2, int(dimension)) for dimension in shape)
    label_map = np.zeros(normalized_shape, dtype=np.int16)
    flat_indices = np.arange(label_map.size)
    for offset, vertebra in enumerate(synthetic_vertebrae()):
        flat_index = flat_indices[offset % len(flat_indices)]
        coordinates = np.unravel_index(int(flat_index), normalized_shape)
        x = int(coordinates[0])
        y = int(coordinates[1])
        z = int(coordinates[2])
        x_end = min(normalized_shape[0], x + 1)
        y_end = min(normalized_shape[1], y + 1)
        z_end = min(normalized_shape[2], z + 1)
        label_map[x:x_end, y:y_end, z:z_end] = vertebra.label_value
    return label_map


def write_ascii_box_ply(
    output_path: Path,
    vertebra_id: str,
    center: tuple[float, float, float],
    extents: tuple[float, float, float],
    *,
    comment: str,
) -> None:
    cx, cy, cz = center
    ex, ey, ez = (extent / 2.0 for extent in extents)
    vertices = [
        (cx - ex, cy - ey, cz - ez),
        (cx + ex, cy - ey, cz - ez),
        (cx + ex, cy + ey, cz - ez),
        (cx - ex, cy + ey, cz - ez),
        (cx - ex, cy - ey, cz + ez),
        (cx + ex, cy - ey, cz + ez),
        (cx + ex, cy + ey, cz + ez),
        (cx - ex, cy + ey, cz + ez),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (2, 3, 7, 6),
        (1, 2, 6, 5),
        (0, 3, 7, 4),
    ]
    lines = [
        "ply",
        "format ascii 1.0",
        f"comment {comment}",
        f"comment vertebra {vertebra_id}",
        f"element vertex {len(vertices)}",
        "property float x",
        "property float y",
        "property float z",
        f"element face {len(faces)}",
        "property list uchar int vertex_indices",
        "end_header",
    ]
    lines.extend(f"{x} {y} {z}" for x, y, z in vertices)
    lines.extend("4 " + " ".join(str(index) for index in face) for face in faces)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def rotation_matrix_xyz(
    *,
    rx_degrees: float = 0.0,
    ry_degrees: float = 0.0,
    rz_degrees: float = 0.0,
) -> np.ndarray:
    rx = math.radians(rx_degrees)
    ry = math.radians(ry_degrees)
    rz = math.radians(rz_degrees)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    rotation_x = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]])
    rotation_y = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]])
    rotation_z = np.array([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]])
    return np.asarray(rotation_z @ rotation_y @ rotation_x, dtype=float)


def homogeneous_transform(
    rotation: np.ndarray,
    translation: tuple[float, float, float],
) -> np.ndarray:
    transform = np.eye(4)
    transform[:3, :3] = rotation
    transform[:3, 3] = np.asarray(translation, dtype=float)
    return transform


def apply_transform_to_point(
    transform: np.ndarray,
    point: tuple[float, float, float],
) -> tuple[float, float, float]:
    homogeneous = np.array([point[0], point[1], point[2], 1.0], dtype=float)
    transformed = transform @ homogeneous
    return (float(transformed[0]), float(transformed[1]), float(transformed[2]))


def apply_transform_to_vector(
    transform: np.ndarray,
    vector: tuple[float, float, float],
) -> tuple[float, float, float]:
    transformed = transform[:3, :3] @ np.asarray(vector, dtype=float)
    return (float(transformed[0]), float(transformed[1]), float(transformed[2]))


def transform_to_payload(transform: np.ndarray) -> list[list[float]]:
    return [[float(value) for value in row] for row in transform.tolist()]


def payload_to_transform(payload: list[list[float]]) -> np.ndarray:
    return np.asarray(payload, dtype=float)


def maybe_write_glb_scene(
    output_path: Path,
    transforms: dict[str, np.ndarray],
    geometries: dict[str, VertebraGeometry],
) -> bool:
    try:
        import trimesh
    except ImportError:
        return False

    scene = trimesh.Scene()
    for vertebra_id, geometry in geometries.items():
        mesh = trimesh.creation.box(extents=np.asarray(geometry.extents, dtype=float))
        transform = transforms[vertebra_id].copy()
        transform[:3, 3] = np.asarray(apply_transform_to_point(transform, geometry.center))
        scene.add_geometry(mesh, node_name=vertebra_id, transform=transform)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(output_path))
    return output_path.exists()


def line_through_points(
    first: tuple[float, float, float],
    second: tuple[float, float, float],
) -> tuple[float, float, float]:
    vector = np.asarray(second, dtype=float) - np.asarray(first, dtype=float)
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        return (0.0, 0.0, 1.0)
    vector /= norm
    return (float(vector[0]), float(vector[1]), float(vector[2]))


def signed_angle_degrees(
    first: tuple[float, float, float],
    second: tuple[float, float, float],
    *,
    plane: str = "sagittal",
) -> float:
    axis_lookup = {
        "sagittal": (0, 2),
        "coronal": (1, 2),
        "axial": (0, 1),
    }
    axis_indices = axis_lookup[plane]
    first_vector = np.asarray([first[axis_indices[0]], first[axis_indices[1]]], dtype=float)
    second_vector = np.asarray([second[axis_indices[0]], second[axis_indices[1]]], dtype=float)
    if np.linalg.norm(first_vector) == 0.0 or np.linalg.norm(second_vector) == 0.0:
        return 0.0
    first_angle = math.atan2(first_vector[1], first_vector[0])
    second_angle = math.atan2(second_vector[1], second_vector[0])
    return math.degrees(second_angle - first_angle)
