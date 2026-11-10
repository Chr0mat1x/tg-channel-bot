import html
import json
import logging
from datetime import date, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import CallbackQuery, Message

from . import db
from .actions import build_digest, build_post, publish, refresh_cache, target_channel
from .config import ADMIN_ID
from .generator import RUBRICS, make_ideas, plan_line
from .keyboards import draft_kb

router = Router()
fallback_router = Router()
logger = logging.getLogger(__name__)


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, **kwargs) -> bool:
        if not event.from_user:
            return False
        if ADMIN_ID and event.from_user.id == ADMIN_ID:
            return True
        stored = await db.get_setting("admin_id", "")
        if stored.isdigit():
            allowed = int(stored) == event.from_user.id
            if not allowed:
                logger.warning(
                    "Отказ доступа: user_id=%s, текст=%r",
                    event.from_user.id,
                    getattr(event, "text", None),
                )
            return allowed
        return isinstance(event, Message) and (event.text or "").startswith("/start")


router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


async def status_text() -> str:
    channel = await target_channel()
    auto = await db.get_setting("auto", "0") == "1"
    slots = await db.get_slots()
    st = await db.stats()
    return (
        "<b>Состояние бота</b>\n\n"
        f"Канал: {html.escape(channel) if channel else 'не задан (/channel @name)'}\n"
        f"Автопостинг: {'включён' if auto else 'выключен'} (/auto on)\n"
        f"Слоты публикаций: {', '.join(slots)}\n\n"
        f"Опубликовано: {st['published']}\n"
        f"Черновиков в очереди: {st['drafts']}\n"
        f"Новостей в кэше: {st['cached']} (неиспользованных {st['unused']})"
    )


async def send_draft(bot: Bot, chat_id: int, post_id: int, data: dict, header: str = "") -> None:
    text = f"{header}\n\n{data['text']}" if header else data["text"]
    await bot.send_message(
        chat_id,
        text,
        reply_markup=draft_kb(post_id),
        disable_web_page_preview=False,
    )


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if not ADMIN_ID and not await db.get_setting("admin_id", ""):
        await db.set_setting("admin_id", str(message.from_user.id))
        await message.answer("Ты назначен владельцем бота.")
    await message.answer(
        "Бот-редактор канала. Собирает посты из свежих ИТ-новостей, "
        "присылает черновик, публикует по кнопке или по расписанию.\n\n"
        + await status_text()
        + "\n\n/help — список команд",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>Команды</b>\n"
        "/post — собрать черновик сейчас\n"
        "/digest — собрать дайджест из нескольких новостей\n"
        "/auto on|off — автопубликация по слотам\n"
        "/schedule 10:00,15:00,19:00 — время публикаций\n"
        "/channel @name или -100… — канал\n"
        "/plan — контент-план на неделю\n"
        "/ideas — идеи тем\n"
        "/queue — очередь черновиков\n"
        "/stats — статистика\n"
        "/refresh — обновить новости\n\n"
        "Кнопки под черновиком: опубликовать, переписать, пропустить, удалить."
    )


@router.message(Command("channel"))
async def cmd_channel(message: Message, command: CommandObject) -> None:
    arg = (command.args or "").strip()
    if not arg:
        await message.answer(f"Текущий канал: {await target_channel() or 'не задан'}")
        return
    try:
        chat = await message.bot.get_chat(arg)
    except Exception as error:
        await message.answer(f"Не нашёл канал: {error}")
        return
    await db.set_setting("channel", str(chat.id))
    rights = ""
    try:
        member = await message.bot.get_chat_member(chat.id, (await message.bot.me()).id)
        if member.status not in ("administrator", "creator"):
            rights = "\n⚠️ Бот не админ канала — публикация не сработает."
    except Exception:
        pass
    await message.answer(f"Канал сохранён: {chat.title or chat.id}{rights}")


@router.message(Command("auto"))
async def cmd_auto(message: Message, command: CommandObject) -> None:
    arg = (command.args or "").strip().lower()
    if arg not in {"on", "off"}:
        await message.answer("Использование: /auto on или /auto off")
        return
    await db.set_setting("auto", "1" if arg == "on" else "0")
    await message.answer(f"Автопостинг {'включён' if arg == 'on' else 'выключен'}.")


@router.message(Command("schedule"))
async def cmd_schedule(message: Message, command: CommandObject) -> None:
    raw = (command.args or "").replace(" ", ",")
    slots = [s.strip() for s in raw.split(",") if s.strip()]
    valid: list[str] = []
    for slot in slots:
        try:
            hour, minute = (int(x) for x in slot.split(":"))
            if 0 <= hour < 24 and 0 <= minute < 60:
                valid.append(f"{hour:02d}:{minute:02d}")
        except ValueError:
            await message.answer(f"Не понял время «{slot}». Формат: /schedule 10:00,15:00,19:00")
            return
    if not valid:
        await message.answer("Использование: /schedule 10:00,15:00,19:00")
        return
    await db.set_setting("slots", json.dumps(sorted(set(valid))))
    from .scheduler import reschedule

    await reschedule(message.bot)
    await message.answer("Время публикаций: " + ", ".join(sorted(set(valid))))


