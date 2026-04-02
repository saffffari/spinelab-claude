# CADS Composite Segmentation Bundles

## Goal

Add two new selectable segmentation models to the SpineLab GUI:

1. **"CADS Skeleton"** — Full skeleton (61 classes: vertebrae, ribs, appendicular bones, sacrum, sternum, spinal canal)
2. **"CADS Skeleton Plus"** — Skeleton + associated soft tissue (69 classes: above + aorta, IVC, spinal cord, paraspinal muscles)

Both use pretrained CADS nnU-Net models (ResEnc L, `nnUNetTrainerNoMirroring`, `fold_all`).

## Architecture Decision: Composite Driver

The CADS models are split across multiple nnU-Net task models (552, 554, 555, 556, etc.). A single inference requires running 4-6 models sequentially and merging their outputs.

**Approach:** Create a `CADSCompositeSegmentationDriver` that:
- Implements the same `SegmentationModelDriver` protocol
- Stores a list of sub-model specs (task ID → runtime model config + label cherry-pick map)
- Delegates each sub-model inference to the existing `NNUNetV2SegmentationDriver`
- Merges per-task predictions into a single unified label map
- Returns a single `PredictionBatchResult` as if it were one model

This keeps the pipeline stage and GUI completely unchanged — the composite driver is just another driver.

## CADS Model Details (from inspecting zips)

All CADS models share:
- **Trainer**: `nnUNetTrainerNoMirroring`
- **Plan**: `nnUNetResEncUNetLPlans`
- **Config**: `3d_fullres`
- **Fold**: `fold_all`
- **Checkpoint**: `checkpoint_final.pth`
- **Environment**: Same `spinelab-nnunet-verse20-win` conda env (nnU-Net v2)

## Unified Label Map

### CADS Skeleton (61 classes)

| Output Label | Structure | Source Task | Source Index |
|---|---|---|---|
| 1-24 | vertebra_C1 through vertebra_L5 | 552 | 24→1 (reversed) |
| 25-26 | humerus_L, humerus_R | 554 | 1-2 |
| 27-28 | scapula_L, scapula_R | 554 | 3-4 |
| 29-30 | clavicle_L, clavicle_R | 554 | 5-6 |
| 31-32 | femur_L, femur_R | 554 | 7-8 |
| 33-34 | hip_L, hip_R | 554 | 9-10 |
| 35 | sacrum | 554 | 11 |
| 36-47 | rib_1_L through rib_12_L | 555 | 1-12 |
| 48-59 | rib_1_R through rib_12_R | 555 | 13-24 |
| 60 | sternum | 556 | 11 |
| 61 | spinal_canal | 556 | 1 |

### CADS Skeleton Plus (69 classes = 61 + 8)

Everything above, plus:

| Output Label | Structure | Source Task | Source Index |
|---|---|---|---|
| 62 | aorta | 551 | 7 |
| 63 | inferior_vena_cava | 551 | 8 |
| 64-65 | deep_muscle_of_back_L/R | 554 | 18-19 |
| 66-67 | iliopsoas_muscle_L/R | 554 | 20-21 |
| 68-69 | psoas_major_muscle_R/L | 556 | 12-13 |

*Note: spinal_cord from task 559 (source index 10) could be added as label 70, but task 559's "bones" label (index 5) is a coarse whole-skeleton mask that may conflict with per-bone labels. Need to verify whether cherry-picking just spinal_cord from 559 works without artifacts.*

## Bundle Installation Layout

```
{data_root}/raw_test_data/models/segmentation/
  cads-skeleton/
    bundle.json                    # Composite bundle manifest
    nnunet_results/
      Dataset552_Totalseg252/
        nnUNetTrainerNoMirroring__nnUNetResEncUNetLPlans__3d_fullres/
          fold_all/checkpoint_final.pth
          plans.json, dataset.json, etc.
      Dataset554_Totalseg254/
        ...same structure...
      Dataset555_Totalseg255/
        ...
      Dataset556_GC256/
        ...
    nnunet_raw/        (empty, required by nnU-Net)
    nnunet_preprocessed/  (empty, required by nnU-Net)
  cads-skeleton-plus/
    bundle.json
    nnunet_results/
      ...same as above plus Dataset551 and Dataset559...
    nnunet_raw/
    nnunet_preprocessed/
```

## bundle.json Schema Extension

The composite bundle needs a new field `sub_models` listing the task models to run:

