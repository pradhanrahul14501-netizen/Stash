"""Read-only access to files inside a folder the user explicitly names."""

import os
import re
import stat
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path
from ava.file_actions import resolve_connected_folder


MAX_SEARCHED_FILES = 25000
MAX_RESULTS = 20
MAX_CONTENT_SEARCH_FILES = 300
MAX_CONTENT_SEARCH_CHARS = 65536
MAX_CONTENT_SEARCH_BYTES = 2 * 1024 * 1024
MAX_TEXT_FILE_BYTES = 1024 * 1024
MAX_SUMMARY_CHARS = 18000
TEXT_FILE_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".log",
    ".py", ".js", ".ts", ".html", ".css", ".xml", ".yaml", ".yml",
    ".toml", ".ini", ".rst",
}


def _read_bounded_text_file(path, max_chars, max_bytes=None):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError("Ava can only read a regular text file.")
        if max_bytes is not None and file_stat.st_size > max_bytes:
            raise ValueError("That file is too large to search safely.")
        file_handle = os.fdopen(descriptor, "r", encoding="utf-8")
        descriptor = None
        with file_handle:
            content = file_handle.read(max_chars + 1)
        return content, file_stat
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _resolve_folder(folder):
    if not isinstance(folder, str) or not folder.strip():
        raise ValueError("Please tell me which folder to search.")

    path = Path(os.path.expanduser(folder.strip())).resolve(strict=True)
    if not path.is_dir():
        raise ValueError("That path is not a folder I can search.")
    return path


def _make_content_snippet(content, positions):
    positions = [
        position for position in positions
        if isinstance(position, int) and 0 <= position < len(content)
    ]
    if not positions:
        return ""
    match_position = min(positions)
    start = max(0, match_position - 80)
    end = min(len(content), start + 240)
    snippet = " ".join(content[start:end].split())
    if start:
        snippet = "…" + snippet
    if end < len(content):
        snippet += "…"
    return snippet


def _match_content_terms(content, terms):
    """Match requested words with a small typo allowance for explicit content searches."""
    folded = content.casefold()
    positions = []
    missing_terms = []
    for term in terms:
        position = folded.find(term)
        if position >= 0:
            positions.append(position)
        else:
            missing_terms.append(term)

    if not missing_terms:
        return True, False, positions
    if len(terms) > 5:
        return False, False, []

    token_positions = {}
    for match in re.finditer(r"[^\W_]+", folded, flags=re.UNICODE):
        token_positions.setdefault(match.group(), match.start())
    tokens = tuple(token_positions)
    for term in missing_terms:
        if len(term) < 4:
            return False, False, []
        threshold = 0.75 if len(term) == 4 else 0.82
        close_token = next((
            token for token in tokens
            if abs(len(term) - len(token)) <= 1
            and SequenceMatcher(None, term, token).ratio() >= threshold
        ), None)
        if close_token is None:
            return False, False, []
        positions.append(token_positions[close_token])
    return True, True, positions


def _filename_close_match(relative_path, filename, terms):
    """Allow a conservative filename fallback for small spelling or ASR errors."""
    if not terms or len(terms) > 5:
        return False
    searchable_path = relative_path.casefold()
    filename_tokens = [
        token for token in re.findall(r"[^\W_]+", filename.casefold(), flags=re.UNICODE)
        if len(token) >= 3
    ]
    if not filename_tokens:
        return False

    for term in terms:
        if term in searchable_path:
            continue
        if len(term) < 3 or not any(
            SequenceMatcher(None, term, token).ratio() >= (0.75 if len(term) == 4 else 0.82)
            for token in filename_tokens
        ):
            return False
    return True


