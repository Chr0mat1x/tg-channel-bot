import asyncio
import html
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import feedparser
import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

SOURCES = [
    {"name": "Хабр", "url": "https://habr.com/ru/rss/best/daily/?fl=ru", "rubric": "news"},
    {"name": "Хабр / ИИ", "url": "https://habr.com/ru/rss/hubs/artificial_intelligence/all/?fl=ru", "rubric": "analysis"},
    {"name": "Хабр / Разработка", "url": "https://habr.com/ru/rss/hubs/develop/all/?fl=ru", "rubric": "tool"},
    {"name": "Tproger", "url": "https://tproger.ru/feed", "rubric": "tool"},
    {"name": "N + 1", "url": "https://nplus1.ru/rss", "rubric": "news"},
    {"name": "3DNews", "url": "https://3dnews.ru/news/rss/", "rubric": "news"},
    {"name": "SecurityLab", "url": "https://www.securitylab.ru/rss/all.php", "rubric": "news"},
]

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
JUNK_RE = re.compile(
    r"(читайте также|читать далее|подписывайтесь|реклама|фото:|источник:)\s*[^.]*",
    re.IGNORECASE,
)


@dataclass(slots=True)
class Item:
    title: str
    summary: str
    url: str
    source: str
    rubric: str
    published: datetime | None

    @property
    def clean_title(self) -> str:
        title = html.unescape(TAG_RE.sub("", self.title))
        title = re.sub(r"\s*[/|—–-]\s*(Хабр|Tproger|N \+ 1|3DNews|SecurityLab)\s*$", "", title)
        return WS_RE.sub(" ", title).strip()


def clean_text(raw: str) -> str:
    text = html.unescape(TAG_RE.sub(" ", raw or ""))
    text = JUNK_RE.sub("", text)
    return WS_RE.sub(" ", text).strip()


def _parse_feed(url: str, source: str, rubric: str, raw: bytes) -> list[Item]:
    feed = feedparser.parse(raw)
    items: list[Item] = []
    for entry in feed.entries[:25]:
        link = (entry.get("link") or "").strip()
        title = (entry.get("title") or "").strip()
        if not link or not title:
            continue
        body = entry.get("summary") or entry.get("description") or ""
        if len(clean_text(body)) < 80 and entry.get("content"):
            body = entry["content"][0].get("value", body)
        published = None
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed:
            published = datetime(*parsed[:6], tzinfo=timezone.utc)
        items.append(
            Item(
                title=title,
                summary=clean_text(body),
                url=link,
                source=source,
                rubric=rubric,
                published=published,
            )
        )
    return items


async def fetch_source(source: dict, client: httpx.AsyncClient) -> list[Item]:
    try:
        response = await client.get(source["url"])
        response.raise_for_status()
    except Exception:
        return []
    return await asyncio.to_thread(
        _parse_feed, source["url"], source["name"], source["rubric"], response.content
    )


async def fetch_all(max_age_days: int = 4) -> list[Item]:
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "ru,en;q=0.8"}
    async with httpx.AsyncClient(headers=headers, timeout=25, follow_redirects=True) as client:
        results = await asyncio.gather(*(fetch_source(s, client) for s in SOURCES))
    threshold = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    items = [i for batch in results for i in batch]
    fresh = [i for i in items if i.published is None or i.published >= threshold]
    return fresh or items
