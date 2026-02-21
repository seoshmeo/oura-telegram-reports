"""
Daily morning report generation.
Refactored from oura_telegram_daily.py.
"""

import logging
from datetime import datetime, timedelta

from bot.core.oura_api import get_oura_data_range, check_sleep_completed
from bot.core.telegram import send_telegram_message
from bot.analysis.percentiles import get_percentile_context
from bot.weather.client import get_weather_summary

logger = logging.getLogger(__name__)


def _emoji_indicator(score: int) -> str:
    if score >= 85:
        return "\U0001f7e2"
    elif score >= 70:
        return "\U0001f7e1"
    else:
        return "\U0001f534"


def _format_time_diff(hours: float) -> str:
    if hours > 0:
        return f"+{hours:.1f}\u0447"
    return f"{hours:.1f}\u0447"


async def generate_daily_report() -> str:
    """Generate the daily morning report."""

    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')

    sleep_data = await get_oura_data_range("usercollection/daily_sleep", yesterday, today)
    readiness_data = await get_oura_data_range("usercollection/daily_readiness", yesterday, today)
    activity_data = await get_oura_data_range("usercollection/daily_activity", yesterday, today)
    sleep_sessions = await get_oura_data_range("usercollection/sleep", yesterday, today)
    stress_data = await get_oura_data_range("usercollection/daily_stress", yesterday, today)

    if not all([sleep_data, readiness_data, activity_data]):
        return "\u274c \u041e\u0448\u0438\u0431\u043a\u0430 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u044f \u0434\u0430\u043d\u043d\u044b\u0445 \u0438\u0437 Oura API"

    sleep = sleep_data['data'][-1] if sleep_data.get('data') else None
    readiness = readiness_data['data'][-1] if readiness_data.get('data') else None
    activity = activity_data['data'][-1] if activity_data.get('data') else None
    last_session = sleep_sessions['data'][-1] if sleep_sessions and sleep_sessions.get('data') else None

    if not all([sleep, readiness, activity]):
        return "\u274c \u041d\u0435\u0434\u043e\u0441\u0442\u0430\u0442\u043e\u0447\u043d\u043e \u0434\u0430\u043d\u043d\u044b\u0445 \u0437\u0430 \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0439 \u0434\u0435\u043d\u044c"

    report_date = datetime.now().strftime('%d.%m.%Y')
    sleep_score = sleep['score']
    readiness_score = readiness['score']

    report = f"<b>\U0001f305 OURA \u0423\u0422\u0420\u0415\u041d\u041d\u0418\u0419 \u041e\u0422\u0427\u0401\u0422</b>\n"
    report += f"\U0001f4c5 {report_date}\n\n"

    # Summary
    report += f"<b>\u0421\u0412\u041e\u0414\u041a\u0410</b>\n"
    report += f"{_emoji_indicator(sleep_score)} \u0421\u043e\u043d: <b>{sleep_score}/100</b>  |  "
    report += f"{_emoji_indicator(readiness_score)} \u0413\u043e\u0442\u043e\u0432\u043d\u043e\u0441\u0442\u044c: <b>{readiness_score}/100</b>\n"

    # Percentile context
    pct_ctx = get_percentile_context(sleep_score, readiness_score)
    if pct_ctx:
        report += pct_ctx + "\n"

    report += "\n"

    # Sleep
    report += f"<b>\U0001f4a4 \u0421\u041e\u041d</b>\n"
    if last_session:
        bedtime_start = datetime.fromisoformat(last_session['bedtime_start'].replace('Z', '+00:00'))
        bedtime_end = datetime.fromisoformat(last_session['bedtime_end'].replace('Z', '+00:00'))
        total_sleep_hours = last_session.get('total_sleep_duration', 0) / 3600
        deep_sleep_hours = last_session.get('deep_sleep_duration', 0) / 3600
        rem_sleep_hours = last_session.get('rem_sleep_duration', 0) / 3600
        light_sleep_hours = last_session.get('light_sleep_duration', 0) / 3600
        sleep_diff = total_sleep_hours - 7.5
        efficiency = last_session.get('efficiency', 0)

        report += f"  \u041e\u0431\u0449\u0438\u0439 \u0441\u043e\u043d: <b>{total_sleep_hours:.1f}\u0447</b> (\u0446\u0435\u043b\u044c: 7.5\u0447) [{_format_time_diff(sleep_diff)}]\n"
        report += f"  \u0417\u0430\u0441\u044b\u043f\u0430\u043d\u0438\u0435: {bedtime_start.strftime('%H:%M')} \u2192 \u041f\u043e\u0434\u044a\u0451\u043c: {bedtime_end.strftime('%H:%M')}\n"
        report += f"  Deep: {deep_sleep_hours:.1f}\u0447 | REM: {rem_sleep_hours:.1f}\u0447 | Light: {light_sleep_hours:.1f}\u0447\n"

        sleep_onset_latency = last_session.get('latency', 0)
        if sleep_onset_latency > 1800:
            report += f"  \u26a0\ufe0f \u0417\u0430\u0441\u044b\u043f\u0430\u043d\u0438\u0435 \u0437\u0430: <b>{sleep_onset_latency // 60} \u043c\u0438\u043d</b>\n"
        else:
            report += f"  \u0417\u0430\u0441\u044b\u043f\u0430\u043d\u0438\u0435 \u0437\u0430: {sleep_onset_latency // 60} \u043c\u0438\u043d\n"
        report += f"  Efficiency: {efficiency}%\n"
    else:
        report += f"  \u0414\u0430\u043d\u043d\u044b\u0435 \u043e \u0441\u0435\u0441\u0441\u0438\u0438 \u0441\u043d\u0430 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b\n"
    report += "\n"

    # Recovery
    report += f"<b>\u2764\ufe0f \u0412\u041e\u0421\u0421\u0422\u0410\u041d\u041e\u0412\u041b\u0415\u041d\u0418\u0415</b>\n"
    if last_session:
        hrv = last_session.get('average_hrv', 0)
        lowest_hr = last_session.get('lowest_heart_rate', 0)
        avg_hr = last_session.get('average_heart_rate', 0)
        report += f"  HRV \u0437\u0430 \u043d\u043e\u0447\u044c: {hrv} \u043c\u0441\n"
        report += f"  \u041c\u0438\u043d. \u043f\u0443\u043b\u044c\u0441: {lowest_hr} bpm\n"
        report += f"  \u0421\u0440\u0435\u0434\u043d\u0438\u0439 \u043f\u0443\u043b\u044c\u0441 \u0441\u043d\u0430: {avg_hr:.0f} bpm\n"

    recovery_index = readiness['contributors'].get('recovery_index', 0)
    if recovery_index < 30:
        report += f"  \u26a0\ufe0f\u26a0\ufe0f\u26a0\ufe0f Recovery Index: <b>{recovery_index}</b> [\u041a\u0420\u0418\u0422\u0418\u0427\u041d\u041e]\n"
    elif recovery_index < 50:
        report += f"  \u26a0\ufe0f Recovery Index: <b>{recovery_index}</b>\n"
    else:
        report += f"  Recovery Index: {recovery_index}\n"

    temp_dev = readiness.get('temperature_deviation', 0)
    if abs(temp_dev) > 1.0:
        report += f"  \u26a0\ufe0f \u0422\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430: <b>{temp_dev:+.2f}\u00b0C</b>\n"
    else:
        report += f"  \u0422\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430: {temp_dev:+.2f}\u00b0C\n"
    report += "\n"

    # Stress
    stress = None
    if stress_data and stress_data.get('data'):
        stress = stress_data['data'][-1]

    if stress:
        report += f"<b>\U0001f9d8 \u0421\u0422\u0420\u0415\u0421\u0421</b>\n"
        day_summary = stress.get('day_summary', 'unknown')
        summary_labels = {
            'restored': '\U0001f7e2 \u0412\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d',
            'normal': '\U0001f7e1 \u041d\u043e\u0440\u043c\u0430\u043b\u044c\u043d\u044b\u0439',
            'stressful': '\U0001f534 \u0421\u0442\u0440\u0435\u0441\u0441\u043e\u0432\u044b\u0439',
        }
        report += f"  \u0421\u0442\u0430\u0442\u0443\u0441 \u0434\u043d\u044f: <b>{summary_labels.get(day_summary, day_summary)}</b>\n"
        stress_high = stress.get('stress_high', 0)
        recovery_high = stress.get('recovery_high', 0)
        report += f"  \u0412\u044b\u0441\u043e\u043a\u0438\u0439 \u0441\u0442\u0440\u0435\u0441\u0441: {stress_high} \u043c\u0438\u043d\n"
        report += f"  \u0412\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435: {recovery_high} \u043c\u0438\u043d\n"
        if recovery_high > 0:
            ratio = stress_high / recovery_high
            ratio_emoji = "\U0001f7e2" if ratio < 1 else "\U0001f7e1" if ratio < 2 else "\U0001f534"
            report += f"  \u0421\u043e\u043e\u0442\u043d\u043e\u0448\u0435\u043d\u0438\u0435 \u0441\u0442\u0440\u0435\u0441\u0441/recovery: {ratio_emoji} {ratio:.1f}\n"
        elif stress_high > 0:
            report += f"  \u26a0\ufe0f \u041d\u0435\u0442 \u0432\u0440\u0435\u043c\u0435\u043d\u0438 \u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f \u043f\u0440\u0438 \u043d\u0430\u043b\u0438\u0447\u0438\u0438 \u0441\u0442\u0440\u0435\u0441\u0441\u0430\n"
        report += "\n"

    # Sleep balance
    sleep_balance = readiness['contributors'].get('sleep_balance', 0)
    report += f"<b>\u2696\ufe0f \u0411\u0410\u041b\u0410\u041d\u0421 \u0421\u041d\u0410</b>\n"
    if sleep_balance < 70:
        report += f"  \u26a0\ufe0f Sleep Balance: <b>{sleep_balance}/100</b>\n"
    else:
        report += f"  Sleep Balance: {sleep_balance}/100\n"
    report += "\n"

    # Weather section
    weather_section = await _get_weather_section()
    if weather_section:
        report += weather_section

    # Recommendations
    report += f"<b>\U0001f4a1 \u0420\u0415\u041a\u041e\u041c\u0415\u041d\u0414\u0410\u0426\u0418\u042f \u0414\u041d\u042f</b>\n"
    recommendations = []
    if sleep_score < 70:
        recommendations.append("\u041f\u0440\u0438\u043e\u0440\u0438\u0442\u0435\u0442: \u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435. \u041b\u043e\u0436\u0438\u0442\u0435\u0441\u044c \u0434\u043e 23:00.")
    if recovery_index < 30:
        recommendations.append("Recovery \u043a\u0440\u0438\u0442\u0438\u0447\u0435\u0441\u043a\u0438 \u043d\u0438\u0437\u043a\u0438\u0439 - \u0438\u0437\u0431\u0435\u0433\u0430\u0439\u0442\u0435 \u0438\u043d\u0442\u0435\u043d\u0441\u0438\u0432\u043d\u044b\u0445 \u043d\u0430\u0433\u0440\u0443\u0437\u043e\u043a.")
    elif recovery_index < 50:
        recommendations.append("\u0412\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435 \u043d\u0435\u043f\u043e\u043b\u043d\u043e\u0435 - \u043b\u0451\u0433\u043a\u0430\u044f \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0441\u0442\u044c (\u043f\u0440\u043e\u0433\u0443\u043b\u043a\u0430).")
    if sleep['contributors'].get('timing', 100) < 50:
        recommendations.append("\u0420\u0435\u0436\u0438\u043c \u0441\u043d\u0430 \u0441\u0431\u0438\u0442 - \u0432\u0435\u0440\u043d\u0438\u0442\u0435\u0441\u044c \u043a 22:30 \u043e\u0442\u0431\u043e\u0439.")
    if temp_dev < -1.0:
        recommendations.append("\u0422\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430 \u043f\u043e\u043d\u0438\u0436\u0435\u043d\u0430 - \u0441\u043b\u0435\u0434\u0438\u0442\u0435 \u0437\u0430 \u0441\u0430\u043c\u043e\u0447\u0443\u0432\u0441\u0442\u0432\u0438\u0435\u043c.")
    if not recommendations:
        if readiness_score >= 85:
            recommendations.append("\u041e\u0442\u043b\u0438\u0447\u043d\u043e\u0435 \u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435! \u041c\u043e\u0436\u043d\u043e \u043f\u043b\u0430\u043d\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0442\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u043a\u0443.")
        else:
            recommendations.append("\u041f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0439\u0442\u0435 \u0440\u0435\u0436\u0438\u043c. \u0426\u0435\u043b\u044c: \u0441\u043e\u043d 7.5\u0447, \u043e\u0442\u0431\u043e\u0439 \u0432 22:30.")
    for rec in recommendations:
        report += f"  \u2022 {rec}\n"
    report += "\n"

    # Yesterday's activity
    report += f"<b>\U0001f3c3 \u0412\u0427\u0415\u0420\u0410\u0428\u041d\u042f\u042f \u0410\u041a\u0422\u0418\u0412\u041d\u041e\u0421\u0422\u042c</b>\n"
    steps = activity.get('steps', 0)
    active_cal = activity.get('active_calories', 0)
    total_cal = activity.get('calories', 0)
    medium_activity = activity.get('medium_activity_time', 0) // 60

    steps_emoji = "\u2705" if steps >= 8000 else "\u26a0\ufe0f"
    activity_emoji = "\u2705" if medium_activity >= 30 else "\u26a0\ufe0f"

    report += f"  {steps_emoji} \u0428\u0430\u0433\u0438: <b>{steps:,}</b> (\u0446\u0435\u043b\u044c: 8000)\n"
    report += f"  \u041a\u0430\u043b\u043e\u0440\u0438\u0438: {active_cal} \u0430\u043a\u0442. / {total_cal} \u0432\u0441\u0435\u0433\u043e\n"
    report += f"  {activity_emoji} Medium activity: <b>{medium_activity} \u043c\u0438\u043d</b> (\u0446\u0435\u043b\u044c: 30 \u043c\u0438\u043d)\n"

    return report


async def _get_weather_section() -> str | None:
    """Get weather section for daily report."""
    try:
        summary = await get_weather_summary()
        if summary:
            return summary
    except Exception as e:
        logger.debug("Weather unavailable: %s", e)
    return None


async def run_daily_report():
    """Generate and send the daily report."""
    logger.info("Generating daily report...")

    report = await generate_daily_report()
    if report.startswith("\u274c"):
        logger.error(report)
        return False

    success = await send_telegram_message(report)
    if not success:
        logger.error("Failed to send daily report")
        return False

    logger.info("Daily report sent")
    return True
