#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/nnunet_verse20_lambda_common.sh"

if [[ $# -gt 0 ]]; then
  case "$1" in
    --fold)
      if [[ $# -lt 2 ]]; then
        echo "Expected a fold number after --fold" >&2
        exit 1
      fi
      FOLD="$2"
      shift 2
      ;;
    *)
      echo "Usage: $0 [--fold <fold-number>]" >&2
      exit 1
      ;;
  esac
fi

if [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--fold <fold-number>]" >&2
  exit 1
fi

nnunet_verse20_activate_environment
nnunet_verse20_require_training_ready
nnunet_verse20_assert_fold_dir_unused "$FOLD"

CUDA_VISIBLE_DEVICES="$CUDA_VISIBLE_DEVICES" nnUNetv2_train \
  "$DATASET_ID" \
  "$NNUNET_CONFIGURATION" \
  "$FOLD" \
  -tr "$TRAINER_NAME" \
  -p "$PLAN_NAME" \
  -device cuda
