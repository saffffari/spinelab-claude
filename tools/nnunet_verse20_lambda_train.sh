#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/nnunet_verse20_lambda_common.sh"

nnunet_verse20_bootstrap_environment

python "$REPO_DIR/tools/prepare_verse20_nnunet.py" \
  --verse-root "$VERSE_ROOT" \
  --output-root "$nnUNet_raw" \
  --dataset-id "$DATASET_ID" \
  --dataset-name "$DATASET_NAME" \
  --link-mode symlink \
  --skip-eval-exports

nnUNetv2_extract_fingerprint \
  -d "$DATASET_ID" \
  -np "$FINGERPRINT_PROCESSES" \
  --verify_dataset_integrity

nnUNetv2_plan_experiment \
  -d "$DATASET_ID" \
  -pl ResEncUNetPlanner \
  -gpu_memory_target "$GPU_MEMORY_TARGET_GB" \
  -overwrite_plans_name "$PLAN_NAME"

nnUNetv2_preprocess \
  -d "$DATASET_ID" \
  -plans_name "$PLAN_NAME" \
  -c "$NNUNET_CONFIGURATION" \
  -np "$PREPROCESS_PROCESSES"

CUDA_VISIBLE_DEVICES="$CUDA_VISIBLE_DEVICES" nnUNetv2_train \
  "$DATASET_ID" \
  "$NNUNET_CONFIGURATION" \
  "$FOLD" \
  -tr "$TRAINER_NAME" \
  -p "$PLAN_NAME" \
  -device cuda
