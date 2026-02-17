"""
Telegram message handler for interactive event input.
"""

import json
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from bot.events.parser import parse_event, get_event_emoji
from bot.events.tracker import add_event, get_today_events, delete_event
from bot.events.voice import download_and_transcribe
from bot.analysis.correlator import get_correlation_report
from bot.analysis.claude_analyzer import OuraClaudeAnalyzer
from bot.config import CLAUDE_API_KEY, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


def _is_authorized(update: Update) -> bool:
    """Check if the message is from the authorized chat."""
    return str(update.effective_chat.id) == TELEGRAM_CHAT_ID


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming text messages - try to parse as event."""
    if not _is_authorized(update):
        return

    text = update.message.text.strip()
    if not text or text.startswith('/'):
        return

    # Try regex parser first
    parsed = parse_event(text)

    # Fall back to Claude if no regex match
    if not parsed and CLAUDE_API_KEY:
        try:
            analyzer = OuraClaudeAnalyzer(api_key=CLAUDE_API_KEY)
            parsed = analyzer.parse_event(text)
        except Exception as e:
            logger.debug("Claude parse failed: %s", e)

    if not parsed:
        # Not recognized as an event - ignore silently
        return

    event_type = parsed['event_type']
    emoji = parsed.get('emoji', get_event_emoji(event_type))
    details = parsed.get('details', {})
    metrics = parsed.get('metrics_to_correlate', [])

    # Determine timestamp
    event_time = datetime.now()
    if details.get('time'):
        try:
            time_parts = details['time'].split(':')
            event_time = event_time.replace(
                hour=int(time_parts[0]),
                minute=int(time_parts[1]),
                second=0, microsecond=0,
            )
        except (ValueError, IndexError):
            pass

    event_id = add_event(
        event_type=event_type,
        raw_text=text,
        details=details,
        metrics_to_correlate=metrics,
        source='text',
        timestamp=event_time,
    )

    time_str = event_time.strftime('%H:%M')
    metrics_str = ", ".join(metrics[:3]) if metrics else ""
    confirmation = f"{emoji} <b>{event_type.replace('_', ' ').title()}</b> \u0437\u0430\u043f\u0438\u0441\u0430\u043d\u043e \u0432 {time_str}"
    if metrics_str:
        confirmation += f"\n\U0001f50d \u041f\u043e\u0441\u043c\u043e\u0442\u0440\u044e \u0432\u043b\u0438\u044f\u043d\u0438\u0435 \u043d\u0430: {metrics_str}"

    await update.message.reply_text(confirmation, parse_mode='HTML')

    # Schedule HR check after 60 min for relevant events
    if event_type in ('coffee', 'hookah', 'workout', 'cold_shower', 'sauna'):
        _schedule_hr_check(context, event_id, event_type, event_time)


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages - transcribe and parse as event."""
    if not _is_authorized(update):
        return

    voice = update.message.voice or update.message.audio
    if not voice:
        return

    text = await download_and_transcribe(context.bot, voice.file_id)
    if not text:
        await update.message.reply_text("\u26a0\ufe0f \u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u0442\u044c \u0433\u043e\u043b\u043e\u0441\u043e\u0432\u043e\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435")
        return

    # Parse transcribed text
    parsed = parse_event(text)
    if not parsed and CLAUDE_API_KEY:
        try:
            analyzer = OuraClaudeAnalyzer(api_key=CLAUDE_API_KEY)
            parsed = analyzer.parse_event(text)
        except Exception:
            pass

    if not parsed:
        await update.message.reply_text(
            f"\U0001f3a4 \u0420\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u043d\u043e: \u00ab{text}\u00bb\n\u2753 \u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u0438\u0442\u044c \u0441\u043e\u0431\u044b\u0442\u0438\u0435",
            parse_mode='HTML',
        )
        return

    event_type = parsed['event_type']
    emoji = parsed.get('emoji', get_event_emoji(event_type))
    details = parsed.get('details', {})
    metrics = parsed.get('metrics_to_correlate', [])

    event_id = add_event(
        event_type=event_type,
        raw_text=text,
        details=details,
        metrics_to_correlate=metrics,
        source='voice',
    )

    time_str = datetime.now().strftime('%H:%M')
    await update.message.reply_text(
        f"\U0001f3a4 \u0420\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u043d\u043e: \u00ab{text}\u00bb\n{emoji} \u0417\u0430\u043f\u0438\u0441\u0430\u043d\u043e \u0432 {time_str}",
        parse_mode='HTML',
    )

    if event_type in ('coffee', 'hookah', 'workout', 'cold_shower', 'sauna'):
        _schedule_hr_check(context, event_id, event_type, datetime.now())


