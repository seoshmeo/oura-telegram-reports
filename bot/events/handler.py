"""
Telegram message handler for interactive event input.
"""

import json
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes, CallbackContext

from bot.events.parser import parse_event, get_event_emoji
from bot.events.tracker import (
    add_event, get_today_events, delete_event, get_events_range,
    add_measurement, get_last_measurement, get_recent_measurements, get_measurement_stats,
)
from bot.events.voice import download_and_transcribe
from bot.analysis.correlator import get_correlation_report
from bot.analysis.claude_analyzer import OuraClaudeAnalyzer
from bot.config import CLAUDE_API_KEY, TELEGRAM_CHAT_ID
from bot.keyboards import (
    MAIN_KEYBOARD, cancel_keyboard,
    COMMAND_BUTTONS, AWAITING_BUTTONS,
    BTN_EVENTS, BTN_MEDS, BTN_MEASUREMENTS, BTN_BP, BTN_SUGAR, BTN_WEIGHT,
    BTN_LISINOPRIL, BTN_GLUCOPHAGE,
)

logger = logging.getLogger(__name__)


def _is_authorized(update: Update) -> bool:
    """Check if the message is from the authorized chat."""
    return str(update.effective_chat.id) == TELEGRAM_CHAT_ID


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming text messages - buttons, awaiting input, or free text."""
    if not _is_authorized(update):
        return

    text = update.message.text.strip()
    if not text or text.startswith('/'):
        return

    # 1. Handle command buttons
    if text == BTN_EVENTS:
        return await cmd_events(update, context)
    if text == BTN_MEDS:
        return await cmd_meds(update, context)
    if text == BTN_MEASUREMENTS:
        return await cmd_measurements(update, context)

    # 2. Handle measurement buttons (set awaiting state)
    if text == BTN_BP:
        context.user_data['awaiting'] = 'blood_pressure'
        await update.message.reply_text(
            "\U0001fa78 \u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0434\u0430\u0432\u043b\u0435\u043d\u0438\u0435:\n"
            "  <code>120/80</code>\n"
            "  <code>120/80 \u043f\u0443\u043b\u044c\u0441 72</code>",
            parse_mode='HTML',
            reply_markup=MAIN_KEYBOARD,
        )
        return
    if text == BTN_SUGAR:
        context.user_data['awaiting'] = 'blood_sugar'
        await update.message.reply_text(
            "\U0001fa78 \u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0443\u0440\u043e\u0432\u0435\u043d\u044c \u0441\u0430\u0445\u0430\u0440\u0430:\n"
            "  <code>5.6</code>",
            parse_mode='HTML',
            reply_markup=MAIN_KEYBOARD,
        )
        return
    if text == BTN_WEIGHT:
        context.user_data['awaiting'] = 'weight'
        await update.message.reply_text(
            "\u2696\ufe0f \u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0432\u0435\u0441 \u0432 \u043a\u0433:\n"
            "  <code>75.5</code>",
            parse_mode='HTML',
            reply_markup=MAIN_KEYBOARD,
        )
        return

    # 3. Handle awaiting input (user typed just the value after pressing a measurement button)
    awaiting = context.user_data.pop('awaiting', None)
    if awaiting == 'blood_pressure':
        text = f"\u0434\u0430\u0432\u043b\u0435\u043d\u0438\u0435 {text}"
    elif awaiting == 'blood_sugar':
        text = f"\u0441\u0430\u0445\u0430\u0440 {text}"
    elif awaiting == 'weight':
        text = f"\u0432\u0435\u0441 {text}"

    # 3a. Check for pending alert dialog response
    from bot.alerts.monitor import get_alert_dialog, clear_alert_dialog
    alert_dialog = get_alert_dialog()
    if alert_dialog and not awaiting:
        clear_alert_dialog()
        from bot.analysis.chat import answer_alert_followup
        try:
            response = await answer_alert_followup(alert_dialog['context'], text)
            if response:
                await update.message.reply_text(response, reply_markup=MAIN_KEYBOARD)
        except Exception as e:
            logger.error("Alert followup error: %s", e)
        return

    # 3b. Default dosages for medication buttons
    if text == BTN_LISINOPRIL:
        text = "\u043b\u0438\u0437\u0438\u043d\u043e\u043f\u0440\u0438\u043b 5\u043c\u0433"
    elif text == BTN_GLUCOPHAGE:
        text = "\u0433\u043b\u044e\u043a\u043e\u0444\u0430\u0436 500\u043c\u0433"

    # 4. Skip regex parsing for likely questions (avoid "кофе" in "как кофе влияет на сон?")
    is_likely_question = text.rstrip().endswith('?') and len(text) > 15

    # 5. Parse event (regex, then Claude fallback)
    parsed = None if is_likely_question else parse_event(text)

    if not parsed and CLAUDE_API_KEY and not is_likely_question:
        try:
            analyzer = OuraClaudeAnalyzer(api_key=CLAUDE_API_KEY)
            parsed = analyzer.parse_event(text)
        except Exception as e:
            logger.debug("Claude parse failed: %s", e)

    if not parsed:
        from bot.analysis.chat import is_health_question, answer_health_question
        if is_health_question(text):
            try:
                response = await answer_health_question(text)
                if response:
                    await update.message.reply_text(response, reply_markup=MAIN_KEYBOARD)
            except Exception as e:
                logger.error("AI chat error: %s", e)
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

    # Save health measurements if applicable
    measurement_info = _save_measurement_if_needed(event_type, details, 'text', event_time)

    time_str = event_time.strftime('%H:%M')
    metrics_str = ", ".join(metrics[:3]) if metrics else ""

    # Build confirmation
    if measurement_info:
        confirmation = measurement_info
    elif event_type.startswith('med_'):
        confirmation = _format_med_confirmation(event_type, details, time_str)
    else:
        confirmation = f"{emoji} <b>{event_type.replace('_', ' ').title()}</b> \u0437\u0430\u043f\u0438\u0441\u0430\u043d\u043e \u0432 {time_str}"
        if metrics_str:
            confirmation += f"\n\U0001f50d \u041f\u043e\u0441\u043c\u043e\u0442\u0440\u044e \u0432\u043b\u0438\u044f\u043d\u0438\u0435 \u043d\u0430: {metrics_str}"

    await update.message.reply_text(
        confirmation, parse_mode='HTML',
        reply_markup=cancel_keyboard(event_id),
    )

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

    # Save health measurements if applicable
    measurement_info = _save_measurement_if_needed(event_type, details, 'voice')

    time_str = datetime.now().strftime('%H:%M')
    if measurement_info:
        reply = f"\U0001f3a4 \u0420\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u043d\u043e: \u00ab{text}\u00bb\n{measurement_info}"
    elif event_type.startswith('med_'):
        reply = f"\U0001f3a4 \u0420\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u043d\u043e: \u00ab{text}\u00bb\n{_format_med_confirmation(event_type, details, time_str)}"
    else:
        reply = f"\U0001f3a4 \u0420\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u043d\u043e: \u00ab{text}\u00bb\n{emoji} \u0417\u0430\u043f\u0438\u0441\u0430\u043d\u043e \u0432 {time_str}"
    await update.message.reply_text(reply, parse_mode='HTML')

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


MED_LABELS = {
    'med_lisinopril': ('\U0001f48a \u041b\u0438\u0437\u0438\u043d\u043e\u043f\u0440\u0438\u043b', '\u0434\u0430\u0432\u043b\u0435\u043d\u0438\u0435, \u043f\u0443\u043b\u044c\u0441, HRV'),
    'med_glucophage': ('\U0001f48a \u0413\u043b\u044e\u043a\u043e\u0444\u0430\u0436', '\u0441\u0430\u0445\u0430\u0440, \u0441\u043e\u043d, \u0433\u043e\u0442\u043e\u0432\u043d\u043e\u0441\u0442\u044c'),
}


def _format_med_confirmation(event_type: str, details: dict, time_str: str) -> str:
    """Format medication intake confirmation."""
    default_label = "\U0001f48a \u041b\u0435\u043a\u0430\u0440\u0441\u0442\u0432\u043e"
    label, tracks = MED_LABELS.get(event_type, (default_label, ''))
    msg = f"{label}"
    if details.get('dosage'):
        unit = details.get('dosage_unit', "\u043c\u0433")
        msg += f" {details['dosage']}{unit}"
    msg += f" \u043f\u0440\u0438\u043d\u044f\u0442\u043e \u0432 {time_str}"
    if tracks:
        msg += f"\n\U0001f50d \u041e\u0442\u0441\u043b\u0435\u0436\u0438\u0432\u0430\u044e \u0432\u043b\u0438\u044f\u043d\u0438\u0435 \u043d\u0430: {tracks}"
    return msg


async def cmd_meds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /meds command - show medication intake today and recent history."""
    if not _is_authorized(update):
        return

    from bot.core.database import fetchall
    today = datetime.now().strftime('%Y-%m-%d')

    # Today's medication events
    today_meds = [
        dict(row) for row in fetchall(
            """SELECT * FROM events
               WHERE event_type LIKE 'med_%' AND date(timestamp) = ?
               ORDER BY timestamp""",
            (today,),
        )
    ]

    # Last 7 days summary
    from datetime import timedelta
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    week_meds = [
        dict(row) for row in fetchall(
            """SELECT date(timestamp) as day, event_type, COUNT(*) as cnt
               FROM events
               WHERE event_type LIKE 'med_%' AND date(timestamp) >= ?
               GROUP BY date(timestamp), event_type
               ORDER BY day DESC""",
            (week_ago,),
        )
    ]

    if not today_meds and not week_meds:
        await update.message.reply_text(
            "\U0001f48a \u041d\u0435\u0442 \u0437\u0430\u043f\u0438\u0441\u0435\u0439 \u043e \u043f\u0440\u0438\u0451\u043c\u0435 \u043b\u0435\u043a\u0430\u0440\u0441\u0442\u0432.\n\n"
            "\u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435:\n"
            "  \u00ab\u043b\u0438\u0437\u0438\u043d\u043e\u043f\u0440\u0438\u043b\u00bb \u0438\u043b\u0438 \u00ab\u043f\u0440\u0438\u043d\u044f\u043b \u043b\u0438\u0437\u0438\u043d\u043e\u043f\u0440\u0438\u043b 10\u043c\u0433\u00bb\n"
            "  \u00ab\u0433\u043b\u044e\u043a\u043e\u0444\u0430\u0436\u00bb \u0438\u043b\u0438 \u00ab\u043c\u0435\u0442\u0444\u043e\u0440\u043c\u0438\u043d 500\u00bb"
        )
        return

    msg = "<b>\U0001f48a \u041b\u0415\u041a\u0410\u0420\u0421\u0422\u0412\u0410</b>\n"

    if today_meds:
        msg += "\n<b>\u0421\u0435\u0433\u043e\u0434\u043d\u044f:</b>\n"
        for ev in today_meds:
            ts = datetime.fromisoformat(ev['timestamp'])
            label = MED_LABELS.get(ev['event_type'], ('\U0001f48a', ''))[0]
            details = {}
            try:
                details = json.loads(ev.get('details', '{}'))
            except Exception:
                pass
            dose_str = ""
            if details.get('dosage'):
                unit = details.get('dosage_unit', "\u043c\u0433")
                dose_str = f" {details['dosage']}{unit}"
            msg += f"  \u2705 {ts.strftime('%H:%M')} - {label}{dose_str}\n"
    else:
        msg += "\n\u26a0\ufe0f <b>\u0421\u0435\u0433\u043e\u0434\u043d\u044f \u043b\u0435\u043a\u0430\u0440\u0441\u0442\u0432\u0430 \u043d\u0435 \u043f\u0440\u0438\u043d\u044f\u0442\u044b!</b>\n"

    if week_meds:
        msg += "\n<b>\u0417\u0430 7 \u0434\u043d\u0435\u0439:</b>\n"
        days_map = {}
        for row in week_meds:
            day = row['day']
            if day == today:
                continue
            if day not in days_map:
                days_map[day] = []
            label = MED_LABELS.get(row['event_type'], ('\U0001f48a', ''))[0]
            count = row['cnt']
            days_map[day].append(f"{label} x{count}" if count > 1 else label)
        for day, items in days_map.items():
            msg += f"  {day}: {', '.join(items)}\n"

    await update.message.reply_text(msg, parse_mode='HTML')


