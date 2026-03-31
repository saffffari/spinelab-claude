from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

ANATOMY_ONTOLOGY_VERSION = "spinelab.anatomy.v1"


class CoordinateSystem(StrEnum):
    LPS = "LPS"
    RAS = "RAS"


class Modality(StrEnum):
    CT = "CT"
    MR = "MR"


class RegionId(StrEnum):
    CERVICAL = "cervical"
    THORACIC = "thoracic"
    LUMBAR = "lumbar"
    SACRUM = "sacrum"
    PELVIS = "pelvis"
    OTHER = "other"


class StructureType(StrEnum):
    VERTEBRA = "vertebra"
    SACRUM = "sacrum"
    FEMORAL_HEAD = "femoral_head"
    GLOBAL_STRUCTURE = "global_structure"
    OTHER = "other"


class PrimitiveId(StrEnum):
    VERTEBRAL_CENTROID = "vertebral_centroid"
    SUPERIOR_ENDPLATE_PLANE = "superior_endplate_plane"
    INFERIOR_ENDPLATE_PLANE = "inferior_endplate_plane"
    ANTERIOR_SUPERIOR_CORNER = "anterior_superior_corner"
    POSTERIOR_SUPERIOR_CORNER = "posterior_superior_corner"
    ANTERIOR_INFERIOR_CORNER = "anterior_inferior_corner"
    POSTERIOR_INFERIOR_CORNER = "posterior_inferior_corner"
    POSTERIOR_WALL_LINE = "posterior_wall_line"
    SUPERIOR_ENDPLATE_MIDPOINT = "superior_endplate_midpoint"
    INFERIOR_ENDPLATE_MIDPOINT = "inferior_endplate_midpoint"
    VERTEBRA_LOCAL_FRAME = "vertebra_local_frame"


class GlobalStructureId(StrEnum):
    C7_CENTROID = "C7_centroid"
    S1_SUPERIOR_ENDPLATE_PLANE = "S1_superior_endplate_plane"
    S1_SUPERIOR_MIDPOINT = "S1_superior_midpoint"
    POSTERIOR_SUPERIOR_S1_CORNER = "posterior_superior_S1_corner"
    LEFT_FEMORAL_HEAD_CENTER = "left_femoral_head_center"
    RIGHT_FEMORAL_HEAD_CENTER = "right_femoral_head_center"
    BICOXOFEMORAL_AXIS_MIDPOINT = "bicoxofemoral_axis_midpoint"
    SACRAL_CENTER = "sacral_center"


class VariantTag(StrEnum):
    NUMBERING_AMBIGUOUS = "numbering_ambiguous"
    EXTRA_THORACIC_SEGMENT = "extra_thoracic_segment"
    EXTRA_LUMBAR_SEGMENT = "extra_lumbar_segment"
    TRANSITIONAL_LUMBOSACRAL = "transitional_lumbosacral"
    RIB_BEARING_ANOMALY = "rib_bearing_anomaly"
    HEMIVERTEBRA = "hemivertebra"
    BLOCK_VERTEBRA = "block_vertebra"
    FUSED_VERTEBRA = "fused_vertebra"
    MALFORMED_VERTEBRA = "malformed_vertebra"
    UPPER_CERVICAL_SPECIAL_CASE = "upper_cervical_special_case"


@dataclass(frozen=True, slots=True)
class StandardStructureDef:
    standard_level_id: str
    structure_instance_id: str
    region_id: RegionId
    structure_type: StructureType
    order_index: int


STANDARD_LEVEL_IDS: tuple[str, ...] = (
    "C7",
    "T1",
    "T2",
    "T3",
    "T4",
    "T5",
    "T6",
    "T7",
    "T8",
    "T9",
    "T10",
    "T11",
    "T12",
    "L1",
    "L2",
    "L3",
    "L4",
    "L5",
    "S1",
)

PRIMITIVE_IDS: tuple[PrimitiveId, ...] = (
    PrimitiveId.VERTEBRAL_CENTROID,
    PrimitiveId.SUPERIOR_ENDPLATE_PLANE,
    PrimitiveId.INFERIOR_ENDPLATE_PLANE,
    PrimitiveId.ANTERIOR_SUPERIOR_CORNER,
    PrimitiveId.POSTERIOR_SUPERIOR_CORNER,
    PrimitiveId.ANTERIOR_INFERIOR_CORNER,
    PrimitiveId.POSTERIOR_INFERIOR_CORNER,
    PrimitiveId.POSTERIOR_WALL_LINE,
    PrimitiveId.SUPERIOR_ENDPLATE_MIDPOINT,
    PrimitiveId.INFERIOR_ENDPLATE_MIDPOINT,
    PrimitiveId.VERTEBRA_LOCAL_FRAME,
)

GLOBAL_STRUCTURE_IDS: tuple[GlobalStructureId, ...] = (
    GlobalStructureId.C7_CENTROID,
    GlobalStructureId.S1_SUPERIOR_ENDPLATE_PLANE,
    GlobalStructureId.S1_SUPERIOR_MIDPOINT,
    GlobalStructureId.POSTERIOR_SUPERIOR_S1_CORNER,
    GlobalStructureId.LEFT_FEMORAL_HEAD_CENTER,
    GlobalStructureId.RIGHT_FEMORAL_HEAD_CENTER,
    GlobalStructureId.BICOXOFEMORAL_AXIS_MIDPOINT,
    GlobalStructureId.SACRAL_CENTER,
)


def normalize_level_id(level_id: str | None) -> str | None:
    if level_id is None:
        return None
    normalized = level_id.strip().upper()
    return normalized or None


