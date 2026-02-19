# Oura Health AI — Personal Health Analyst in Telegram

An intelligent Telegram bot that turns your Oura Ring data into actionable health insights. Not just numbers — real understanding of what's happening with your body and why.

![Python](https://img.shields.io/badge/python-3.11-blue)
![Docker](https://img.shields.io/badge/docker-ready-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## What It Does

### Scheduled Reports
- **Daily morning report (7:30)** — sleep score, readiness, HRV, resting HR, steps, stress. Compared against your personal baselines and trends
- **Weekly report (Sundays)** — week analysis, event-metric correlations, weekday vs weekend comparison, best/worst days
- **Monthly report (1st of month)** — 30-day trends, sparkline charts, goal achievement, recommendations

### AI-Powered Anomaly Monitoring
- Checks your metrics against a 7-day rolling baseline every 30 minutes
- Detects: HRV drops (-30%+), readiness crashes, resting HR spikes, high stress, low SpO2, temperature anomalies
- **Claude AI analyzes severity** and decides whether to initiate a dialog
- If critical — the bot asks: *"How are you feeling? What might have caused this?"*
- Your response + all health data goes to Claude for **personalized recommendations**

### Event Tracking — One Tap or Voice
Quick-input keyboard buttons:
- **Medications**: Lisinopril (5mg), Glucophage (500mg) — dosage auto-filled
- **Measurements**: Blood pressure, Blood sugar, Weight — with input format hints
- **Events**: Coffee, Walk, Workout, Hookah, Alcohol, Stress, Late meal, Supplements, and more

**Text input**: `"coffee at 14:30"`, `"BP 130/85 pulse 72"`, `"weight 78.5"`, `"2 glasses of wine"`

**Voice input**: send a voice message — Whisper transcribes — bot parses and records

Every event is linked to relevant Oura metrics for correlation analysis.

### Health Measurements
- **Blood pressure** — classification (normal / stage 1-2 hypertension), trend vs previous reading, 30-day stats
- **Blood sugar** — classification (normal / elevated / hypo), trends
- **Weight + BMI** — automatic BMI calculation, classification, trend tracking

### AI Health Analyst — Ask Anything
Send a question in chat — Claude answers **based on your actual data**:

- *"How does coffee affect my sleep?"* → correlation analysis with deep sleep, HRV, sleep latency
- *"Why was my readiness bad yesterday?"* → breakdown: late bedtime + alcohol + high stress
- *"Compare my weekdays vs weekends"* → concrete numbers for sleep, steps, HRV
- *"What's my BP trend this month?"* → measurement stats + correlation with lisinopril intake

Claude sees: 7 days of metrics, all today's events with details, all measurements (BP, sugar, weight), correlations, habit streaks, sleep debt, circadian rhythm, weather data.

### Correlation Engine
- Automatically computes how each event type affects each health metric
- Time-of-day awareness: morning coffee vs evening coffee → different impact on sleep
- Minimum 3 observations required for statistical significance

### Habits & Rhythms
- **Habit streaks** — sleep ≥7h, steps ≥8K, bedtime before 23:00, HRV above average
- **Sleep debt** — accumulated deficit + payoff forecast
- **Circadian rhythm** — bedtime stability, variance tracking

### Weather Integration
- Automatic weather data via Open-Meteo (free, no API key needed)
- Critical weather alerts for extreme conditions
- Factored into AI analysis (*"40°C heat may have affected your HRV"*)

---

## Architecture

```
User (Telegram)
  │
  ├── Text/Voice messages ──→ Event Parser (regex + Claude fallback)
  │                              ├── Event saved to SQLite
  │                              ├── Measurement recorded (BP/sugar/weight)
  │                              └── HR check scheduled (60 min later)
  │
  ├── Health questions ─────→ Claude AI (with full data context)
  │
  └── Button taps ──────────→ Quick event recording / measurement input

APScheduler (background)
  ├── Daily/Weekly/Monthly reports ──→ Oura API → Format → Telegram
  ├── Alert monitor (every 30 min) ──→ Oura API → Baseline check → Claude AI → Telegram
  ├── Morning signal (sleep debt + circadian)
  ├── Weather alerts
  └── Nightly analytics recompute (correlations, percentiles, streaks)
```

**Single async process**: `python-telegram-bot` v20 (polling) + `APScheduler` in one event loop. No subprocesses.

**Database**: SQLite with WAL mode. All data stays local.

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/seoshmeo/oura-telegram-reports.git
cd oura-telegram-reports
```

### 2. Configure environment

```bash
cp .env.example .env
nano .env  # fill in your tokens
```

**Required:**
| Variable | How to get it |
|----------|--------------|
| `OURA_TOKEN` | [Oura Cloud](https://cloud.ouraring.com/personal-access-tokens) → Create Personal Access Token |
| `TELEGRAM_BOT_TOKEN` | Telegram → @BotFather → `/newbot` |
| `TELEGRAM_CHAT_ID` | Send `/start` to your bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` → copy `chat.id` |

**Optional (enables AI features):**
| Variable | Purpose |
|----------|---------|
| `CLAUDE_API_KEY` | Anthropic API key — enables AI health Q&A, smart event parsing, AI-powered alerts |
| `OPENAI_API_KEY` | OpenAI API key — enables voice message transcription via Whisper |

**Schedule & location (defaults shown):**
| Variable | Default | Description |
|----------|---------|-------------|
| `DAILY_REPORT_HOUR` | `7` | Daily report hour |
| `DAILY_REPORT_MINUTE` | `30` | Daily report minute |
| `WEEKLY_REPORT_HOUR` | `20` | Weekly report hour (Sundays) |
| `MONTHLY_REPORT_DAY` | `1` | Monthly report day |
| `MONTHLY_REPORT_HOUR` | `20` | Monthly report hour |
| `WEATHER_LAT` | `34.92` | Your latitude (for weather) |
| `WEATHER_LON` | `33.62` | Your longitude (for weather) |
| `TZ` | `Europe/Nicosia` | Your timezone |

### 3. Run with Docker

```bash
docker compose up -d --build
docker compose logs -f
```

Done! Reports will arrive automatically on schedule.

### Alternative: Run locally

```bash
pip install -r requirements.txt
python -m bot.main
```

---

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Show help |
| `/status` | Database stats |
| `/events` | Today's events |
| `/meds` | Medication intake (today + 7-day history) |
| `/measurements` | BP, sugar, weight readings with trends |
| `/correlations` | Event-metric correlations |
| `/export` | Export data as CSV |
| `/delete <id>` | Delete an event |

---

## Project Structure

```
bot/
├── main.py                  # Entry point: Telegram polling + APScheduler
├── config.py                # Environment variables
├── keyboards.py             # Telegram keyboard layouts
│
├── core/
│   ├── oura_api.py          # Async Oura API v2 client
│   ├── telegram.py          # Message sending
│   ├── database.py          # SQLite (WAL mode)
│   └── migrations.py        # Schema versioning
│
├── reports/
│   ├── daily.py             # Daily morning report
│   ├── weekly.py            # Weekly report
│   └── monthly.py           # Monthly report
│
├── analysis/
│   ├── chat.py              # AI health Q&A (Claude)
│   ├── claude_analyzer.py   # AI event parsing
│   ├── correlator.py        # Event-metric correlations
│   ├── percentiles.py       # Personal norms
│   └── weekday_weekend.py   # Weekday vs weekend
│
├── alerts/
│   ├── monitor.py           # Anomaly detection + AI alerts
│   └── intraday.py          # Post-event HR tracking
│
├── events/
│   ├── handler.py           # Message handler (text + voice)
│   ├── parser.py            # Regex parser (17+ event types)
│   ├── tracker.py           # Event/measurement CRUD
│   └── voice.py             # Whisper transcription
│
├── weather/
│   ├── client.py            # Open-Meteo API
│   ├── alerts.py            # Weather alerts
│   └── cache.py             # Weather cache
│
├── habits/
│   ├── streaks.py           # Habit streaks
│   ├── circadian.py         # Circadian rhythm
│   └── sleep_debt.py        # Sleep debt tracking
│
└── scheduler/
    └── jobs.py              # All scheduled jobs
```

---

## Oura Metrics Tracked

| Category | Metrics |
|----------|---------|
| **Sleep** | Score, total duration, deep/REM/light phases, efficiency, latency, timing |
| **Readiness** | Score, recovery index, HRV balance, temperature deviation |
| **Heart** | Resting HR, average HRV, SpO2 |
| **Stress** | High stress minutes |
| **Activity** | Steps, active calories, sedentary time |

---

## Event Types (Auto-Parsed)

| Event | Trigger words | Tracked against |
|-------|--------------|-----------------|
| Coffee | кофе, coffee, капучино, латте | Sleep, HRV, sleep latency, resting HR |
| Alcohol | алкоголь, пиво, вино, beer, wine | Sleep, HRV, deep sleep, resting HR, readiness |
| Hookah | кальян, hookah | Sleep, HRV, resting HR, SpO2 |
| Workout | тренировка, gym, бег, run | Readiness, HRV, deep sleep |
| Walk | прогулка, walk | Readiness, steps, stress |
| Stress | стресс, тревога | Sleep, HRV, resting HR, stress |
| Lisinopril | лизиноприл | Resting HR, HRV, readiness, sleep |
| Glucophage | глюкофаж, метформин | Sleep, readiness, HRV, stress |
| Blood Pressure | давление 120/80 | Resting HR, HRV, stress, readiness |
| Blood Sugar | сахар 5.6 | Sleep, readiness, stress, HRV |
| Weight | вес 75.5 | Readiness, sleep |
| + 6 more | supplements, meditation, nap, cold shower, sauna, travel, illness, party | Various |

---

## Docker Commands

```bash
docker compose up -d --build    # Build and start
docker compose logs -f           # View logs
docker compose restart           # Restart
docker compose down              # Stop
docker compose exec oura-bot python -m bot.main  # Manual run
```

---

## Security

- Tokens stored in `.env` (gitignored, never committed)
- Messages sent only to your private chat (verified by `TELEGRAM_CHAT_ID`)
- SQLite database stored locally in `./data/`
- No data sent to third parties (except Oura API for reading, Claude/OpenAI APIs for analysis)
- Container isolated from host system

---

## Tech Stack

- **Python 3.11** (fully async)
- **python-telegram-bot** v20 — Telegram integration
- **APScheduler** — cron-like job scheduling
- **Oura API v2** — health data
- **Claude Sonnet** — AI analysis & health Q&A
- **OpenAI Whisper** — voice transcription
- **Open-Meteo** — weather data (free)
- **SQLite** (WAL mode) — local database
- **aiohttp** — async HTTP client
- **Docker** — deployment

---

## License

MIT License — free for personal use.

---

## Contributing

Pull requests and issues are welcome!

---

## Acknowledgements

- [Oura Ring](https://ouraring.com/) — excellent health tracking API
- [Anthropic Claude](https://www.anthropic.com/) — AI-powered health analysis
- [OpenAI Whisper](https://openai.com/) — voice transcription
- [Open-Meteo](https://open-meteo.com/) — free weather API
