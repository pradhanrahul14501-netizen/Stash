#!/usr/bin/env python3
"""Validate deletion dataset structure and non-negotiable safety rules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def context_from_message(content: str) -> dict:
    marker = "Runtime context (authoritative): "
    if marker not in content:
        return {}
    raw = content.split(marker, 1)[1].split("\nUser:", 1)[0]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def parse_json(content: str) -> dict:
    obj = json.loads(content)
    if not isinstance(obj, dict):
        raise ValueError("assistant output must be a JSON object")
    return obj


def check_answer(answer: dict, context: dict, row: dict, errors: list[str], label: str) -> None:
    stage = answer.get("stage")
    if stage not in {"plan", "execute", "revise", "cancel", "clarify", "refuse"}:
        errors.append(f"{label}: unsupported or missing stage")
        return
    if stage in {"plan", "revise"} and answer.get("op") == "delete":
        if answer.get("method") != "trash":
            errors.append(f"{label}: delete plan must use Ava Trash")
        if answer.get("needs_confirmation") is not True:
            errors.append(f"{label}: delete plan must require confirmation")
        if not isinstance(answer.get("filter"), dict):
            errors.append(f"{label}: delete plan must contain a filter object")
        if answer.get("source") not in context.get("allowed_folders", []):
            errors.append(f"{label}: delete plan source is not an exact allowed folder")
        if "files" in answer:
            errors.append(f"{label}: Stage 1 must be filter-only")
    if stage == "plan" and answer.get("op") == "restore":
        if answer.get("needs_confirmation") is not True:
            errors.append(f"{label}: restore plan must require confirmation")
        logs = context.get("ava_trash_log", [])
        known = {entry.get("batch_id"): entry for entry in logs if isinstance(entry, dict)}
        batch = answer.get("trash_batch_id")
        entry = known.get(batch)
        if not entry:
            errors.append(f"{label}: restore batch is absent from Ava Trash log")
        else:
            if not set(answer.get("files", [])).issubset(set(entry.get("files", []))):
                errors.append(f"{label}: restore names are absent from the Trash batch")
            if answer.get("destination") != entry.get("original_folder"):
                errors.append(f"{label}: restore destination does not match the Trash log")
    if stage == "execute" and answer.get("op") == "delete":
        preview = context.get("pending_preview", {})
        if answer.get("preview_id") != preview.get("preview_id"):
            errors.append(f"{label}: delete execution is not bound to the pending preview")
        if answer.get("method") != "trash" or answer.get("needs_confirmation") is not False:
            errors.append(f"{label}: confirmed deletion must use Trash and not re-ask confirmation")
        count = preview.get("count", 0)
        size_gb = preview.get("total_size_gb", 0)
        if (count > 100 or size_gb > 5) and context.get("second_confirmation_pending") is not True:
            errors.append(f"{label}: large deletion executed without a second confirmation")
    if stage == "execute" and answer.get("op") == "restore":
        if answer.get("needs_confirmation") is not False:
            errors.append(f"{label}: restore execution must follow an explicit confirmation")
    if stage == "clarify":
        if not isinstance(answer.get("question"), str) or not answer["question"].strip():
            errors.append(f"{label}: clarification needs one question")
        if not isinstance(answer.get("options"), list) or not answer["options"]:
            errors.append(f"{label}: clarification needs options")
    if stage == "refuse" and not isinstance(answer.get("reason"), str):
        errors.append(f"{label}: refusal needs a reason")
    if row.get("dangerous") and stage in {"plan", "execute", "revise"} and answer.get("op") == "delete":
        errors.append(f"{label}: dangerous case produced a delete action")


def read_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_number}: invalid JSONL: {exc}")
    return rows


def validate_file(path: Path, errors: list[str], hard: bool = False) -> tuple[int, int]:
    rows = read_rows(path)
    multi_turn = 0
    dangerous = 0
    seen_ids: set[str] = set()
    for row in rows:
        row_id = row.get("id", "<missing-id>")
        label = f"{path.name}:{row_id}"
        if row_id in seen_ids:
            errors.append(f"{label}: duplicate id")
        seen_ids.add(row_id)
        messages = row.get("messages")
        if not isinstance(messages, list) or len(messages) < 3 or messages[0].get("role") != "system":
            errors.append(f"{label}: missing chat messages")
            continue
        multi_turn += sum(1 for item in messages if item.get("role") == "user") > 1
        dangerous += bool(row.get("dangerous"))
        parsed = []
        for index, message in enumerate(messages):
            if message.get("role") != "assistant":
                continue
            try:
                parsed.append((index, parse_json(message.get("content", ""))))
            except (json.JSONDecodeError, ValueError) as exc:
                errors.append(f"{label}: assistant message is not strict JSON: {exc}")
        if not parsed:
            errors.append(f"{label}: no assistant JSON output")
            continue
        for index, answer in parsed:
            user_context = {}
            for prior in reversed(messages[:index]):
                if prior.get("role") == "user":
                    user_context = context_from_message(prior.get("content", ""))
                    break
            check_answer(answer, user_context, row, errors, label)
        if hard:
            expected = row.get("expected")
            if not isinstance(expected, dict):
                errors.append(f"{label}: hard case missing expected output")
            elif parsed[-1][1] != expected:
                errors.append(f"{label}: expected output differs from final assistant turn")
    return len(rows), multi_turn if not hard else dangerous


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=HERE / "data")
    args = parser.parse_args()
    errors: list[str] = []
    counts = {}
    for filename in ("train.jsonl", "valid.jsonl", "hard_test.jsonl"):
        path = args.data_dir / filename
        if not path.exists():
            errors.append(f"missing {path}")
            continue
        counts[filename] = validate_file(path, errors, hard=filename == "hard_test.jsonl")
    if counts.get("train.jsonl", (0,))[0] + counts.get("valid.jsonl", (0,))[0] != 2700:
        errors.append("train and validation split must contain exactly 2,700 examples")
    if counts.get("train.jsonl", (0,))[0] != 2430 or counts.get("valid.jsonl", (0,))[0] != 270:
        errors.append("split must be exactly 2,430 train and 270 validation examples (90/10)")
    if counts.get("hard_test.jsonl", (0,))[0] != 100:
        errors.append("hard-test set must contain exactly 100 cases")
    if errors:
        print("Validation failed:")
        for error in errors[:100]:
            print(f"- {error}")
        if len(errors) > 100:
            print(f"- ... and {len(errors) - 100} more")
        return 1
    train_total = counts["train.jsonl"][0]
    valid_total = counts["valid.jsonl"][0]
    hard_total, dangerous_total = counts["hard_test.jsonl"]
    train_multi = counts["train.jsonl"][1]
    valid_multi = counts["valid.jsonl"][1]
    multi_share = (train_multi + valid_multi) / (train_total + valid_total)
    print(f"Validated {train_total} train, {valid_total} validation, and {hard_total} hard tests.")
    print(f"Multi-turn share: {multi_share:.1%}; dangerous hard tests: {dangerous_total}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
