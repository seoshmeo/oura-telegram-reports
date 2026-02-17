# CLAUDE.md - Oura Bot v2

## Project Description

Interactive Telegram health analyst bot powered by Oura Ring data. Sends scheduled reports (daily, weekly, monthly), monitors anomalies, accepts user events (text + voice), correlates events with health metrics, tracks weather impact, habit streaks, circadian rhythm, and sleep debt.

Location: Cyprus, Larnaca. Database: SQLite. Voice: OpenAI Whisper. AI: Claude Sonnet.

Repository: `https://github.com/seoshmeo/oura-telegram-reports.git`

## Project Structure

```
oura-telegram-reports/
├── bot/
│   ├── __init__.py
│   ├── main.py                     # Entry point: telegram polling + APScheduler
│   ├── config.py                   # All environment variables
│   │
│   ├── core/
│   │   ├── oura_api.py             # Async Oura API v2 client
│   │   ├── telegram.py             # Telegram message sending
│   │   ├── database.py             # SQLite connection, helpers
│   │   └── migrations.py           # SQL schema versioning
│   │
│   ├── reports/
│   │   ├── daily.py                # Daily morning report
│   │   ├── weekly.py               # Weekly report (Sundays)
│   │   └── monthly.py              # Monthly report (1st)
│   │
│   ├── analysis/
│   │   ├── claude_analyzer.py      # Claude AI health analysis + event parsing
│   │   ├── correlator.py           # Event-metric correlation engine
│   │   ├── percentiles.py          # Percentile calculations, top/worst days
│   │   └── weekday_weekend.py      # Weekday vs weekend analysis
│   │
│   ├── alerts/
│   │   ├── monitor.py              # Anomaly detection with baselines
│   │   └── intraday.py             # Morning signal + post-event HR tracking
│   │
│   ├── events/
│   │   ├── handler.py              # Telegram message handler (text + voice)
│   │   ├── parser.py               # Regex event parser + Claude fallback
│   │   ├── voice.py                # OpenAI Whisper transcription
│   │   └── tracker.py              # Event CRUD in SQLite
│   │
│   ├── weather/
│   │   ├── client.py               # Open-Meteo API (free, no key)
│   │   ├── alerts.py               # Critical weather alerts
│   │   └── cache.py                # Weather cache in SQLite
│   │
│   ├── habits/
│   │   ├── streaks.py              # Habit streak tracking
│   │   ├── circadian.py            # Circadian rhythm stability
│   │   └── sleep_debt.py           # Sleep debt + payoff forecast
│   │
│   └── scheduler/
│       └── jobs.py                 # All scheduled jobs
│
├── tests/
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── .gitignore
```

## Architecture

**Single async process**: `bot/main.py` runs `python-telegram-bot` v20 (polling) + `APScheduler` (async cron) in one event loop. No subprocess calls.

**Database**: SQLite with WAL mode. Tables: events, daily_metrics, weather, correlations, intraday_hr, percentile_cache, habit_streaks. Schema versioned via migrations.py.

**Data flow**:
1. APScheduler triggers jobs (reports, alerts, analytics)
2. Jobs call async Oura API client
3. Data cached in SQLite daily_metrics table
4. Reports sent via async Telegram client
5. User messages parsed as events, stored in DB
6. Nightly job recomputes percentiles, correlations, streaks

## Key Modules

### bot/main.py (entry point)
- Initializes DB, runs migrations, starts APScheduler
- Registers Telegram command handlers: /start, /status, /events, /delete, /correlations, /export
- Registers message handlers: text → event parser, voice → Whisper → parser
- Schedules: daily report (7:30 + retries), alerts (30min), weekly (Sun 20:00), monthly (1st 20:00), analytics (03:00)

### bot/core/oura_api.py
- Async HTTP via aiohttp (replaces sync requests)
- `get_oura_data()`, `get_oura_data_range()`, `fetch_days()`, `fetch_all_metrics()`
- `check_sleep_completed()` - polls sleep sessions for wakeup detection

### bot/events/parser.py
- 15+ regex patterns for common events (coffee, alcohol, hookah, walk, workout, stress, etc.)
- Extracts time and quantity from text
- Claude AI fallback for unrecognized events

### bot/analysis/correlator.py
- Computes event-metric correlations with time-bucket awareness
- Morning/afternoon/evening splits for events like coffee

## Technology Stack

- **Language**: Python 3.11
- **Bot**: python-telegram-bot v20 (async)
- **Scheduler**: APScheduler (async cron)
- **API**: Oura API v2, Open-Meteo (weather), OpenAI Whisper (voice)
- **AI**: Anthropic Claude Sonnet
- **Database**: SQLite (WAL mode)
- **HTTP**: aiohttp (async)
- **Deploy**: Docker + Docker Compose
- **Timezone**: Europe/Nicosia

## Environment Variables

| Variable | Description |
|---|---|
| `OURA_TOKEN` | Oura Personal Access Token |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Target chat ID |
| `CLAUDE_API_KEY` | Anthropic API key (optional) |
| `OPENAI_API_KEY` | OpenAI API key for Whisper (optional) |
| `DAILY_REPORT_HOUR/MINUTE` | Daily report time (default 7:30) |
| `WEEKLY_REPORT_HOUR` | Weekly report hour (default 20) |
| `MONTHLY_REPORT_DAY/HOUR` | Monthly report (default 1st, 20:00) |
| `WEATHER_LAT/LON` | Location coordinates (default Larnaca) |
| `TZ` | Timezone (default Europe/Nicosia) |

## Commands

```bash
# Docker
docker-compose up -d --build        # Build and start
docker-compose logs -f               # View logs
docker-compose down                  # Stop

# Local development
pip install -r requirements.txt
python -m bot.main                   # Run the bot
```

## Telegram Bot Commands

- `/start` - Show help
- `/status` - Show database stats
- `/events` - Today's events
- `/delete <id>` - Delete an event
- `/correlations` - Event-metric correlations
- `/export` - Export data as CSV

## Legacy Files (kept for reference)

The following files are from v1 and are superseded by the bot/ package:
- `scheduler.py` → `bot/main.py` + `bot/scheduler/jobs.py`
- `oura_telegram_daily.py` → `bot/reports/daily.py`
- `oura_telegram_weekly.py` → `bot/reports/weekly.py` + `bot/reports/monthly.py`
- `claude_analyzer.py` → `bot/analysis/claude_analyzer.py`
- `alert_monitor.py` → `bot/alerts/monitor.py`
