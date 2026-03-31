#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_DIR="${REPO_DIR:-$DEFAULT_REPO_DIR}"
WORK_ROOT="${WORK_ROOT:-/lambda/nfs/spinelab}"
VERSE_ROOT="${VERSE_ROOT:-$WORK_ROOT/data/verse_data}"
VENV_DIR="${VENV_DIR:-$WORK_ROOT/venvs/verse20-nnunet}"
DATASET_ID="${DATASET_ID:-321}"
DATASET_NAME="${DATASET_NAME:-VERSE20Vertebrae}"
PLAN_NAME="${PLAN_NAME:-nnUNetResEncL_24G}"
TRAINER_NAME="${TRAINER_NAME:-nnUNetTrainer}"
NNUNET_CONFIGURATION="${NNUNET_CONFIGURATION:-3d_fullres}"
GPU_MEMORY_TARGET_GB="${GPU_MEMORY_TARGET_GB:-24}"
FOLD="${FOLD:-0}"
FINGERPRINT_PROCESSES="${FINGERPRINT_PROCESSES:-8}"
PREPROCESS_PROCESSES="${PREPROCESS_PROCESSES:-4}"
CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

nnUNet_raw="${nnUNet_raw:-$WORK_ROOT/nnunet/raw}"
nnUNet_preprocessed="${nnUNet_preprocessed:-$WORK_ROOT/nnunet/preprocessed}"
nnUNet_results="${nnUNet_results:-$WORK_ROOT/nnunet/results}"

nnunet_verse20_ensure_workdirs() {
  mkdir -p "$WORK_ROOT/venvs" "$nnUNet_raw" "$nnUNet_preprocessed" "$nnUNet_results"
}

nnunet_verse20_export_paths() {
  export nnUNet_raw
  export nnUNet_preprocessed
  export nnUNet_results
}

nnunet_verse20_bootstrap_environment() {
  nnunet_verse20_ensure_workdirs
  python3 -m venv --system-site-packages "$VENV_DIR"
  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"
  python -m pip install --upgrade pip
  python -m pip install -r "$REPO_DIR/envs/nnunet_verse20_requirements.txt"
  nnunet_verse20_export_paths
}

nnunet_verse20_activate_environment() {
  if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
    echo "Expected verse20 training environment at $VENV_DIR" >&2
    echo "Run tools/nnunet_verse20_lambda_train.sh first to bootstrap it." >&2
    exit 1
  fi
  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"
  nnunet_verse20_export_paths
}

nnunet_verse20_dataset_dir() {
  printf '%s\n' "$nnUNet_raw/Dataset$(printf '%03d' "$DATASET_ID")_${DATASET_NAME}"
}

nnunet_verse20_preprocessed_dataset_dir() {
  printf '%s\n' "$nnUNet_preprocessed/Dataset$(printf '%03d' "$DATASET_ID")_${DATASET_NAME}"
}

nnunet_verse20_plan_json() {
  printf '%s\n' "$(nnunet_verse20_preprocessed_dataset_dir)/${PLAN_NAME}.json"
}

nnunet_verse20_configuration_data_dir() {
  local plan_json
  plan_json="$(nnunet_verse20_plan_json)"
  python - "$plan_json" "$NNUNET_CONFIGURATION" <<'PY'
import json
import sys
from pathlib import Path

plan_path = Path(sys.argv[1])
configuration_name = sys.argv[2]
payload = json.loads(plan_path.read_text(encoding="utf-8"))
data_identifier = payload["configurations"][configuration_name]["data_identifier"]
print(plan_path.parent / data_identifier)
PY
}

nnunet_verse20_results_root() {
  printf '%s\n' "$nnUNet_results/Dataset$(printf '%03d' "$DATASET_ID")_${DATASET_NAME}/${TRAINER_NAME}__${PLAN_NAME}__${NNUNET_CONFIGURATION}"
}

nnunet_verse20_fold_dir() {
  local fold="${1:-$FOLD}"
  printf '%s\n' "$(nnunet_verse20_results_root)/fold_${fold}"
}

nnunet_verse20_require_training_dataset() {
  local dataset_dir
  dataset_dir="$(nnunet_verse20_dataset_dir)"
  if [[ ! -d "$dataset_dir/imagesTr" || ! -d "$dataset_dir/labelsTr" ]]; then
    echo "Missing prepared nnU-Net dataset at $dataset_dir" >&2
    echo "Run tools/nnunet_verse20_lambda_train.sh first to prepare Dataset${DATASET_ID}." >&2
    exit 1
  fi
}

nnunet_verse20_require_training_plan() {
  local plan_json
  local configuration_dir
  plan_json="$(nnunet_verse20_plan_json)"
  if [[ ! -f "$plan_json" ]]; then
    echo "Missing nnU-Net plans JSON at $plan_json" >&2
    echo "Run tools/nnunet_verse20_lambda_train.sh first to finish planning and preprocessing." >&2
    exit 1
  fi

  configuration_dir="$(nnunet_verse20_configuration_data_dir)"
  if [[ ! -d "$configuration_dir" ]]; then
    echo "Missing nnU-Net preprocessed configuration directory at $configuration_dir" >&2
    echo "Run tools/nnunet_verse20_lambda_train.sh first to finish preprocessing." >&2
    exit 1
  fi

  if ! find "$configuration_dir" -maxdepth 1 -type f \( -name '*.npz' -o -name '*.npy' -o -name '*.pkl' \) -print -quit | grep -q .; then
    echo "No preprocessed case files found in $configuration_dir" >&2
    echo "Run tools/nnunet_verse20_lambda_train.sh first to finish preprocessing." >&2
    exit 1
  fi
}

nnunet_verse20_require_training_ready() {
  nnunet_verse20_require_training_dataset
  nnunet_verse20_require_training_plan
}

nnunet_verse20_assert_fold_dir_unused() {
  local fold_dir
  fold_dir="$(nnunet_verse20_fold_dir "${1:-$FOLD}")"
  if [[ -d "$fold_dir" ]] && find "$fold_dir" -mindepth 1 -print -quit | grep -q .; then
    echo "Refusing to reuse non-empty fold directory: $fold_dir" >&2
    exit 1
  fi
}
