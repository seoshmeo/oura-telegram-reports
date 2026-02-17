"""
Weather-based alerts for critical conditions.
"""

import logging
from datetime import datetime

from bot.weather.client import fetch_weather
from bot.core.telegram import send_telegram_message

logger = logging.getLogger(__name__)


async def check_weather_alerts():
    """Check for critical weather conditions and send alert."""
    data = await fetch_weather()
    if not data or not data.get('is_critical'):
        return

    reasons = data.get('critical_reasons', [])
    if not reasons:
        return

    message = "<b>\U0001f326\ufe0f \u041f\u041e\u0413\u041e\u0414\u041d\u042b\u0419 \u0410\u041b\u0415\u0420\u0422</b>\n\n"
    for reason in reasons:
        message += f"\u26a0\ufe0f {reason}\n"

    # Add health recommendations based on conditions
    recs = []
    for reason in reasons:
        if "\u0416\u0430\u0440\u0430" in reason:
            recs.append("\u0418\u0437\u0431\u0435\u0433\u0430\u0439\u0442\u0435 \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0441\u0442\u0438 \u043d\u0430 \u0443\u043b\u0438\u0446\u0435, \u043f\u0435\u0439\u0442\u0435 \u0431\u043e\u043b\u044c\u0448\u0435 \u0432\u043e\u0434\u044b")
        if "PM" in reason or "AQI" in reason:
            recs.append("\u041e\u0433\u0440\u0430\u043d\u0438\u0447\u044c\u0442\u0435 \u043f\u0440\u0435\u0431\u044b\u0432\u0430\u043d\u0438\u0435 \u043d\u0430 \u0443\u043b\u0438\u0446\u0435, \u043f\u044b\u043b\u044c \u0432 \u0432\u043e\u0437\u0434\u0443\u0445\u0435")
        if "\u0412\u0435\u0442\u0435\u0440" in reason:
            recs.append("\u0421\u0438\u043b\u044c\u043d\u044b\u0439 \u0432\u0435\u0442\u0435\u0440 - \u0431\u0443\u0434\u044c\u0442\u0435 \u043e\u0441\u0442\u043e\u0440\u043e\u0436\u043d\u044b \u043d\u0430 \u0443\u043b\u0438\u0446\u0435")
        if "UV" in reason:
            recs.append("\u0412\u044b\u0441\u043e\u043a\u0438\u0439 UV - \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439\u0442\u0435 \u0441\u043e\u043b\u043d\u0446\u0435\u0437\u0430\u0449\u0438\u0442\u043d\u044b\u0439 \u043a\u0440\u0435\u043c")

    if recs:
        message += "\n<b>\U0001f4a1 \u0420\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0430\u0446\u0438\u0438:</b>\n"
        for rec in recs:
            message += f"  \u2022 {rec}\n"

    await send_telegram_message(message)
    logger.info("Weather alert sent: %s", reasons)