def _save_measurement_if_needed(event_type: str, details: dict, source: str = 'text',
                                timestamp: datetime | None = None) -> str | None:
    """Save health measurement and return formatted confirmation with trend, or None."""
    now = timestamp or datetime.now()
    time_str = now.strftime('%H:%M')

    if event_type == 'blood_pressure' and 'systolic' in details and 'diastolic' in details:
        sys_val = details['systolic']
        dia_val = details['diastolic']

        # Get previous measurement for trend
        prev = get_last_measurement('blood_pressure')

        add_measurement(
            measurement_type='blood_pressure',
            value1=sys_val, value2=dia_val,
            unit='mmHg',
            note=f"pulse:{details['pulse']}" if details.get('pulse') else None,
            source=source, timestamp=now,
        )

        # Format confirmation
        msg = f"\U0001fa78 <b>\u0414\u0430\u0432\u043b\u0435\u043d\u0438\u0435</b> {sys_val}/{dia_val}"
        if details.get('pulse'):
            msg += f" \u043f\u0443\u043b\u044c\u0441 {details['pulse']}"
        msg += f" \u0437\u0430\u043f\u0438\u0441\u0430\u043d\u043e \u0432 {time_str}"

        # Classification
        if sys_val < 120 and dia_val < 80:
            msg += "\n\u2705 \u041d\u043e\u0440\u043c\u0430"
        elif sys_val < 130 and dia_val < 85:
            msg += "\n\U0001f7e1 \u041f\u043e\u0432\u044b\u0448\u0435\u043d\u043d\u043e\u0435 \u043d\u043e\u0440\u043c\u0430\u043b\u044c\u043d\u043e\u0435"
        elif sys_val < 140 and dia_val < 90:
            msg += "\n\U0001f7e0 \u0413\u0438\u043f\u0435\u0440\u0442\u043e\u043d\u0438\u044f 1 \u0441\u0442."
        else:
            msg += "\n\U0001f534 \u0413\u0438\u043f\u0435\u0440\u0442\u043e\u043d\u0438\u044f 2+ \u0441\u0442."

        # Trend vs last measurement
        if prev:
            prev_sys = prev['value1']
            prev_dia = prev['value2']
            d_sys = sys_val - prev_sys
            d_dia = dia_val - prev_dia
            sign_s = "+" if d_sys > 0 else ""
            sign_d = "+" if d_dia > 0 else ""
            arrow = "\u2197\ufe0f" if d_sys > 0 else "\u2198\ufe0f" if d_sys < 0 else "\u27a1\ufe0f"
            msg += f"\n{arrow} \u0412\u0441 \u043f\u0440\u043e\u0448\u043b\u043e\u0433\u043e: {sign_s}{d_sys:.0f}/{sign_d}{d_dia:.0f} mmHg"

        # 30-day stats
        stats = get_measurement_stats('blood_pressure', 30)
        if stats and stats['cnt'] >= 3:
            msg += f"\n\U0001f4ca \u0421\u0440\u0435\u0434\u043d\u0435\u0435 \u0437\u0430 30\u0434: {stats['avg1']:.0f}/{stats['avg2']:.0f}"

        return msg

    elif event_type == 'blood_sugar' and 'glucose' in details:
        glucose = details['glucose']

        # Get previous measurement for trend
        prev = get_last_measurement('blood_sugar')

        add_measurement(
            measurement_type='blood_sugar',
            value1=glucose, value2=None,
            unit='mmol/L',
            source=source, timestamp=now,
        )

        # Format confirmation
        msg = f"\U0001fa78 <b>\u0421\u0430\u0445\u0430\u0440</b> {glucose} \u043c\u043c\u043e\u043b\u044c/\u043b \u0437\u0430\u043f\u0438\u0441\u0430\u043d\u043e \u0432 {time_str}"

        # Classification (fasting glucose)
        if glucose < 3.9:
            msg += "\n\U0001f534 \u0413\u0438\u043f\u043e\u0433\u043b\u0438\u043a\u0435\u043c\u0438\u044f!"
        elif glucose <= 5.5:
            msg += "\n\u2705 \u041d\u043e\u0440\u043c\u0430"
        elif glucose <= 6.9:
            msg += "\n\U0001f7e1 \u041f\u043e\u0432\u044b\u0448\u0435\u043d\u043d\u044b\u0439"
        else:
            msg += "\n\U0001f534 \u0412\u044b\u0441\u043e\u043a\u0438\u0439!"

        # Trend vs last measurement
        if prev:
            prev_glucose = prev['value1']
            d = glucose - prev_glucose
            sign = "+" if d > 0 else ""
            arrow = "\u2197\ufe0f" if d > 0 else "\u2198\ufe0f" if d < 0 else "\u27a1\ufe0f"
            msg += f"\n{arrow} \u0412\u0441 \u043f\u0440\u043e\u0448\u043b\u043e\u0433\u043e: {sign}{d:.1f} \u043c\u043c\u043e\u043b\u044c/\u043b"

        # 30-day stats
        stats = get_measurement_stats('blood_sugar', 30)
        if stats and stats['cnt'] >= 3:
            msg += f"\n\U0001f4ca \u0421\u0440\u0435\u0434\u043d\u0435\u0435 \u0437\u0430 30\u0434: {stats['avg1']:.1f}"

        return msg

    elif event_type == 'weight' and 'weight_kg' in details:
        weight = details['weight_kg']
        HEIGHT_M = 1.75
        bmi = weight / (HEIGHT_M ** 2)

        prev = get_last_measurement('weight')

        add_measurement(
            measurement_type='weight',
            value1=weight, value2=round(bmi, 1),
            unit='kg', source=source, timestamp=now,
        )

        msg = f"\u2696\ufe0f <b>\u0412\u0435\u0441</b> {weight:.1f} \u043a\u0433 (\u0418\u041c\u0422 {bmi:.1f})"
        msg += f" \u0437\u0430\u043f\u0438\u0441\u0430\u043d\u043e \u0432 {time_str}"

        if bmi < 18.5:
            msg += "\n\U0001f535 \u0414\u0435\u0444\u0438\u0446\u0438\u0442 \u043c\u0430\u0441\u0441\u044b"
        elif bmi < 25:
            msg += "\n\u2705 \u041d\u043e\u0440\u043c\u0430"
        elif bmi < 30:
            msg += "\n\U0001f7e1 \u0418\u0437\u0431\u044b\u0442\u043e\u0447\u043d\u044b\u0439 \u0432\u0435\u0441"
        else:
            msg += "\n\U0001f534 \u041e\u0436\u0438\u0440\u0435\u043d\u0438\u0435"

        if prev:
            d = weight - prev['value1']
            sign = "+" if d > 0 else ""
            arrow = "\u2197\ufe0f" if d > 0 else "\u2198\ufe0f" if d < 0 else "\u27a1\ufe0f"
            msg += f"\n{arrow} Vs \u043f\u0440\u043e\u0448\u043b\u043e\u0433\u043e: {sign}{d:.1f} \u043a\u0433"

        stats = get_measurement_stats('weight', 30)
        if stats and stats['cnt'] >= 3:
            msg += f"\n\U0001f4ca \u0421\u0440\u0435\u0434\u043d\u0435\u0435 \u0437\u0430 30\u0434: {stats['avg1']:.1f} \u043a\u0433"

        return msg

    return None


