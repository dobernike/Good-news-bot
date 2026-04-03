import asyncio
import logging
import os
import textwrap
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from newsapi import NewsApiClient
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
NEWS_API_KEY = os.environ["NEWS_API_KEY"]
# Comma-separated post times in HH:MM UTC, e.g. "09:00,18:00"
POST_TIMES = [t.strip() for t in os.environ.get("POST_TIMES", "09:00,18:00").split(",")]

# Each category: emoji, label, and queries tried in order until an article is found.
CATEGORIES = [
    {
        "emoji": "\U0001f4bb",
        "label": "Разработка",
        "queries": [
            "программирование инструменты разработчик",
            "фреймворк библиотека релиз",
            "open source разработка",
        ],
    },
    {
        "emoji": "\U0001f4b9",
        "label": "Инвестиции",
        "queries": [
            "инвестиции акции рынок возможности",
            "стартап финансирование раунд",
            "фондовый рынок тренд",
        ],
    },
    {
        "emoji": "\U0001f4b0",
        "label": "Крипто",
        "queries": [
            "криптовалюта биткоин ethereum",
            "блокчейн DeFi Web3",
            "крипто новости токен",
        ],
    },
    {
        "emoji": "\u2708\ufe0f",
        "label": "Путешествия",
        "queries": [
            "путешествия туризм направления",
            "авиабилеты отели скидки",
            "туристические места открытие",
        ],
    },
    {
        "emoji": "\U0001f3ae",
        "label": "Игры",
        "queries": [
            "видеоигры релиз анонс",
            "игровая индустрия новинка",
            "геймплей обновление игра",
        ],
    },
]


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fetch_article_for_category(api: NewsApiClient, queries: list[str], seen_urls: set[str]) -> dict | None:
    """Try each query in order and return the first fresh article found."""
    for query in queries:
        try:
            response = api.get_everything(
                q=query,
                language="ru",
                sort_by="publishedAt",
                page_size=10,
            )
        except Exception as exc:
            logger.warning("NewsAPI query %r failed: %s", query, exc)
            continue

        for article in response.get("articles") or []:
            url = article.get("url", "")
            title = (article.get("title") or "").strip()
            if not title or title == "[Removed]" or url in seen_urls:
                continue
            seen_urls.add(url)
            return article

    return None


def fetch_digest() -> list[tuple[dict, dict]]:
    """Return a list of (category, article) pairs — one per category."""
    api = NewsApiClient(api_key=NEWS_API_KEY)
    seen_urls: set[str] = set()
    results = []

    for category in CATEGORIES:
        article = fetch_article_for_category(api, category["queries"], seen_urls)
        if article:
            results.append((category, article))
        else:
            logger.warning("No article found for category %r", category["label"])

    return results


def build_message(digest: list[tuple[dict, dict]]) -> str:
    now = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    parts = [f"\U0001f4f0 <b>Дайджест {now}</b>\n"]

    for category, article in digest:
        emoji = category["emoji"]
        label = category["label"]
        title = _escape((article.get("title") or "Без заголовка").strip())
        description = _escape((article.get("description") or "").strip())
        url = article.get("url", "")
        source = _escape(article.get("source", {}).get("name") or "Неизвестно")

        if len(description) > 250:
            description = textwrap.shorten(description, width=250, placeholder="…")

        block = f"{emoji} <b>{label}</b>\n<b>{title}</b>"
        if description:
            block += f"\n{description}"
        block += f"\n<i>— {source}</i>"
        if url:
            block += f'\n<a href="{url}">Читать</a>'

        parts.append(block)

    return "\n\n".join(parts)


async def post_digest(bot: Bot) -> None:
    logger.info("Building digest…")
    digest = fetch_digest()

    if not digest:
        logger.warning("No articles retrieved — skipping post.")
        return

    message = build_message(digest)

    if len(message) > 4096:
        message = message[:4090] + "\n…"

    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        logger.info("Posted digest (%d categories) to %s.", len(digest), TELEGRAM_CHAT_ID)
    except TelegramError as exc:
        logger.error("Failed to send message: %s", exc)


async def main() -> None:
    bot = Bot(token=TELEGRAM_TOKEN)

    me = await bot.get_me()
    logger.info("Logged in as @%s — will post at %s UTC.", me.username, ", ".join(POST_TIMES))

    scheduler = AsyncIOScheduler(timezone="UTC")
    for post_time in POST_TIMES:
        hour, minute = (int(x) for x in post_time.split(":"))
        scheduler.add_job(
            post_digest,
            trigger="cron",
            hour=hour,
            minute=minute,
            args=[bot],
        )
    scheduler.start()

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        scheduler.shutdown()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
