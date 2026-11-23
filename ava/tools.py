from urllib.parse import unquote
import os
import re
from difflib import SequenceMatcher
from datetime import datetime
from storage_manager import delete_item as delete_stored_item, load_items, update_items_fields
from app_paths import STORAGE_DIR

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TYPE_ALIASES = {
    "videos": "video",
    "photos": "image",
    "photo": "image",
    "pictures": "image",
    "picture": "image",
    "images": "image",
    "notes": "text",
    "note": "text",
    "messages": "text",
    "documents": "file",
    "document": "file",
    "files": "file",
    "links": "link",
    "urls": "link",
    "webpage": "link",
    "webpages": "link",
    "audio": "audio",
    "music": "audio",
}
IMAGE_EXTENSIONS = {".avif", ".bmp", ".gif", ".heic", ".icns", ".jpeg", ".jpg", ".png", ".svg", ".tif", ".tiff", ".webp"}
VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".webm"}
AUDIO_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".wma"}
LINK_EXTENSIONS = {".url", ".webloc"}
URL_PATTERN = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


def normalize_item_type(item_type):
    value = str(item_type or "").strip().lower()
    return TYPE_ALIASES.get(value, value)


def get_item_category(item):
    actual_type = normalize_item_type(item.get("type"))
    file_name = str(item.get("file") or item.get("original_name") or "")
    extension = os.path.splitext(file_name.split("?", 1)[0])[1].lower()
    mime_type = str(item.get("mime_type") or "").lower()
    content = str(item.get("content") or "")

    if actual_type == "video" or extension in VIDEO_EXTENSIONS or mime_type.startswith("video/"):
        return "videos"
    if actual_type == "image" or extension in IMAGE_EXTENSIONS or mime_type.startswith("image/"):
        return "images"
    if actual_type == "audio" or extension in AUDIO_EXTENSIONS or mime_type.startswith("audio/"):
        return "audio"
    if actual_type == "link" or extension in LINK_EXTENSIONS or (not item.get("file") and URL_PATTERN.search(content)):
        return "links"
    if actual_type in ("text", "note"):
        return "text"
    return "files"


def item_matches_type(item, item_type):
    requested_type = normalize_item_type(item_type)
    if not requested_type:
        return True

    actual_type = normalize_item_type(item.get("type"))
    category = get_item_category(item)

    if requested_type == "file":
        return category == "files"
    if requested_type == "image":
        return category == "images"
    if requested_type == "video":
        return category == "videos"
    if requested_type == "audio":
        return category == "audio"
    if requested_type == "link":
        return category == "links"
    if requested_type == "text":
        return actual_type in ("text", "note")
    return actual_type == requested_type


def load_library():
    return load_items()


def find_videos():
    items = load_library()

    videos = [
        item for item in items
        if item.get("type") == "video"
    ]

    return videos



def search_library(
    query=None,
    item_type=None,
    source=None,
    date=None,
    limit=20,
    fuzzy=False
):
    """
    Search the canonical Stash library.
    Fuzzy matching is optional and disabled for other operations.
    """
    query = (query or "").strip().lower()
    item_type = normalize_item_type(item_type)
    source = (source or "").strip().lower()
    date = (date or "").strip()

    return _search_items(
        load_library(), query, item_type, source, date, limit,
        fuzzy=fuzzy
    )


