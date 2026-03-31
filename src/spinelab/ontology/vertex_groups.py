from __future__ import annotations

from enum import StrEnum

SURFACE_PATCH_SCHEMA_VERSION = "spinelab.surface_patch_labels.v1"


class SurfacePatchId(StrEnum):
    BACKGROUND_OR_UNKNOWN = "background_or_unknown"
    SUPERIOR_ENDPLATE = "superior_endplate"
    INFERIOR_ENDPLATE = "inferior_endplate"
    POSTERIOR_BODY_WALL = "posterior_body_wall"
    VERTEBRAL_BODY_SURFACE = "vertebral_body_surface"
    LEFT_PEDICLE = "left_pedicle"
    RIGHT_PEDICLE = "right_pedicle"
    LEFT_FACET_SURFACE = "left_facet_surface"
    RIGHT_FACET_SURFACE = "right_facet_surface"


SURFACE_PATCH_CLASS_INDEX: dict[SurfacePatchId, int] = {
    SurfacePatchId.BACKGROUND_OR_UNKNOWN: 0,
    SurfacePatchId.SUPERIOR_ENDPLATE: 1,
    SurfacePatchId.INFERIOR_ENDPLATE: 2,
    SurfacePatchId.POSTERIOR_BODY_WALL: 3,
    SurfacePatchId.VERTEBRAL_BODY_SURFACE: 4,
    SurfacePatchId.LEFT_PEDICLE: 5,
    SurfacePatchId.RIGHT_PEDICLE: 6,
    SurfacePatchId.LEFT_FACET_SURFACE: 7,
    SurfacePatchId.RIGHT_FACET_SURFACE: 8,
}

SURFACE_PATCH_IDS: tuple[SurfacePatchId, ...] = tuple(
    patch_id for patch_id, _ in sorted(SURFACE_PATCH_CLASS_INDEX.items(), key=lambda item: item[1])
)

SURFACE_PATCH_ID_BY_CLASS_INDEX: dict[int, SurfacePatchId] = {
    class_index: patch_id for patch_id, class_index in SURFACE_PATCH_CLASS_INDEX.items()
}


def surface_patch_segment_name(level_id: str, patch_id: SurfacePatchId) -> str:
    return f"{level_id.strip().upper()}_{patch_id.value}"
