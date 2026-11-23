import json
import sqlite3
from contextlib import closing
from pathlib import Path
from storage_manager import load_items
from app_paths import BASE_DIR as APP_BASE_DIR, STORAGE_DIR


BASE_DIR = Path(APP_BASE_DIR)
DATABASE_FILE = Path(STORAGE_DIR) / "copy_maker.db"


def connect():
    return sqlite3.connect(DATABASE_FILE)


def create_database():

    DATABASE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with closing(connect()) as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                original_name TEXT,
                file TEXT,
                source_url TEXT,
                page_url TEXT,
                created_at TEXT,
                metadata TEXT
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_items_type
            ON items(type)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_items_created_at
            ON items(created_at)
        """)

        conn.commit()


def import_clipboard():
    items = load_items()

    with closing(connect()) as conn:

        for item in items:

            item_id = str(
                item.get("id", "")
            )

            if not item_id:
                continue

            conn.execute("""
                INSERT OR REPLACE INTO items (
                    id,
                    type,
                    original_name,
                    file,
                    source_url,
                    page_url,
                    created_at,
                    metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item_id,
                item.get("type", "unknown"),
                item.get("original_name"),
                item.get("file"),
                item.get("source_url"),
                item.get("page_url"),
                item.get("created_at"),
                json.dumps(
                    item,
                    ensure_ascii=False
                )
            ))

        conn.commit()

    print(f"Imported {len(items)} records.")


if __name__ == "__main__":

    print("Creating Stash database...")

    create_database()

    import_clipboard()

    print()
    print("Database:", DATABASE_FILE)
    print("Done.")
