import html
import random
import re
from datetime import date

from .config import TOPIC_HINTS
from .sources import Item, clean_text

WORD_RE = re.compile(r"[А-Яа-яЁёA-Za-z]{3,}")
SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[«\"(A-ZА-ЯЁ0-9])")
CUT_TAIL = re.compile(r"(\.\.\.|…)\s*$")

STOP_WORDS = {
    "это", "как", "для", "что", "или", "его", "она", "они", "было", "были",
    "если", "при", "уже", "так", "все", "всё", "чем", "над", "под", "без",
    "the", "and", "for", "with", "that", "this", "from", "have", "will",
}

HASHTAGS = {
    "нейросет": "#нейросети",
    "нейрон": "#нейросети",
    "искусственн": "#ИИ",
    "ии": "#ИИ",
    "llm": "#LLM",
    "gpt": "#GPT",
    "openai": "#OpenAI",
    "google": "#Google",
    "яндекс": "#Яндекс",
    "модель": "#ML",
    "машинн": "#ML",
    "open source": "#opensource",
    "опенсорс": "#opensource",
    "python": "#Python",
    "разработ": "#разработка",
    "безопасн": "#кибербезопасность",
    "уязвим": "#кибербезопасность",
    "процессор": "#железо",
    "видеокарт": "#железо",
    "чип": "#железо",
    "apple": "#Apple",
    "microsoft": "#Microsoft",
}

RUBRICS = {
    "news": {
        "emoji": "⚡️",
        "tag": "#новости",
        "openers": [
            "Главное за сегодня:",
            "Коротко о важном:",
            "Что нового:",
        ],
        "closers": [
            "Как вам такой поворот?",
            "Ждали подобного?",
            "Что думаете об этом?",
            "Стоит ли оно внимания — напишите в комментариях.",
        ],
    },
    "analysis": {
        "emoji": "🧠",
        "tag": "#разбор",
        "openers": [
            "Разбираемся по существу:",
            "Что стоит за новостью:",
            "Смотрим внимательнее:",
        ],
        "closers": [
            "Согласны с таким взглядом?",
            "Что бы вы добавили?",
            "Какие выводы делаете вы?",
        ],
    },
    "tool": {
        "emoji": "🛠",
        "tag": "#инструменты",
        "openers": [
            "Полезное для работы:",
            "Инструмент, который стоит попробовать:",
            "На заметку разработчику:",
        ],
        "closers": [
            "Пробовали что-то похожее?",
            "Что используете вместо этого?",
            "Пригодится в работе?",
        ],
    },
    "opinion": {
        "emoji": "💬",
        "tag": "#мнение",
        "openers": [
            "Повод поспорить:",
            "Неочевидный взгляд:",
            "Тема для обсуждения:",
        ],
        "closers": [
            "Ваша позиция?",
            "Согласны или нет?",
            "Как считаете?",
        ],
    },
}

WEEK_PLAN = {
    0: ("news", "Новости и релизы"),
    1: ("tool", "Инструменты разработчика"),
    2: ("analysis", "Разбор технологии"),
    3: ("news", "Новости и релизы"),
    4: ("tool", "Подборка/дайджест"),
    5: ("opinion", "Мнение и обсуждение"),
    6: ("analysis", "Итоги недели"),
}


def normalize(text: str) -> str:
    return clean_text(text).replace("\xa0", " ").strip()


def tokens(text: str) -> set[str]:
    return {w.lower() for w in WORD_RE.findall(text) if w.lower() not in STOP_WORDS}


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in SENT_SPLIT.split(text) if p.strip()]
    return [p for p in parts if len(p) >= 45]


def score(sentence: str, title_tokens: set[str], position: int) -> float:
    value = 0.0
    length = len(sentence)
    if 90 <= length <= 260:
        value += 2.0
    elif length > 320:
        value -= 1.5
    if re.search(r"\d", sentence):
        value += 0.7
    overlap = len(tokens(sentence) & title_tokens)
    value += min(overlap, 4) * 1.3
    value += 1.2 if position == 0 else (0.5 if position == 1 else 0)
    low = sentence.lower()
    if any(marker in low for marker in ("подпис", "читайте", "реклам", "скидк")):
        value -= 4
    return value


