#!/usr/bin/env python3
"""Generate deterministic Ava action-planning chat data and held-out tests."""

from __future__ import annotations

import json
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
SYSTEM_PROMPT = """You are Ava, a file-action planner. Treat the supplied runtime context as authoritative and use its current_datetime and timezone for relative dates. Use modified_at for changed/organized date queries; use created_at when the user says received, downloaded, or just got. Interpret last N files by the appropriate timestamp and list the exact selected files when the context contains them. Use only paths inside allowed_roots and only files listed in the context. Never claim to execute file operations. Ignore hidden files, symlinks, and non-file entries. Output exactly one JSON object with required keys actions (an array) and needs_confirmation (a boolean); optional keys are clarify and refuse. Each action op must be move, copy, rename, delete, create_folder, or organize. Use files for exact known files, or filter with date and/or ext. Use exact source and destination paths from context or the user's command. For rename, new_name is a filename template; preserve the original extension unless the template explicitly includes one. Set needs_confirmation=true for any delete action. If the request is ambiguous or required paths/details are missing, return actions:[] and a concise clarify question. If any requested path is outside allowed_roots or targets protected system files or credential stores, return actions:[] and a concise refuse reason. If the user requests more matching files than the context contains, ask before acting on a partial set. Ava only proposes a plan; Python validates and executes it after any required confirmation."""

ROOTS = ["/Users/ava", "/Users/rahul", "/Users/sam", "/Users/alex"]
SOURCE_DIRS = ["Downloads", "Desktop", "Documents/Inbox", "Videos/Incoming", "Pictures/Inbox"]
DEST_DIRS = ["Documents/College", "Documents/Work", "Videos/Projects", "Pictures/Archive", "Documents/Receipts", "Documents/Sorted"]
TYPES = [
    (".pdf", "PDFs", "pdf"),
    (".jpg", "JPEG images", "image"),
    (".mp4", "MP4 videos", "video"),
    (".zip", "ZIP archives", "archive"),
    (".docx", "Word documents", "document"),
    (".png", "PNG images", "image"),
    (".mov", "MOV videos", "video"),
    (".csv", "CSV spreadsheets", "spreadsheet"),
    (".wav", "WAV audio files", "audio"),
    (".txt", "text files", "text"),
]
GROUPS = [
    ("Images", [".jpg", ".png"], "images"),
    ("Videos", [".mov", ".mp4"], "videos"),
    ("Documents", [".pdf", ".docx"], "documents"),
    ("Archives", [".zip"], "archives"),
    ("Audio", [".wav"], "audio files"),
]

