# Good News Bot

A Telegram bot that automatically posts 1–3 uplifting news stories to a channel or group chat once a day. Powered by [NewsAPI](https://newsapi.org) and [python-telegram-bot](https://python-telegram-bot.org).

## How it works

1. At the configured time each day the bot queries NewsAPI for positive, inspiring stories.
2. It picks up to 3 articles and formats them into a single HTML message.
3. The message is sent to the configured Telegram channel or group.

## Setup

### 1. Get credentials

| Credential | Where to get it |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Message [@BotFather](https://t.me/BotFather) → `/newbot` |
| `TELEGRAM_CHAT_ID` | Channel username (`@mychannel`) or numeric chat ID |
| `NEWS_API_KEY` | [newsapi.org/register](https://newsapi.org/register) (free) |

For a **channel**: add the bot as an administrator with "Post Messages" permission.  
For a **group**: add the bot to the group.

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in your values:

```
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=@mychannel
NEWS_API_KEY=abc123...
POST_TIME=09:00        # HH:MM UTC, default 09:00
MAX_ARTICLES=3         # 1–3, default 3
```

### 3. Run locally

```bash
pip install -r requirements.txt
# export variables or use a .env loader
export $(cat .env | xargs)
python bot.py
```

## Deploy to Railway

1. Create a new project in [Railway](https://railway.app) and connect this repo.
2. Add the environment variables from `.env.example` in the Railway dashboard under **Variables**.
3. Railway detects `Procfile` and runs `python bot.py` as a worker service — no web server needed.

The free Railway hobby tier comfortably covers a lightweight always-on worker like this.

## Project structure

```
bot.py           # Main bot — fetches news, formats, posts, schedules
requirements.txt # Python dependencies
Procfile         # Railway / Heroku process declaration
railway.toml     # Railway deploy config
.env.example     # Environment variable template
```

## Dependencies

- `python-telegram-bot` — Telegram Bot API client
- `newsapi-python` — NewsAPI client
- `APScheduler` — In-process cron scheduler