def _search_items(
    items, query=None, item_type=None, source=None, date=None,
    limit=20, fuzzy=False
):
    query = (query or "").strip().lower()
    item_type = normalize_item_type(item_type)
    source = (source or "").strip().lower()
    date = (date or "").strip()
    results = []

    synonym_groups = [
        {"dog", "dogs", "puppy", "puppies", "canine"},
        {"cat", "cats", "kitten", "kittens", "feline"},
        {"clip", "clips", "video", "videos", "footage"},
        {"photo", "photos", "picture", "pictures", "image", "images"},
        {"song", "songs", "music", "audio", "track", "tracks"},
        {"website", "webpage", "webpages", "link", "links", "url", "urls"},
        {"note", "notes", "text", "message", "messages"},
    ]
    synonyms = {}
    for group in synonym_groups:
        for word in group:
            synonyms[word] = group

    ignored = {
        "find", "show", "get", "my", "me", "the", "a", "an",
        "that", "this", "saved", "of", "for", "from", "please"
    }

    def normalize_word(word):
        word = word.lower()
        if len(word) > 4 and word.endswith("ies"):
            return word[:-3] + "y"
        if len(word) > 4 and word.endswith("ing"):
            return word[:-3]
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            return word[:-1]
        return word

    type_words = {
        "video": {"clip", "clips", "video", "videos", "footage"},
        "image": {"photo", "photos", "picture", "pictures", "image", "images", "screenshot", "screenshots"},
        "audio": {"song", "songs", "music", "audio", "track", "tracks"},
        "text": {"note", "notes", "text", "message", "messages"},
        "link": {"website", "webpage", "webpages", "link", "links", "url", "urls"},
        "file": {"file", "files", "document", "documents"},
    }.get(item_type, set())

    query_words = [
        normalize_word(word)
        for word in re.findall(r"[a-z0-9]+", query)
        if word not in ignored
        and normalize_word(word) not in type_words
    ]

    # Type words such as "videos" describe the filter, not item text. Once
    # removed, an empty query-word list means a type/date-only search.
    search_text_query = bool(query_words)

    def item_local_date(value):
        value = str(value or "").strip()
        if not value:
            return None
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value[:10] if len(value) >= 10 else None
        if timestamp.tzinfo is not None:
            timestamp = timestamp.astimezone()
        return timestamp.date().isoformat()

    for item in items:
        if not item_matches_type(item, item_type):
            continue

        created_at = str(item.get("created_at", ""))
        if date and item_local_date(created_at) != date:
            continue

        fields = [
            str(item.get("original_name", "")),
            str(item.get("title", "")),
            str(item.get("source_url", "")),
            str(item.get("page_url", "")),
            str(item.get("url", "")),
            str(item.get("metadata", "")),
            str(item.get("content", "")),
            str(item.get("organized_category", "")),
        ]
        # Decode URL-encoded titles and metadata before searching.
        decoded_fields = [unquote(field) for field in fields]
        searchable = " ".join(decoded_fields).lower()

        if source and source not in searchable:
            continue

        score = 0

        if query and search_text_query:
            compact_query = re.sub(r"[\W_]+", "", query)
            compact_text = re.sub(r"[\W_]+", "", searchable)

            exact_match = (
                query in searchable
                or (compact_query and compact_query in compact_text)
            )

            if exact_match:
                score = 100
            elif not fuzzy:
                continue
            else:
                words = set(
                    normalize_word(word)
                    for word in re.findall(r"[a-z0-9]+", searchable)
                )
                words.add(normalize_word(str(item.get("type", ""))))

                matched = 0

                for query_word in query_words:
                    alternatives = synonyms.get(query_word, {query_word})
                    alternatives = {
                        normalize_word(word) for word in alternatives
                    }

                    found = bool(alternatives & words)

                    if not found and len(query_word) >= 4:
                        found = any(
                            SequenceMatcher(None, query_word, target).ratio() >= 0.86
                            for target in words
                            if len(target) >= 4
                        )

                    if found:
                        matched += 1

                if not query_words or matched == 0:
                    continue

                coverage = matched / len(query_words)
                if coverage < 0.5:
                    continue

                score = 50 + 40 * coverage

                title_text = " ".join(fields[:2]).lower()
                if any(word in title_text for word in query_words):
                    score += 5

        # Keep stored data unchanged; decode titles in returned results.
        results.append((score, item))

    for _, item in results:
        for key in ("title", "original_name"):
            value = item.get(key)
            if isinstance(value, str):
                item[key] = unquote(value)

    if fuzzy and query:
        results.sort(
            key=lambda pair: (
                pair[0],
                str(pair[1].get("created_at", ""))
            ),
            reverse=True
        )
    else:
        results.sort(
            key=lambda pair: str(pair[1].get("created_at", "")),
            reverse=True
        )

    matched_items = [item for _, item in results]
    return matched_items if limit is None else matched_items[:limit]



