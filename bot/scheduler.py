from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import db
from .actions import admin_chat, build_post, publish, refresh_cache, target_channel
from .keyboards import draft_kb

scheduler = AsyncIOScheduler(timezone=datetime.now().astimezone().tzinfo)


async def scheduled_post(bot) -> None:
    owner = await admin_chat()
    post_id, data = await build_post()
    if not post_id:
        if owner:
            await bot.send_message(owner, "⚠️ Не смог собрать пост: нет свежих новостей.")
        return

    auto = await db.get_setting("auto", "0") == "1"
    channel = await target_channel()
    if auto and channel and await publish(bot, post_id):
        if owner:
            await bot.send_message(owner, f"📤 Автопост ушёл в {channel}.")
        return

    if not owner:
        return
    if auto and not channel:
        await bot.send_message(owner, "⚠️ Автопостинг включён, но канал не задан.")
    await bot.send_message(
        owner,
        data["text"],
        reply_markup=draft_kb(post_id),
        disable_web_page_preview=False,
    )


async def refresh_job() -> None:
    await refresh_cache()


async def reschedule(bot) -> None:
    slots = await db.get_slots()
    scheduler.remove_all_jobs()
    for slot in slots:
        try:
            hour, minute = (int(x) for x in slot.split(":"))
        except ValueError:
            continue
        scheduler.add_job(
            scheduled_post,
            CronTrigger(hour=hour, minute=minute),
            args=[bot],
            id=f"post-{slot}",
            replace_existing=True,
        )
    scheduler.add_job(
        refresh_job,
        CronTrigger(hour=8, minute=0),
        id="refresh",
        replace_existing=True,
    )
