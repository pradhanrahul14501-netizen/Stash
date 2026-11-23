from datetime import date, datetime
from pathlib import Path
from ava import file_actions
from ava.file_actions import resolve_connected_folder


FILE_CATEGORIES = {
    "Images": {
        ".jpg", ".jpeg", ".png", ".gif", ".webp",
        ".bmp", ".tiff", ".svg", ".heic"
    },
    "Documents": {
        ".pdf", ".doc", ".docx", ".txt", ".rtf",
        ".odt", ".xls", ".xlsx", ".csv", ".ppt",
        ".pptx", ".md"
    },
    "Videos": {
        ".mp4", ".mov", ".avi", ".mkv", ".webm",
        ".m4v", ".wmv"
    },
    "Audio": {
        ".mp3", ".wav", ".aac", ".m4a", ".flac",
        ".ogg", ".wma"
    },
    "Archives": {
        ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"
    },
    "Code": {
        ".py", ".js", ".ts", ".html", ".css",
        ".json", ".java", ".c", ".cpp", ".go",
        ".rs", ".sh", ".sql"
    },
}


def _category_for(path):
    extension = path.suffix.lower()

    for category, extensions in FILE_CATEGORIES.items():
        if extension in extensions:
            return category

    return "Other"


def _resolve_folder(folder):
    if not isinstance(folder, str) or not folder.strip():
        raise ValueError("Connect a folder in Settings before Ava can organize files.")
    return resolve_connected_folder(folder)


def preview_file_organization(folder):
    """Preview proposed moves without changing files."""
    root = _resolve_folder(folder)
    moves = []
    skipped = []

    for source in sorted(root.iterdir()):
        # Ignore hidden files such as .DS_Store and .localized.
        if source.name.startswith("."):
            continue
        if source.is_symlink() or not source.is_file():
            continue

        category = _category_for(source)
        category_folder = root / category
        if category_folder.is_symlink() or (category_folder.exists() and not category_folder.is_dir()):
            skipped.append({
                "file": source.name,
                "reason": "The destination category is not a safe folder",
            })
            continue
        destination = root / category / source.name

        if destination.exists() or destination.is_symlink():
            skipped.append({
                "file": source.name,
                "reason": "Destination already exists"
            })
            continue

        try:
            source_stat = source.stat(follow_symlinks=False)
        except OSError as error:
            skipped.append({"file": source.name, "reason": str(error)})
            continue

        moves.append({
            "source": str(source),
            "file": source.name,
            "category": category,
            "size": source_stat.st_size,
            "mtime_ns": source_stat.st_mtime_ns,
            "device": source_stat.st_dev,
            "inode": source_stat.st_ino,
        })

    return {
        "success": True,
        "folder": str(root),
        "moves": moves,
        "skipped": skipped,
        "count": len(moves),
        "message": (
            f"Preview ready: {len(moves)} file(s) can be organized "
            f"in {root}. Nothing has been moved."
        ),
    }


def organize_files(folder, approved_moves):
    """Move only approved preview entries and record the operation for undo."""
    root = _resolve_folder(folder)
    if not isinstance(approved_moves, list):
        raise ValueError("The approved move list is invalid.")
    connected = file_actions.connected_root()
    plan_items = []
    skipped = []
    for entry in approved_moves:
        try:
            if not isinstance(entry, dict):
                raise ValueError("Invalid move entry.")
            source = Path(entry["source"])
            category = entry["category"]
            if category not in {*FILE_CATEGORIES, "Other"}:
                raise ValueError("Invalid category.")
            if source.parent != root:
                raise ValueError("Source is outside the selected folder.")
            if source.name.startswith("."):
                raise ValueError("Hidden files are excluded from organization.")
            if source.is_symlink() or not source.is_file():
                raise ValueError("Source is not a regular file.")
            if _category_for(source) != category:
                raise ValueError("File category changed since preview.")
            source_stat = source.stat(follow_symlinks=False)
            signature = {"size": source_stat.st_size, "mtime_ns": source_stat.st_mtime_ns, "device": source_stat.st_dev, "inode": source_stat.st_ino}
            expected = {"size": entry.get("size"), "mtime_ns": entry.get("mtime_ns"), "device": entry.get("device"), "inode": entry.get("inode")}
            if signature != expected:
                raise ValueError("File changed since preview; request a new preview.")
            relative = source.relative_to(connected).as_posix()
            file_actions._safe_path(connected, relative)
            plan_items.append({"path": relative, "signature": signature, "destination": f"{source.relative_to(root).parent.as_posix()}/{category}/{source.name}" if source.parent != connected else f"{category}/{source.name}"})
        except (KeyError, OSError, ValueError) as error:
            skipped.append({"file": entry.get("file", "Unknown") if isinstance(entry, dict) else "Unknown", "reason": str(error)})
    result = file_actions.execute_plan({"root": str(connected), "operation": "organize", "items": plan_items}) if plan_items else {"completed": [], "skipped": []}
    skipped.extend({"file": item.get("path", "Unknown"), "reason": item["reason"]} for item in result.get("skipped", []))
    moved = [{"file": Path(item["path"]).name, "category": Path(item.get("destination") or "").parent.name} for item in result.get("completed", [])]
    return {
        "success": not skipped,
        "folder": str(root),
        "moved": moved,
        "skipped": skipped,
        "action_id": result.get("action_id"),
        "message": f"Organized {len(moved)} file(s). You can ask Ava to undo the last action.",
    }