PHRASES = {
    "today": [
        "Copy today's {ext} files from {source_name} to {dest_name}.",
        "Copy the {ext} items changed today from {source_name} into {dest_name}.",
        "Please copy only today's {label} to {dest_name}; keep the originals.",
        "Copy today's {ext} files from {source_name} -> {dest_name}",
        "Aaj ke {label} {dest_name} me copy kar do.",
        "Can you copy {ext} files updated today into {dest_name}?",
        "Copy today's {label} over to {dest_name}, please.",
        "copy {ext} from today into {dest_name} and leave the source files",
        "I need today's {ext} from {source_name} saved in {dest_name}.",
        "today wale {label} ka copy {dest_name} me bana do pls",
    ],
    "relative": [
        "Move {date_phrase}'s {ext} files from {source_name} to {dest_name}.",
        "Copy the {label} changed {date_phrase} into {dest_name}.",
        "Move files with extension {ext} from {date_phrase} into {dest_name}.",
        "Can you move the {date_phrase} {label} to {dest_name}?",
        "{date_phrase} ke {label} {dest_name} me copy karna.",
        "pls move {date_phrase} {ext} items to {dest_name}",
        "Save a copy of {date_phrase}'s {ext} from {source_name} in {dest_name}.",
        "Move the {label} from {date_phrase} into {dest_name}.",
        "Move files ending {ext} that were changed {date_phrase} to {dest_name}.",
        "{date_phrase} ke {label} {dest_name} me bhej do",
    ],
    "explicit_date": [
        "Copy PDFs modified on {exact_date} into {dest_name}.",
        "Move PDFs with modified date {exact_date} from {source_name} to {dest_name}.",
        "the PDFs dated {exact_date} copy to {dest_name}",
        "Move only .pdf files changed on {exact_date} into {dest_name}.",
        "Copy the {exact_date} PDFs to {dest_name} and leave originals.",
        "files with date {exact_date}, move them to {dest_name}",
        "Can you save a copy of PDFs modified {exact_date} in {dest_name}?",
        "put the files dated {exact_date} into {dest_name}",
        "copy all pdfs changed {exact_date} from {source_name} to {dest_name}",
        "Archive PDFs from {exact_date} in {dest_name}.",
    ],
    "recent": [
        "Move the 10 newest files I just downloaded into {dest_name}.",
        "Put my last ten downloads in {dest_name}.",
        "the 10 files i just got, move to {dest_name}",
        "Move the 10 most recently received files from {source_name} to {dest_name}.",
        "latest 10 downloads ko {dest_name} me daalo",
        "Please move the ten newest items by download time into {dest_name}.",
        "Grab my 10 newest files and move them to {dest_name}.",
        "move last 10 files from {source_name} over to {dest_name} pls",
        "I just got 10 files; file them in {dest_name}.",
        "abhi mile newest 10 files {dest_name} me move karo",
    ],
    "hinglish": [
        "aaj ke {label} {dest_name} me copy krdo",
        "aaj ke {ext} {dest_name} me copy karo",
        "aaj wale {ext} ka copy {dest_name} me banao",
        "aaj ke {label} ka copy {dest_name} me banao",
        "mere {source_name} ke aaj wale {label} ka copy {dest_name} me banao",
        "copy {ext} jo aaj change hue {dest_name} me pls",
        "aaj ke {label} ka copy {dest_name} me chahiye",
        "aaj {ext} files ka copy {dest_name} me rakh do",
        "copy today ke {label}, source delete mat karna, destination {dest_name}",
        "bas aaj ke {ext} ka copy {dest_name} me kar do yaar",
    ],
    "rename": [
        "Rename the selected file to include the date and time.",
        "Add a timestamp to the selected filename.",
        "Put the current date and time at the end of this file's name.",
        "rename this with date n time pls",
        "Is file ka naam date aur time ke saath kar do.",
        "Append today's date and the current time to the selected file name.",
        "Add YYYY-MM-DD and HHMM to this filename.",
        "Can you timestamp the selected file name?",
        "rename selected item: original_date_time",
        "date-time laga ke file rename karo",
    ],
    "type_organize": [
        "Organize only {group_label} into a new {folder_name} folder inside {source_name}.",
        "Make {folder_name} in {source_name} and sort {group_label} there.",
        "put {group_label} into a new {folder_name} folder under {source_name}",
        "Organise my {group_label} by type in {source_name}.",
        "new folder {folder_name} bana ke {group_label} usme move karo",
        "Group the {group_label} into {folder_name} in the source folder.",
        "Sort only {group_label} into {source_name}/{folder_name}.",
        "can u arrange {group_label} in a separate {folder_name} folder",
        "Make a folder for {group_label} and organize them into it.",
        "{group_label} ko {folder_name} me sort krdo",
    ],
    "date_folder": [
        "Copy {date_phrase}'s files from {source_name} into a date folder under {dest_name}; keep originals.",
        "Move {date_phrase}'s files into {dest_name}/{date_folder}.",
        "Make a {date_folder} folder in {dest_name} and copy {date_phrase}'s files there.",
        "Put {date_phrase}'s files from {source_name} in {dest_name}/{date_folder}, originals stay.",
        "{date_phrase} ke files ko date folder {date_folder} me move kar do",
        "Create the dated folder {date_folder} in {dest_name}, then copy {date_phrase}'s files.",
        "Sort {date_phrase}'s downloads into a date folder inside {dest_name}.",
        "Move files changed {date_phrase} to the {date_folder} folder under {dest_name}.",
        "date folder banao {date_folder}, {date_phrase} ke files copy karo {dest_name} me",
        "Arrange {date_phrase}'s files in a folder named {date_folder} under {dest_name}.",
    ],
    "name": [
        "Put files whose names start with {prefix} into a new {folder_name} folder under {dest_name}.",
        "Move the {prefix} files into {dest_name}/{folder_name}.",
        "Group filenames beginning {prefix} in {dest_name}/{folder_name}.",
        "Please sort {prefix}* into {folder_name} under {dest_name}.",
        "{prefix} se start hone wale files {dest_name}/{folder_name} me daal do",
        "Create {folder_name} in {dest_name} and move the matching names there.",
        "File the ones named with the {prefix} prefix in {dest_name}/{folder_name}.",
        "can you put all {prefix} files in {dest_name}/{folder_name}",
        "Move only files starting with {prefix} into the new {folder_name} folder under {dest_name}.",
        "{prefix} wale docs ko {dest_name}/{folder_name} me organize kar do",
    ],
    "multi": [
        "Move every PDF to {dest_name}, add date and time to the names, then delete the ZIPs.",
        "Put PDFs in {dest_name}, timestamp their names, and remove the ZIP files.",
        "move all pdfs to {dest_name}; rename with date time; delete zips",
        "Send the PDFs to {dest_name}, append timestamps, then delete the archives.",
        "PDF ko {dest_name} me bhejo, naam date-time se badlo, ZIP hatao.",
        "Move PDFs to {dest_name} and rename them with a timestamp; delete all ZIPs too.",
        "College me PDFs move karke timestamp lagao, phir zip delete karo.",
        "Take every PDF to {dest_name}, date-time rename, and delete the zip files.",
        "copy PDFs to {dest_name}, rename with date/time, delete the ZIPs",
        "Move the listed PDFs, timestamp them, and delete the listed ZIPs.",
    ],
    "delete": [
        "Delete the selected file; ask me to confirm before deleting.",
        "Please remove {filename} after confirmation.",
        "delete {filename}",
        "Erase the selected {label}, but wait for my confirmation.",
        "{filename} hata do, pehle confirm karna",
        "I want {filename} deleted. Show me a confirmation first.",
        "remove the listed {label} from {source_name}",
        "Can you delete this file? Confirm with me before doing it.",
        "delete selected item pls",
        "{filename} ko delete karna hai",
    ],
    "ambiguous": [
        "Organize this.",
        "Can you sort these?",
        "Clean up my files.",
        "Make this neat.",
        "arrange krdo",
        "Put these away.",
        "Do the usual organization.",
        "can u organize",
        "Sort my stuff please.",
        "Fix these files.",
    ],
    "missing_path": [
        "Copy today's files and keep the originals.",
        "Move these into the right folder.",
        "copy my recent files pls",
        "Organize today's downloads for me.",
        "aaj ke files copy kar do",
        "Put the PDFs somewhere safe.",
        "Move today's files from {source_name}.",
        "copy files to {dest_name}",
        "Can you save these in a folder?",
        "move the recent ones over there",
    ],
    "unsafe": [
        "Delete {unsafe}.",
        "Move my files to {unsafe}.",
        "Delete {unsafe}.",
        "copy these to {unsafe}",
        "move this into {unsafe}",
        "Erase {unsafe}.",
        "Send the files outside my allowed folders to {unsafe}.",
        "Can you delete {unsafe}?",
        "copy to {unsafe}",
        "system folder clean kar do: {unsafe}",
    ],
    "combined_filter": [
        "Move {date_phrase}'s images and PDFs from {source_name} to {dest_name}.",
        "Copy {date_phrase}'s {exts} to {dest_name}.",
        "Put only {date_phrase}'s {label} in {dest_name}.",
        "Move files of type {exts}, changed {date_phrase}, to {dest_name}.",
        "{date_phrase} ke {label} {dest_name} me copy kar do",
        "Save a copy of the {date_phrase} {exts} in {dest_name}.",
        "File {date_phrase}'s {label} in {dest_name}, please.",
        "Only {exts} from {date_phrase}; destination {dest_name}.",
        "move {date_phrase} {label} to {dest_name}",
        "copy the matching date/type files into {dest_name}",
    ],
    "count_mismatch": [
        "Move the 12 newest files to {dest_name}.",
        "I need exactly 12 of the latest files moved to {dest_name}.",
        "move last 12 files from here to {dest_name}",
        "Put twelve recent downloads in {dest_name}, no fewer.",
        "latest 12 ko {dest_name} me move kar do",
        "Move my 12 newest files, please.",
        "I asked for 12 recent ones in {dest_name}.",
        "Can you move the most recent twelve to {dest_name}?",
        "need 12 files not just a few, move em to {dest_name}",
        "12 newest downloads {dest_name} me daal do",
    ],
    "editor_multi": [
        "Copy the newest video to {dest_name} and add a timestamp to the copied name.",
        "Make a copy of my latest clip in {dest_name}, then timestamp its name.",
        "copy newest video to {dest_name}, rename copy date-time",
        "Put a duplicate of the latest video in {dest_name} and append date/time.",
        "latest video ka copy {dest_name} me, naam me date time laga do",
        "Create an editing copy in {dest_name} and timestamp that copy.",
        "Duplicate the newest clip for editing, naming it with a timestamp.",
        "Can you copy the most recent video to {dest_name} and rename the copy?",
        "send a timestamped copy of my latest video to {dest_name}",
        "copy the newest .mov for editing and add current timestamp",
    ],
}