@router.message(Command("refresh"))
async def cmd_refresh(message: Message) -> None:
    added = await refresh_cache()
    await message.answer(f"Новости обновлены, новых записей: {added}.")


@router.message(Command("post"))
async def cmd_post(message: Message) -> None:
    note = await message.answer("Собираю черновик…")
    post_id, data = await build_post()
    await note.delete()
    if not post_id:
        await message.answer("Свежих новостей не нашлось. Попробуй /refresh позже.")
        return
    await send_draft(message.bot, message.chat.id, post_id, data, "📝 Черновик")


@router.message(Command("digest"))
async def cmd_digest(message: Message) -> None:
    note = await message.answer("Собираю дайджест…")
    post_id, data = await build_digest()
    await note.delete()
    if not post_id:
        await message.answer("Недостаточно новостей для дайджеста.")
        return
    await send_draft(message.bot, message.chat.id, post_id, data, "🗞 Дайджест")


@router.message(Command("plan"))
async def cmd_plan(message: Message) -> None:
    slots = await db.get_slots()
    today = date.today()
    lines = ["<b>Контент-план на неделю</b>", ""]
    for offset in range(7):
        day = today + timedelta(days=offset)
        rubric, label = plan_line(day)
        marker = " (сегодня)" if offset == 0 else ""
        lines.append(
            f"<b>{day.strftime('%d.%m')}, "
            f"{['Пн','Вт','Ср','Чт','Пт','Сб','Вс'][day.weekday()]}</b>{marker}\n"
            f"{label}\nСлоты: {', '.join(slots)}"
        )
        lines.append("")
    await message.answer("\n".join(lines))


@router.message(Command("ideas"))
async def cmd_ideas(message: Message) -> None:
    rows = await db.unused_rows(limit=15)
    if not rows:
        await refresh_cache()
        rows = await db.unused_rows(limit=15)
    from .actions import row_to_item

    ideas = make_ideas([row_to_item(r) for r in rows], count=5)
    if not ideas:
        await message.answer("Идей пока нет — кэш пуст, обнови новости: /refresh")
        return
    text = "<b>Идеи тем</b>\n\n" + "\n".join(f"{i}. {html.escape(t)}" for i, t in enumerate(ideas, 1))
    await message.answer(text)


@router.message(Command("queue"))
async def cmd_queue(message: Message) -> None:
    posts = await db.pending_posts(limit=10)
    if not posts:
        await message.answer("Очередь пуста.")
        return
    lines = ["<b>Черновики</b>", ""]
    for post_id, title, created in posts:
        lines.append(f"• #{post_id} {html.escape(title or 'без заголовка')} — {created[:16]}")
    await message.answer("\n".join(lines))


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    await message.answer(await status_text())


@router.callback_query(F.data.startswith("pub:"))
async def cb_publish(callback: CallbackQuery) -> None:
    post_id = int(callback.data.split(":")[1])
    channel = await target_channel()
    if not channel:
        await callback.answer("Сначала задай канал: /channel @name", show_alert=True)
        return
    ok = await publish(callback.bot, post_id)
    if not ok:
        await callback.answer(
            "Не опубликовалось. Проверь, что бот администратор канала.", show_alert=True
        )
        return
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"✅ Опубликовано (пост #{post_id}).")
    await callback.answer("Готово")


@router.callback_query(F.data.startswith("rew:"))
async def cb_rewrite(callback: CallbackQuery) -> None:
    old_id = int(callback.data.split(":")[1])
    await db.update_post(old_id, status="skipped")
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Переписываю")
    post_id, data = await build_post()
    if not post_id:
        await callback.message.answer("Новых новостей нет — черновик остался прежним.")
        return
    await send_draft(callback.bot, callback.message.chat.id, post_id, data, "🔄 Другой вариант")


@router.callback_query(F.data.startswith("skip:"))
async def cb_skip(callback: CallbackQuery) -> None:
    post_id = int(callback.data.split(":")[1])
    await db.update_post(post_id, status="skipped")
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Пропущено")


@router.callback_query(F.data.startswith("del:"))
async def cb_delete(callback: CallbackQuery) -> None:
    post_id = int(callback.data.split(":")[1])
    await db.update_post(post_id, status="deleted")
    if callback.message:
        await callback.message.delete()
    await callback.answer("Удалено")


@fallback_router.message()
async def on_unhandled(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else None
    logger.info("Необработанное сообщение: user_id=%s, текст=%r", user_id, message.text)
    owner = await db.get_setting("admin_id", "")
    if owner.isdigit() and user_id == int(owner):
        await message.answer(
            "Не понял команду. Список команд — /help.\n"
            "Привязка канала: /channel @название"
        )
    else:
        await message.answer("Это приватный бот. Отправь /start")
