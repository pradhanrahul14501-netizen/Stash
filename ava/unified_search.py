"""Combined, read-only search across Stash and macOS Spotlight."""

import os
import re
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from ava import tools
import storage_manager


PAGE_SIZE = 20
SPOTLIGHT_TIMEOUT_SECONDS = 20
_TYPE_PATTERNS = (
    (r"\b(?:pdfs?|portable document format)\b", "file", "pdf"),
    (r"\b(?:videos?|vids?|clips?|footage)\b", "video", None),
    (r"\b(?:photos?|pictures?|pics?|images?|screenshots?)\b", "image", None),
    (r"\b(?:audios?|music|songs?|tracks?)\b", "audio", None),
    (r"\b(?:texts?|notes?|messages?)\b", "text", None),
    (r"\b(?:links?|urls?|websites?|webpages?)\b", "link", None),
    (r"\b(?:files?|documents?|docs?)\b", "file", None),
)
_DATE_PATTERNS = (
    (r"\bday before yesterday\b", "day before yesterday"),
    (r"\byesterday\b", "yesterday"),
    (r"\btoday\b", "today"),
    (r"\blast week\b", "last week"),
    (r"\bthis month\b", "this month"),
)
_STOP_WORDS = {
    "a", "about", "all", "and", "any", "can", "could", "find", "for",
    "from", "get", "i", "in", "look", "me", "my", "of", "on", "please",
    "search", "see", "show", "the", "to", "want", "with", "would", "named", "called", "only", "more",
    "that", "mention", "mentions", "says", "said", "contains", "containing", "inside", "word", "words",
    "modified", "created", "changed", "copied", "saved", "stash", "library", "computer", "mac", "macos",
    "here", "there", "item", "items", "thing", "things", "everything", "every",
}
_TYPE_ONLY_WORDS = {
    "video", "videos", "vid", "vids", "clip", "clips", "footage",
    "photo", "photos", "picture", "pictures", "pic", "pics", "image", "images",
    "screenshot", "screenshots", "audio", "audios", "music", "song", "songs",
    "track", "tracks", "text", "texts", "note", "notes", "message", "messages",
    "link", "links", "url", "urls", "website", "websites", "webpage", "webpages",
    "file", "files", "document", "documents", "doc", "docs", "pdf", "pdfs",
}
_MEDIA_EXTENSIONS = {
    ".avif", ".bmp", ".gif", ".heic", ".icns", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".svg", ".webp",
    ".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".webm",
    ".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".wma", ".url", ".webloc",
}
_TYPE_EXTENSIONS = {
    "video": {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".webm"},
    "image": {".avif", ".bmp", ".gif", ".heic", ".icns", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".svg", ".webp"},
    "audio": {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".wma"},
    "text": {".txt", ".md", ".markdown", ".csv", ".tsv", ".rtf"},
    "link": {".url", ".webloc"},
}


def local_calendar_date(value):
    """Return an ISO date in the computer's local timezone."""
    if isinstance(value, datetime):
        timestamp = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            timestamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text[:10] if len(text) >= 10 else None
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone()
    return timestamp.date().isoformat()


def resolve_local_date_range(phrase, now=None):
    """Resolve common date words into inclusive local calendar dates."""
    moment = now or datetime.now().astimezone()
    if moment.tzinfo is not None:
        moment = moment.astimezone()
    today = moment.date()
    normalized = str(phrase or "").strip().casefold()
    if normalized == "today":
        start = end = today
    elif normalized == "yesterday":
        start = end = today - timedelta(days=1)
    elif normalized in {"day before yesterday", "the day before yesterday"}:
        start = end = today - timedelta(days=2)
    elif normalized == "last week":
        this_monday = today - timedelta(days=today.weekday())
        start, end = this_monday - timedelta(days=7), this_monday - timedelta(days=1)
    elif normalized == "this month":
        start, end = today.replace(day=1), today
    else:
        try:
            start = end = date.fromisoformat(normalized)
        except ValueError:
            return None
    return {"start": start.isoformat(), "end": end.isoformat(), "label": normalized}