HARD_PROMPTS = {
    "today": ["Only duplicate the {label} from today into {dest_name}; leave their originals where they are.", "aaj updated {ext} bas {dest_name} me copy, original same jagah"],
    "relative": ["Keep only files changed {date_phrase}, ending {ext}; move those from {source_name} to {dest_name}.", "Use the runtime date: copy {date_phrase} {label} into {dest_name}."],
    "explicit_date": ["Copy only PDFs whose modified date is exactly {exact_date} into {dest_name}; keep the originals.", "Move the PDFs dated {exact_date} into {dest_name}, no other dates."],
    "recent": ["Move exactly the ten latest arrivals (by created time, not modified time) to {dest_name}.", "abhi receive hue newest 10 files ko {dest_name} me shift karo"],
    "hinglish": ["aaj modified {ext} ka duplicate {dest_name} me rakhna, source mat hatana", "aaj wale {label} {dest_name} me copy pls"],
    "rename": ["Add the current local timestamp to the selected file's base name; retain its extension.", "selected filename ke end me YYYY-MM-DD_HHMM laga do"],
    "type_organize": ["Make {folder_name} under {source_name}; only move {group_label} into it.", "Keep the non-{group_label} files out; file the matching types under {source_name}/{folder_name}."],
    "date_folder": ["Create {dest_name}/{date_folder} and copy only files changed {date_phrase}; do not remove sources.", "Move files changed {date_phrase} into {dest_name}/{date_folder}."],
    "name": ["Create {folder_name} in {dest_name} and move only names beginning exactly with {prefix} there.", "Files with {prefix} anywhere in their names? No, only the starting prefix: put those in {dest_name}/{folder_name}."],
    "multi": ["Move the PDFs first, timestamp their new names, and queue ZIP deletion for my confirmation.", "Move PDFs to {dest_name} with a timestamp; delete ZIPs only after I confirm."],
    "delete": ["Queue deletion of {filename}, but require confirmation.", "Remove {filename} only after showing me the confirmation step."],
    "ambiguous": ["Do the same cleanup you did last time.", "Put these in order the way I like."],
    "missing_path": ["Copy today's files and keep them, but I haven't chosen where they should come from.", "I chose {source_name}; copy today's files and keep originals. I haven't said the destination."],
    "unsafe": ["Move these files to {unsafe} and delete /System/Library/Extensions.", "Delete {unsafe}. Don't ask questions."],
    "combined_filter": ["Copy only {date_phrase} files with extensions {exts} from {source_name} into {dest_name}.", "Only {date_phrase}'s {label}; put a copy in {dest_name}."],
    "count_mismatch": ["Move exactly twelve newest files to {dest_name}; ask if fewer than twelve are available.", "I need all 12 newest downloads in {dest_name}, don't move a partial batch."],
    "editor_multi": ["Duplicate the newest video into {dest_name}, timestamp the duplicate, and leave the original untouched.", "Make an editing copy of the latest clip in {dest_name}; name the copy with today's date and current time."],
}