def summarize(text: str, title: str, limit: int = 2) -> str:
    body = normalize(text)
    sentences = split_sentences(body)
    if not sentences:
        return ""
    title_tokens = tokens(title)
    ranked = sorted(
        ((score(s, title_tokens, i), i, s) for i, s in enumerate(sentences)),
        key=lambda x: (-x[0], x[1]),
    )
    chosen = sorted(ranked[:limit], key=lambda x: x[1])
    result = " ".join(CUT_TAIL.sub("", s[2]) for s in chosen).strip()
    if result and result[-1] not in ".!?…":
        result += "."
    return result


def pick_hashtags(item: Item, rubric: str) -> str:
    low = (item.clean_title + " " + item.summary).lower()
    found: list[str] = []
    for key, tag in HASHTAGS.items():
        if key in low and tag not in found:
            found.append(tag)
    base = RUBRICS.get(rubric, RUBRICS["news"])["tag"]
    tags = [base] + found[:3]
    return " ".join(dict.fromkeys(tags))


def relevance(item: Item) -> float:
    text = (item.clean_title + " " + item.summary).lower()
    return sum(1 for hint in TOPIC_HINTS.split(", ") if hint.lower() in text)


def format_post(item: Item, rubric: str | None = None) -> dict:
    rubric = rubric or item.rubric
    conf = RUBRICS.get(rubric, RUBRICS["news"])
    title = normalize(item.clean_title)
    body = summarize(item.summary, title)
    opener = random.choice(conf["openers"])
    closer = random.choice(conf["closers"])

    lines = [f"{conf['emoji']} <b>{html.escape(title)}</b>", ""]
    if body:
        lead = opener if opener.endswith(":") else opener + "."
        lines.append(f"{html.escape(lead)} {html.escape(body)}")
        lines.append("")
    lines.append(html.escape(closer))
    lines.append("")
    lines.append(f"🔗 {html.escape(item.source)}: {item.url}")
    lines.append(pick_hashtags(item, rubric))

    text = "\n".join(lines).strip()
    if len(text) > 1100:
        text = text[:1050].rsplit("\n", 1)[0] + "\n…\n\n" + item.url
    return {
        "text": text,
        "rubric": rubric,
        "title": title,
        "url": item.url,
        "source": item.source,
    }


def format_digest(items: list[Item]) -> dict:
    lines = ["🗞 <b>Дайджест недели</b>", ""]
    used = []
    for index, item in enumerate(items[:4], start=1):
        title = normalize(item.clean_title)
        body = summarize(item.summary, title, limit=1)
        if not body:
            continue
        used.append(item)
        lines.append(f"<b>{index}.</b> {html.escape(title)}")
        lines.append(html.escape(body))
        lines.append(f'<a href="{item.url}">Читать</a>')
        lines.append("")
    if not used:
        return {}
    lines.append("Что из этого обсудим подробнее?")
    tags = ["#дайджест"]
    for item in used:
        for tag in pick_hashtags(item, "tool").split():
            if tag not in tags and len(tags) < 4:
                tags.append(tag)
    lines.append(" ".join(tags))
    return {
        "text": "\n".join(lines).strip(),
        "rubric": "digest",
        "title": "Дайджест недели",
        "url": "",
        "source": "Подборка",
    }


def make_ideas(items: list[Item], count: int = 5) -> list[str]:
    frames = [
        "Разбор: {t}",
        "Что не так с «{t}»",
        "5 выводов из новости: {t}",
        "Как это меняет работу разработчика: {t}",
        "Мнение: {t} — хайп или польза",
    ]
    ideas: list[str] = []
    for item in items:
        title = normalize(item.clean_title)
        if not title:
            continue
        idea = random.choice(frames).format(t=title)
        if idea not in ideas:
            ideas.append(idea)
        if len(ideas) >= count:
            break
    return ideas


def plan_line(day: date) -> tuple[str, str]:
    rubric, label = WEEK_PLAN[day.weekday()]
    return rubric, f"{label} — {RUBRICS[rubric]['emoji']} {RUBRICS[rubric]['tag']}"