def parse_search_request(command, folder_resolver=None):
    """Extract explicit search filters without asking for a directory."""
    text = str(command or "").strip()
    folded = text.casefold()
    item_type = None
    extension = None
    type_pattern = None
    for pattern, candidate_type, candidate_extension in _TYPE_PATTERNS:
        if re.search(pattern, folded):
            item_type, extension, type_pattern = candidate_type, candidate_extension, pattern
            break

    date_phrase = None
    date_pattern = None
    for pattern, candidate in _DATE_PATTERNS:
        if re.search(pattern, folded):
            date_phrase, date_pattern = candidate, pattern
            break
    if not date_phrase:
        explicit_date = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", folded)
        if explicit_date:
            date_phrase = explicit_date.group(1)
            date_pattern = re.escape(explicit_date.group(1))

    folder = folder_resolver(text) if folder_resolver else None
    query_text = text
    for pattern in (type_pattern, date_pattern):
        if pattern:
            query_text = re.sub(pattern, " ", query_text, flags=re.IGNORECASE)
    # Remove paths and common folder aliases after recording the explicit filter.
    query_text = re.sub(r"[\"']~?/[^\"']+[\"']|(?<![\w:])~?/[^\s,;]+", " ", query_text)
    query_text = re.sub(
        r"\b(?:in|inside|within|under|from|search)\s+(?:my\s+)?(?:downloads?|desktop|documents?)\b",
        " ", query_text, flags=re.IGNORECASE,
    )
    words = [
        word for word in re.findall(r"[^\W_]+", query_text, flags=re.UNICODE)
        if word.casefold() not in _STOP_WORDS
        and word.casefold() not in _TYPE_ONLY_WORDS
        and word.casefold() not in {"today", "yesterday", "tomorrow", "week", "month", "last", "this"}
    ]
    query = " ".join(words).strip() or None
    date_range = resolve_local_date_range(date_phrase) if date_phrase else None
    places = "stash"
    if folder or re.search(r"\b(?:on\s+(?:my\s+)?mac|finder)\b", folded):
        places = "mac"
    elif re.search(r"\b(?:everywhere|both\s+(?:stash\s+and\s+)?(?:mac|finder))\b", folded):
        places = "stash_and_mac"

    return {
        "query": query,
        "type": item_type,
        "extension": extension,
        "date_phrase": date_phrase,
        "date_range": date_range,
        "folder": folder,
        "places": places,
        "page": 0,
    }


def validate_search_context(context):
    """Keep browser-persisted follow-up state small and limited to search filters."""
    if not isinstance(context, dict):
        return None
    cleaned = {}
    query = context.get("query")
    if isinstance(query, str) and query.strip():
        cleaned["query"] = query.strip()[:300]
    item_type = tools.normalize_item_type(context.get("type"))
    if item_type in {"video", "image", "audio", "text", "file", "link"}:
        cleaned["type"] = item_type
    extension = context.get("extension")
    if isinstance(extension, str):
        extension = extension.strip().lstrip(".").casefold()
        if re.fullmatch(r"[a-z0-9]{1,10}", extension):
            cleaned["extension"] = extension
    date_range = context.get("date_range")
    if isinstance(date_range, dict):
        try:
            start = date.fromisoformat(str(date_range.get("start")))
            end = date.fromisoformat(str(date_range.get("end")))
            if start <= end:
                cleaned["date_range"] = {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "label": str(date_range.get("label") or start.isoformat())[:40],
                }
        except ValueError:
            pass
    folder = context.get("folder")
    if isinstance(folder, str) and folder.strip() and os.path.isabs(os.path.expanduser(folder.strip())):
        cleaned["folder"] = os.path.expanduser(folder.strip())[:2048]
    places = context.get("places")
    if places in {"stash", "mac", "stash_and_mac"}:
        cleaned["places"] = places
    else:
        cleaned["places"] = "mac" if cleaned.get("folder") else "stash"
    return cleaned if cleaned else None


def parse_search_followup(command, search_context, offset=0):
    """Apply a short type/date refinement or page request to the chat's last search."""
    filters = validate_search_context(search_context)
    if not filters:
        return None
    text = re.sub(r"[.!?,]+", " ", str(command or "").casefold()).strip()
    text = re.sub(r"\s+", " ", text)
    if re.fullmatch(r"(?:show\s+)?(?:more|more results|next page|show next)", text):
        try:
            next_offset = max(0, min(int(offset), 10_000_000))
        except (TypeError, ValueError, OverflowError):
            next_offset = 0
        return {"filters": filters, "offset": next_offset, "action": "more"}

    parsed = parse_search_request("find " + text)
    if parsed.get("query") is not None:
        return None
    if not parsed.get("type") and not parsed.get("date_range"):
        return None
    if parsed.get("type"):
        filters["type"] = parsed["type"]
        # An explicit type refinement replaces an old extension restriction.
        filters["extension"] = parsed.get("extension")
    if parsed.get("date_range"):
        filters["date_range"] = parsed["date_range"]
    return {"filters": filters, "offset": 0, "action": "filter"}


