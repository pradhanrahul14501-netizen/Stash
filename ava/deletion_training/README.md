# Ava safe bulk-deletion fine-tuning

This is an isolated deletion-only training pipeline. It does not overwrite the general Ava dataset or adapter under ava/training/, and it does not change the live Copy Maker app.

## Data

generate_dataset.py creates:

- data/train.jsonl: 2,430 conversations
- data/valid.jsonl: 270 conversations, split 90/10 from the 2,700-example generated set
- data/hard_test.jsonl: 100 held-out cases, weighted toward protected paths, permanent-delete requests, global wildcards, saved-rule conflicts, filename injection, and large previews

About 30% of train/validation conversations are multi-turn. Contexts vary current local date, allowed and protected folders, file statistics, sample names, and saved rules. Stage 1 only creates a filter plan and requires confirmation. Approved stage-2 deletes bind to a preview ID and route to Ava Trash. Large previews require a second confirmation. Restore examples use only entries in the supplied Ava Trash log.

The examples are synthetic. Add reviewed, anonymized real failure cases only after checking that they do not leak private filenames or paths.

## Train

Wait for any other MLX training process to finish before starting this one. The deletion adapter and fused model use separate output folders; the base Qwen model cache is reused from the existing Ava training cache.

From regular macOS Terminal after the other training run has ended:

~~~
cd ~/copy-maker
bash ava/deletion_training/train.sh
~~~

The run uses the cached base mlx-community/Qwen3-8B-4bit, LoRA rank 16, 8 adapted layers, batch size 1, gradient accumulation 8, 1,000 iterations, learning rate 1e-5, 2,048-token sequences, and gradient checkpointing. It validates the data, trains into a new adapter folder, evaluates the 100 hard cases, and fuses the adapter only if the dangerous false-delete rate is zero.

The hard-test inference is separate from the training loop and can take additional time. Do not connect the adapter to the live file executor until the executor independently enforces folder allowlists, protected-folder checks, immutable preview IDs, the large-volume second confirmation, Ava Trash, 30-day restore, and an action log.

## Evaluation

evaluate.py reports strict JSON validity, schema validity, delete-confirmation compliance, exact filter accuracy, dangerous-case refusal accuracy, and dangerous false-delete rate. The evaluation command exits with failure if any dangerous case emits a delete action.

To score saved model responses without loading MLX, create a JSONL file with id and output fields and run:

~~~
python3 ava/deletion_training/evaluate.py --predictions path/to/predictions.jsonl
~~~

The validation script checks row counts, JSON, confirmation rules, allowed source folders, preview binding, second confirmation on large deletes, and restore references.
