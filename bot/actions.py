import random
import re
from datetime import date, datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from . import db
from .config import ADMIN_ID
from .generator import format_digest, format_post, plan_line
from .sources import Item, fetch_all

TOPIC_RE = re.compile(
    r"ии\b|нейросет|нейрон|искусственн|llm|gpt|модел|машинн|разработ|"
    r"программ|код\b|кода|сервер|облак|данн|процессор|видеокарт|чип|желез|"
    r"гаджет|безопасн|уязвим|open source|опенсорс|python|javascript|"
    r"алгоритм|робот|автоматизац|интернет|сети|софт|приложен|платформ",
    re.IGNORECASE,
)


def topical(rows):
    matched = [r for r in rows if TOPIC_RE.search(f"{r[2] or ''} {r[3] or ''}")]
    return matched or rows


def row_to_item(row) -> Item:
    _id, url, title, summary, source, rubric = row
    return Item(
        title=title or "",
        summary=summary or "",
        url=url or "",
        source=source or "",
        rubric=rubric or "news",
        published=None,
    )


async def refresh_cache() -> int:
    items = await fetch_all()
    return await db.save_items(items)


async def build_post(rubric: str | None = None) -> tuple[int | None, dict | None]:
    rows = await db.unused_rows(limit=40)
    if len(rows) < 5:
        await refresh_cache()
        rows = await db.unused_rows(limit=40)
    if not rows:
        return None, None

    today_rubric, _ = plan_line(date.today())
    wanted = rubric or today_rubric
    pool = topical(rows)
    matched = [r for r in pool if (r[5] or "") == wanted]
    pool = matched if matched else pool
    row = random.choice(pool[:15])
    item = row_to_item(row)
    data = format_post(item, wanted if matched else item.rubric)
    await db.mark_used(row[0])
    post_id = await db.create_post(data)
    return post_id, data


async def build_digest() -> tuple[int | None, dict | None]:
    rows = await db.unused_rows(limit=12)
    if len(rows) < 3:
        await refresh_cache()
        rows = await db.unused_rows(limit=12)
    if len(rows) < 3:
        return None, None
    items = [row_to_item(r) for r in topical(rows)[:4]]
    data = format_digest(items)
    if not data:
        return None, None
    for row in rows[:4]:
        await db.mark_used(row[0])
    post_id = await db.create_post(data)
    return post_id, data


async def target_channel() -> str:
    return await db.get_setting("channel", "")


async def admin_chat() -> int:
    stored = await db.get_setting("admin_id", "")
    if stored.isdigit():
        return int(stored)
    return ADMIN_ID


async def publish(bot: Bot, post_id: int, chat_id: str | None = None) -> bool:
    post = await db.get_post(post_id)
    if not post:
        return False
    channel = chat_id or await target_channel()
    if not channel:
        return False
    try:
        message = await bot.send_message(
            channel,
            post["text"],
            disable_web_page_preview=False,
        )
    except TelegramAPIError:
        return False
    await db.update_post(
        post_id,
        status="published",
        published_at=datetime.now().isoformat(timespec="seconds"),
        message_id=message.message_id,
    )
    return True
