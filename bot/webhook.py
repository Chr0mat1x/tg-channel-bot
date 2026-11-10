import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiohttp import web

from . import db
from .actions import build_post, publish, target_channel
from .config import TZ_NAME, WEBHOOK_SECRET
from .keyboards import draft_kb

logger = logging.getLogger(__name__)


def _authorized(request: web.Request) -> bool:
    return request.match_info.get("secret") == WEBHOOK_SECRET


async def health(request: web.Request) -> web.Response:
    return web.Response(text="ok")


async def on_webhook(request: web.Request) -> web.Response:
    if not _authorized(request):
        return web.Response(status=403, text="forbidden")
    data = await request.json()
    update = Update.model_validate(data)
    await request.app["dispatcher"].feed_update(request.app["bot"], update)
    return web.Response(text="ok")


async def run_due_slot(bot: Bot) -> str:
    if await db.get_setting("auto", "0") != "1":
        return "auto off"
    channel = await target_channel()
    if not channel:
        return "channel not set"

    now = datetime.now(ZoneInfo(TZ_NAME))
    slots = await db.get_slots()
    due = [s for s in slots if s <= now.strftime("%H:%M")]
    if not due:
        return "not due"
    key = f"{now.date().isoformat()} {due[-1]}"
    if await db.get_setting("last_slot", "") == key:
        return "already posted"

    post_id, data = await build_post()
    if not post_id:
        return "no news"
    if not await publish(bot, post_id):
        return "publish failed"
    await db.set_setting("last_slot", key)
    return f"published {post_id}"


async def on_tick(request: web.Request) -> web.Response:
    if not _authorized(request):
        return web.Response(status=403, text="forbidden")
    try:
        result = await run_due_slot(request.app["bot"])
    except Exception:
        logger.exception("Ошибка /tick")
        return web.Response(status=500, text="error")
    return web.Response(text=result)


async def on_draft(request: web.Request) -> web.Response:
    if not _authorized(request):
        return web.Response(status=403, text="forbidden")
    bot: Bot = request.app["bot"]
    owner = await db.get_setting("admin_id", "")
    post_id, data = await build_post()
    if not post_id or not owner.isdigit():
        return web.Response(status=409, text="cannot build")
    await bot.send_message(
        int(owner),
        data["text"],
        reply_markup=draft_kb(post_id),
        disable_web_page_preview=False,
    )
    return web.Response(text=f"draft {post_id}")


def make_app(bot: Bot, dispatcher: Dispatcher) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app["dispatcher"] = dispatcher
    app.router.add_get("/", health)
    app.router.add_post("/webhook/{secret}", on_webhook)
    app.router.add_get("/tick/{secret}", on_tick)
    app.router.add_post("/tick/{secret}", on_tick)
    app.router.add_get("/draft/{secret}", on_draft)
    return app
