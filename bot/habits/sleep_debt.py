"""
Sleep debt calculation and payoff forecast.
"""

import logging

from bot.core.database import fetchall

logger = logging.getLogger(__name__)

TARGET_SLEEP_HOURS = 7.5


def calculate_sleep_debt(days: int = 14) -> dict | None:
    """
    Calculate accumulated sleep debt.

    Returns:
        dict with debt_hours, avg_sleep, days_to_payoff, label
    """
    rows = fetchall(
        "SELECT total_sleep_duration FROM daily_metrics WHERE total_sleep_duration IS NOT NULL ORDER BY day DESC LIMIT ?",
        (days,),
    )

    if len(rows) < 3:
        return None

    sleep_hours = [row['total_sleep_duration'] / 3600 for row in rows]
    avg_sleep = sum(sleep_hours) / len(sleep_hours)

    # Debt = sum of (target - actual) for each day, only count deficits
    debt = sum(max(0, TARGET_SLEEP_HOURS - h) for h in sleep_hours)

    # Days to payoff: assuming 30 min extra sleep per night
    extra_per_night = 0.5  # hours
    days_to_payoff = int(debt / extra_per_night) + 1 if debt > 0 else 0

    if debt <= 0:
        label = "\U0001f7e2 \u041d\u0435\u0442 \u0434\u043e\u043b\u0433\u0430 \u0441\u043d\u0430"
    elif debt <= 3:
        label = "\U0001f7e1 \u041d\u0435\u0431\u043e\u043b\u044c\u0448\u043e\u0439 \u0434\u043e\u043b\u0433"
    elif debt <= 7:
        label = "\U0001f7e0 \u0417\u043d\u0430\u0447\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0439 \u0434\u043e\u043b\u0433"
    else:
        label = "\U0001f534 \u041a\u0440\u0438\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u0434\u043e\u043b\u0433"

    return {
        'debt_hours': debt,
        'avg_sleep': avg_sleep,
        'days_to_payoff': days_to_payoff,
        'label': label,
    }


def get_sleep_debt_section() -> str | None:
    """Generate sleep debt section for reports."""
    data = calculate_sleep_debt()
    if not data:
        return None

    section = "<b>\U0001f4b0 \u0414\u041e\u041b\u0413 \u0421\u041d\u0410</b>\n"
    section += f"  \u0421\u0440\u0435\u0434\u043d\u0438\u0439 \u0441\u043e\u043d: {data['avg_sleep']:.1f}\u0447 (\u0446\u0435\u043b\u044c: {TARGET_SLEEP_HOURS}\u0447)\n"

    if data['debt_hours'] > 0:
        section += f"  \u041d\u0430\u043a\u043e\u043f\u043b\u0435\u043d\u043d\u044b\u0439 \u0434\u043e\u043b\u0433: <b>{data['debt_hours']:.1f}\u0447</b>\n"
        section += f"  \u041f\u0440\u043e\u0433\u043d\u043e\u0437 \u043f\u043e\u0433\u0430\u0448\u0435\u043d\u0438\u044f: ~{data['days_to_payoff']} \u0434\u043d\u0435\u0439 (+30\u043c\u0438\u043d/\u043d\u043e\u0447\u044c)\n"
    section += f"  {data['label']}\n\n"
    return section
