"""Hierarchical organ-system groupings for the Anatomy Explorer tree.

Defines display names and group membership for segmentation labels so the
measurement workspace can present a collapsible organ-system tree with
per-structure visibility toggles.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnatomyGroup:
    display_name: str
    label_names: tuple[str, ...]


# ---------------------------------------------------------------------------
# Display name overrides — keys that need friendlier UI text
# ---------------------------------------------------------------------------

DISPLAY_NAME_OVERRIDES: dict[str, str] = {
    "inferior_vena_cava": "IVC",
    "portal_vein_and_splenic_vein": "Portal / Splenic Vein",
    "heart_myocardium": "Myocardium",
    "heart_atrium_left": "Atrium Left",
    "heart_ventricle_left": "Ventricle Left",
    "heart_atrium_right": "Atrium Right",
    "heart_ventricle_right": "Ventricle Right",
    "lung_upper_lobe_left": "Upper Lobe Left",
    "lung_lower_lobe_left": "Lower Lobe Left",
    "lung_upper_lobe_right": "Upper Lobe Right",
    "lung_middle_lobe_right": "Middle Lobe Right",
    "lung_lower_lobe_right": "Lower Lobe Right",
    "adrenal_gland_right": "Adrenal Right",
    "adrenal_gland_left": "Adrenal Left",
    "clavicula_left": "Clavicle Left",
    "clavicula_right": "Clavicle Right",
    "iliac_artery_left": "Iliac Artery Left",
    "iliac_artery_right": "Iliac Artery Right",
    "iliac_vena_left": "Iliac Vein Left",
    "iliac_vena_right": "Iliac Vein Right",
    "pulmonary_artery": "Pulmonary Artery",
}


def display_name_for_label(label_name: str) -> str:
    """Return a user-friendly display name for a segmentation label."""
    if label_name in DISPLAY_NAME_OVERRIDES:
        return DISPLAY_NAME_OVERRIDES[label_name]
    # Standard vertebra IDs (C1, T12, L5, etc.) stay as-is
    if len(label_name) <= 3 and label_name[0] in "CTLS":
        return label_name
    return label_name.replace("_", " ").title()


# ---------------------------------------------------------------------------
# Organ system groups
# ---------------------------------------------------------------------------

ANATOMY_GROUPS: tuple[AnatomyGroup, ...] = (
    AnatomyGroup(
        "Spine",
        (
            "C1", "C2", "C3", "C4", "C5", "C6", "C7",
            "T1", "T2", "T3", "T4", "T5", "T6",
            "T7", "T8", "T9", "T10", "T11", "T12",
            "L1", "L2", "L3", "L4", "L5",
        ),
    ),
    AnatomyGroup(
        "Pelvis & Sacrum",
        ("sacrum", "hip_left", "hip_right"),
    ),
    AnatomyGroup(
        "Upper Extremities",
        (
            "humerus_left", "humerus_right",
            "scapula_left", "scapula_right",
            "clavicula_left", "clavicula_right",
        ),
    ),
    AnatomyGroup(
        "Lower Extremities",
        ("femur_left", "femur_right"),
    ),
    AnatomyGroup(
        "Ribs",
        (
            "rib_left_1", "rib_left_2", "rib_left_3",
            "rib_left_4", "rib_left_5", "rib_left_6",
            "rib_left_7", "rib_left_8", "rib_left_9",
            "rib_left_10", "rib_left_11", "rib_left_12",
            "rib_right_1", "rib_right_2", "rib_right_3",
            "rib_right_4", "rib_right_5", "rib_right_6",
            "rib_right_7", "rib_right_8", "rib_right_9",
            "rib_right_10", "rib_right_11", "rib_right_12",
            "sternum",
        ),
    ),
    AnatomyGroup(
        "Spinal Canal & Cord",
        ("spinal_canal", "spinal_cord"),
    ),
    AnatomyGroup(
        "Vasculature",
        (
            "aorta", "inferior_vena_cava",
            "iliac_artery_left", "iliac_artery_right",
            "iliac_vena_left", "iliac_vena_right",
            "portal_vein_and_splenic_vein",
            "pulmonary_artery",
        ),
    ),
    AnatomyGroup(
        "Heart",
        (
            "heart_myocardium",
            "heart_atrium_left", "heart_ventricle_left",
            "heart_atrium_right", "heart_ventricle_right",
        ),
    ),
    AnatomyGroup(
        "Lungs",
        (
            "lung_upper_lobe_left", "lung_lower_lobe_left",
            "lung_upper_lobe_right", "lung_middle_lobe_right",
            "lung_lower_lobe_right",
        ),
    ),
    AnatomyGroup(
        "Airway",
        ("esophagus", "trachea"),
    ),
    AnatomyGroup(
        "Abdominal Organs",
        (
            "liver", "spleen",
            "kidney_right", "kidney_left",
            "gallbladder", "stomach",
            "pancreas",
            "adrenal_gland_right", "adrenal_gland_left",
        ),
    ),
)


def available_anatomy_groups(label_names: set[str]) -> list[AnatomyGroup]:
    """Return groups filtered to only include labels present in the case.

    Matching is case-insensitive so that UPPER viewport IDs match the
    lowercase canonical names defined in *ANATOMY_GROUPS*.
    """
    upper_names = {n.upper() for n in label_names}
    result: list[AnatomyGroup] = []
    for group in ANATOMY_GROUPS:
        present = tuple(name for name in group.label_names if name.upper() in upper_names)
        if present:
            result.append(AnatomyGroup(group.display_name, present))
    return result
