#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/nnunet_verse20_lambda_common.sh"

GATE_FOLD="${GATE_FOLD:-0}"
NEXT_FOLD="${NEXT_FOLD:-1}"
MIN_FOREGROUND_DICE="${MIN_FOREGROUND_DICE:-0.70}"
NEXT_FOLD_SESSION_NAME="${NEXT_FOLD_SESSION_NAME:-verse20-fold${NEXT_FOLD}}"

nnunet_verse20_activate_environment
nnunet_verse20_require_training_ready

if pgrep -f "nnUNetv2_train ${DATASET_ID} ${NNUNET_CONFIGURATION} ${GATE_FOLD}" >/dev/null; then
  echo "Fold ${GATE_FOLD} training is still running; aborting post-fold automation." >&2
  exit 1
fi

if tmux has-session -t "$NEXT_FOLD_SESSION_NAME" 2>/dev/null; then
  echo "tmux session $NEXT_FOLD_SESSION_NAME already exists; refusing to start fold ${NEXT_FOLD}." >&2
  exit 1
fi

gate_fold_dir="$(nnunet_verse20_fold_dir "$GATE_FOLD")"
next_fold_dir="$(nnunet_verse20_fold_dir "$NEXT_FOLD")"
post_fold_output_dir="$gate_fold_dir/post_fold"

if [[ ! -d "$gate_fold_dir" ]]; then
  echo "Missing fold directory for fold ${GATE_FOLD}: $gate_fold_dir" >&2
  exit 1
fi

nnunet_verse20_assert_fold_dir_unused "$NEXT_FOLD"

CUDA_VISIBLE_DEVICES="$CUDA_VISIBLE_DEVICES" nnUNetv2_train \
  "$DATASET_ID" \
  "$NNUNET_CONFIGURATION" \
  "$GATE_FOLD" \
  -tr "$TRAINER_NAME" \
  -p "$PLAN_NAME" \
  --val \
  --val_best \
  -device cuda

python "$REPO_DIR/tools/nnunet_verse20_post_fold_gate.py" \
  --fold-dir "$gate_fold_dir" \
  --output-dir "$post_fold_output_dir" \
  --minimum-foreground-dice "$MIN_FOREGROUND_DICE"

printf -v launch_command \
  "cd %q && REPO_DIR=%q WORK_ROOT=%q VERSE_ROOT=%q VENV_DIR=%q DATASET_ID=%q DATASET_NAME=%q PLAN_NAME=%q TRAINER_NAME=%q NNUNET_CONFIGURATION=%q CUDA_VISIBLE_DEVICES=%q FOLD=%q bash tools/nnunet_verse20_lambda_train_fold.sh" \
  "$REPO_DIR" \
  "$REPO_DIR" \
  "$WORK_ROOT" \
  "$VERSE_ROOT" \
  "$VENV_DIR" \
  "$DATASET_ID" \
  "$DATASET_NAME" \
  "$PLAN_NAME" \
  "$TRAINER_NAME" \
  "$NNUNET_CONFIGURATION" \
  "$CUDA_VISIBLE_DEVICES" \
  "$NEXT_FOLD"
tmux new-session -d -s "$NEXT_FOLD_SESSION_NAME" "$launch_command"

python "$REPO_DIR/tools/nnunet_verse20_post_fold_gate.py" \
  --fold-dir "$gate_fold_dir" \
  --output-dir "$post_fold_output_dir" \
  --minimum-foreground-dice "$MIN_FOREGROUND_DICE" \
  --launch-fold "$NEXT_FOLD" \
  --launch-session "$NEXT_FOLD_SESSION_NAME" \
  --launch-fold-dir "$next_fold_dir"

echo "Fold ${GATE_FOLD} gate passed."
echo "Gate summary: $post_fold_output_dir/fold_${GATE_FOLD}_gate_summary.json"
echo "Gate summary (Markdown): $post_fold_output_dir/fold_${GATE_FOLD}_gate_summary.md"
echo "Started fold ${NEXT_FOLD} in tmux session: $NEXT_FOLD_SESSION_NAME"