def region_for_level(level_id: str | None) -> RegionId:
    normalized = normalize_level_id(level_id)
    if normalized is None:
        return RegionId.OTHER
    if normalized.startswith("C"):
        return RegionId.CERVICAL
    if normalized.startswith("T"):
        return RegionId.THORACIC
    if normalized.startswith("L"):
        return RegionId.LUMBAR
    if normalized.startswith("S"):
        return RegionId.SACRUM
    return RegionId.OTHER


def structure_type_for_level(level_id: str | None) -> StructureType:
    normalized = normalize_level_id(level_id)
    if normalized == "S1":
        return StructureType.SACRUM
    if normalized is not None and normalized[0] in {"C", "T", "L"}:
        return StructureType.VERTEBRA
    if normalized is not None and normalized.startswith("S"):
        return StructureType.SACRUM
    return StructureType.OTHER


def structure_instance_id_for_level(level_id: str | None) -> str:
    normalized = normalize_level_id(level_id)
    if normalized is None:
        return "other_unknown"
    if normalized.startswith("S"):
        return f"sacrum_{normalized}"
    return f"vertebra_{normalized}"


STANDARD_STRUCTURES: tuple[StandardStructureDef, ...] = tuple(
    StandardStructureDef(
        standard_level_id=level_id,
        structure_instance_id=structure_instance_id_for_level(level_id),
        region_id=region_for_level(level_id),
        structure_type=structure_type_for_level(level_id),
        order_index=index,
    )
    for index, level_id in enumerate(STANDARD_LEVEL_IDS)
)

STANDARD_LEVEL_INDEX: dict[str, int] = {
    definition.standard_level_id: definition.order_index for definition in STANDARD_STRUCTURES
}
STANDARD_STRUCTURE_LOOKUP: dict[str, StandardStructureDef] = {
    definition.standard_level_id: definition for definition in STANDARD_STRUCTURES
}
STANDARD_STRUCTURE_INSTANCE_LOOKUP: dict[str, StandardStructureDef] = {
    definition.structure_instance_id: definition for definition in STANDARD_STRUCTURES
}


def is_supported_standard_level(level_id: str | None) -> bool:
    normalized = normalize_level_id(level_id)
    return normalized in STANDARD_LEVEL_INDEX if normalized is not None else False


def standard_level_sort_key(level_id: str | None) -> tuple[int, str]:
    normalized = normalize_level_id(level_id)
    if normalized is None:
        return (2, "")
    if normalized in STANDARD_LEVEL_INDEX:
        return (0, f"{STANDARD_LEVEL_INDEX[normalized]:03d}")
    return (1, normalized)


def standard_structure_for_level(level_id: str | None) -> StandardStructureDef | None:
    normalized = normalize_level_id(level_id)
    if normalized is None:
        return None
    return STANDARD_STRUCTURE_LOOKUP.get(normalized)


def level_from_structure_instance_id(structure_instance_id: str) -> str | None:
    normalized = structure_instance_id.strip()
    if normalized in STANDARD_STRUCTURE_INSTANCE_LOOKUP:
        return STANDARD_STRUCTURE_INSTANCE_LOOKUP[normalized].standard_level_id
    lowered = normalized.lower()
    if (
        lowered.startswith("vertebra_")
        or lowered.startswith("vertebrae_")
        or lowered.startswith("sacrum_")
    ):
        return normalized.split("_", 1)[1].upper()
    return None


def standard_neighbors(
    level_ids: tuple[str, ...] | list[str],
) -> dict[str, tuple[str | None, str | None]]:
    ordered = sorted(
        {
            normalized
            for level_id in level_ids
            if (normalized := normalize_level_id(level_id)) is not None
            and is_supported_standard_level(normalized)
        },
        key=standard_level_sort_key,
    )
    lookup: dict[str, tuple[str | None, str | None]] = {}
    for index, level_id in enumerate(ordered):
        superior = ordered[index - 1] if index > 0 else None
        inferior = ordered[index + 1] if index + 1 < len(ordered) else None
        lookup[level_id] = (superior, inferior)
    return lookup


def level_token_index(level_id: str | None) -> int:
    normalized = normalize_level_id(level_id)
    if normalized is None:
        return -1
    return STANDARD_LEVEL_INDEX.get(normalized, -1)


def structure_type_token(structure_type: StructureType) -> int:
    order = (
        StructureType.VERTEBRA,
        StructureType.SACRUM,
        StructureType.FEMORAL_HEAD,
        StructureType.GLOBAL_STRUCTURE,
        StructureType.OTHER,
    )
    return order.index(structure_type)


def default_variant_tags_for_display_label(display_label: str | None) -> tuple[VariantTag, ...]:
    normalized = normalize_level_id(display_label)
    if normalized is None:
        return (VariantTag.NUMBERING_AMBIGUOUS,)
    if is_supported_standard_level(normalized):
        return ()
    if normalized.startswith("T") and normalized[1:].isdigit() and int(normalized[1:]) > 12:
        return (VariantTag.EXTRA_THORACIC_SEGMENT, VariantTag.NUMBERING_AMBIGUOUS)
    if normalized.startswith("L") and normalized[1:].isdigit() and int(normalized[1:]) > 5:
        return (VariantTag.EXTRA_LUMBAR_SEGMENT, VariantTag.NUMBERING_AMBIGUOUS)
    if normalized.startswith("C") and normalized[1:].isdigit() and int(normalized[1:]) < 7:
        return (VariantTag.UPPER_CERVICAL_SPECIAL_CASE, VariantTag.NUMBERING_AMBIGUOUS)
    return (VariantTag.NUMBERING_AMBIGUOUS,)


def supports_standard_measurements_for_level(
    standard_level_id: str | None,
    variant_tags: tuple[VariantTag, ...] = (),
) -> bool:
    return standard_level_id is not None and VariantTag.NUMBERING_AMBIGUOUS not in variant_tags
