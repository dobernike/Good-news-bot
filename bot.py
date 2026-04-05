import asyncio
import json
import logging
import os
import textwrap
from pathlib import Path

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
POST_TIMES = [t.strip() for t in os.environ.get("POST_TIMES", "09:00,18:00").split(",")]

ARTICLES_PER_POST = 3
# How many past URLs to remember (avoids repeats across many posts)
HISTORY_SIZE = 200
HISTORY_FILE = Path(os.environ.get("HISTORY_FILE", "posted_urls.json"))

# Tried in order; combined they cover plenty of bizarre/funny material.
QUERIES = [
    "funny weird bizarre news",
    "strange odd unusual news",
    "absurd ridiculous unexpected",
    "humor amusing surprising news",
    "quirky offbeat odd",
]


# ---------------------------------------------------------------------------
# URL history — persisted to a local JSON file so restarts don't reset it
# ---------------------------------------------------------------------------

def load_history() -> list[str]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            pass
    return []


def save_history(history: list[str]) -> None:
    try:
        HISTORY_FILE.write_text(json.dumps(history))
    except Exception as exc:
        logger.warning("Could not save history: %s", exc)


def add_to_history(urls: list[str]) -> None:
    history = load_history()
    history.extend(urls)
    # Keep only the most recent entries
    save_history(history[-HISTORY_SIZE:])


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_funny_news() -> list[dict]:
    """Return ARTICLES_PER_POST funny articles not seen before."""
    api = NewsApiClient(api_key=NEWS_API_KEY)
    seen_urls = set(load_history())
    articles: list[dict] = []

    for query in QUERIES:
        if len(articles) >= ARTICLES_PER_POST:
            break
        try:
            response = api.get_everything(
                q=query,
                language="en",
                sort_by="publishedAt",
                page_size=20,
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
            articles.append(article)
            if len(articles) >= ARTICLES_PER_POST:
                break

    return articles


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_message(articles: list[dict]) -> str:
    parts = ["\U0001f923 <b>Смешные новости дня</b> \U0001f923\n"]

    for i, article in enumerate(articles, 1):
        title = _escape((article.get("title") or "No title").strip())
        description = _escape((article.get("description") or "").strip())
        url = article.get("url", "")
        source = _escape(article.get("source", {}).get("name") or "Unknown")

        if len(description) > 280:
            description = textwrap.shorten(description, width=280, placeholder="…")

        block = f"<b>{i}. {title}</b>"
        if description:
            block += f"\n{description}"
        block += f"\n<i>— {source}</i>"
        if url:
            block += f'\n<a href="{url}">Читать</a>'

        parts.append(block)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------

async def post_funny_news(bot: Bot) -> None:
    logger.info("Fetching funny news…")
    articles = fetch_funny_news()

    if not articles:
        logger.warning("No new articles found — skipping post.")
        return

    message = build_message(articles)
    if len(message) > 4096:
        message = message[:4090] + "\n…"

    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        add_to_history([a.get("url", "") for a in articles])
        logger.info("Posted %d article(s); history size: %d.", len(articles), len(load_history()))
    except TelegramError as exc:
        logger.error("Failed to send message: %s", exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    bot = Bot(token=TELEGRAM_TOKEN)
    me = await bot.get_me()
    logger.info("Logged in as @%s — posting at %s UTC.", me.username, ", ".join(POST_TIMES))

    scheduler = AsyncIOScheduler(timezone="UTC")
    for post_time in POST_TIMES:
        hour, minute = (int(x) for x in post_time.split(":"))
        scheduler.add_job(post_funny_news, trigger="cron", hour=hour, minute=minute, args=[bot])
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