def _escape_predicate(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _spotlight_predicate(query, item_type, extension):
    clauses = []
    for term in re.findall(r"[^\W_]+", str(query or ""), flags=re.UNICODE):
        escaped = _escape_predicate(term)
        # Spotlight searches its indexed text; Stash only receives matching
        # paths and metadata, never document contents. Protected paths are
        # filtered before any file metadata is inspected or returned.
        clauses.append(
            f'(kMDItemFSName == "*{escaped}*"cd '
            f'|| kMDItemTextContent == "*{escaped}*"cd)'
        )
    if extension:
        clauses.append(f'kMDItemFSName == "*.{_escape_predicate(extension.lstrip("."))}"cd')
    content_types = {
        "video": 'kMDItemContentTypeTree == "public.movie"',
        "image": 'kMDItemContentTypeTree == "public.image"',
        "audio": 'kMDItemContentTypeTree == "public.audio"',
        "text": 'kMDItemContentTypeTree == "public.plain-text"',
    }
    if item_type in content_types:
        clauses.append(content_types[item_type])
    elif item_type == "file":
        clauses.append('kMDItemContentTypeTree == "public.item"')
    return " && ".join(clauses) if clauses else 'kMDItemFSName == "*"'


def _sensitive_path(path, home=None, storage_dir=None):
    candidate = Path(path).expanduser().resolve(strict=False)
    home = Path(home or Path.home()).resolve(strict=False)
    protected = [
        Path(storage_dir or storage_manager.STORAGE_DIR).resolve(strict=False),
        home / "Library",
        home / ".ssh",
        home / ".aws",
        home / ".config" / "gcloud",
        home / ".kube",
        Path("/System"), Path("/Library"), Path("/Applications"), Path("/Volumes"), Path("/private/var/db"),
        Path("/usr"), Path("/bin"), Path("/sbin"), Path("/etc"), Path("/dev"),
    ]
    for root in protected:
        root = root.resolve(strict=False)
        try:
            if os.path.commonpath((str(root), str(candidate))) == str(root):
                return True
        except ValueError:
            continue
    parts = {part.casefold() for part in candidate.parts}
    if {".ssh", ".aws", ".env", "keychain"} & parts:
        return True
    name = candidate.name.casefold()
    if (
        name == ".env" or name.startswith(".env.")
        or any(marker in name for marker in ("credential", "secret", "keychain", "private-key", "password", "token"))
        or candidate.suffix.casefold() in {".key", ".pem", ".p8", ".p12", ".pfx", ".p7b", ".keychain", ".crt", ".cer", ".der"}
        or name in {"id_rsa", "id_ed25519", "authorized_keys", "known_hosts"}
        or (name.startswith("id_") and name.endswith(".pub"))
        or name in {"auth.json", "passwd", "passwords", "tokens.json", "credentials.json"}
    ):
        return True
    return any(part.startswith(".env.") for part in parts)


def _excluded_search_path(path):
    """Skip development environments, package trees, and generated caches."""
    excluded = {
        ".venv", "venv", "env", "site-packages", "node_modules", ".git",
        "build", "dist", "__pycache__", ".cache", "caches", "cache",
        ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    }
    return any(part.casefold() in excluded for part in Path(path).parts)


def spotlight_search(query=None, item_type=None, extension=None, folder=None, runner=None):
    """Use mdfind for file names and metadata, then stat safe result paths only."""
    runner = runner or subprocess.run
    if folder:
        root = Path(os.path.expanduser(folder)).resolve(strict=False)
        if _sensitive_path(root):
            return {"results": [], "available": False, "permission_blocked": True, "protected_path": True}
        if not root.is_dir():
            return {"results": [], "available": True, "error": "That folder is unavailable."}
    else:
        root = None
    command = ["/usr/bin/mdfind", "-0"]
    if root:
        command.extend(["-onlyin", str(root)])
    command.append(_spotlight_predicate(query, item_type, extension))
    try:
        completed = runner(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=SPOTLIGHT_TIMEOUT_SECONDS, check=False,
        )
    except FileNotFoundError:
        return {"results": [], "available": False, "permission_blocked": False}
    except subprocess.TimeoutExpired:
        return {"results": [], "available": False, "permission_blocked": False, "timed_out": True}
    except OSError:
        return {"results": [], "available": False, "permission_blocked": False}

    stderr = completed.stderr.decode("utf-8", "replace") if isinstance(completed.stderr, bytes) else str(completed.stderr or "")
    if completed.returncode and re.search(r"permission|not authorized|privacy|denied", stderr, re.I):
        return {"results": [], "available": False, "permission_blocked": True}
    if completed.returncode:
        return {"results": [], "available": False, "permission_blocked": False, "error": "Spotlight could not complete the Mac search."}
    raw_output = completed.stdout or b""
    if isinstance(raw_output, bytes):
        paths = [part.decode("utf-8", "replace") for part in raw_output.split(b"\0") if part]
    else:
        paths = [part for part in str(raw_output).splitlines() if part]

    results = []
    for raw_path in paths:
        candidate = Path(raw_path).resolve(strict=False)
        if _sensitive_path(candidate) or _excluded_search_path(candidate):
            continue
        try:
            file_stat = candidate.stat(follow_symlinks=False)
        except OSError:
            continue
        if not candidate.is_file():
            continue
        suffix = candidate.suffix.casefold()
        if item_type == "file" and suffix in _MEDIA_EXTENSIONS:
            continue
        if item_type in _TYPE_EXTENSIONS and suffix not in _TYPE_EXTENSIONS[item_type]:
            continue
        if extension and suffix != f".{extension.lstrip('.').casefold()}":
            continue
        category = "file"
        for type_name, extensions in _TYPE_EXTENSIONS.items():
            if suffix in extensions:
                category = type_name
                break
        modified = datetime.fromtimestamp(file_stat.st_mtime).astimezone()
        results.append({
            "source": "mac",
            "name": candidate.name,
            "type": category,
            "size": file_stat.st_size,
            "modified_at": modified.isoformat(timespec="minutes"),
            "location": str(candidate.parent),
            "path": str(candidate),
        })
    return {"results": results, "available": True, "permission_blocked": False}


def resolve_safe_mac_file(path):
    """Revalidate a Spotlight result before an explicit OS/file action."""
    if not isinstance(path, str) or not os.path.isabs(path):
        raise ValueError("Choose a file from the Mac search results first.")
    candidate = Path(path).resolve(strict=True)
    if _sensitive_path(candidate):
        raise ValueError("Stash does not allow actions on protected system or private files.")
    file_stat = candidate.stat(follow_symlinks=False)
    if not candidate.is_file():
        raise ValueError("That search result is no longer a regular file.")
    return str(candidate)


def _item_date_in_range(item, date_range):
    if not date_range:
        return True
    item_date = local_calendar_date(item.get("created_at"))
    return bool(item_date and date_range["start"] <= item_date <= date_range["end"])


def _stash_result(item):
    category = tools.get_item_category(item)
    content = item.get("content") if isinstance(item.get("content"), str) else ""
    name = item.get("title") or item.get("original_name") or item.get("url")
    if not name and content.strip():
        name = content.strip().splitlines()[0][:100]
    name = name or category.rstrip("s").title()
    result = {
        "id": item.get("id"),
        "source": "stash",
        "name": str(name),
        "type": category.rstrip("s") if category != "audio" else "audio",
        "size": item.get("size"),
        "created_at": item.get("created_at"),
        "location": "Stash",
        "url": item.get("url") or item.get("page_url") or item.get("source_url"),
        "has_file": False,
    }
    if category == "text" and content.strip():
        result["content_preview"] = content.strip()[:240]
    stored_file = item.get("file")
    if isinstance(stored_file, str) and stored_file.strip():
        candidate = stored_file if os.path.isabs(stored_file) else os.path.join(storage_manager.BASE_DIR, stored_file)
        candidate = os.path.realpath(candidate)
        storage_root = os.path.realpath(storage_manager.STORAGE_DIR)
        for directory, route in (("media", "/media/"), ("videos", "/videos/")):
            media_root = os.path.realpath(os.path.join(storage_root, directory))
            try:
                if os.path.commonpath((media_root, candidate)) == media_root and candidate != media_root and os.path.isfile(candidate):
                    relative = os.path.relpath(candidate, media_root)
                    result["open_url"] = route + quote(relative, safe="/")
                    result["has_file"] = True
                    break
            except ValueError:
                continue
    return result


def search_everywhere(filters, offset=0, limit=PAGE_SIZE, spotlight_backend=None):
    """Search encrypted Stash metadata and safe Spotlight results, returning one page."""
    filters = filters if isinstance(filters, dict) else {}
    query = str(filters.get("query") or "").strip() or None
    item_type = tools.normalize_item_type(filters.get("type")) or None
    extension = filters.get("extension")
    date_range = filters.get("date_range") if isinstance(filters.get("date_range"), dict) else None
    folder = filters.get("folder") if isinstance(filters.get("folder"), str) else None
    places = filters.get("places")
    if places not in {"stash", "mac", "stash_and_mac"}:
        places = "mac" if folder else "stash"

    stash_items = []
    if places in {"stash", "stash_and_mac"}:
        stash_items = tools._search_items(
            storage_manager.load_items(), query=query, item_type=item_type,
            limit=None, fuzzy=True,
        )
    stash_results = [
        _stash_result(item) for item in stash_items
        if _item_date_in_range(item, date_range)
        and (not extension or str(item.get("original_name") or item.get("file") or "").casefold().endswith("." + extension.casefold().lstrip(".")))
    ]
    mac_search = {"results": [], "available": True, "permission_blocked": False}
    if places in {"mac", "stash_and_mac"}:
        backend = spotlight_backend or spotlight_search
        mac_search = backend(query=query, item_type=item_type, extension=extension, folder=folder)
    mac_results = [
        item for item in mac_search.get("results", [])
        if _item_date_in_range({"created_at": item.get("modified_at")}, date_range)
    ]

    all_results = stash_results + mac_results
    all_results.sort(
        key=lambda item: str(item.get("created_at") or item.get("modified_at") or ""),
        reverse=True,
    )
    total = len(all_results)
    source_counts = {
        "stash": len(stash_results),
        "mac": len(mac_results),
    }
    page = all_results[max(0, int(offset)):max(0, int(offset)) + max(1, min(int(limit), PAGE_SIZE))]
    type_label = item_type or "all types"
    if extension:
        type_label = f"{extension.upper()} files"
    date_label = (
        f" from {date_range['label']} ({date_range['start']} to {date_range['end']})"
        if date_range and date_range.get("label") else ""
    )
    places_label = {
        "stash": "Stash",
        "mac": "On your Mac",
        "stash_and_mac": "Stash and your Mac",
    }[places]
    if total:
        source_summary = []
        if places in {"stash", "stash_and_mac"}:
            source_summary.append(f"{source_counts['stash']} in Stash")
        if places in {"mac", "stash_and_mac"}:
            source_summary.append(f"{source_counts['mac']} on your Mac")
        result_word = "result" if total == 1 else "results"
        message = f"Found {total} {result_word} for {type_label}{date_label}: {', '.join(source_summary)}."
    else:
        message = f"No matches for {type_label}{date_label} in {places_label}. Try a broader search or remove a filter."
    if places in {"mac", "stash_and_mac"} and not mac_search.get("available"):
        if mac_search.get("protected_path"):
            mac_message = "Ava skipped that protected folder. Stash results are still available."
        elif mac_search.get("permission_blocked"):
            mac_message = "macOS blocked Spotlight access. Enable Full Disk Access for Stash in System Settings → Privacy & Security, then search again."
        elif mac_search.get("timed_out"):
            mac_message = "Spotlight took too long to answer. Stash results are still available; try the Mac search again."
        else:
            mac_message = "Spotlight is unavailable. Stash results are still available."
        message += " " + mac_message
    elif places in {"mac", "stash_and_mac"} and mac_search.get("error"):
        message += " " + mac_search["error"]

    context = {
        "query": query,
        "type": item_type,
        "extension": extension,
        "date_range": date_range,
        "folder": folder,
        "places": places,
    }
    return {
        "success": True,
        "message": message,
        "results": page,
        "count": total,
        "offset": max(0, int(offset)),
        "page_size": max(1, min(int(limit), PAGE_SIZE)),
        "has_more": max(0, int(offset)) + len(page) < total,
        "search_context": context,
        "search_summary": {
            "type": type_label,
            "date_range": date_range,
            "places": [
                label for include, label in (
                    (places in {"stash", "stash_and_mac"}, "In Stash"),
                    (places in {"mac", "stash_and_mac"}, "On your Mac"),
                ) if include
            ],
            "source_counts": source_counts,
        },
        "spotlight_permission_blocked": bool(mac_search.get("permission_blocked")),
        "source_counts": source_counts,
        "_conversation_refs": [
            {key: item[key] for key in ("id", "source", "path") if key in item}
            for item in all_results
            if item.get("source") != "stash" or item.get("id") is not None
        ],
    }
