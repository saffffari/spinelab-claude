from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spinelab.ontology import (
    CaseOntologyContext,
    StructureInstanceContext,
)

POINTCLOUD_SCHEMA_VERSION = "spinelab.pointcloud.v1"
PTV3_VERTEX_GROUP_SCHEMA_VERSION = "spinelab.ptv3.vertex_groups.v1"
LANDMARK_SCHEMA_VERSION = "spinelab.landmarks.contract.v1"

CaseContext = CaseOntologyContext
StructureContext = StructureInstanceContext


@dataclass(frozen=True, slots=True)
class CaseAnnotationPaths:
    image_path: Path
    structures_segmentation_path: Path
    surface_patches_segmentation_path: Path
    landmark_markup_path: Path
    metadata_path: Path


@dataclass(frozen=True, slots=True)
class StructurePackageMetadata:
    schema_version: str
    case_context: CaseOntologyContext
    structure_context: StructureInstanceContext
    image_path: str
    source_paths: dict[str, str]
    landmark_names: tuple[str, ...]
    surface_patch_names: tuple[str, ...]
    point_count: int
    preprocessing_notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "case_context": self.case_context.to_dict(),
            "structure_context": self.structure_context.to_dict(),
            "image_path": self.image_path,
            "source_paths": dict(self.source_paths),
            "landmark_names": list(self.landmark_names),
            "surface_patch_names": list(self.surface_patch_names),
            "point_count": self.point_count,
            "preprocessing_notes": list(self.preprocessing_notes),
        }


@dataclass(frozen=True, slots=True)
class LandmarkInferencePayload:
    case_id: str
    model_name: str
    model_version: str
    provider_name: str
    coordinate_frame: str
    vertebrae: tuple[dict[str, Any], ...]
    global_structures: tuple[dict[str, Any], ...] = ()
    schema_version: str = LANDMARK_SCHEMA_VERSION
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "landmark_model": f"{self.model_name}:{self.model_version}",
            "model_name": self.model_name,
            "model_version": self.model_version,
            "provider_name": self.provider_name,
            "coordinate_frame": self.coordinate_frame,
            "vertebrae": list(self.vertebrae),
            "global_structures": list(self.global_structures),
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class VertexGroupInferencePayload:
    case_id: str
    model_name: str
    model_version: str
    provider_name: str
    vertebrae: tuple[dict[str, Any], ...]
    schema_version: str = PTV3_VERTEX_GROUP_SCHEMA_VERSION
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "provider_name": self.provider_name,
            "vertebrae": list(self.vertebrae),
            "notes": list(self.notes),
        }


def json_ready_path_map(**paths: Path) -> dict[str, str]:
    return {key: str(value) for key, value in paths.items()}
