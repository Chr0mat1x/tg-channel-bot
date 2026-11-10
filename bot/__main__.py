import asyncio
import json
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

from . import db
from .config import (
    ADMIN_ID,
    BASE_DIR,
    BOT_TOKEN,
    CHANNEL_ID,
    PORT,
    SEED_AUTO,
    SEED_SLOTS,
    TZ_NAME,
    USE_WEBHOOK,
    WEBHOOK_BASE,
    WEBHOOK_SECRET,
)
from .handlers import fallback_router, router
from .scheduler import reschedule, scheduler
from .webhook import make_app

logger = logging.getLogger(__name__)


async def seed_settings() -> None:
    if CHANNEL_ID:
        await db.set_setting("channel", CHANNEL_ID)
    if ADMIN_ID:
        await db.set_setting("admin_id", str(ADMIN_ID))
    if SEED_AUTO in {"0", "1"}:
        await db.set_setting("auto", SEED_AUTO)
    if SEED_SLOTS:
        slots = [s.strip() for s in SEED_SLOTS.replace(" ", ",").split(",") if s.strip()]
        if slots:
            await db.set_setting("slots", json.dumps(sorted(set(slots))))


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(BASE_DIR / "bot.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не задан")

    await db.init()
    await seed_settings()

    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    dispatcher.include_router(fallback_router)
    scheduler.start()

    if USE_WEBHOOK:
        bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        url = f"{WEBHOOK_BASE}/webhook/{WEBHOOK_SECRET}"
        await bot.set_webhook(url, drop_pending_updates=True, allowed_updates=dispatcher.resolve_used_update_types())
        logger.info("Webhook установлен: %s (TZ=%s)", url, TZ_NAME)
        runner = web.AppRunner(make_app(bot, dispatcher))
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", PORT).start()
        logger.info("HTTP-сервер слушает порт %s", PORT)
        await reschedule(bot)
        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()
            await bot.session.close()
            scheduler.shutdown(wait=False)
        return

    try:
        while True:
            bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
            await reschedule(bot)
            try:
                await dispatcher.start_polling(bot)
            except Exception:
                logger.exception("Polling остановился, переподключение через 15 секунд")
            finally:
                await bot.session.close()
            await asyncio.sleep(15)
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