async def cmd_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /events command - show today's events."""
    if not _is_authorized(update):
        return

    events = get_today_events()
    if not events:
        await update.message.reply_text("\U0001f4cb \u0421\u0435\u0433\u043e\u0434\u043d\u044f \u0441\u043e\u0431\u044b\u0442\u0438\u0439 \u043d\u0435\u0442")
        return

    message = "<b>\U0001f4cb \u0421\u041e\u0411\u042b\u0422\u0418\u042f \u0421\u0415\u0413\u041e\u0414\u041d\u042f</b>\n\n"
    for ev in events:
        ts = datetime.fromisoformat(ev['timestamp'])
        emoji = get_event_emoji(ev['event_type'])
        source_icon = "\U0001f3a4" if ev['source'] == 'voice' else "\u2328\ufe0f"
        message += f"{emoji} {ts.strftime('%H:%M')} - {ev['event_type']} {source_icon}\n"
        if ev.get('raw_text'):
            message += f"   <i>{ev['raw_text'][:50]}</i>\n"

    message += f"\n\U0001f5d1 \u0414\u043b\u044f \u0443\u0434\u0430\u043b\u0435\u043d\u0438\u044f: /delete <id>"
    await update.message.reply_text(message, parse_mode='HTML')


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /delete <id> command."""
    if not _is_authorized(update):
        return

    if not context.args:
        await update.message.reply_text("\u2753 \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /delete <id>")
        return

    try:
        event_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("\u274c ID \u0434\u043e\u043b\u0436\u0435\u043d \u0431\u044b\u0442\u044c \u0447\u0438\u0441\u043b\u043e\u043c")
        return

    if delete_event(event_id):
        await update.message.reply_text(f"\u2705 \u0421\u043e\u0431\u044b\u0442\u0438\u0435 #{event_id} \u0443\u0434\u0430\u043b\u0435\u043d\u043e")
    else:
        await update.message.reply_text(f"\u274c \u0421\u043e\u0431\u044b\u0442\u0438\u0435 #{event_id} \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e")


async def cmd_correlations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /correlations command."""
    if not _is_authorized(update):
        return

    report = get_correlation_report()
    await update.message.reply_text(report, parse_mode='HTML')


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /export command - export data as CSV."""
    if not _is_authorized(update):
        return

    import csv
    import io
    from bot.core.database import fetchall

    output = io.StringIO()
    writer = csv.writer(output)

    # Export daily metrics
    rows = fetchall("SELECT * FROM daily_metrics ORDER BY day")
    if rows:
        writer.writerow(rows[0].keys())
        for row in rows:
            writer.writerow(tuple(row))

    csv_content = output.getvalue()
    output.close()

    if csv_content:
        from telegram import InputFile
        bio = io.BytesIO(csv_content.encode('utf-8'))
        bio.name = 'oura_data_export.csv'
        await update.message.reply_document(document=bio, caption="\U0001f4e6 \u042d\u043a\u0441\u043f\u043e\u0440\u0442 \u0434\u0430\u043d\u043d\u044b\u0445 Oura")
    else:
        await update.message.reply_text("\u274c \u041d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445 \u0434\u043b\u044f \u044d\u043a\u0441\u043f\u043e\u0440\u0442\u0430")


def _schedule_hr_check(context: ContextTypes.DEFAULT_TYPE, event_id: int,
                       event_type: str, event_time: datetime):
    """Schedule HR check 60 minutes after event."""
    from bot.alerts.intraday import check_hr_after_event

    async def _check(ctx):
        await check_hr_after_event(event_id, event_type, event_time)

    context.job_queue.run_once(_check, when=3600, name=f"hr_check_{event_id}")
    logger.info("HR check scheduled for event %d in 60 min", event_id)
