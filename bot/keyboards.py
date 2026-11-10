from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def draft_kb(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"pub:{post_id}"),
                InlineKeyboardButton(text="🔄 Переписать", callback_data=f"rew:{post_id}"),
            ],
            [
                InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"skip:{post_id}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del:{post_id}"),
            ],
        ]
    )
