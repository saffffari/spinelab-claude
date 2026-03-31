from __future__ import annotations

from enum import StrEnum


class SegmentationProfile(StrEnum):
    PRODUCTION = "production"
    SCAFFOLD = "scaffold"


DEFAULT_SEGMENTATION_PROFILE = SegmentationProfile.PRODUCTION.value

SEGMENTATION_PROFILE_LABELS: dict[str, str] = {
    SegmentationProfile.PRODUCTION.value: "Production",
    SegmentationProfile.SCAFFOLD.value: "Scaffold",
}
def canonical_segmentation_profile(value: str | None) -> str:
    if not value:
        return DEFAULT_SEGMENTATION_PROFILE
    normalized = value.strip().lower()
    if normalized == SegmentationProfile.PRODUCTION.value:
        return SegmentationProfile.PRODUCTION.value
    if normalized == SegmentationProfile.SCAFFOLD.value:
        return SegmentationProfile.SCAFFOLD.value
    return DEFAULT_SEGMENTATION_PROFILE


def segmentation_profile_label(value: str | None) -> str:
    return SEGMENTATION_PROFILE_LABELS[canonical_segmentation_profile(value)]
