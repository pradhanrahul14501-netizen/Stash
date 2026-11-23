# Ava file-action fine-tuning

This folder builds a JSON action planner for Ava. The model only proposes a plan; Python remains responsible for validating paths, previewing changes, and asking before deletion.

## What is included

- **data/train.jsonl**: 1,530 generated chat examples, plus any reviewed failure examples you add.
- **data/valid.jsonl**: 170 examples using held-out phrasing patterns.
- **data/hard_test.jsonl**: 30 separate prompts with expected plans; these stay out of training.
- **generate_dataset.py**: reproducibly generates the datasets with varied dates, file metadata, folders, casual wording, typos, and Hinglish.
- **validate_plan.py**: checks the JSON plan structure, operation fields, deletion confirmation, and paths against the runtime allowlist.
- **evaluate.py**: measures strict JSON/schema validity, operation accuracy, destination accuracy, date-filter accuracy, and delete-confirmation accuracy.
- **config.yaml** and **train.sh**: MLX QLoRA setup for Apple silicon.

The examples use synthetic users and files. Add reviewed, anonymized real commands over time; synthetic phrasing alone will not capture every way you ask Ava for help.

## Train on the Mac

From Terminal:

~~~bash
cd ~/copy-maker
python3 -m venv .venv-mlx-ava
source .venv-mlx-ava/bin/activate
python -m pip install --upgrade pip
python -m pip install "mlx-lm[train]"
bash ava/training/train.sh
~~~

The default base is **mlx-community/Qwen3-8B-4bit**, matching the Qwen3 8B family already used by Copy Maker. Because the base is quantized to 4-bit, MLX-LM uses QLoRA. The starter settings are 4 trainable layers, batch size 1, gradient accumulation 8, 600 iterations, learning rate 1e-5, rank 16, scale 32, 2,048-token sequences, and gradient checkpointing. They favor lower memory use on a MacBook; reduce max_seq_length to 1,024 if memory pressure stops training.

To choose another compatible MLX model, set AVA_BASE_MODEL before running train.sh. Keep the same exact base model for training, evaluation, and fusion.

The run caches downloaded model weights in ava/training/.hf-cache, evaluates the adapter on the 30 held-out prompts, saves the per-prompt outputs and metric report under ava/training/outputs/, then fuses the adapter into a separate MLX model folder. Model weights and outputs need several gigabytes of free disk space. It does not overwrite the base model.

If MLX reports that no Metal device is available, run train.sh from the Mac's regular Terminal. Some sandboxed shells can access the Mac filesystem but not its GPU.

## Validate or evaluate separately

~~~bash
cd ~/copy-maker/ava/training
python validate_plan.py --dataset data
python evaluate.py --dataset data/hard_test.jsonl --model mlx-community/Qwen3-8B-4bit --adapter-path outputs/ava-qwen3-8b-4bit-adapter --report outputs/hard_test_metrics.json
~~~

To score saved model outputs without loading MLX, provide a JSONL file whose rows have id and output fields:

~~~bash
python evaluate.py --dataset data/hard_test.jsonl --predictions outputs/my_predictions.jsonl
~~~

valid_json_rate requires strict JSON and a valid schema. Operation and destination rates compare the full action sequence and destination sequence. Date-filter accuracy is reported only for cases whose expected plans contain date filters. Delete-confirmation, clarification, and refusal rates are scored on their applicable prompts.

## Add a failure after reviewing it

1. Save the exact runtime context and command that produced the bad result.
2. Decide the correct plan yourself; do not copy the model's incorrect guess.
3. Add a one-line chat JSONL record to data/reviewed_failures.jsonl, with the same system prompt, the runtime context plus command as the user message, and the corrected plan as the assistant message.
4. Run python generate_dataset.py again. Reviewed failures are added to training only; validation and hard-test sets remain separate.
5. Validate, retrain, and compare the new hard_test_metrics.json with the previous run. Keep a copy of the previous adapter until the new one scores better on the hard cases.

Do not promote any example that encourages guessing a source/destination, includes files outside allowed_roots, or bypasses deletion confirmation.

## Connecting this model to the live app

Copy Maker currently calls Ollama with qwen3:8b and expects Ava's existing intent JSON. This training set teaches the new actions plan format, so the trained adapter is not switched into the live app. Before connecting it, the app needs a reviewed plan-execution layer that rechecks allowed paths and file identity, previews move/copy/rename actions, and requires a separate user confirmation before any delete.

MLX-LM can fuse the adapter into an MLX model with the command used in train.sh. Its built-in GGUF export currently supports Llama, Mistral, and Mixtral model types, so a Qwen3 adapter does not become an Ollama model through that export option. Keep the fused result in MLX until you choose and verify a compatible serving path.