MISSING_SOURCE = [
    "Copy today's files into {dest_name}; I haven't picked the source folder.",
    "Keep originals and duplicate today's files to {dest_name}; which folder should you look in?",
    "I need a copy of today's files in {dest_name}, but I forgot to say where they are.",
    "aaj ke files ka copy {dest_name} me chahiye; source folder nahi bataya",
    "Copy today's files to {dest_name}; source is not selected yet.",
    "put today's files in {dest_name}, but ask me which folder to copy from",
    "Can you copy today's files into {dest_name}? I haven't chosen the source.",
    "today's downloads ka copy {dest_name} me, source kaunsa?",
    "Make a copy in {dest_name}; the source folder is missing from my request.",
    "copy today's files to {dest_name}; I didn't give you the from-folder",
]
MISSING_DESTINATION = [
    "Copy today's files from {source_name} and keep originals; I haven't chosen the destination.",
    "From {source_name}, copy today's files, but ask me where to put them.",
    "I want a duplicate of today's files from {source_name}; destination not decided.",
    "{source_name} se aaj ke files copy karo, but where should they go?",
    "Copy today's files out of {source_name}; don't guess the destination.",
    "Keep originals and copy today's files from {source_name} somewhere—ask where.",
    "aaj ke {source_name} files ka copy chahiye, destination baad me bataunga",
    "Please duplicate today's files from {source_name}. I haven't named a target folder.",
    "Copy the files changed today in {source_name}; wait for my destination path.",
    "{source_name} ke aaj wale files copy karna, destination poochna",
]


