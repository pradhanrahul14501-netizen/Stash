#!/usr/bin/env python3
"""Read-only MCP tools for a local Stash library."""

import json
import os
import sys
from pathlib import Path


COPY_MAKER_HOME = Path(
    os.environ.get("COPY_MAKER_HOME", str(Path.home() / "copy-maker"))
).expanduser().resolve()
STORAGE_DIR = Path(
    os.environ.get("STASH_STORAGE_DIR", str(COPY_MAKER_HOME / "storage"))
).expanduser().resolve()
MEDIA_DIRS = [STORAGE_DIR / "media", STORAGE_DIR / "videos", STORAGE_DIR / "integrations" / "cursor"]


TOOLS = [
    {
        "name": "list_copy_maker_items",
        "description": "List recent items saved in the local Stash library. Returns names and metadata, not full text contents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "Optional type filter, such as text, image, audio, or video."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
            },
        },
    },
    {
        "name": "search_copy_maker_text",
        "description": "Search text items saved in Stash. Matching snippets are returned to Cursor.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "description": "Text to search for."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_copy_maker_text",
        "description": "Read the full text of one text item by its Stash item ID. The returned text is visible to Cursor.",
        "inputSchema": {
            "type": "object",
            "properties": {"item_id": {"type": "integer"}},
            "required": ["item_id"],
        },
    },
    {
        "name": "list_copy_maker_media",
        "description": "List local media files in Stash's media, video, and Cursor handoff folders. Returns file paths so the user can open them in Cursor.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Optional filename filter."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
            },
        },
    },
]


def read_items():
    if str(COPY_MAKER_HOME) not in sys.path:
        sys.path.insert(0, str(COPY_MAKER_HOME))
    try:
        from library_security import LibraryEncryptionError
        from storage_manager import load_items
    except ImportError as error:
        raise ValueError(
            f"Copy Maker's storage modules could not be loaded from {COPY_MAKER_HOME}."
        ) from error

    try:
        data = load_items(read_only=True)
    except LibraryEncryptionError as error:
        raise ValueError(
            "Copy Maker's encrypted Stash library could not be opened. "
            "Check Keychain access and library integrity."
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Copy Maker's Stash library could not be read.") from error

    if not isinstance(data, list):
        raise ValueError("Copy Maker's Stash library has an invalid format.")
    return data


def as_json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def list_items(args):
    type_filter = str(args.get("type", "")).strip().lower()
    limit = max(1, min(int(args.get("limit", 25)), 100))
    rows = []
    for item in reversed(read_items()):
        item_type = str(item.get("type", "file")).lower()
        if type_filter and item_type != type_filter:
            continue
        filename = item.get("original_name") or Path(str(item.get("file", ""))).name
        rows.append({
            "id": item.get("id"),
            "type": item_type,
            "name": filename or f"Copy {item.get('id', '')}",
            "created_at": item.get("created_at"),
            "size_bytes": item.get("size"),
        })
        if len(rows) >= limit:
            break
    return as_json_text(rows)


def search_text(args):
    query = str(args.get("query", "")).strip()
    if not query:
        raise ValueError("Enter text to search for.")
    limit = max(1, min(int(args.get("limit", 10)), 50))
    needle = query.casefold()
    results = []
    for item in reversed(read_items()):
        if str(item.get("type", "")).lower() != "text":
            continue
        content = item.get("content")
        if not isinstance(content, str) or needle not in content.casefold():
            continue
        index = content.casefold().find(needle)
        start = max(0, index - 100)
        end = min(len(content), index + len(query) + 160)
        results.append({
            "id": item.get("id"),
            "created_at": item.get("created_at"),
            "snippet": content[start:end],
        })
        if len(results) >= limit:
            break
    return as_json_text(results)


def get_text(args):
    try:
        requested_id = int(args.get("item_id"))
    except (TypeError, ValueError):
        raise ValueError("Provide a valid Stash item ID.")
    for item in read_items():
        try:
            item_id = int(item.get("id", -1))
        except (TypeError, ValueError):
            continue
        if item_id == requested_id and str(item.get("type", "")).lower() == "text":
            content = item.get("content")
            if isinstance(content, str):
                return content
            raise ValueError("That item does not contain readable text.")
    raise ValueError("That text item was not found.")


def list_media(args):
    query = str(args.get("query", "")).strip().casefold()
    limit = max(1, min(int(args.get("limit", 50)), 100))
    results = []
    for root in MEDIA_DIRS:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.name.startswith(".") or not path.is_file():
                continue
            resolved = path.resolve()
            if not any(resolved.is_relative_to(root.resolve()) for root in MEDIA_DIRS if root.exists()):
                continue
            if query and query not in path.name.casefold():
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            results.append({
                "name": path.name,
                "path": str(resolved),
                "size_bytes": stat.st_size,
                "modified_at": stat.st_mtime,
            })
            if len(results) >= limit:
                return as_json_text(results)
    return as_json_text(results)


def call_tool(name, args):
    handlers = {
        "list_copy_maker_items": list_items,
        "search_copy_maker_text": search_text,
        "get_copy_maker_text": get_text,
        "list_copy_maker_media": list_media,
    }
    handler = handlers.get(name)
    if not handler:
        raise ValueError(f"Unknown Stash tool: {name}")
    return handler(args)


def write_message(message):
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle_message(message):
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}
    if request_id is None:
        return

    if method == "initialize":
        write_message({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "copy-maker-library", "version": "1.0.0"},
            },
        })
    elif method == "ping":
        write_message({"jsonrpc": "2.0", "id": request_id, "result": {}})
    elif method == "tools/list":
        write_message({"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}})
    elif method == "tools/call":
        try:
            result = call_tool(str(params.get("name", "")), params.get("arguments") or {})
            write_message({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": result}], "isError": False},
            })
        except Exception as error:
            write_message({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": str(error)}], "isError": True},
            })
    else:
        write_message({
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        })


def main():
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if isinstance(message, dict):
                handle_message(message)
        except Exception as error:
            sys.stderr.write(f"Stash Cursor plug-in error: {error}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
