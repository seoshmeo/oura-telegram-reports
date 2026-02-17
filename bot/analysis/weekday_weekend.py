"""
Weekday vs Weekend analysis.
"""

import logging
import statistics

from bot.core.database import fetchall

logger = logging.getLogger(__name__)


def get_weekday_weekend_stats() -> dict | None:
    """Compare metrics for weekdays vs weekends."""
    weekday_rows = fetchall(
        "SELECT * FROM daily_metrics WHERE is_weekend = 0 ORDER BY day DESC LIMIT 60"
    )
    weekend_rows = fetchall(
        "SELECT * FROM daily_metrics WHERE is_weekend = 1 ORDER BY day DESC LIMIT 30"
    )

    if len(weekday_rows) < 5 or len(weekend_rows) < 2:
        return None

    def avg(rows, field):
        vals = [r[field] for r in rows if r[field] is not None]
        return statistics.mean(vals) if vals else None

    metrics = ['sleep_score', 'readiness_score', 'total_sleep_duration',
               'average_hrv', 'lowest_heart_rate', 'steps', 'stress_high']

    result = {}
    for m in metrics:
        wd = avg(weekday_rows, m)
        we = avg(weekend_rows, m)
        if wd is not None and we is not None:
            result[m] = {
                'weekday': wd,
                'weekend': we,
                'delta': we - wd,
                'delta_pct': ((we - wd) / wd * 100) if wd != 0 else 0,
            }

    return result if result else None


def get_weekday_weekend_section() -> str | None:
    """Generate weekday vs weekend section for weekly report."""
    data = get_weekday_weekend_stats()
    if not data:
        return None

    section = "<b>\U0001f4c6 \u0411\u0423\u0414\u041d\u0418 vs \u0412\u042b\u0425\u041e\u0414\u041d\u042b\u0415</b>\n"

    labels = {
        'sleep_score': ('\u0421\u043e\u043d', '', 0),
        'total_sleep_duration': ('\u0414\u043b\u0438\u0442. \u0441\u043d\u0430', '\u0447', 1),
        'average_hrv': ('HRV', '\u043c\u0441', 0),
        'steps': ('\u0428\u0430\u0433\u0438', '', 0),
    }

    for metric, (label, unit, decimals) in labels.items():
        if metric not in data:
            continue
        d = data[metric]
        wd = d['weekday']
        we = d['weekend']
        # For sleep duration convert seconds to hours
        if metric == 'total_sleep_duration':
            wd /= 3600
            we /= 3600

        delta = we - wd if metric != 'total_sleep_duration' else (d['weekend'] / 3600 - d['weekday'] / 3600)
        arrow = "\u2197\ufe0f" if delta > 0 else "\u2198\ufe0f" if delta < 0 else "\u2192"

        if decimals:
            section += f"  {label}: \u0431\u0443\u0434\u043d\u0438 {wd:.{decimals}f}{unit} | \u0432\u044b\u0445. {we:.{decimals}f}{unit} {arrow}\n"
        else:
            section += f"  {label}: \u0431\u0443\u0434\u043d\u0438 {wd:.0f}{unit} | \u0432\u044b\u0445. {we:.0f}{unit} {arrow}\n"

    section += "\n"
    return section