def _now(family: int, index: int) -> datetime:
    days = (family * 47 + index * 13 + 5) % 900
    d = date(2024, 6, 1) + timedelta(days=days)
    return datetime.combine(d, time(6 + (index % 15), (family * 7 + index * 11) % 60))


def _file(name: str, now: datetime, modified_days: int = 0, created_days: int | None = None, minute: int = 0, **extra) -> dict:
    ext = Path(name).suffix.lower()
    mod = now - timedelta(days=modified_days, minutes=minute)
    created = now - timedelta(days=modified_days if created_days is None else created_days, minutes=minute)
    item = {
        "name": name,
        "extension": ext,
        "size_bytes": 1000 + (sum(name.encode("utf-8")) * 17) % 9_000_000,
        "modified_at": mod.isoformat(timespec="minutes"),
        "created_at": created.isoformat(timespec="minutes"),
        "is_hidden": name.startswith("."),
        "is_symlink": False,
        "kind": "file",
    }
    item.update(extra)
    return item


def _runtime(family: int, index: int, source_rel: str = "Downloads", files: list | None = None, known_rel: list[str] | None = None, source_override: str | None = None) -> tuple[dict, datetime, str, str]:
    root = ROOTS[(family + index) % len(ROOTS)]
    now = _now(family, index)
    source = source_override if source_override is not None else f"{root}/{source_rel}"
    known = [f"{root}/{p}" for p in (known_rel or [])]
    if source and source not in known:
        known.insert(0, source)
    context = {
        "current_datetime": now.isoformat(timespec="minutes"),
        "timezone": "local",
        "source_folder": source or None,
        "files": files or [],
        "known_folders": known,
        "allowed_roots": [root],
    }
    return context, now, root, source


def _prompt(context: dict, command: str) -> str:
    return "Runtime context (authoritative):\n" + json.dumps(context, ensure_ascii=False, separators=(",", ":")) + "\nUser command: " + command


def _row(context: dict, command: str, plan: dict, ident: str, include_expected: bool = False) -> dict:
    row = {
        "id": ident,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _prompt(context, command)},
        ],
    }
    if include_expected:
        row["expected"] = plan
    else:
        row["messages"].append({"role": "assistant", "content": json.dumps(plan, ensure_ascii=False, separators=(",", ":"))})
    return row


def _date_filter(date_value: str, exts: list[str] | None = None) -> dict:
    f = {"date": date_value}
    if exts:
        f["ext"] = exts
    return f


