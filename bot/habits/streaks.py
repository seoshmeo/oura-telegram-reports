"""
Habit streak tracking.
"""

import logging
from datetime import datetime, timedelta

from bot.core.database import fetchall, fetchone, execute

logger = logging.getLogger(__name__)

# Default habit definitions: (name, metric_field, operator, target)
DEFAULT_HABITS = [
    ('sleep_7h', 'total_sleep_duration', '>=', 7.0 * 3600),       # 7+ hours sleep
    ('steps_8k', 'steps', '>=', 8000),                             # 8000+ steps
    ('bedtime_2300', 'bedtime_end', 'bedtime_before', '23:00'),    # Bedtime before 23:00
    ('hrv_above_avg', 'average_hrv', '>=', None),                  # HRV above personal average
]


def update_streaks():
    """Update all habit streaks based on latest daily_metrics."""
    rows = fetchall("SELECT * FROM daily_metrics ORDER BY day DESC LIMIT 90")
    if not rows:
        return

    rows_asc = list(reversed(rows))

    for habit_name, field, op, target in DEFAULT_HABITS:
        # For HRV, compute personal average as target
        if target is None and field == 'average_hrv':
            vals = [r[field] for r in rows_asc if r[field] is not None]
            if vals:
                target = sum(vals) / len(vals)
            else:
                continue

        current_streak = 0
        best_streak = 0
        streak = 0
        last_day = None

        for row in rows_asc:
            val = row[field]
            if val is None:
                streak = 0
                continue

            hit = False
            if op == '>=':
                hit = val >= target
            elif op == 'bedtime_before':
                # Check bedtime_start time
                bt = row['bedtime_start'] if row['bedtime_start'] else row['bedtime_end']
                if bt:
                    try:
                        bt_time = datetime.fromisoformat(bt.replace('Z', '+00:00'))
                        target_hour, target_min = map(int, target.split(':'))
                        hit = bt_time.hour < target_hour or (bt_time.hour == target_hour and bt_time.minute <= target_min)
                    except (ValueError, AttributeError):
                        hit = False

            if hit:
                streak += 1
                best_streak = max(best_streak, streak)
                last_day = row['day']
            else:
                streak = 0

        current_streak = streak

        execute(
            """INSERT INTO habit_streaks (habit_name, current_streak, best_streak, last_day, target_value, updated_at)
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(habit_name) DO UPDATE SET
               current_streak=excluded.current_streak, best_streak=excluded.best_streak,
               last_day=excluded.last_day, target_value=excluded.target_value,
               updated_at=CURRENT_TIMESTAMP""",
            (habit_name, current_streak, best_streak, last_day, target if isinstance(target, (int, float)) else 0),
        )

    logger.info("Habit streaks updated")


def get_streaks_report() -> str | None:
    """Generate habit streaks section for reports."""
    rows = fetchall("SELECT * FROM habit_streaks ORDER BY habit_name")
    if not rows:
        return None

    labels = {
        'sleep_7h': ('\U0001f4a4 \u0421\u043e\u043d \u22657\u0447', '\u0434\u043d\u0435\u0439'),
        'steps_8k': ('\U0001f6b6 \u0428\u0430\u0433\u0438 \u22658K', '\u0434\u043d\u0435\u0439'),
        'bedtime_2300': ('\U0001f319 \u041e\u0442\u0431\u043e\u0439 \u0434\u043e 23:00', '\u0434\u043d\u0435\u0439'),
        'hrv_above_avg': ('\u2764\ufe0f HRV>\u0441\u0440\u0435\u0434\u043d\u0435\u0433\u043e', '\u0434\u043d\u0435\u0439'),
    }

    section = "<b>\U0001f525 \u0421\u0415\u0420\u0418\u0418 \u041f\u0420\u0418\u0412\u042b\u0427\u0415\u041a</b>\n"
    for row in rows:
        label, unit = labels.get(row['habit_name'], (row['habit_name'], '\u0434.'))
        current = row['current_streak']
        best = row['best_streak']

        fire = "\U0001f525" if current >= 7 else "\u2b50" if current >= 3 else ""
        section += f"  {label}: <b>{current}</b> {unit} {fire}"
        if best > current:
            section += f" (\u0440\u0435\u043a\u043e\u0440\u0434: {best})"
        section += "\n"

    section += "\n"
    return section
