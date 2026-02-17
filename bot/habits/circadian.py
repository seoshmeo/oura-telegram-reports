"""
Circadian rhythm stability tracking.
Target: bedtime stdev < 30 minutes.
"""

import logging
import statistics
from datetime import datetime

from bot.core.database import fetchall

logger = logging.getLogger(__name__)


def get_circadian_stability(days: int = 14) -> dict | None:
    """
    Calculate circadian rhythm stability.

    Returns dict with:
        - bedtime_stdev_min: stdev of bedtime in minutes
        - avg_bedtime: average bedtime as HH:MM
        - stability_score: 0-100 (100 = perfect, <30min stdev)
        - label: emoji + text
    """
    rows = fetchall(
        "SELECT bedtime_start FROM daily_metrics WHERE bedtime_start IS NOT NULL ORDER BY day DESC LIMIT ?",
        (days,),
    )

    if len(rows) < 5:
        return None

    # Convert bedtime to minutes past midnight
    bedtime_minutes = []
    for row in rows:
        try:
            bt = datetime.fromisoformat(row['bedtime_start'].replace('Z', '+00:00'))
            # Convert to local minutes past midnight
            bt_local = bt.astimezone()
            minutes = bt_local.hour * 60 + bt_local.minute
            # Handle after-midnight bedtimes (0:00-6:00 -> add 24h)
            if minutes < 360:  # Before 6 AM
                minutes += 1440
            bedtime_minutes.append(minutes)
        except (ValueError, AttributeError):
            continue

    if len(bedtime_minutes) < 5:
        return None

    stdev_min = statistics.stdev(bedtime_minutes)
    avg_min = statistics.mean(bedtime_minutes)

    # Convert average back to HH:MM
    avg_min_normalized = avg_min % 1440
    avg_hour = int(avg_min_normalized // 60)
    avg_minute = int(avg_min_normalized % 60)
    avg_bedtime = f"{avg_hour:02d}:{avg_minute:02d}"

    # Stability score: 100 if stdev=0, 0 if stdev>=60min
    stability_score = max(0, min(100, int(100 - (stdev_min / 60 * 100))))

    if stdev_min <= 15:
        label = "\U0001f7e2 \u041e\u0442\u043b\u0438\u0447\u043d\u0430\u044f \u0441\u0442\u0430\u0431\u0438\u043b\u044c\u043d\u043e\u0441\u0442\u044c"
    elif stdev_min <= 30:
        label = "\U0001f7e1 \u0425\u043e\u0440\u043e\u0448\u0430\u044f \u0441\u0442\u0430\u0431\u0438\u043b\u044c\u043d\u043e\u0441\u0442\u044c"
    elif stdev_min <= 45:
        label = "\U0001f7e0 \u0423\u043c\u0435\u0440\u0435\u043d\u043d\u0430\u044f \u043d\u0435\u0441\u0442\u0430\u0431\u0438\u043b\u044c\u043d\u043e\u0441\u0442\u044c"
    else:
        label = "\U0001f534 \u041d\u0435\u0441\u0442\u0430\u0431\u0438\u043b\u044c\u043d\u044b\u0439 \u0440\u0438\u0442\u043c"

    return {
        'bedtime_stdev_min': stdev_min,
        'avg_bedtime': avg_bedtime,
        'stability_score': stability_score,
        'label': label,
    }


def get_circadian_section() -> str | None:
    """Generate circadian rhythm section for reports."""
    data = get_circadian_stability()
    if not data:
        return None

    section = "<b>\U0001f570\ufe0f \u0426\u0418\u0420\u041a\u0410\u0414\u041d\u042b\u0419 \u0420\u0418\u0422\u041c</b>\n"
    section += f"  \u0421\u0440\u0435\u0434\u043d\u0438\u0439 \u043e\u0442\u0431\u043e\u0439: {data['avg_bedtime']}\n"
    section += f"  \u0420\u0430\u0437\u0431\u0440\u043e\u0441: \u00b1{data['bedtime_stdev_min']:.0f} \u043c\u0438\u043d (\u0446\u0435\u043b\u044c: <30)\n"
    section += f"  {data['label']}\n\n"
    return section