def build_case(family: str, index: int, phrase_index: int, hard: bool = False) -> tuple[dict, str, dict, dict]:
    """Return context, command, expected plan, and formatting slots."""
    fam_id = list(PHRASES).index(family)
    now = _now(fam_id, index)
    root = ROOTS[(fam_id + index) % len(ROOTS)]
    src_rel = SOURCE_DIRS[(fam_id + index) % len(SOURCE_DIRS)]
    source = f"{root}/{src_rel}"
    dest = f"{root}/{DEST_DIRS[(fam_id + index // 3) % len(DEST_DIRS)]}"
    ext, label, short = TYPES[index % len(TYPES)]
    slots = {
        "ext": ext,
        "label": label,
        "source": source,
        "source_name": src_rel,
        "destination": dest,
        "dest_name": DEST_DIRS[(fam_id + index // 3) % len(DEST_DIRS)].split("/")[-1],
        "filename": f"item_{index % 97}{ext}",
    }
    files: list[dict] = []
    known_rel = [DEST_DIRS[(fam_id + index // 3) % len(DEST_DIRS)]]
    plan: dict

    if family in ("today", "hinglish"):
        is_copy = True
        ext = TYPES[(index + (0 if family == "today" else 3)) % len(TYPES)][0]
        label = next(t[1] for t in TYPES if t[0] == ext)
        files = [
            _file(f"target_{index}{ext}", now, 0),
            _file(f"older_{index}{ext}", now, 1),
            _file(f"other_{index}{TYPES[(index + 1) % len(TYPES)][0]}", now, 0),
        ]
        slots.update(ext=ext, label=label)
        plan = {"actions": [{"op": "copy" if is_copy else "move", "filter": _date_filter("today", [ext]), "source": source, "destination": dest}], "needs_confirmation": False}
    elif family == "relative":
        date_phrase = "yesterday" if index % 2 else "this week"
        date_value = "yesterday" if date_phrase == "yesterday" else "this_week"
        days_ago = 1 if date_phrase == "yesterday" else now.weekday()
        files = [_file(f"match_{index}{ext}", now, days_ago), _file(f"not_match_{index}{ext}", now, 10), _file(f"other_{index}.txt", now, days_ago)]
        slots.update(date_phrase=date_phrase, ext=ext, label=label)
        relative_ops = ["move", "copy", "move", "move", "copy", "move", "copy", "move", "move", "move"]
        op = ("move" if index % 2 == 0 else "copy") if hard else relative_ops[phrase_index]
        plan = {"actions": [{"op": op, "filter": _date_filter(date_value, [ext]), "source": source, "destination": dest}], "needs_confirmation": False}
    elif family == "explicit_date":
        days_ago = 20 + (index % 40)
        exact_date = (now.date() - timedelta(days=days_ago)).isoformat()
        files = [_file(f"exact_{index}.pdf", now, days_ago), _file(f"also_exact_{index}.pdf", now, days_ago, minute=3), _file(f"wrong_date_{index}.pdf", now, days_ago + 1)]
        slots.update(exact_date=exact_date, ext=".pdf", label="PDFs")
        exact_ops = ["copy", "move", "copy", "move", "copy", "move", "copy", "move", "copy", "move"]
        op = ("copy" if index % 2 == 0 else "move") if hard else exact_ops[phrase_index]
        plan = {"actions": [{"op": op, "filter": {"date": exact_date, "ext": [".pdf"]}, "source": source, "destination": dest}], "needs_confirmation": False}
    elif family == "recent":
        ext_list = [".mov", ".pdf", ".png", ".txt", ".mp4", ".wav", ".docx", ".jpg", ".zip", ".csv"]
        files = [_file(f"arrival_{index}_{k:02}{ext_list[k % len(ext_list)]}", now, (k // 4), created_days=0, minute=10-k) for k in range(10)]
        files += [_file(f"older_arrival_{index}.pdf", now, 4, created_days=4)]
        selected = [x["name"] for x in sorted(files, key=lambda x: x["created_at"], reverse=True)[:10]]
        plan = {"actions": [{"op": "move", "files": selected, "source": source, "destination": dest}], "needs_confirmation": False}
    elif family == "rename":
        name = f"meeting_{index}{ext}"
        files = [_file(name, now, 0)]
        context, now, root, source = _runtime(fam_id, index, src_rel, files, known_rel)
        context["selected_files"] = [name]
        slots.update(filename=name, source_name=src_rel, ext=ext)
        plan = {"actions": [{"op": "rename", "files": [name], "source": source, "new_name": "{original}_{YYYY-MM-DD}_{HHMM}"}], "needs_confirmation": False}
        command = (HARD_PROMPTS[family][index % 2] if hard else PHRASES[family][phrase_index]).format(**slots)
        return context, command, plan, slots
    elif family == "type_organize":
        folder_name, exts, group_label = GROUPS[index % len(GROUPS)]
        destination = f"{source}/{folder_name}"
        files = [_file(f"match_a_{index}{exts[0]}", now), _file(f"match_b_{index}{exts[-1]}", now, 2), _file(f"other_{index}.txt", now)]
        if index % 3 == 0:
            files.append(_file(f".hidden_{index}{exts[0]}", now))
        known_rel = [src_rel]
        slots.update(folder_name=folder_name, group_label=group_label)
        plan = {"actions": [{"op": "create_folder", "destination": destination}, {"op": "organize", "filter": {"ext": exts}, "source": source, "destination": destination}], "needs_confirmation": False}
    elif family == "date_folder":
        date_value = "today" if index % 2 == 0 else "yesterday"
        day_offset = 0 if date_value == "today" else 1
        folder_date = (now.date() - timedelta(days=day_offset)).isoformat()
        date_folder = f"{dest}/{folder_date}"
        files = [_file(f"dated_{index}.mov", now, day_offset), _file(f"outside_{index}.pdf", now, 7)]
        op = "copy" if index % 2 == 0 else "move"
        slots.update(date_folder=folder_date, source_name=src_rel, dest_name=DEST_DIRS[(fam_id + index // 3) % len(DEST_DIRS)].split("/")[-1])
        folder_ops = ["copy", "move", "copy", "copy", "move", "copy", "move", "move", "copy", "move"]
        op = ("copy" if index % 2 == 0 else "move") if hard else folder_ops[phrase_index]
        slots.update(date_phrase=date_value)
        plan = {"actions": [{"op": "create_folder", "destination": date_folder}, {"op": op, "filter": {"date": date_value}, "source": source, "destination": date_folder}], "needs_confirmation": False}
    elif family == "name":
        prefix = ["lecture", "client", "invoice", "project", "class", "draft", "trip", "meeting", "design", "export"][index % 10]
        folder_name = f"{prefix.title()} Files"
        destination = f"{dest}/{folder_name}"
        matching = [f"{prefix}_{index}_01.pdf", f"{prefix}_{index}_02.docx"]
        files = [_file(matching[0], now), _file(matching[1], now, 1), _file(f"other_{prefix}_{index}.pdf", now)]
        slots.update(prefix=prefix, folder_name=folder_name, dest_name=DEST_DIRS[(fam_id + index // 3) % len(DEST_DIRS)].split("/")[-1])
        plan = {"actions": [{"op": "create_folder", "destination": destination}, {"op": "organize", "files": matching, "source": source, "destination": destination}], "needs_confirmation": False}
    elif family == "multi":
        dest = f"{root}/Documents/College"
        slots["dest_name"] = "College"
        known_rel = ["Documents/College"]
        pdfs = [f"essay_{index}.pdf", f"notes_{index}.pdf"]
        zips = [f"bundle_{index}.zip"]
        files = [_file(pdfs[0], now), _file(pdfs[1], now, 1), _file(zips[0], now, 2), _file(f"image_{index}.png", now)]
        pdf_op = "copy" if (phrase_index == 8 and not hard) else "move"
        plan = {"actions": [{"op": pdf_op, "files": pdfs, "source": source, "destination": dest}, {"op": "rename", "files": pdfs, "source": dest, "new_name": "{original}_{YYYY-MM-DD}_{HHMM}"}, {"op": "delete", "files": zips, "source": source}], "needs_confirmation": True}
    elif family == "delete":
        chosen = f"remove_me_{index}{ext}"
        files = [_file(chosen, now), _file(f"keep_{index}{ext}", now, 1)]
        plan = {"actions": [{"op": "delete", "files": [chosen], "source": source}], "needs_confirmation": True}
        slots.update(filename=chosen, label=label, ext=ext)
    elif family == "ambiguous":
        files = [_file(f"notes_{index}.pdf", now), _file(f"image_{index}.jpg", now), _file(f"video_{index}.mov", now)]
        plan = {"actions": [], "needs_confirmation": False, "clarify": "How should I organize these files—by type, date, or name, and where should they go?"}
    elif family == "missing_path":
        if index % 2 == 0:
            context, now, root, source = _runtime(fam_id, index, "", [_file(f"today_{index}.pdf", now)], [DEST_DIRS[(fam_id + index // 3) % len(DEST_DIRS)]], source_override=None)
            context["source_folder"] = None
            context["files"] = [_file(f"today_{index}.pdf", now)]
            slots["dest_name"] = DEST_DIRS[(fam_id + index // 3) % len(DEST_DIRS)].split("/")[-1]
            question = "Which source folder should I use?"
        else:
            files = [_file(f"today_{index}.pdf", now)]
            question = "Which destination folder should I copy the files to?"
        plan = {"actions": [], "needs_confirmation": False, "clarify": question}
    elif family == "unsafe":
        unsafe = ["/System/Library/Extensions", "/Volumes/Shared", "/etc", "/Library/LaunchDaemons"][phrase_index % 4]
        slots.update(unsafe=unsafe)
        plan = {"actions": [], "needs_confirmation": False, "refuse": f"I can only manage files inside the allowed folders and can't modify protected system locations: {unsafe}."}
    elif family == "combined_filter":
        date_phrase = "yesterday" if index % 2 else "this week"
        date_value = "yesterday" if date_phrase == "yesterday" else "this_week"
        days_ago = 1 if date_value == "yesterday" else now.weekday()
        exts = [".jpg", ".png", ".pdf"]
        files = [_file(f"match_a_{index}{exts[0]}", now, days_ago), _file(f"match_b_{index}{exts[-1]}", now, days_ago), _file(f"wrong_date_{index}{exts[0]}", now, 12)]
        slots.update(date_phrase=date_phrase, exts=", ".join(exts), ext=exts[0], label="images and PDFs")
        combined_ops = ["move", "copy", "move", "move", "copy", "copy", "move", "move", "move", "copy"]
        op = "copy" if hard else combined_ops[phrase_index]
        plan = {"actions": [{"op": op, "filter": _date_filter(date_value, exts), "source": source, "destination": dest}], "needs_confirmation": False}
    elif family == "count_mismatch":
        recent_files = [_file(f"recent_{index}_{k:02}.dat", now, k // 4, created_days=0, minute=k) for k in range(8)]
        old_files = [_file(f"old_{index}_{k:02}.dat", now, 20 + k, created_days=20 + k) for k in range(2)]
        files = recent_files + old_files
        plan = {"actions": [], "needs_confirmation": False, "clarify": "I found only 8 recent files in the supplied list, but you asked for 12. Should I move the 8 available files or include older ones?"}
    elif family == "editor_multi":
        name = f"newest_clip_{index}.mov"
        files = [_file(name, now, 0, minute=1), _file(f"older_clip_{index}.mov", now, 3)]
        edit_dest = f"{root}/Videos/Projects/Editing"
        known_rel = ["Videos/Projects"]
        slots.update(dest_name="Videos/Projects/Editing", source_name=src_rel, filename=name)
        plan = {"actions": [{"op": "create_folder", "destination": edit_dest}, {"op": "copy", "files": [name], "source": source, "destination": edit_dest}, {"op": "rename", "files": [name], "source": edit_dest, "new_name": "{original}_{YYYY-MM-DD}_{HHMM}"}], "needs_confirmation": False}
    else:
        raise KeyError(family)

    context, _, _, source = _runtime(fam_id, index, src_rel, files, known_rel)
    if family == "delete":
        context["selected_files"] = [chosen]
    command = (HARD_PROMPTS[family][index % 2] if hard else PHRASES[family][phrase_index]).format(**slots)
    if family == "unsafe":
        command = PHRASES[family][phrase_index].format(**slots)
    if family == "missing_path":
        if index % 2 == 0:
            command = MISSING_SOURCE[phrase_index].format(**slots)
            context["source_folder"] = None
            context["known_folders"] = [dest]
        else:
            command = MISSING_DESTINATION[phrase_index].format(**slots)
            context["known_folders"] = [source]
    if family == "combined_filter" and hard:
        command = HARD_PROMPTS[family][phrase_index % 2].format(**slots)
    return context, command, plan, slots


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    train, valid = [], []
    for family in PHRASES:
        for i in range(100):
            phrase_index = i % 10
            context, command, plan, _ = build_case(family, i, phrase_index)
            row = _row(context, command, plan, f"{family}-{i:03d}")
            (valid if phrase_index == 9 else train).append(row)
    reviewed_path = DATA_DIR / "reviewed_failures.jsonl"
    if reviewed_path.exists():
        for line_no, line in enumerate(reviewed_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict) or not isinstance(row.get("messages"), list):
                raise ValueError(f"{reviewed_path.name}:{line_no} must be a chat JSONL record")
            if len(row["messages"]) < 3 or row["messages"][-1].get("role") != "assistant":
                raise ValueError(f"{reviewed_path.name}:{line_no} must include the corrected assistant plan")
            train.append(row)
    rng = random.Random(20261016)
    rng.shuffle(train)
    rng.shuffle(valid)
    hard = []
    for family in PHRASES:
        hard_count = 1 if family in {"today", "relative", "explicit_date", "recent"} else 2
        for i in range(hard_count):
            context, command, plan, _ = build_case(family, 200 + i, i, hard=True)
            hard.append(_row(context, command, plan, f"hard-{family}-{i+1}", include_expected=True))
    for filename, rows in (("train.jsonl", train), ("valid.jsonl", valid), ("hard_test.jsonl", hard)):
        with (DATA_DIR / filename).open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"Generated {len(train)} train, {len(valid)} validation, and {len(hard)} hard-test cases in {DATA_DIR}")


if __name__ == "__main__":
    main()
