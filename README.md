# Competitive Search Bot

A Telegram bot that performs **concurrent search** across Wikipedia, GitHub, and Stack Overflow. It merges results from all sources into a single message, enforces per-source timeouts and concurrency limits, and gracefully returns **partial results** when one or more sources fail.

## Features

- Concurrent querying of multiple external APIs using `asyncio`
- Per-source **timeout** and **concurrency limiting** (semaphores) to avoid overloading upstream APIs
- Graceful **partial-failure handling** — if one source times out or errors, results from the others are still returned
- Results aggregated into a single, unified Telegram message
- Strict data validation and schema modeling with **Pydantic**
- Structured, queryable logging via **structlog**
- Covered by unit and integration tests with **pytest**

``
Python, asyncio, aiogram 3, HTTPX, Pydantic, structlog, pytest
``