async def cmd_measurements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /measurements command - show recent health measurements."""
    if not _is_authorized(update):
        return

    bp_readings = get_recent_measurements('blood_pressure', 10)
    sugar_readings = get_recent_measurements('blood_sugar', 10)
    weight_readings = get_recent_measurements('weight', 10)

    if not bp_readings and not sugar_readings and not weight_readings:
        await update.message.reply_text(
            "\U0001f4cb \u041d\u0435\u0442 \u0438\u0437\u043c\u0435\u0440\u0435\u043d\u0438\u0439.\n\n"
            "\u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435:\n"
            "  \u00ab\u0434\u0430\u0432\u043b\u0435\u043d\u0438\u0435 120/80\u00bb\n"
            "  \u00ab\u0441\u0430\u0445\u0430\u0440 5.6\u00bb\n"
            "  \u00ab\u0432\u0435\u0441 75.5\u00bb"
        )
        return

    msg = "<b>\U0001fa78 \u0418\u0417\u041c\u0415\u0420\u0415\u041d\u0418\u042f</b>\n"

    if bp_readings:
        msg += "\n<b>\U0001f4c9 \u0414\u0430\u0432\u043b\u0435\u043d\u0438\u0435</b>\n"
        for r in bp_readings:
            ts = datetime.fromisoformat(r['timestamp'])
            sys_val = r['value1']
            dia_val = r['value2']
            note = r.get('note', '')
            pulse_str = ""
            if note and note.startswith('pulse:'):
                pulse_str = f" \u2764\ufe0f{note.split(':')[1]}"
            # Color indicator
            if sys_val < 120 and dia_val < 80:
                dot = "\u2705"
            elif sys_val < 140 and dia_val < 90:
                dot = "\U0001f7e1"
            else:
                dot = "\U0001f534"
            msg += f"  {dot} {ts.strftime('%d.%m %H:%M')} - <b>{sys_val:.0f}/{dia_val:.0f}</b>{pulse_str}\n"

        bp_stats = get_measurement_stats('blood_pressure', 30)
        if bp_stats and bp_stats['cnt'] >= 3:
            msg += f"  \U0001f4ca 30\u0434: \u0441\u0440 {bp_stats['avg1']:.0f}/{bp_stats['avg2']:.0f}"
            msg += f" (\u043c\u0438\u043d {bp_stats['min1']:.0f}/{bp_stats['min2']:.0f}"
            msg += f" \u043c\u0430\u043a\u0441 {bp_stats['max1']:.0f}/{bp_stats['max2']:.0f})\n"

    if sugar_readings:
        msg += "\n<b>\U0001f4c9 \u0421\u0430\u0445\u0430\u0440</b>\n"
        for r in sugar_readings:
            ts = datetime.fromisoformat(r['timestamp'])
            glucose = r['value1']
            if glucose < 3.9:
                dot = "\U0001f534"
            elif glucose <= 5.5:
                dot = "\u2705"
            elif glucose <= 6.9:
                dot = "\U0001f7e1"
            else:
                dot = "\U0001f534"
            msg += f"  {dot} {ts.strftime('%d.%m %H:%M')} - <b>{glucose:.1f}</b> \u043c\u043c\u043e\u043b\u044c/\u043b\n"

        sugar_stats = get_measurement_stats('blood_sugar', 30)
        if sugar_stats and sugar_stats['cnt'] >= 3:
            msg += f"  \U0001f4ca 30\u0434: \u0441\u0440 {sugar_stats['avg1']:.1f}"
            msg += f" (\u043c\u0438\u043d {sugar_stats['min1']:.1f} \u043c\u0430\u043a\u0441 {sugar_stats['max1']:.1f})\n"

    if weight_readings:
        msg += "\n<b>\u2696\ufe0f \u0412\u0435\u0441</b>\n"
        for r in weight_readings:
            ts = datetime.fromisoformat(r['timestamp'])
            weight = r['value1']
            bmi = r['value2']
            if bmi and bmi < 18.5:
                dot = "\U0001f535"
            elif bmi and bmi < 25:
                dot = "\u2705"
            elif bmi and bmi < 30:
                dot = "\U0001f7e1"
            else:
                dot = "\U0001f534"
            bmi_str = f" \u0418\u041c\u0422={bmi:.1f}" if bmi else ""
            msg += f"  {dot} {ts.strftime('%d.%m %H:%M')} - <b>{weight:.1f}</b> \u043a\u0433{bmi_str}\n"

        weight_stats = get_measurement_stats('weight', 30)
        if weight_stats and weight_stats['cnt'] >= 3:
            msg += f"  \U0001f4ca 30\u0434: \u0441\u0440 {weight_stats['avg1']:.1f} \u043a\u0433"
            msg += f" (\u043c\u0438\u043d {weight_stats['min1']:.1f} \u043c\u0430\u043a\u0441 {weight_stats['max1']:.1f})\n"

    await update.message.reply_text(msg, parse_mode='HTML')


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()

    data = query.data or ''

    # Cancel event: "cancel:123"
    if data.startswith('cancel:'):
        try:
            event_id = int(data.split(':')[1])
            if delete_event(event_id):
                await query.edit_message_text(
                    f"\u274c \u0421\u043e\u0431\u044b\u0442\u0438\u0435 #{event_id} \u043e\u0442\u043c\u0435\u043d\u0435\u043d\u043e"
                )
            else:
                await query.edit_message_text(
                    f"\u2753 \u0421\u043e\u0431\u044b\u0442\u0438\u0435 #{event_id} \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e"
                )
        except (ValueError, IndexError):
            pass


def _schedule_hr_check(context: ContextTypes.DEFAULT_TYPE, event_id: int,
                       event_type: str, event_time: datetime):
    """Schedule HR check 60 minutes after event."""
    from bot.alerts.intraday import check_hr_after_event

    async def _check(ctx):
        await check_hr_after_event(event_id, event_type, event_time)

    context.job_queue.run_once(_check, when=3600, name=f"hr_check_{event_id}")
    logger.info("HR check scheduled for event %d in 60 min", event_id)
