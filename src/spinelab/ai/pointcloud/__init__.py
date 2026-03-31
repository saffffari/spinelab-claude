"""Point-cloud anatomy learning, preprocessing, geometry, and inference contracts."""

from spinelab.ontology import (
    STANDARD_LEVEL_IDS,
    STANDARD_STRUCTURES,
    CoordinateSystem,
    GlobalStructureId,
    Modality,
    PrimitiveId,
    RegionId,
    StructureType,
    SurfacePatchId,
    VariantTag,
)

from .contracts import CaseAnnotationPaths, CaseContext, StructureContext

__all__ = [
    "CaseAnnotationPaths",
    "CaseContext",
    "CoordinateSystem",
    "GlobalStructureId",
    "Modality",
    "PrimitiveId",
    "RegionId",
    "STANDARD_LEVEL_IDS",
    "STANDARD_STRUCTURES",
    "StructureContext",
    "StructureType",
    "SurfacePatchId",
    "VariantTag",
]
