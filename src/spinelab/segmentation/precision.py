from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class InferencePrecisionTier(str, Enum):
    DRAFT = "draft"
    STANDARD = "standard"
    QUALITY = "quality"


@dataclass(frozen=True, slots=True)
class InferencePrecisionParams:
    disable_tta: bool
    tile_step_size: float


PRECISION_TIER_PARAMS: dict[InferencePrecisionTier, InferencePrecisionParams] = {
    InferencePrecisionTier.DRAFT: InferencePrecisionParams(disable_tta=True, tile_step_size=0.7),
    InferencePrecisionTier.STANDARD: InferencePrecisionParams(
        disable_tta=True, tile_step_size=0.5
    ),
    InferencePrecisionTier.QUALITY: InferencePrecisionParams(
        disable_tta=False, tile_step_size=0.5
    ),
}

DEFAULT_PRECISION_TIER = InferencePrecisionTier.STANDARD
