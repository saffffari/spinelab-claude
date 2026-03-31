from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .core import (
    CoordinateSystem,
    Modality,
    RegionId,
    StructureType,
    VariantTag,
    default_variant_tags_for_display_label,
    normalize_level_id,
    region_for_level,
    standard_structure_for_level,
    structure_instance_id_for_level,
    structure_type_for_level,
    supports_standard_measurements_for_level,
)


@dataclass(frozen=True, slots=True)
class StructureInstanceContext:
    structure_instance_id: str
    display_label: str
    standard_level_id: str | None
    region_id: RegionId
    structure_type: StructureType
    order_index: int | None
    modality: Modality
    numbering_confidence: float
    variant_tags: tuple[VariantTag, ...] = ()
    supports_standard_measurements: bool = True
    superior_neighbor_instance_id: str | None = None
    inferior_neighbor_instance_id: str | None = None

    @property
    def structure_id(self) -> str:
        return self.structure_instance_id

    @property
    def superior_neighbor(self) -> str | None:
        return self.superior_neighbor_instance_id

    @property
    def inferior_neighbor(self) -> str | None:
        return self.inferior_neighbor_instance_id

    @property
    def is_atypical(self) -> bool:
        return (
            self.standard_level_id is None
            or bool(self.variant_tags)
            or not self.supports_standard_measurements
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["region_id"] = self.region_id.value
        payload["structure_type"] = self.structure_type.value
        payload["modality"] = self.modality.value
        payload["variant_tags"] = [tag.value for tag in self.variant_tags]
        payload["is_atypical"] = self.is_atypical
        payload["structure_id"] = self.structure_instance_id
        payload["superior_neighbor"] = self.superior_neighbor_instance_id
        payload["inferior_neighbor"] = self.inferior_neighbor_instance_id
        return payload


@dataclass(frozen=True, slots=True)
class CaseOntologyContext:
    case_id: str
    modality: Modality
    source_coordinate_system: CoordinateSystem
    canonical_coordinate_system: CoordinateSystem = CoordinateSystem.LPS
    levels_present: tuple[str, ...] = ()
    unsupported_levels_present: tuple[str, ...] = ()
    pelvis_present: bool = False
    field_of_view_start: str | None = None
    field_of_view_end: str | None = None
    numbering_review_flags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["modality"] = self.modality.value
        payload["source_coordinate_system"] = self.source_coordinate_system.value
        payload["canonical_coordinate_system"] = self.canonical_coordinate_system.value
        payload["levels_present"] = list(self.levels_present)
        payload["unsupported_levels_present"] = list(self.unsupported_levels_present)
        payload["numbering_review_flags"] = list(self.numbering_review_flags)
        return payload


def build_structure_instance_context(
    *,
    display_label: str,
    modality: Modality,
    numbering_confidence: float = 1.0,
    structure_instance_id: str | None = None,
    variant_tags: tuple[VariantTag, ...] = (),
    superior_neighbor_instance_id: str | None = None,
    inferior_neighbor_instance_id: str | None = None,
) -> StructureInstanceContext:
    normalized = normalize_level_id(display_label)
    definition = standard_structure_for_level(normalized)
    inferred_variant_tags = default_variant_tags_for_display_label(display_label)
    combined_variant_tags = tuple(dict.fromkeys((*inferred_variant_tags, *variant_tags)))
    standard_level_id = definition.standard_level_id if definition is not None else None
    structure_type = (
        definition.structure_type
        if definition is not None
        else structure_type_for_level(normalized)
    )
    region_id = definition.region_id if definition is not None else region_for_level(normalized)
    order_index = definition.order_index if definition is not None else None
    return StructureInstanceContext(
        structure_instance_id=structure_instance_id
        or structure_instance_id_for_level(standard_level_id or normalized),
        display_label=normalized or display_label,
        standard_level_id=standard_level_id,
        region_id=region_id,
        structure_type=structure_type,
        order_index=order_index,
        modality=modality,
        numbering_confidence=numbering_confidence,
        variant_tags=combined_variant_tags,
        supports_standard_measurements=supports_standard_measurements_for_level(
            standard_level_id,
            combined_variant_tags,
        ),
        superior_neighbor_instance_id=superior_neighbor_instance_id,
        inferior_neighbor_instance_id=inferior_neighbor_instance_id,
    )
