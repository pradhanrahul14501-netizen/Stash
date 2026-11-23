#!/usr/bin/env python3
"""Validate Ava's JSON action-plan schema and safe path boundaries."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

OPS = {"move", "copy", "rename", "delete", "create_folder", "organize"}
TOP_KEYS = {"actions", "needs_confirmation", "clarify", "refuse"}
ACTION_KEYS = {"op", "files", "filter", "source", "destination", "new_name"}
DATE_FILTERS = {"today", "yesterday", "this_week", "last_week"}


def _inside(path_text: str, roots: list[str]) -> bool:
    try:
        path = str(Path(path_text).expanduser().resolve(strict=False))
        for root_text in roots:
            root = str(Path(root_text).expanduser().resolve(strict=False))
            if os.path.commonpath([path, root]) == root:
                return True
    except (OSError, ValueError):
        return False
    return False


def _protected(path_text: str) -> bool:
    path = str(Path(path_text).expanduser())
    normalized = os.path.normpath(path)
    protected_roots = (
        "/System", "/Library", "/etc", "/private/var", "/usr", "/bin",
        "/sbin", "/dev", "/Applications",
    )
    if any(normalized == root or normalized.startswith(root + os.sep) for root in protected_roots):
        return True
    return bool(re.search(r"(^|/)Library/Keychains(?:/|$)", normalized))


def validate_plan(plan: object, allowed_roots: list[str] | None = None, available_files: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    roots = allowed_roots or []
    if not isinstance(plan, dict):
        return ["plan must be a JSON object"]
    extra = set(plan) - TOP_KEYS
    missing = {"actions", "needs_confirmation"} - set(plan)
    if extra:
        errors.append(f"unexpected top-level key(s): {', '.join(sorted(extra))}")
    if missing:
        errors.append(f"missing top-level key(s): {', '.join(sorted(missing))}")
    actions = plan.get("actions")
    if not isinstance(actions, list):
        return errors + ["actions must be an array"]
    if type(plan.get("needs_confirmation")) is not bool:
        errors.append("needs_confirmation must be true or false")
    if "clarify" in plan and (not isinstance(plan["clarify"], str) or not plan["clarify"].strip()):
        errors.append("clarify must be a non-empty string")
    if "refuse" in plan and (not isinstance(plan["refuse"], str) or not plan["refuse"].strip()):
        errors.append("refuse must be a non-empty string")
    if "clarify" in plan and "refuse" in plan:
        errors.append("clarify and refuse cannot both be present")
    if ("clarify" in plan or "refuse" in plan) and actions:
        errors.append("clarification/refusal plans must have an empty actions array")

    has_delete = False
    for i, action in enumerate(actions):
        where = f"actions[{i}]"
        if not isinstance(action, dict):
            errors.append(f"{where} must be an object")
            continue
        unknown = set(action) - ACTION_KEYS
        if unknown:
            errors.append(f"{where} has unexpected key(s): {', '.join(sorted(unknown))}")
        op = action.get("op")
        if op not in OPS:
            errors.append(f"{where}.op must be one of {', '.join(sorted(OPS))}")
            continue
        has_delete = has_delete or op == "delete"
        files = action.get("files")
        filt = action.get("filter")
        if files is not None and filt is not None:
            errors.append(f"{where} must use files or filter, not both")
        if files is not None:
            if not isinstance(files, list) or not files:
                errors.append(f"{where}.files must be a non-empty array")
            else:
                for name in files:
                    if not isinstance(name, str) or not name or Path(name).name != name or name in {".", ".."} or name.startswith("."):
                        errors.append(f"{where}.files entries must be visible file names, not paths")
                        break
                if available_files is not None:
                    unknown_files = set(files) - available_files
                    if unknown_files:
                        errors.append(f"{where}.files references names absent from runtime context: {', '.join(sorted(unknown_files))}")
        if filt is not None:
            if not isinstance(filt, dict) or not filt or set(filt) - {"date", "ext"}:
                errors.append(f"{where}.filter may contain only date and ext")
            else:
                if "date" in filt:
                    value = filt["date"]
                    if not isinstance(value, str) or not (value in DATE_FILTERS or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)):
                        errors.append(f"{where}.filter.date must be a supported relative date or YYYY-MM-DD")
                if "ext" in filt:
                    values = filt["ext"]
                    if not isinstance(values, list) or not values or any(not isinstance(x, str) or not re.fullmatch(r"\.[a-z0-9]{1,12}", x) for x in values):
                        errors.append(f"{where}.filter.ext must be a non-empty array of lowercase extensions")
        if op in {"move", "copy", "organize", "delete"} and files is None and filt is None:
            errors.append(f"{where} needs files or filter")
        if op == "rename":
            if files is None:
                errors.append(f"{where} rename requires exact files")
            if not isinstance(action.get("new_name"), str) or not action.get("new_name", "").strip():
                errors.append(f"{where}.new_name must be a non-empty template")
        if op in {"move", "copy", "organize"} and not isinstance(action.get("destination"), str):
            errors.append(f"{where}.destination is required")
        if op in {"move", "copy", "organize", "delete", "rename"} and not isinstance(action.get("source"), str):
            errors.append(f"{where}.source is required")

        for field in ("source", "destination"):
            value = action.get(field)
            if value is None:
                continue
            if not isinstance(value, str) or not Path(value).expanduser().is_absolute():
                errors.append(f"{where}.{field} must be an absolute path")
                continue
            if _protected(value):
                errors.append(f"{where}.{field} targets a protected system or credential location")
            if roots and not _inside(value, roots):
                errors.append(f"{where}.{field} is outside allowed_roots")
        if op in {"copy", "move", "organize"} and action.get("source") == action.get("destination"):
            errors.append(f"{where} source and destination cannot be the same folder")

    if has_delete and plan.get("needs_confirmation") is not True:
        errors.append("delete actions require needs_confirmation=true")
    if ("clarify" in plan or "refuse" in plan) and plan.get("needs_confirmation") is not False:
        errors.append("clarification/refusal plans must set needs_confirmation=false")
    return errors


def _context_from_user(content: str) -> dict:
    prefix = "Runtime context (authoritative):\n"
    if not content.startswith(prefix):
        return {}
    body = content[len(prefix):].split("\nUser command:", 1)[0]
    try:
        value = json.loads(body)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def validate_record(row: dict) -> list[str]:
    messages = row.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        return ["messages must contain system and user messages"]
    if messages[0].get("role") != "system" or messages[1].get("role") != "user":
        return ["messages must start with system then user"]
    if "expected" in row:
        plan = row["expected"]
    else:
        if len(messages) < 3 or messages[-1].get("role") != "assistant":
            return ["training record must end with an assistant message"]
        try:
            plan = json.loads(messages[-1].get("content", ""))
        except (TypeError, json.JSONDecodeError):
            return ["assistant content is not strict JSON"]
    context = _context_from_user(messages[1].get("content", ""))
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
    return validate_plan(plan, context.get("allowed_roots", []), available)


def validate_dataset(path: Path) -> tuple[int, list[str]]:
    errors: list[str] = []
    count = 0
    with path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                errors.append(f"{path.name}:{line_no}: blank JSONL row")
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{path.name}:{line_no}: invalid JSONL: {exc.msg}")
                continue
            count += 1
            for error in validate_record(row):
                errors.append(f"{path.name}:{line_no}: {error}")
    return count, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="JSONL file or directory with JSONL files")
    args = parser.parse_args()
    paths = sorted(args.dataset.glob("*.jsonl")) if args.dataset.is_dir() else [args.dataset]
    total = 0
    all_errors: list[str] = []
    for path in paths:
        count, errors = validate_dataset(path)
        total += count
        all_errors.extend(errors)
        print(f"{path.name}: {count} rows, {len(errors)} errors")
    if all_errors:
        print("\n".join(all_errors[:100]), file=sys.stderr)
        if len(all_errors) > 100:
            print(f"... and {len(all_errors) - 100} more", file=sys.stderr)
        return 1
    print(f"PASS: validated {total} JSONL rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
