"""
Intraday signals: morning readiness signal and post-event HR monitoring.
"""

import logging
from datetime import datetime, timedelta

from bot.core.oura_api import get_oura_data_range, get_oura_data
from bot.core.telegram import send_telegram_message
from bot.core.database import fetchall, execute

logger = logging.getLogger(__name__)


async def send_morning_signal():
    """Send morning readiness signal based on today's readiness score."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')

    readiness = await get_oura_data_range("usercollection/daily_readiness", yesterday, today)
    if not readiness or not readiness.get('data'):
        return

    latest = readiness['data'][-1]
    score = latest.get('score', 0)
    recovery = latest.get('contributors', {}).get('recovery_index', 0)

    if score >= 85 and recovery >= 70:
        signal = "\U0001f7e2 \u0412\u044b \u043d\u0430 \u043f\u0438\u043a\u0435! \u0411\u0435\u0440\u0438\u0442\u0435\u0441\u044c \u0437\u0430 \u0441\u043b\u043e\u0436\u043d\u043e\u0435, \u043f\u043b\u0430\u043d\u0438\u0440\u0443\u0439\u0442\u0435 \u0442\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u043a\u0443."
    elif score >= 70:
        signal = "\U0001f7e1 \u041d\u043e\u0440\u043c\u0430\u043b\u044c\u043d\u044b\u0439 \u0434\u0435\u043d\u044c. \u0420\u0430\u0431\u043e\u0442\u0430\u0439\u0442\u0435 \u0432 \u043e\u0431\u044b\u0447\u043d\u043e\u043c \u0440\u0435\u0436\u0438\u043c\u0435."
    else:
        signal = "\U0001f534 \u0414\u0435\u043d\u044c \u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f. \u0421\u043d\u0438\u0437\u044c\u0442\u0435 \u043d\u0430\u0433\u0440\u0443\u0437\u043a\u0443, \u043e\u0442\u0434\u044b\u0445\u0430\u0439\u0442\u0435."

    message = f"<b>\U0001f305 \u0421\u0418\u0413\u041d\u0410\u041b \u0414\u041d\u042f</b>\n"
    message += f"\u0413\u043e\u0442\u043e\u0432\u043d\u043e\u0441\u0442\u044c: {score}/100 | Recovery: {recovery}\n"
    message += f"{signal}"

    await send_telegram_message(message)
    logger.info("Morning signal sent: score=%d", score)


async def check_hr_after_event(event_id: int, event_type: str, event_time: datetime):
    """Check heart rate 60 minutes after an event and store data."""
    # Fetch 5-minute HR data from Oura
    start = event_time.strftime('%Y-%m-%dT%H:%M:%S')
    end = (event_time + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%S')

    hr_data = await get_oura_data("usercollection/heartrate", {
        'start_datetime': start,
        'end_datetime': end,
    })

    if not hr_data or not hr_data.get('data'):
        logger.debug("No HR data available for event %d", event_id)
        return

    # Store HR samples linked to event
    for sample in hr_data['data']:
        ts = sample.get('timestamp', '')
        bpm = sample.get('bpm', 0)
        if bpm > 0:
            execute(
                "INSERT INTO intraday_hr (timestamp, heart_rate, event_id) VALUES (?, ?, ?)",
                (ts, bpm, event_id),
            )

    # Calculate average HR in different windows
    hr_values = [s['bpm'] for s in hr_data['data'] if s.get('bpm')]
    if hr_values:
        avg_hr = sum(hr_values) / len(hr_values)
        logger.info("Event %d (%s): avg HR post-event = %.0f bpm (%d samples)",
                     event_id, event_type, avg_hr, len(hr_values))


def get_hr_reaction_summary(event_type: str) -> str | None:
    """Get average HR reaction curve for an event type."""
    rows = fetchall(
        """SELECT e.event_type, h.heart_rate,
                  (julianday(h.timestamp) - julianday(e.timestamp)) * 24 * 60 as minutes_after
           FROM intraday_hr h
           JOIN events e ON h.event_id = e.id
           WHERE e.event_type = ?
           ORDER BY minutes_after""",
        (event_type,),
    )

    if len(rows) < 10:
        return None

    # Group by 15-min buckets
    buckets = {}
    for row in rows:
        minutes = int(row['minutes_after'])
        bucket = (minutes // 15) * 15
        if bucket not in buckets:
            buckets[bucket] = []
        buckets[bucket].append(row['heart_rate'])

    if not buckets:
        return None

    summary = f"\U0001f493 HR \u043f\u043e\u0441\u043b\u0435 {event_type}:\n"
    for bucket in sorted(buckets.keys()):
        if bucket > 120:
            break
        avg = sum(buckets[bucket]) / len(buckets[bucket])
        summary += f"  +{bucket}\u043c\u0438\u043d: {avg:.0f} bpm\n"

    return summary
