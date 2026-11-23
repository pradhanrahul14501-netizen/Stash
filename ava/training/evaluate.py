#!/usr/bin/env python3
"""Run Ava's held-out prompts or score a saved prediction JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from validate_plan import validate_plan, _context_from_user


def _read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _predict(model_name: str, adapter_path: str | None, cases: list[dict], max_tokens: int) -> dict[str, str]:
    try:
        from mlx_lm import generate, load
    except ImportError as exc:
        raise SystemExit("Install mlx-lm on Apple silicon first: pip install 'mlx-lm[train]'") from exc
    kwargs = {}
    if adapter_path:
        kwargs["adapter_path"] = adapter_path
    model, tokenizer = load(model_name, **kwargs)
    outputs: dict[str, str] = {}
    for index, row in enumerate(cases, 1):
        messages = row["messages"]
        try:
            prompt = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        outputs[row["id"]] = generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens, verbose=False)
        print(f"Generated {index}/{len(cases)}: {row['id']}")
    return outputs


def _plan_lists(plan: dict, field: str) -> list[Any]:
    if not isinstance(plan, dict):
        return []
    return [action[field] for action in plan.get("actions", []) if isinstance(action, dict) and field in action]


def _date_filters(plan: dict) -> list[tuple[Any, Any]]:
    return [
        (action.get("filter", {}).get("date"), action.get("filter", {}).get("ext"))
        for action in plan.get("actions", [])
        if isinstance(action, dict) and isinstance(action.get("filter"), dict) and "date" in action["filter"]
    ]


def _score(cases: list[dict], outputs: dict[str, str]) -> dict:
    valid_json = 0
    op_total = op_correct = 0
    destination_total = destination_correct = 0
    date_total = date_correct = 0
    confirmation_total = confirmation_correct = 0
    clarify_total = clarify_correct = 0
    refusal_total = refusal_correct = 0
    details = []
    for row in cases:
        expected = row["expected"]
        expected_ops = _plan_lists(expected, "op")
        expected_dest = _plan_lists(expected, "destination")
        expected_dates = _date_filters(expected)
        requires_confirmation = any(action.get("op") == "delete" for action in expected.get("actions", []))
        expects_clarify = "clarify" in expected
        expects_refusal = "refuse" in expected
        op_total += int(bool(expected_ops))
        destination_total += int(bool(expected_dest))
        date_total += int(bool(expected_dates))
        confirmation_total += int(requires_confirmation)
        clarify_total += int(expects_clarify)
        refusal_total += int(expects_refusal)
        output = outputs.get(row["id"], "")
        predicted = None
        try:
            candidate = json.loads(output)
            user_content = row["messages"][1].get("content", "")
            context = _context_from_user(user_content)
            roots = context.get("allowed_roots", [])
            available = {
                item.get("name")
                for item in context.get("files", [])
                if isinstance(item, dict)
                and isinstance(item.get("name"), str)
                and not item.get("is_hidden", item["name"].startswith("."))
                and not item.get("is_symlink", False)
                and item.get("kind", "file") == "file"
            }
            available.update(name for name in context.get("selected_files", []) if isinstance(name, str) and not name.startswith("."))
            if not validate_plan(candidate, roots, available):
                predicted = candidate
                valid_json += 1
        except (TypeError, json.JSONDecodeError):
            pass
        if predicted is None:
            details.append({
                "id": row["id"],
                "valid": False,
                "operation_correct": False,
                "destination_correct": False if expected_dest else None,
                "date_filter_correct": False if expected_dates else None,
                "delete_confirmation_correct": False if requires_confirmation else None,
                "clarification_correct": False if expects_clarify else None,
                "refusal_correct": False if expects_refusal else None,
                "output": output,
            })
            continue

        predicted_ops = _plan_lists(predicted, "op")
        op_ok = expected_ops == predicted_ops if expected_ops else None
        op_correct += int(bool(op_ok))

        if expected_dest:
            dest_ok = expected_dest == _plan_lists(predicted, "destination")
            destination_correct += int(dest_ok)
        else:
            dest_ok = None

        if expected_dates:
            date_ok = expected_dates == _date_filters(predicted)
            date_correct += int(date_ok)
        else:
            date_ok = None

        if requires_confirmation:
            confirmation_ok = predicted.get("needs_confirmation") is True
            confirmation_correct += int(confirmation_ok)
        else:
            confirmation_ok = None
        if expects_clarify:
            clarify_ok = bool(predicted.get("clarify")) and not predicted.get("actions")
            clarify_correct += int(clarify_ok)
        else:
            clarify_ok = None
        if expects_refusal:
            refusal_ok = bool(predicted.get("refuse")) and not predicted.get("actions")
            refusal_correct += int(refusal_ok)
        else:
            refusal_ok = None
        details.append({
            "id": row["id"],
            "valid": True,
            "operation_correct": op_ok,
            "destination_correct": dest_ok,
            "date_filter_correct": date_ok,
            "delete_confirmation_correct": confirmation_ok,
            "clarification_correct": clarify_ok,
            "refusal_correct": refusal_ok,
        })

    def rate(correct: int, total: int):
        return None if total == 0 else round(correct / total, 4)

    return {
        "cases": len(cases),
        "valid_json_rate": rate(valid_json, len(cases)),
        "correct_operation_rate": rate(op_correct, op_total),
        "correct_destination_rate": rate(destination_correct, destination_total),
        "correct_date_filter_rate": rate(date_correct, date_total),
        "delete_confirmation_rate": rate(confirmation_correct, confirmation_total),
        "clarification_rate": rate(clarify_correct, clarify_total),
        "refusal_rate": rate(refusal_correct, refusal_total),
        "denominators": {
            "all_prompts": len(cases),
            "operation_prompts": op_total,
            "destination_prompts": destination_total,
            "date_filter_prompts": date_total,
            "delete_prompts": confirmation_total,
            "clarification_prompts": clarify_total,
            "refusal_prompts": refusal_total,
        },
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path(__file__).resolve().parent / "data/hard_test.jsonl")
    parser.add_argument("--model", default="mlx-community/Qwen3-8B-4bit")
    parser.add_argument("--adapter-path", default=None)
    parser.add_argument("--predictions", type=Path, help="Score saved JSONL rows with id and output fields instead of loading a model")
    parser.add_argument("--save-predictions", type=Path)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    cases = _read_jsonl(args.dataset)
    if args.predictions:
        outputs = {row["id"]: row["output"] for row in _read_jsonl(args.predictions)}
    else:
        outputs = _predict(args.model, args.adapter_path, cases, args.max_tokens)
    if args.save_predictions:
        args.save_predictions.parent.mkdir(parents=True, exist_ok=True)
        with args.save_predictions.open("w", encoding="utf-8") as stream:
            for row in cases:
                stream.write(json.dumps({"id": row["id"], "output": outputs.get(row["id"], "")}, ensure_ascii=False) + "\n")
    report = _score(cases, outputs)
    output_text = json.dumps(report, ensure_ascii=False, indent=2)
    print(output_text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output_text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
