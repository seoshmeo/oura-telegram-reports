"""
Oura Bot v2 - Single entry point.
Combines Telegram bot polling + APScheduler for cron jobs.
Replaces scheduler.py + subprocess execution model.
"""

import asyncio
import logging
import os
import sys

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    DAILY_REPORT_HOUR,
    DAILY_REPORT_MINUTE,
    WEEKLY_REPORT_HOUR,
    MONTHLY_REPORT_HOUR,
    MONTHLY_REPORT_DAY,
    TZ,
    LOGS_DIR,
)
from bot.core.database import get_connection, close as close_db
from bot.core.migrations import run_migrations
from bot.events.handler import (
    handle_text_message,
    handle_voice_message,
    cmd_events,
    cmd_delete,
    cmd_correlations,
    cmd_export,
    cmd_measurements,
    cmd_meds,
)
from bot.scheduler.jobs import (
    job_daily_report,
    job_force_daily_report,
    job_weekly_report,
    job_monthly_report,
    job_alert_check,
    job_morning_signal,
    job_weather_alert,
    job_recompute_analytics,
    job_backfill_metrics,
)

# Logging setup
os.makedirs(LOGS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'bot.log')),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Suppress noisy loggers
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.WARNING)


async def cmd_start(update: Update, context):
    """Handle /start command."""
    if str(update.effective_chat.id) != TELEGRAM_CHAT_ID:
        return
    await update.message.reply_text(
        "<b>\U0001f44b Oura Bot v2</b>\n\n"
        "\u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0441\u043e\u0431\u044b\u0442\u0438\u0435 \u0442\u0435\u043a\u0441\u0442\u043e\u043c \u0438\u043b\u0438 \u0433\u043e\u043b\u043e\u0441\u043e\u043c:\n"
        "\u2615 \u043a\u043e\u444e\u0435  \U0001f37a \u0430\u043b\u043a\u043e\u0433\u043e\u043b\u044c  \U0001f4a8 \u043a\u0430\u043b\u044c\u044f\u043d  \U0001f6b6 \u043f\u0440\u043e\u0433\u0443\u043b\u043a\u0430\n"
        "\U0001f3cb\ufe0f \u0442\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u043a\u0430  \U0001f624 \u0441\u0442\u0440\u0435\u0441\u0441  \U0001f374 \u043f\u043e\u0437\u0434\u043d\u044f\u044f \u0435\u0434\u0430  \U0001f48a \u0434\u043e\u0431\u0430\u0432\u043a\u0438\n\n"
        "<b>\U0001fa78 \u0418\u0437\u043c\u0435\u0440\u0435\u043d\u0438\u044f:</b>\n"
        "  \u00ab\u0434\u0430\u0432\u043b\u0435\u043d\u0438\u0435 120/80\u00bb  \u00ab\u0434\u0430\u0432\u043b\u0435\u043d\u0438\u0435 130/85 \u043f\u0443\u043b\u044c\u0441 72\u00bb\n"
        "  \u00ab\u0441\u0430\u0445\u0430\u0440 5.6\u00bb  \u00ab\u0433\u043b\u044e\u043a\u043e\u0437\u0430 6.2\u00bb\n\n"
        "<b>\U0001f48a \u041b\u0435\u043a\u0430\u0440\u0441\u0442\u0432\u0430:</b>\n"
        "  \u00ab\u043b\u0438\u0437\u0438\u043d\u043e\u043f\u0440\u0438\u043b\u00bb  \u00ab\u043b\u0438\u0437\u0438\u043d\u043e\u043f\u0440\u0438\u043b 10\u043c\u0433\u00bb  \u00ab\u0433\u043b\u044e\u043a\u043e\u0444\u0430\u0436 500\u00bb\n\n"
        "<b>\u041a\u043e\u043c\u0430\u043d\u0434\u044b:</b>\n"
        "/events - \u0441\u043e\u0431\u044b\u0442\u0438\u044f \u0441\u0435\u0433\u043e\u0434\u043d\u044f\n"
        "/meds - \u043f\u0440\u0438\u0451\u043c \u043b\u0435\u043a\u0430\u0440\u0441\u0442\u0432\n"
        "/measurements - \u0434\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u0438 \u0441\u0430\u0445\u0430\u0440\n"
        "/delete &lt;id&gt; - \u0443\u0434\u0430\u043b\u0438\u0442\u044c \u0441\u043e\u0431\u044b\u0442\u0438\u0435\n"
        "/correlations - \u043a\u043e\u0440\u0440\u0435\u043b\u044f\u0446\u0438\u0438 \u0441\u043e\u0431\u044b\u0442\u0438\u0439\n"
        "/export - \u044d\u043a\u0441\u043f\u043e\u0440\u0442 \u0434\u0430\u043d\u043d\u044b\u0445",
        parse_mode='HTML',
    )