def search_local_files(
    folder,
    query=None,
    extension=None,
    limit=20,
    search_content=False,
    modified_date=None,
):
    """Search visible file names and, when explicitly requested, supported text content."""
    root = _resolve_folder(folder)
    terms = re.findall(r"[^\W_]+", str(query or "").casefold(), flags=re.UNICODE)
    suffix = str(extension or "").strip().casefold()
    if suffix and not suffix.startswith("."):
        suffix = f".{suffix}"
    if modified_date:
        try:
            modified_date = datetime.strptime(str(modified_date), "%Y-%m-%d").date().isoformat()
        except ValueError as error:
            raise ValueError("For a date filter, use today, yesterday, or a date like 2026-10-20.") from error

    matches = []
    filename_candidates = []
    scanned = 0
    content_files_scanned = 0
    content_scan_limited = False
    content_search_skipped_large_files = False
    content_search_truncated = False
    for current, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        directory_names[:] = [
            name for name in directory_names
            if not name.startswith(".") and not (current_path / name).is_symlink()
        ]

        for name in file_names:
            if name.startswith("."):
                continue
            candidate = current_path / name
            if candidate.is_symlink():
                continue

            try:
                file_stat = candidate.stat(follow_symlinks=False)
            except OSError:
                continue
            if not stat.S_ISREG(file_stat.st_mode):
                continue

            scanned += 1
            if scanned > MAX_SEARCHED_FILES:
                break
            file_modified_date = datetime.fromtimestamp(file_stat.st_mtime).astimezone().date().isoformat()
            if modified_date and file_modified_date != modified_date:
                continue
            if suffix and candidate.suffix.casefold() != suffix:
                continue

            relative_path = candidate.relative_to(root).as_posix()
            searchable = relative_path.casefold()
            # Keep filename hits in content searches too: a file may be relevant
            # because its title matches even when its format cannot be read here.
            filename_match = not terms or all(term in searchable for term in terms)
            content_match = False
            snippet = ""
            if (
                terms
                and search_content
                and candidate.suffix.casefold() in TEXT_FILE_EXTENSIONS
            ):
                if content_files_scanned >= MAX_CONTENT_SEARCH_FILES:
                    content_scan_limited = True
                else:
                    content_files_scanned += 1
                    try:
                        content, _ = _read_bounded_text_file(
                            candidate,
                            MAX_CONTENT_SEARCH_CHARS,
                            MAX_CONTENT_SEARCH_BYTES,
                        )
                        if len(content) > MAX_CONTENT_SEARCH_CHARS:
                            content_search_truncated = True
                            content = content[:MAX_CONTENT_SEARCH_CHARS]
                    except ValueError:
                        content = ""
                        if file_stat.st_size > MAX_CONTENT_SEARCH_BYTES:
                            content_search_skipped_large_files = True
                    except OSError:
                        content = ""
                    except UnicodeDecodeError:
                        content = ""
                    content_match, approximate_content_match, content_positions = (
                        _match_content_terms(content, terms) if content else (False, False, [])
                    )
                    if content_match:
                        snippet = _make_content_snippet(content, content_positions)

            if not filename_match and not content_match:
                if terms:
                    filename_candidates.append({
                        "name": name,
                        "path": relative_path,
                        "type": candidate.suffix.lstrip(".").upper() or "File",
                        "size": file_stat.st_size,
                        "modified_at": datetime.fromtimestamp(file_stat.st_mtime).astimezone().isoformat(timespec="minutes"),
                        "match_source": "filename",
                        "approximate_match": True,
                        "approximate_match_source": "filename",
                        "snippet": "",
                        "modified_date": file_modified_date,
                        "_modified": file_stat.st_mtime,
                    })
                continue

            match = {
                "name": name,
                "path": relative_path,
                "type": candidate.suffix.lstrip(".").upper() or "File",
                "size": file_stat.st_size,
                "modified_at": datetime.fromtimestamp(file_stat.st_mtime).astimezone().isoformat(timespec="minutes"),
                "match_source": "content" if content_match else "filename",
                "approximate_match": approximate_content_match if content_match else False,
                "approximate_match_source": "content" if content_match and approximate_content_match else None,
                "snippet": snippet,
                "modified_date": file_modified_date,
                "_modified": file_stat.st_mtime,
            }
            matches.append(match)

        if scanned > MAX_SEARCHED_FILES:
            break

    used_approximate_matches = False
    if not matches and filename_candidates:
        matches = [
            item for item in filename_candidates
            if _filename_close_match(item["path"], item["name"], terms)
        ]
        used_approximate_matches = bool(matches)
    matches.sort(key=lambda item: item["_modified"], reverse=True)
    capped_limit = max(1, min(int(limit), MAX_RESULTS))
    results = matches[:capped_limit]
    for item in results:
        item.pop("_modified", None)

    return {
        "folder": str(root),
        "modified_date": modified_date,
        "used_approximate_matches": used_approximate_matches,
        "used_approximate_content_matches": any(
            item.get("approximate_match_source") == "content" for item in matches
        ),
        "results": results,
        "count": len(matches),
        "scanned": min(scanned, MAX_SEARCHED_FILES),
        "scan_limited": scanned > MAX_SEARCHED_FILES,
        "content_scan_limited": content_scan_limited,
        "content_search_skipped_large_files": content_search_skipped_large_files,
        "content_search_truncated": content_search_truncated,
    }


def read_text_file(folder, relative_path):
    """Read a small supported text file without leaving the selected folder."""
    root = resolve_connected_folder(folder)
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("Tell me which file in that folder you want summarized.")

    supplied = Path(relative_path.strip())
    if supplied.is_absolute() or ".." in supplied.parts:
        raise ValueError("I can only read a file inside the folder you selected.")

    candidate = root / supplied
    current = root
    for part in supplied.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("I can’t read a file reached through a symbolic link.")

    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError("That file is outside the selected folder or is not a regular file.")
    if resolved.suffix.casefold() not in TEXT_FILE_EXTENSIONS:
        raise ValueError("I can summarize text, Markdown, CSV, JSON, and common source files for now.")

    try:
        content, file_stat = _read_bounded_text_file(
            resolved,
            MAX_SUMMARY_CHARS,
            MAX_TEXT_FILE_BYTES,
        )
    except UnicodeDecodeError as error:
        raise ValueError("That file is not readable as UTF-8 text.") from error
    except ValueError as error:
        if "too large" in str(error):
            raise ValueError("That file is too large for Ava to summarize safely (maximum 1 MB).") from error
        raise

    truncated = len(content) > MAX_SUMMARY_CHARS
    if truncated:
        content = content[:MAX_SUMMARY_CHARS]
    return {
        "name": resolved.name,
        "path": resolved.relative_to(root).as_posix(),
        "size": file_stat.st_size,
        "content": content,
        "truncated": truncated,
    }