def library_stats():
    stats = {"videos": 0, "images": 0, "audio": 0, "text": 0, "links": 0, "files": 0}
    for item in load_library():
        stats[get_item_category(item)] += 1
    return stats

def find_latest_video():
    videos = find_videos()

    if not videos:
        return None

    videos.sort(
        key=lambda x: x.get("created_at", ""),
        reverse=True
    )

    return videos[0]


def get_library_item(item_id):
    if item_id is None:
        return None

    matches = [
        item for item in load_library()
        if str(item.get("id")) == str(item_id)
    ]
    return matches[0] if len(matches) == 1 else None


def delete_library_item(item_id):
    if item_id is None:
        return {"success": False, "message": "No item was selected."}

    items = load_library()
    matches = [
        item for item in items
        if str(item.get("id")) == str(item_id)
    ]
    if len(matches) != 1:
        return {"success": False, "message": "I couldn't identify one saved item to delete."}

    item = matches[0]
    file_path = item.get("file")
    resolved_path = None
    if file_path:
        candidate = file_path if os.path.isabs(file_path) else os.path.join(BASE_DIR, file_path)
        resolved_path = os.path.realpath(candidate)
        storage_root = os.path.realpath(STORAGE_DIR)
        try:
            is_in_storage = os.path.commonpath((storage_root, resolved_path)) == storage_root
        except ValueError:
            is_in_storage = False
        if not is_in_storage or resolved_path == storage_root:
            return {"success": False, "message": "I can't safely delete a file outside Stash storage."}
        if os.path.exists(resolved_path) and not os.path.isfile(resolved_path):
            return {"success": False, "message": "The saved path isn't a file, so I left it unchanged."}

    deleted = delete_stored_item(item_id, expected_item=item)
    if deleted is None:
        return {"success": False, "message": "That saved item changed before I could delete it."}

    label = item.get("title") or item.get("original_name") or get_item_category(item).rstrip("s")
    return {
        "success": True,
        "message": f"Deleted {label}.",
        "deleted_id": item.get("id"),
        "deleted_type": item.get("type")
    }


def delete_video(video):
    return delete_library_item(video.get("id") if isinstance(video, dict) else video)


# =========================================================
# AVA - ORGANIZE LIBRARY ITEMS
# =========================================================

def get_arrange_category(item):
    return get_item_category(item)


def get_today_items():
    today = datetime.now().strftime("%Y-%m-%d")
    return search_library(date=today, limit=None)


def preview_organize_items(item_type=None, date=None, query=None):
    items = _search_items(
        load_library(),
        query=query,
        item_type=item_type,
        date=date,
        limit=None
    )
    categories = {}
    for item in items:
        category = get_item_category(item)
        categories[category] = categories.get(category, 0) + 1

    return {
        "success": True,
        "date": date,
        "type": normalize_item_type(item_type) or None,
        "count": len(items),
        "categories": categories,
        "items": [
            {
                "id": item.get("id"),
                "type": item.get("type"),
                "title": item.get("title") or item.get("original_name") or str(item.get("content") or "")[:100],
                "created_at": item.get("created_at")
            }
            for item in items[:8]
        ]
    }


def organize_items(item_type=None, date=None, query=None):
    items = load_library()
    selected_items = _search_items(
        items,
        query=query,
        item_type=item_type,
        date=date,
        limit=None
    )
    categories = {}
    updates_by_id = {}
    for item in selected_items:
        category = get_item_category(item)
        categories[category] = categories.get(category, 0) + 1
        if item.get("id") is not None:
            updates_by_id[str(item["id"])] = {"organized_category": category}

    if updates_by_id:
        update_items_fields(updates_by_id)

    return {
        "success": True,
        "message": (
            f"Organized {len(selected_items)} item(s) by type in your library: "
            + ", ".join(f"{count} {category}" for category, count in categories.items())
            + "."
        ),
        "organized_count": len(selected_items),
        "categories": categories,
        "date": date,
        "type": normalize_item_type(item_type) or None
    }


def preview_arrange_today():
    today = datetime.now().strftime("%Y-%m-%d")
    return preview_organize_items(date=today)


def arrange_today():
    today = datetime.now().strftime("%Y-%m-%d")
    return organize_items(date=today)
