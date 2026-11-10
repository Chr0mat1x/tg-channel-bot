import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
_db_override = os.getenv("DB_PATH", "").strip()
DB_PATH = Path(_db_override) if _db_override else BASE_DIR / "bot.db"

PORT = int(os.getenv("PORT", "8080"))
TZ_NAME = os.getenv("TZ", "Asia/Dubai")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "local-secret")
_bases = [os.getenv("RENDER_EXTERNAL_URL", ""), os.getenv("WEBHOOK_URL", "")]
WEBHOOK_BASE = next((b.strip().rstrip("/") for b in _bases if b.strip()), "")
USE_WEBHOOK = bool(WEBHOOK_BASE)
SEED_AUTO = os.getenv("AUTO", "").strip()
SEED_SLOTS = os.getenv("SLOTS", "").strip()

DEFAULT_SLOTS = ["10:00", "15:00", "19:00"]
DEFAULT_TONE = "tech"

TOPIC_HINTS = (
    "ИИ, нейросети, LLM, разработка, open source, железо, кибербезопасность, "
    "продукты и инструменты для разработчиков"
)

SYSTEM_STYLE = (
    "Пиши по-русски, живо и по делу, без канцелярита и без воды. "
    "Абзацы короткие, максимум 900 символов на пост. Не выдумывай факты: "
    "только то, что есть в источнике, иначе формулируй как вопрос."
)
