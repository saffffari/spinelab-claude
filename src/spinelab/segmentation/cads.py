"""CADS composite segmentation task definitions and label maps.

Defines the sub-model configurations for CADS pretrained nnU-Net models
used by the composite segmentation driver.  Each sub-model corresponds
to one CADS task (Dataset551-559) and specifies which source labels to
cherry-pick and what unified output label they map to.

Reference: https://github.com/murong-xu/CADS
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CADSSubModelSpec:
    """Specification for one CADS nnU-Net task model within a composite bundle."""

    task_id: str
    dataset_name: str
    label_cherry_pick: dict[int, int]
    """Mapping of source label index → unified output label."""


# ---------------------------------------------------------------------------
# Shared nnU-Net training configuration for all CADS pretrained models
# ---------------------------------------------------------------------------

CADS_TRAINER_NAME = "nnUNetTrainerNoMirroring"
CADS_PLAN_NAME = "nnUNetResEncUNetLPlans"
CADS_CONFIGURATION = "3d_fullres"
CADS_FOLD = "all"
CADS_CHECKPOINT_NAME = "checkpoint_final.pth"
CADS_FAMILY = "cads-composite"
CADS_DRIVER_ID = "cads-composite"
CADS_ENVIRONMENT_ID = "nnunet-verse20-win"

# ---------------------------------------------------------------------------
# Unified label map — output label assignments
#
# Skeleton (61 classes):
#   1-24   Vertebrae (from task 552, source reversed: L5=1 ... C1=24)
#   25-35  Appendicular bones + sacrum (from task 554, source 1-11)
#   36-47  Ribs left 1-12 (from task 555, source 1-12)
#   48-59  Ribs right 1-12 (from task 555, source 13-24)
#   60     Sternum (from task 556, source 11)
#   61     Spinal canal (from task 556, source 1)
#
# Skeleton Plus adds (labels 62-69):
#   62     Aorta (from task 551, source 7)
#   63     Inferior vena cava (from task 551, source 8)
#   64     Iliac artery left (from task 553, source 10)
#   65     Iliac artery right (from task 553, source 11)
#   66     Iliac vein left (from task 553, source 12)
#   67     Iliac vein right (from task 553, source 13)
#   68     Spinal cord (from task 559, source 10)
# ---------------------------------------------------------------------------

# -- Task 552: Vertebrae C1-L5 (source labels are L5=1 .. C1=24) ----------

_TASK_552_CHERRY_PICK: dict[int, int] = {
    1: 1,    # vertebrae_L5
    2: 2,    # vertebrae_L4
    3: 3,    # vertebrae_L3
    4: 4,    # vertebrae_L2
    5: 5,    # vertebrae_L1
    6: 6,    # vertebrae_T12
    7: 7,    # vertebrae_T11
    8: 8,    # vertebrae_T10
    9: 9,    # vertebrae_T9
    10: 10,  # vertebrae_T8
    11: 11,  # vertebrae_T7
    12: 12,  # vertebrae_T6
    13: 13,  # vertebrae_T5
    14: 14,  # vertebrae_T4
    15: 15,  # vertebrae_T3
    16: 16,  # vertebrae_T2
    17: 17,  # vertebrae_T1
    18: 18,  # vertebrae_C7
    19: 19,  # vertebrae_C6
    20: 20,  # vertebrae_C5
    21: 21,  # vertebrae_C4
    22: 22,  # vertebrae_C3
    23: 23,  # vertebrae_C2
    24: 24,  # vertebrae_C1
}

# -- Task 554: Appendicular bones + sacrum (skip muscles 12-21) -----------

_TASK_554_BONES_CHERRY_PICK: dict[int, int] = {
    1: 25,   # humerus_left
    2: 26,   # humerus_right
    3: 27,   # scapula_left
    4: 28,   # scapula_right
    5: 29,   # clavicula_left
    6: 30,   # clavicula_right
    7: 31,   # femur_left
    8: 32,   # femur_right
    9: 33,   # hip_left
    10: 34,  # hip_right
    11: 35,  # sacrum
}

# -- Task 555: Ribs --------------------------------------------------------

_TASK_555_CHERRY_PICK: dict[int, int] = {
    1: 36,   # rib_left_1
    2: 37,   # rib_left_2
    3: 38,   # rib_left_3
    4: 39,   # rib_left_4
    5: 40,   # rib_left_5
    6: 41,   # rib_left_6
    7: 42,   # rib_left_7
    8: 43,   # rib_left_8
    9: 44,   # rib_left_9
    10: 45,  # rib_left_10
    11: 46,  # rib_left_11
    12: 47,  # rib_left_12
    13: 48,  # rib_right_1
    14: 49,  # rib_right_2
    15: 50,  # rib_right_3
    16: 51,  # rib_right_4
    17: 52,  # rib_right_5
    18: 53,  # rib_right_6
    19: 54,  # rib_right_7
    20: 55,  # rib_right_8
    21: 56,  # rib_right_9
    22: 57,  # rib_right_10
    23: 58,  # rib_right_11
    24: 59,  # rib_right_12
}

# -- Task 556: Spinal canal + sternum (skip other structures) --------------

_TASK_556_CHERRY_PICK: dict[int, int] = {
    11: 60,  # sternum
    1: 61,   # spinal_canal
}

# -- Task 551: Aorta + IVC (Plus only) ------------------------------------

_TASK_551_CHERRY_PICK: dict[int, int] = {
    7: 62,   # aorta
    8: 63,   # inferior_vena_cava
}

# -- Task 553: Iliac arteries/veins (Plus only) ---------------------------

_TASK_553_CHERRY_PICK: dict[int, int] = {
    10: 64,  # iliac_artery_left
    11: 65,  # iliac_artery_right
    12: 66,  # iliac_vena_left
    13: 67,  # iliac_vena_right
}

# -- Task 559: Spinal cord (Plus only, cherry-pick index 10 only) ----------

_TASK_559_CHERRY_PICK: dict[int, int] = {
    10: 68,  # spinal_cord
}

# ---------------------------------------------------------------------------
# Sub-model lists for each composite bundle
# ---------------------------------------------------------------------------

CADS_SKELETON_SUB_MODELS: tuple[CADSSubModelSpec, ...] = (
    CADSSubModelSpec(
        task_id="552",
        dataset_name="Dataset552_Totalseg252",
        label_cherry_pick=_TASK_552_CHERRY_PICK,
    ),
    CADSSubModelSpec(
        task_id="554",
        dataset_name="Dataset554_Totalseg254",
        label_cherry_pick=_TASK_554_BONES_CHERRY_PICK,
    ),
    CADSSubModelSpec(
        task_id="555",
        dataset_name="Dataset555_Totalseg255",
        label_cherry_pick=_TASK_555_CHERRY_PICK,
    ),
    CADSSubModelSpec(
        task_id="556",
        dataset_name="Dataset556_GC256",
        label_cherry_pick=_TASK_556_CHERRY_PICK,
    ),
)

CADS_SKELETON_PLUS_SUB_MODELS: tuple[CADSSubModelSpec, ...] = (
    *CADS_SKELETON_SUB_MODELS,
    CADSSubModelSpec(
        task_id="551",
        dataset_name="Dataset551_Totalseg251",
        label_cherry_pick=_TASK_551_CHERRY_PICK,
    ),
    CADSSubModelSpec(
        task_id="553",
        dataset_name="Dataset553_Totalseg253",
        label_cherry_pick=_TASK_553_CHERRY_PICK,
    ),
    CADSSubModelSpec(
        task_id="559",
        dataset_name="Dataset559_Saros259",
        label_cherry_pick=_TASK_559_CHERRY_PICK,
    ),
)

# ---------------------------------------------------------------------------
# Unified label_mapping dicts (structure_name → output_label)
#
# Keys that match SpineLab ontology standard_level_ids (e.g. "L5", "T1")
# will be processed by the downstream vertebrae pipeline.  All other keys
# are carried in the segmentation NIfTI for visualization but do not feed
# into landmarks / measurements.
# ---------------------------------------------------------------------------

CADS_SKELETON_LABEL_MAPPING: dict[str, int] = {
    # Vertebrae — use SpineLab standard level IDs so downstream pipeline picks them up
    "L5": 1, "L4": 2, "L3": 3, "L2": 4, "L1": 5,
    "T12": 6, "T11": 7, "T10": 8, "T9": 9, "T8": 10,
    "T7": 11, "T6": 12, "T5": 13, "T4": 14, "T3": 15,
    "T2": 16, "T1": 17,
    "C7": 18, "C6": 19, "C5": 20, "C4": 21, "C3": 22, "C2": 23, "C1": 24,
    # Appendicular bones + sacrum
    "humerus_left": 25, "humerus_right": 26,
    "scapula_left": 27, "scapula_right": 28,
    "clavicula_left": 29, "clavicula_right": 30,
    "femur_left": 31, "femur_right": 32,
    "hip_left": 33, "hip_right": 34,
    "sacrum": 35,
    # Ribs
    "rib_left_1": 36, "rib_left_2": 37, "rib_left_3": 38,
    "rib_left_4": 39, "rib_left_5": 40, "rib_left_6": 41,
    "rib_left_7": 42, "rib_left_8": 43, "rib_left_9": 44,
    "rib_left_10": 45, "rib_left_11": 46, "rib_left_12": 47,
    "rib_right_1": 48, "rib_right_2": 49, "rib_right_3": 50,
    "rib_right_4": 51, "rib_right_5": 52, "rib_right_6": 53,
    "rib_right_7": 54, "rib_right_8": 55, "rib_right_9": 56,
    "rib_right_10": 57, "rib_right_11": 58, "rib_right_12": 59,
    # Sternum + spinal canal
    "sternum": 60,
    "spinal_canal": 61,
}

CADS_SKELETON_PLUS_LABEL_MAPPING: dict[str, int] = {
    **CADS_SKELETON_LABEL_MAPPING,
    # Vasculature
    "aorta": 62, "inferior_vena_cava": 63,
    "iliac_artery_left": 64, "iliac_artery_right": 65,
    "iliac_vena_left": 66, "iliac_vena_right": 67,
    # Neural
    "spinal_cord": 68,
}

# ---------------------------------------------------------------------------
# Bundle IDs and display names
# ---------------------------------------------------------------------------

CADS_SKELETON_BUNDLE_ID = "cads-skeleton"
CADS_SKELETON_DISPLAY_NAME = "CADS Skeleton"
CADS_SKELETON_PLUS_BUNDLE_ID = "cads-skeleton-plus"
CADS_SKELETON_PLUS_DISPLAY_NAME = "CADS Skeleton Plus"

NUM_SKELETON_CLASSES = 61
NUM_SKELETON_PLUS_CLASSES = 68