async def cmd_status(update: Update, context):
    """Handle /status command."""
    if str(update.effective_chat.id) != TELEGRAM_CHAT_ID:
        return

    from bot.core.database import fetchone
    metrics_count = fetchone("SELECT COUNT(*) as cnt FROM daily_metrics")
    events_count = fetchone("SELECT COUNT(*) as cnt FROM events")
    weather_count = fetchone("SELECT COUNT(*) as cnt FROM weather")
    measurements_count = fetchone("SELECT COUNT(*) as cnt FROM health_measurements")

    msg = "<b>\U0001f4ca \u0421\u0442\u0430\u0442\u0443\u0441 Oura Bot v2</b>\n\n"
    msg += f"  \U0001f4c5 \u041c\u0435\u0442\u0440\u0438\u043a\u0438: {metrics_count['cnt']} \u0434\u043d\u0435\u0439\n"
    msg += f"  \U0001f4cb \u0421\u043e\u0431\u044b\u0442\u0438\u044f: {events_count['cnt']}\n"
    msg += f"  \U0001fa78 \u0418\u0437\u043c\u0435\u0440\u0435\u043d\u0438\u044f: {measurements_count['cnt']}\n"
    msg += f"  \U0001f326\ufe0f \u041f\u043e\u0433\u043e\u0434\u0430: {weather_count['cnt']} \u0434\u043d\u0435\u0439\n"

    await update.message.reply_text(msg, parse_mode='HTML')


def setup_scheduler(app: Application) -> AsyncIOScheduler:
    """Configure APScheduler with all jobs."""
    scheduler = AsyncIOScheduler(timezone=TZ)

    # Daily report: first attempt + retries
    scheduler.add_job(job_daily_report, CronTrigger(
        hour=DAILY_REPORT_HOUR, minute=DAILY_REPORT_MINUTE, timezone=TZ),
        id='daily_report', name='Daily report (attempt 1)')

    # Retry attempts every 30 minutes
    for retry_hour, retry_min in [(8, 0), (8, 30), (9, 0), (9, 30), (10, 0)]:
        scheduler.add_job(job_daily_report, CronTrigger(
            hour=retry_hour, minute=retry_min, timezone=TZ),
            id=f'daily_retry_{retry_hour}_{retry_min}',
            name=f'Daily report retry {retry_hour}:{retry_min:02d}')

    # Force daily report at 10:30
    scheduler.add_job(job_force_daily_report, CronTrigger(
        hour=10, minute=30, timezone=TZ),
        id='daily_force', name='Daily report (force)')

    # Morning signal at 11:00
    scheduler.add_job(job_morning_signal, CronTrigger(
        hour=11, minute=0, timezone=TZ),
        id='morning_signal', name='Morning signal')

    # Alert check every 30 minutes
    scheduler.add_job(job_alert_check, 'interval', minutes=30,
        id='alert_check', name='Alert check')

    # Weather alert at 8:00
    scheduler.add_job(job_weather_alert, CronTrigger(
        hour=8, minute=0, timezone=TZ),
        id='weather_alert', name='Weather alert')

    # Weekly report: Sundays
    scheduler.add_job(job_weekly_report, CronTrigger(
        day_of_week='sun', hour=WEEKLY_REPORT_HOUR, minute=0, timezone=TZ),
        id='weekly_report', name='Weekly report')

    # Monthly report: 1st of month
    scheduler.add_job(job_monthly_report, CronTrigger(
        day=MONTHLY_REPORT_DAY, hour=MONTHLY_REPORT_HOUR, minute=0, timezone=TZ),
        id='monthly_report', name='Monthly report')

    # Nightly analytics recompute at 03:00
    scheduler.add_job(job_recompute_analytics, CronTrigger(
        hour=3, minute=0, timezone=TZ),
        id='recompute_analytics', name='Recompute analytics')

    return scheduler


_scheduler: AsyncIOScheduler | None = None


async def post_init(app: Application):
    """Run after the Application is initialized (inside the event loop)."""
    global _scheduler

    # Start APScheduler inside the running event loop
    _scheduler = setup_scheduler(app)
    _scheduler.start()
    logger.info("APScheduler started with %d jobs", len(_scheduler.get_jobs()))

    # Run backfill on first start
    await job_backfill_metrics()


async def post_shutdown(app: Application):
    """Clean up on shutdown."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None
    close_db()
    logger.info("Bot stopped")


def main():
    """Main entry point."""
    logger.info("Starting Oura Bot v2...")

    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        sys.exit(1)

    # Initialize database
    get_connection()
    run_migrations()
    logger.info("Database initialized")

    # Build telegram application
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Register command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("events", cmd_events))
    app.add_handler(CommandHandler("measurements", cmd_measurements))
    app.add_handler(CommandHandler("meds", cmd_meds))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CommandHandler("correlations", cmd_correlations))
    app.add_handler(CommandHandler("export", cmd_export))

    # Register message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))

    # Start polling (this creates the event loop; post_init starts the scheduler inside it)
    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
