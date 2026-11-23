#!/bin/bash
set -euo pipefail

TRAINING_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$TRAINING_DIR/../.." && pwd)"
cd "$TRAINING_DIR"

VENV="$PROJECT_DIR/.venv-mlx-ava"
if [[ -x "$VENV/bin/python" && -x "$VENV/bin/mlx_lm.lora" ]]; then
  PYTHON="$VENV/bin/python"
  MLX_LORA="$VENV/bin/mlx_lm.lora"
  MLX_FUSE="$VENV/bin/mlx_lm.fuse"
else
  PYTHON="$(command -v python3 || true)"
  MLX_LORA="$(command -v mlx_lm.lora || true)"
  MLX_FUSE="$(command -v mlx_lm.fuse || true)"
fi

if [[ -z "$PYTHON" || -z "$MLX_LORA" || -z "$MLX_FUSE" ]]; then
  echo "MLX-LM is missing. Install mlx-lm[train] in .venv-mlx-ava first."
  exit 1
fi
if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "This training run needs an Apple-silicon Mac."
  exit 1
fi
if ! "$PYTHON" -c 'import mlx.core as mx; mx.default_device()' >/dev/null 2>&1; then
  echo "No Metal device is available in this shell. Run this script from regular macOS Terminal."
  exit 1
fi

ADAPTER_DIR="$TRAINING_DIR/outputs/ava-qwen3-8b-4bit-deletion-adapter"
FUSED_DIR="$TRAINING_DIR/outputs/ava-qwen3-8b-4bit-deletion-fused"
if [[ -e "$ADAPTER_DIR" || -e "$FUSED_DIR" ]]; then
  echo "Deletion training outputs already exist. Rename or archive them before starting a fresh run."
  exit 1
fi

# Reuse the already downloaded model cache from the earlier Ava MLX setup.
export HF_HOME="$PROJECT_DIR/ava/training/.hf-cache"

"$PYTHON" generate_dataset.py
"$PYTHON" validate_dataset.py

"$MLX_LORA" \
  --config "$TRAINING_DIR/config.yaml" \
  --model mlx-community/Qwen3-8B-4bit \
  --data "$TRAINING_DIR/data" \
  --adapter-path "$ADAPTER_DIR" \
  --train

"$PYTHON" evaluate.py \
  --dataset "$TRAINING_DIR/data/hard_test.jsonl" \
  --model mlx-community/Qwen3-8B-4bit \
  --adapter-path "$ADAPTER_DIR" \
  --save-predictions "$TRAINING_DIR/outputs/hard_test_predictions.jsonl" \
  --report "$TRAINING_DIR/outputs/hard_test_metrics.json"

"$MLX_FUSE" \
  --model mlx-community/Qwen3-8B-4bit \
  --adapter-path "$ADAPTER_DIR" \
  --save-path "$FUSED_DIR"

echo "Training and hard-test evaluation passed."
echo "Adapter: $ADAPTER_DIR"
echo "Fused model: $FUSED_DIR"