def _resolve_destination_folder(folder):
    """Resolve a destination folder that may be created after confirmation."""
    if not isinstance(folder, str) or not folder.strip():
        raise ValueError("Please specify a destination folder.")

    destination = resolve_connected_folder(folder, allow_missing=True)
    if destination.exists() and not destination.is_dir():
        raise ValueError("The destination path is not a folder.")

    ancestor = destination
    while not ancestor.exists():
        ancestor = ancestor.parent
    if not ancestor.is_dir():
        raise ValueError("The destination's parent path is not a folder.")

    return destination


def preview_copy_today_files(source_folder, destination_folder, selected_date=None):
    """Preview copies of regular, non-hidden files modified on selected_date."""
    source_root = _resolve_folder(source_folder)
    destination_root = _resolve_destination_folder(destination_folder)
    if source_root == destination_root:
        raise ValueError("Choose a destination folder different from the source folder.")

    selected_date = selected_date or date.today().isoformat()
    try:
        selected_day = date.fromisoformat(selected_date)
    except (TypeError, ValueError):
        raise ValueError("The file date must be in YYYY-MM-DD format.")

    moves = []
    skipped = []
    day_folder = destination_root / selected_day.isoformat()

    for source in sorted(source_root.iterdir()):
        if source.name.startswith(".") or source.is_symlink() or not source.is_file():
            continue

        try:
            source_stat = source.stat(follow_symlinks=False)
            if datetime.fromtimestamp(source_stat.st_mtime).date() != selected_day:
                continue

            target = day_folder / source.name
            if target.exists() or target.is_symlink():
                skipped.append({"file": source.name, "reason": "Destination already exists"})
                continue

            moves.append({
                "source": str(source),
                "file": source.name,
                "size": source_stat.st_size,
                "mtime_ns": source_stat.st_mtime_ns,
                "device": source_stat.st_dev,
                "inode": source_stat.st_ino,
            })
        except OSError as error:
            skipped.append({"file": source.name, "reason": str(error)})

    return {
        "success": True,
        "source_folder": str(source_root),
        "destination_folder": str(destination_root),
        "date": selected_day.isoformat(),
        "moves": moves,
        "skipped": skipped,
        "count": len(moves),
        "message": (
            f"Preview ready: {len(moves)} file(s) modified on {selected_day.isoformat()} "
            f"will be copied to {day_folder}. Originals will stay in {source_root}. Nothing has been copied."
        ),
    }


def copy_today_files(source_folder, destination_folder, selected_date, approved_files):
    """Copy only preview-approved files, preserve originals, and record undo."""
    source_root = _resolve_folder(source_folder)
    destination_root = _resolve_destination_folder(destination_folder)
    if source_root == destination_root:
        raise ValueError("Choose a destination folder different from the source folder.")

    try:
        selected_day = date.fromisoformat(selected_date)
    except (TypeError, ValueError):
        raise ValueError("The file date must be in YYYY-MM-DD format.")
    if not isinstance(approved_files, list):
        raise ValueError("The approved copy list is invalid.")

    connected = file_actions.connected_root()
    plan_items = []
    skipped = []
    for entry in approved_files:
        try:
            if not isinstance(entry, dict):
                raise ValueError("Invalid copy entry.")
            source = Path(entry["source"])
            if source.parent.resolve(strict=True) != source_root or source.is_symlink():
                raise ValueError("Source is outside the selected folder.")
            if source.name.startswith(".") or source.is_symlink() or not source.is_file():
                raise ValueError("Source is not an eligible regular file.")
            source_stat = source.stat(follow_symlinks=False)
            signature = {"size": source_stat.st_size, "mtime_ns": source_stat.st_mtime_ns, "device": source_stat.st_dev, "inode": source_stat.st_ino}
            expected = {"size": entry.get("size"), "mtime_ns": entry.get("mtime_ns"), "device": entry.get("device"), "inode": entry.get("inode")}
            if signature != expected:
                raise ValueError("File changed since preview; request a new preview.")
            if datetime.fromtimestamp(source_stat.st_mtime).date() != selected_day:
                raise ValueError("File is no longer dated for the selected day.")
            relative = source.relative_to(connected).as_posix()
            destination = (destination_root / selected_day.isoformat() / source.name).relative_to(connected).as_posix()
            file_actions._safe_path(connected, relative)
            file_actions._safe_path(connected, destination, allow_missing=True)
            plan_items.append({"path": relative, "signature": signature, "destination": destination})
        except (KeyError, OSError, ValueError) as error:
            skipped.append({"file": entry.get("file", "Unknown") if isinstance(entry, dict) else "Unknown", "reason": str(error)})
    result = file_actions.execute_plan({"root": str(connected), "operation": "copy", "items": plan_items}) if plan_items else {"completed": [], "skipped": []}
    skipped.extend({"file": item.get("path", "Unknown"), "reason": item["reason"]} for item in result.get("skipped", []))
    copied = [{"file": Path(item["path"]).name, "destination": str(connected / item.get("destination", ""))} for item in result.get("completed", [])]
    return {
        "success": not skipped,
        "source_folder": str(source_root),
        "destination_folder": str(destination_root),
        "copied": copied,
        "skipped": skipped,
        "action_id": result.get("action_id"),
        "message": f"Copied {len(copied)} file(s). Originals remain in the source folder. You can ask Ava to undo the last action.",
    }