```json
{
  "bundle_id": "cads-skeleton",
  "display_name": "CADS Skeleton",
  "family": "cads-composite",
  "driver_id": "cads-composite",
  "environment_id": "nnunet-verse20-win",
  "modality": "ct",
  "label_mapping": { "vertebra_C1": 24, "vertebra_C2": 23, ..., "spinal_canal": 61 },
  "sub_models": [
    {
      "task_id": "552",
      "dataset_name": "Dataset552_Totalseg252",
      "trainer_name": "nnUNetTrainerNoMirroring",
      "plan_name": "nnUNetResEncUNetLPlans",
      "configuration": "3d_fullres",
      "fold": "all",
      "checkpoint_name": "checkpoint_final.pth",
      "label_cherry_pick": {
        "1": 24, "2": 23, "3": 22, "4": 21, "5": 20, "6": 19,
        "7": 18, "8": 17, "9": 16, "10": 15, "11": 14, "12": 13,
        "13": 12, "14": 11, "15": 10, "16": 9, "17": 8, "18": 7,
        "19": 6, "20": 5, "21": 4, "22": 3, "23": 2, "24": 1
      }
    },
    {
      "task_id": "554",
      "dataset_name": "Dataset554_Totalseg254",
      "label_cherry_pick": {
        "1": 25, "2": 26, "3": 27, "4": 28, "5": 29, "6": 30,
        "7": 31, "8": 32, "9": 33, "10": 34, "11": 35
      }
    }
  ],
  "merge_priority": "first-writer-wins",
  "active_checkpoint_id": "composite",
  "checkpoints": [{ "checkpoint_id": "composite", "fold": "all", "checkpoint_name": "checkpoint_final.pth", "relative_path": "nnunet_results/Dataset552_Totalseg252/nnUNetTrainerNoMirroring__nnUNetResEncUNetLPlans__3d_fullres/fold_all/checkpoint_final.pth" }],
  "runtime_root": "nnunet_results"
}
```

## Implementation Steps

### Step 1: Define CADS label maps (`src/spinelab/segmentation/cads.py`)

New module with:
- `CADS_SKELETON_TASKS` — list of (task_id, dataset_name, label_cherry_pick) for the 4 skeleton tasks
- `CADS_SKELETON_PLUS_TASKS` — same for the 6-task extended set
- `CADS_UNIFIED_LABEL_MAP` — full structure_name → output_label mapping
- `CADS_SKELETON_LABEL_MAPPING` / `CADS_SKELETON_PLUS_LABEL_MAPPING` — the bundle label_mapping dicts

### Step 2: Create composite driver (`src/spinelab/segmentation/drivers.py`)

Add `CADSCompositeSegmentationDriver`:
- Reads `sub_models` from a new field on `SegmentationRuntimeModel` (or from the bundle manifest directly)
- For each sub-model: constructs a temporary `SegmentationRuntimeModel` and calls `NNUNetV2SegmentationDriver.predict()`
- After all sub-models complete: loads each per-task prediction NIfTI, cherry-picks labels per the mapping, merges into a single output array (first-writer-wins for overlaps)
- Saves merged prediction, returns `PredictionBatchResult`

### Step 3: Register the driver (`src/spinelab/segmentation/drivers.py`)

Add `"cads-composite"` to `resolve_segmentation_driver()`.

### Step 4: Update bundle loading to handle composite bundles (`src/spinelab/segmentation/bundles.py`)

- Add `sub_models` field to `InstalledSegmentationBundle`
- Pass it through to `SegmentationRuntimeModel` (new optional field)
- Add CADS entries to `KNOWN_SEGMENTATION_BACKENDS`

### Step 5: Create install script (`tools/install_cads_bundles.py`)

Script that:
1. Unzips the CADS model zips into the bundle directory structure
2. Writes the composite `bundle.json` with all sub-model specs
3. Optionally activates the bundle

### Step 6: Verify downstream compatibility

- `_build_vertebrae_payload()` already skips non-vertebra keys via `standard_structure_for_level()` returning None → safe
- `_compute_label_statistics()` iterates all keys in label_mapping → all structures get stats computed → safe
- Mesh/point cloud stages use per-vertebra labels → they'll process vertebrae and ignore non-spine labels → safe
- The raw segmentation NIfTI contains ALL labels for visualization

### Step 7: Add to GUI

- Add `KnownSegmentationBackend` entries for `"cads-skeleton"` and `"cads-skeleton-plus"`
- They'll appear automatically in the backends dialog

## Files to Create

1. `src/spinelab/segmentation/cads.py` — CADS task definitions and label maps
2. `tools/install_cads_bundles.py` — Bundle installation from downloaded zips

## Files to Modify

1. `src/spinelab/segmentation/drivers.py` — Add `CADSCompositeSegmentationDriver` + register it
2. `src/spinelab/segmentation/bundles.py` — Add `sub_models` to data classes, add known backends
3. `src/spinelab/segmentation/__init__.py` — Export new symbols if needed

## Memory / Performance

- RTX 4090 24GB: Each CADS sub-model runs sequentially, one at a time. ResEnc L at full res needs ~8-12GB VRAM. No issue.
- 4 models for skeleton = ~4x inference time vs single model. Unavoidable with separate task models.
- 6 models for skeleton-plus = ~6x. User should be aware this is slower.
- Consider DRAFT precision (step_size=0.7, no TTA) for faster composite runs.
