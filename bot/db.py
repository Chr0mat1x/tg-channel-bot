import json
from datetime import datetime

import aiosqlite

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    source TEXT,
    rubric TEXT,
    published TEXT,
    added_at TEXT NOT NULL,
    used INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    rubric TEXT,
    title TEXT,
    url TEXT,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    published_at TEXT,
    message_id INTEGER
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


async def init() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def set_setting(key: str, value: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await db.commit()


async def get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
    return row[0] if row else default


async def get_slots() -> list[str]:
    raw = await get_setting("slots", '["10:00", "15:00", "19:00"]')
    try:
        slots = json.loads(raw)
    except json.JSONDecodeError:
        return ["10:00", "15:00", "19:00"]
    return [s for s in slots if isinstance(s, str)]


async def save_items(items) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    added = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for item in items:
            cursor = await db.execute(
                "INSERT OR IGNORE INTO items(url, title, summary, source, rubric, published, added_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    item.url,
                    item.clean_title,
                    item.summary,
                    item.source,
                    item.rubric,
                    item.published.isoformat() if item.published else None,
                    now,
                ),
            )
            added += cursor.rowcount
        await db.commit()
    return added


async def unused_rows(limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, url, title, summary, source, rubric FROM items WHERE used = 0 "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return await cursor.fetchall()


async def mark_used(item_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE items SET used = 1 WHERE id = ?", (item_id,))
        await db.commit()


async def create_post(data: dict, status: str = "draft") -> int:
    now = datetime.now().isoformat(timespec="seconds")
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO posts(text, rubric, title, url, source, status, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (
                data.get("text", ""),
                data.get("rubric", ""),
                data.get("title", ""),
                data.get("url", ""),
                data.get("source", ""),
                status,
                now,
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def get_post(post_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, text, rubric, title, url, source, status FROM posts WHERE id = ?",
            (post_id,),
        )
        row = await cursor.fetchone()
    if not row:
        return None
    keys = ("id", "text", "rubric", "title", "url", "source", "status")
    return dict(zip(keys, row))


async def update_post(post_id: int, **fields) -> None:
    if not fields:
        return
    columns = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [post_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE posts SET {columns} WHERE id = ?", values)
        await db.commit()


async def pending_posts(limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, title, created_at FROM posts WHERE status = 'draft' "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return await cursor.fetchall()


async def stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT status, COUNT(*) FROM posts GROUP BY status"
        )
        rows = await cursor.fetchall()
        cursor = await db.execute("SELECT COUNT(*) FROM items")
        cached = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM items WHERE used = 0")
        unused = (await cursor.fetchone())[0]
    counts = {status: count for status, count in rows}
    return {
        "published": counts.get("published", 0),
        "drafts": counts.get("draft", 0),
        "skipped": counts.get("skipped", 0),
        "cached": cached,
        "unused": unused,
    }
