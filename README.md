# Competitive Search Bot

Telegram bot: [@competitive_search_bot](https://t.me/competitive_search_bot)

Competitive Search Bot is an educational aiogram 3 project for practicing
async Python, concurrent I/O, timeouts, partial failures, and concurrency
limits.

The bot accepts a text query and searches concurrently across:

- Wikipedia articles
- GitHub repositories
- Stack Overflow questions

Results are normalized to one internal `SearchResult` model and formatted into
a single Telegram response. If one provider fails or times out, successful
results from the other providers are still returned.

## Stack

- Python 3.14
- aiogram 3
- HTTPX
- Pydantic Settings
- structlog
- pytest / pytest-asyncio
- uv

## Setup

Copy the example settings file and fill in your Telegram bot token:

```bash
cp settings.example.toml settings.toml
```

Required config:

```toml
[bot]
token = "your-telegram-bot-token"

[http]
user_agent = "CompetitiveSearchBot/0.1 (https://github.com/arseglaz/Competetive-Search-Bot)"
```

Run the bot:

```bash
uv run -m bot
```

Run tests:

```bash
uv run pytest
```

## Current Behavior

- Searches all providers concurrently via `asyncio.gather`.
- Converts provider-specific JSON to common `SearchResult` objects.
- Handles provider failures independently.
- Applies per-provider timeout.
- Limits concurrent provider calls with `asyncio.Semaphore`.

No database, Redis, Celery, Selenium, browser automation, or search engine
scraping is used.
