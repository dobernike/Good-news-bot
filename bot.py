import asyncio
import logging
import os
import textwrap

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
POST_TIME = os.environ.get("POST_TIME", "09:00")  # HH:MM UTC
MAX_ARTICLES = int(os.environ.get("MAX_ARTICLES", "3"))

# Queries tried in order; first one with enough results wins.
QUERIES = [
    "технологии инновации",
    "искусственный интеллект открытие",
    "наука технологии прорыв",
]

HEADER = "\U0001f4f1 <b>Технологии дня</b> \U0001f4f1\n"


def fetch_good_news() -> list[dict]:
    """Return up to MAX_ARTICLES uplifting articles from NewsAPI."""
    api = NewsApiClient(api_key=NEWS_API_KEY)
    seen_urls: set[str] = set()
    articles: list[dict] = []

    for query in QUERIES:
        if len(articles) >= MAX_ARTICLES:
            break
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
            # Skip removed/deleted articles and duplicates
            if not title or title == "[Removed]" or url in seen_urls:
                continue
            seen_urls.add(url)
            articles.append(article)
            if len(articles) >= MAX_ARTICLES:
                break

    return articles


def _escape(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_message(articles: list[dict]) -> str:
    """Format articles into a single HTML Telegram message."""
    parts = [HEADER]

    for i, article in enumerate(articles, 1):
        title = _escape((article.get("title") or "No title").strip())
        description = _escape((article.get("description") or "").strip())
        url = article.get("url", "")
        source = _escape(article.get("source", {}).get("name") or "Unknown")

        # Truncate long descriptions to keep messages readable
        if len(description) > 300:
            description = textwrap.shorten(description, width=300, placeholder="…")

        block = f"\n<b>{i}. {title}</b>"
        if description:
            block += f"\n{description}"
        block += f"\n<i>— {source}</i>"
        if url:
            block += f'\n<a href="{url}">Read more</a>'

        parts.append(block)

    return "\n\n".join(parts)


async def post_good_news(bot: Bot) -> None:
    logger.info("Fetching good news…")
    articles = fetch_good_news()

    if not articles:
        logger.warning("No articles retrieved — skipping post.")
        return

    message = build_message(articles)

    # Telegram hard limit is 4096 chars; truncate gracefully if needed.
    if len(message) > 4096:
        message = message[:4090] + "\n…"

    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        logger.info("Posted %d article(s) to %s.", len(articles), TELEGRAM_CHAT_ID)
    except TelegramError as exc:
        logger.error("Failed to send message: %s", exc)


async def main() -> None:
    hour, minute = (int(x) for x in POST_TIME.split(":"))

    bot = Bot(token=TELEGRAM_TOKEN)

    # Verify credentials on startup
    me = await bot.get_me()
    logger.info("Logged in as @%s — will post daily at %s UTC.", me.username, POST_TIME)

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        post_good_news,
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
