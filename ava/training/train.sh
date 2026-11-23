#!/bin/bash
set -euo pipefail

TRAINING_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$TRAINING_DIR"
export HF_HOME="$TRAINING_DIR/.hf-cache"
PROJECT_DIR="$(cd "$TRAINING_DIR/../.." && pwd)"
if [[ -x "$PROJECT_DIR/.venv-mlx-ava/bin/mlx_lm.lora" ]]; then
  PATH="$PROJECT_DIR/.venv-mlx-ava/bin:$PATH"
  export PATH
fi

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "This MLX training setup needs an Apple-silicon Mac."
  exit 1
fi
if ! command -v mlx_lm.lora >/dev/null 2>&1; then
  echo "Activate the MLX virtual environment first and install mlx-lm[train]."
  exit 1
fi
if ! python -c 'import mlx.core as mx; mx.default_device()' >/dev/null 2>&1; then
  echo "MLX cannot access a Metal device in this shell. Run this script from regular macOS Terminal, not a sandboxed or remote shell."
  exit 1
fi

BASE_MODEL="$(printenv AVA_BASE_MODEL || true)"
if [[ -z "$BASE_MODEL" ]]; then
  BASE_MODEL="mlx-community/Qwen3-8B-4bit"
fi
ADAPTER_DIR="$TRAINING_DIR/outputs/ava-qwen3-8b-4bit-adapter"
FUSED_DIR="$TRAINING_DIR/outputs/ava-qwen3-8b-4bit-fused"

python generate_dataset.py
python validate_plan.py --dataset data/train.jsonl
python validate_plan.py --dataset data/valid.jsonl
python validate_plan.py --dataset data/hard_test.jsonl

mlx_lm.lora \
  --config config.yaml \
  --model "$BASE_MODEL" \
  --data "$TRAINING_DIR/data" \
  --adapter-path "$ADAPTER_DIR" \
  --train

python evaluate.py \
  --dataset data/hard_test.jsonl \
  --model "$BASE_MODEL" \
  --adapter-path "$ADAPTER_DIR" \
  --save-predictions outputs/hard_test_predictions.jsonl \
  --report outputs/hard_test_metrics.json

mlx_lm.fuse \
  --model "$BASE_MODEL" \
  --adapter-path "$ADAPTER_DIR" \
  --save-path "$FUSED_DIR"

echo "Done. Adapter: $ADAPTER_DIR"
echo "Fused MLX model: $FUSED_DIR"
