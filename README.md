# Competitive Search Bot

A Telegram bot that concurrently searches English Wikipedia articles, GitHub
repositories, and Stack Overflow questions. It combines results into one message.
If a source fails, it returns results from the others and lists unavailable sources.

Stack: Python, asyncio, aiogram 3, HTTPX, Pydantic Settings, structlog, pytest.

## Quick start

You need Git, internet access, and [uv](https://docs.astral.sh/uv/getting-started/installation/).
The commands below use Bash on Linux/macOS.

1. Get a token: open [@BotFather](https://t.me/BotFather) in Telegram, send
   `/newbot`, and choose a name and username. BotFather will provide a token.
   See the [official Telegram guide](https://core.telegram.org/bots/tutorial#obtain-your-bot-token).
2. Clone the repository and install Python and dependencies:

   ```bash
   git clone https://github.com/arseglaz/Competetive-Search-Bot.git
   cd Competetive-Search-Bot
   uv python install 3.14
   uv sync --locked --python 3.14
   cp settings.example.toml settings.toml
   ```

3. Open `settings.toml` and replace `token` in the `[bot]` section with your
   token. You can keep the other settings from the example.
4. Run the bot from the project root:

   ```bash
   uv run -m bot
   ```

5. Open **your** bot in Telegram, send `/start` or `/help`, then try
   `python asyncio semaphore`. Press `Ctrl+C` to stop the process.

The bot uses long polling, so it needs no public server, domain, or webhook.
The current implementation uses public Wikipedia, GitHub, and Stack Overflow
APIs without API keys, subject to their limits.

### Why Python 3.14?

`pyproject.toml` currently requires Python **3.14 or newer**, and `uv.lock` matches
that requirement. These instructions use 3.14 to reproduce the working environment.
Concurrent search itself does not require 3.14: `asyncio.timeout_at` has been
available since 3.11. Compatibility with earlier Python versions and their
dependencies has not been verified here. Lowering the requirement would need
separate validation and a lock file update.

## Configuration

`settings.example.toml` is a tracked template containing a dummy token.
`settings.toml` is your local configuration, excluded from Git.
The application loads it from the repository root.

| Section | Purpose |
|---|---|
| `[bot]` | `token`: Telegram bot token |
| `[http]` | `user_agent`: application identifier sent to external APIs |
| `[search]` | Search timeout and maximum active requests per source |
| `[logs]` | Format (`console`/`json`), timestamps, colors, debug and third-party logs |

Environment variables override TOML values. Nested fields use `__`:
`BOT__TOKEN`, `HTTP__USER_AGENT`, `LOGS__RENDERER`, and `LOGS__SHOW_DEBUG_LOGS`.
Search settings use `SEARCH__SEARCH_TIMEOUT_SECONDS` and
`SEARCH__MAX_CONCURRENT_PER_PROVIDER`.
You can keep the dummy token in your local TOML file and provide the real token
through the environment. This Bash command keeps the token out of command history:

```bash
read -rsp 'Telegram token: ' BOT__TOKEN
printf '\n'
export BOT__TOKEN
uv run -m bot
```

`BOT__TOKEN` replaces only the token. Other required settings must still be
provided through TOML or environment variables. A `.env` file is **not loaded automatically**.

By default, the service allows **5 seconds** per search, including semaphore waits,
and **3 active requests per source** within one service instance. Override these
values in `settings.toml` or through environment variables:

```toml
[search]
search_timeout_seconds = 5.0
max_concurrent_per_provider = 3
```

The timeout must be positive and finite; the concurrency limit must be a positive
integer. Existing configuration files without `[search]` use the defaults.

### Troubleshooting

- `ValidationError`: check that `settings.toml` exists and includes all sections
  and required fields from `settings.example.toml`.
- Invalid token or `Unauthorized`: replace the example token with your bot's
  token and check whether `BOT__TOKEN` overrides it.
- Polling `Conflict`: stop any other process using the same bot.
- An unavailable source in a reply: check the logs for timeouts, network failures,
  or API limits. Other sources will continue returning results.

## Key experiment

Both modes search the same query across three simulated sources. Delays of
**50, 100, and 200 ms** use `asyncio.sleep` to model waiting for network responses.
Sequential search awaits each provider in a loop; concurrent search uses the
actual `SearchService`. Every measurement checks that both modes return the same
three results without provider failures. The timeout is 5 seconds, the limit is
3 requests per source, and no competing searches run. Logging is disabled.

After one warm-up per mode, each mode was measured five times, alternating
execution order. The table shows median elapsed times measured with `perf_counter`.
This is a controlled I/O simulation rather than a measurement of live API latency.

| Mode | Median search time |
|---|---:|
| Sequential | 352.595 ms |
| Concurrent (`SearchService`) | 201.441 ms |

Speedup: **1.75x**. Python 3.14.7, 5 measurements per mode.

Sequential waits add up: approximately `50 + 100 + 200 = 350 ms`. Concurrent waits
overlap, so total time is close to the slowest source,
`max(50, 100, 200) = 200 ms`, plus overhead. `asyncio` lets other requests progress
while one waits for a response. Speedup depends on the relative delays; these
values predict about `350 / 200 = 1.75x`. Live API performance also depends on
network conditions, source limits, and semaphore waits.

Run the experiment from the project root:

```bash
uv run -m experiments.search_load
```

No token or external API access is required. The script prints a new table and
overwrites the [raw measurements JSON](experiments/results/search_load.json).
The table above records the original run; repeated measurements may differ slightly.
Source: [experiments/search_load.py](experiments/search_load.py).

## Tests

```bash
uv run -m pytest -q
```

Tests cover providers, handlers, result aggregation, partial failures, timeouts,
cancellation, concurrency limits, and recovery after bursts of timeouts.
Integration tests use HTTP mocks and require no token or live API access.
