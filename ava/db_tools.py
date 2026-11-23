import sqlite3
from pathlib import Path
from app_paths import BASE_DIR as APP_BASE_DIR, STORAGE_DIR


BASE_DIR = Path(APP_BASE_DIR)
DATABASE_FILE = Path(STORAGE_DIR) / "copy_maker.db"


def connect():
    return sqlite3.connect(DATABASE_FILE)


def count_items(item_type=None):

    with connect() as conn:

        if item_type:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM items
                WHERE type = ?
                """,
                (item_type,)
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM items
                """
            ).fetchone()

    return row[0]


def latest_items(limit=5, item_type=None):

    with connect() as conn:

        if item_type:
            rows = conn.execute(
                """
                SELECT id, type, original_name, file, created_at
                FROM items
                WHERE type = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (item_type, limit)
            ).fetchall()

        else:
            rows = conn.execute(
                """
                SELECT id, type, original_name, file, created_at
                FROM items
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()

    return [
        {
            "id": row[0],
            "type": row[1],
            "original_name": row[2],
            "file": row[3],
            "created_at": row[4]
        }
        for row in rows
    ]


def database_stats():

    with connect() as conn:

        rows = conn.execute(
            """
            SELECT type, COUNT(*)
            FROM items
            GROUP BY type
            ORDER BY type
            """
        ).fetchall()

    return {
        item_type: count
        for item_type, count in rows
    }


# =========================================================
# FIND ITEMS BY DATE
# =========================================================

def find_by_date(date, item_type=None):

    start = f"{date}T00:00:00"
    end = f"{date}T23:59:59"

    with connect() as conn:

        if item_type:
            rows = conn.execute(
                """
                SELECT id, type, original_name, file, created_at
                FROM items
                WHERE created_at >= ?
                  AND created_at <= ?
                  AND type = ?
                ORDER BY created_at DESC
                """,
                (start, end, item_type)
            ).fetchall()

        else:
            rows = conn.execute(
                """
                SELECT id, type, original_name, file, created_at
                FROM items
                WHERE created_at >= ?
                  AND created_at <= ?
                ORDER BY created_at DESC
                """,
                (start, end)
            ).fetchall()

    return [
        {
            "id": row[0],
            "type": row[1],
            "original_name": row[2],
            "file": row[3],
            "created_at": row[4]
        }
        for row in rows
    ]


# =========================================================
# DATE RESOLUTION
# =========================================================

from datetime import datetime, timedelta


def resolve_date_phrase(phrase):

    if not phrase:
        return None

    phrase = phrase.strip().lower()

    today = datetime.now().date()

    if phrase == "today":
        return today.isoformat()

    if phrase == "yesterday":
        return (today - timedelta(days=1)).isoformat()

    if phrase in ("day before yesterday", "the day before yesterday"):
        return (today - timedelta(days=2)).isoformat()

    if phrase == "tomorrow":
        return (today + timedelta(days=1)).isoformat()

    return phrase


def search_items(
    query=None,
    item_type=None,
    source=None,
    date=None,
    limit=20
):
    """
    Search library items using multiple optional signals.

    AVA can search by:
    - query: filename, URL, page URL, or metadata
    - item_type: video, image, audio, text, file
    - source: website/source such as YouTube
    - date: YYYY-MM-DD
    """

    query = (query or "").strip()
    item_type = (item_type or "").strip()
    source = (source or "").strip()
    date = (date or "").strip()

    conditions = []
    parameters = []

    # Text search
    if query:
        pattern = f"%{query}%"

        conditions.append(
            """
            (
                original_name LIKE ?
                OR file LIKE ?
                OR source_url LIKE ?
                OR page_url LIKE ?
                OR metadata LIKE ?
            )
            """
        )

        parameters.extend([
            pattern,
            pattern,
            pattern,
            pattern,
            pattern
        ])

    # Type filter
    if item_type:
        conditions.append("type = ?")
        parameters.append(item_type)

    # Source filter
    if source:
        source_pattern = f"%{source}%"

        conditions.append(
            """
            (
                source_url LIKE ?
                OR page_url LIKE ?
                OR metadata LIKE ?
                OR original_name LIKE ?
            )
            """
        )

        parameters.extend([
            source_pattern,
            source_pattern,
            source_pattern,
            source_pattern
        ])

    # Date filter
    if date:
        start = f"{date}T00:00:00"
        end = f"{date}T23:59:59"

        conditions.append(
            "created_at >= ? AND created_at <= ?"
        )

        parameters.extend([
            start,
            end
        ])

    # No search filters means there is nothing useful to search.
    if not conditions:
        return []

    where_clause = " AND ".join(conditions)

    sql = f"""
        SELECT id, type, original_name, file,
               source_url, page_url, created_at, metadata
        FROM items
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ?
    """

    parameters.append(limit)

    with connect() as conn:
        rows = conn.execute(
            sql,
            tuple(parameters)
        ).fetchall()

    return [
        {
            "id": row[0],
            "type": row[1],
            "original_name": row[2],
            "file": row[3],
            "source_url": row[4],
            "page_url": row[5],
            "created_at": row[6],
            "metadata": row[7]
        }
        for row in rows
    ]
