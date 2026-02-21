"""
Weekly report generation.
Refactored from oura_telegram_weekly.py (weekly part).
"""

import logging
import statistics
from datetime import datetime, timedelta

from bot.core.oura_api import get_oura_data_range
from bot.core.telegram import send_telegram_message
from bot.analysis.weekday_weekend import get_weekday_weekend_section
from bot.analysis.claude_analyzer import OuraClaudeAnalyzer
from bot.config import CLAUDE_API_KEY

logger = logging.getLogger(__name__)


def _sparkline(values: list[float]) -> str:
    if not values:
        return ""
    bars = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
    min_val, max_val = min(values), max(values)
    if max_val == min_val:
        return bars[4] * len(values)
    normalized = [(v - min_val) / (max_val - min_val) for v in values]
    return ''.join(bars[min(int(n * 7), 7)] for n in normalized)


def _bar_chart(value: float, max_value: float = 100) -> str:
    filled = int(value / max_value * 10)
    return "\u2588" * filled + "\u2591" * (10 - filled)


async def generate_weekly_report() -> str:
    """Generate weekly report for the last 7 days."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    sleep_data = await get_oura_data_range("usercollection/daily_sleep", start_str, end_str)
    readiness_data = await get_oura_data_range("usercollection/daily_readiness", start_str, end_str)
    activity_data = await get_oura_data_range("usercollection/daily_activity", start_str, end_str)
    workouts_data = await get_oura_data_range("usercollection/workout", start_str, end_str)
    sleep_sessions = await get_oura_data_range("usercollection/sleep", start_str, end_str)
    stress_data = await get_oura_data_range("usercollection/daily_stress", start_str, end_str)

    if not all([sleep_data, readiness_data, activity_data]):
        return "\u274c \u041e\u0448\u0438\u0431\u043a\u0430 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u044f \u0434\u0430\u043d\u043d\u044b\u0445 \u0438\u0437 Oura API"

    sleep_days = sleep_data['data']
    readiness_days = readiness_data['data']
    activity_days = activity_data['data']
    workouts = workouts_data['data'] if workouts_data else []
    sessions = sleep_sessions['data'] if sleep_sessions else []
    stress_days = stress_data['data'] if stress_data and stress_data.get('data') else []

    report = f"<b>\U0001f4ca OURA \u0415\u0416\u0415\u041d\u0415\u0414\u0415\u041b\u042c\u041d\u042b\u0419 \u041e\u0422\u0427\u0401\u0422</b>\n"
    report += f"\u041d\u0435\u0434\u0435\u043b\u044f: {start_date.strftime('%d.%m')} - {end_date.strftime('%d.%m.%Y')}\n\n"

    # Averages
    avg_sleep = statistics.mean([d['score'] for d in sleep_days]) if sleep_days else 0
    avg_readiness = statistics.mean([d['score'] for d in readiness_days]) if readiness_days else 0
    avg_activity = statistics.mean([d['score'] for d in activity_days]) if activity_days else 0

    report += f"<b>\u041e\u0411\u0429\u0418\u0415 \u041e\u0426\u0415\u041d\u041a\u0418 (\u0441\u0440\u0435\u0434\u043d\u0435\u0435 \u0437\u0430 \u043d\u0435\u0434\u0435\u043b\u044e)</b>\n"
    report += f"  \u0421\u043e\u043d:        <b>{avg_sleep:.1f}</b>\n"
    report += f"  \u0413\u043e\u0442\u043e\u0432\u043d\u043e\u0441\u0442\u044c: <b>{avg_readiness:.1f}</b>\n"
    report += f"  \u0410\u043a\u0442\u0438\u0432\u043d\u043e\u0441\u0442\u044c: <b>{avg_activity:.1f}</b>\n\n"

    # Sleep trend
    report += f"<b>\U0001f4a4 \u0422\u0420\u0415\u041d\u0414 \u0421\u041d\u0410</b>\n"
    for day in sleep_days[:7]:
        date_obj = datetime.fromisoformat(day['day'])
        score = day['score']
        bar = _bar_chart(score)
        report += f"  {date_obj.strftime('%d.%m')}: {bar} {score}\n"

    sleep_durations = [s.get('total_sleep_duration', 0) / 3600 for s in sessions if s.get('total_sleep_duration')]
    avg_sleep_hours = statistics.mean(sleep_durations) if sleep_durations else 0
    days_over_7h = sum(1 for d in sleep_durations if d >= 7)

    best_sleep_day = max(sleep_days, key=lambda x: x['score']) if sleep_days else None
    worst_sleep_day = min(sleep_days, key=lambda x: x['score']) if sleep_days else None

    report += f"\n  \u0421\u0440\u0435\u0434\u043d\u0435\u0435 \u0432\u0440\u0435\u043c\u044f \u0441\u043d\u0430: <b>{avg_sleep_hours:.1f}\u0447</b>\n"
    if best_sleep_day:
        report += f"  \u041b\u0443\u0447\u0448\u0430\u044f \u043d\u043e\u0447\u044c: {best_sleep_day['day'][5:]} (score: {best_sleep_day['score']})\n"
    if worst_sleep_day:
        report += f"  \u0425\u0443\u0434\u0448\u0430\u044f \u043d\u043e\u0447\u044c: {worst_sleep_day['day'][5:]} (score: {worst_sleep_day['score']})\n"
    report += f"  \u0414\u043d\u0435\u0439 \u0441 \u0446\u0435\u043b\u0435\u0432\u044b\u043c \u0441\u043d\u043e\u043c (\u22657\u0447): <b>{days_over_7h} \u0438\u0437 {len(sleep_durations)}</b>\n\n"

    # Readiness trend
    report += f"<b>\u2764\ufe0f \u0422\u0420\u0415\u041d\u0414 \u0413\u041e\u0422\u041e\u0412\u041d\u041e\u0421\u0422\u0418</b>\n"
    sleep_balances = [d['contributors'].get('sleep_balance', 0) for d in readiness_days]
    recovery_indexes = [d['contributors'].get('recovery_index', 0) for d in readiness_days]

    if len(sleep_balances) >= 2:
        balance_trend = "\u2197\ufe0f" if sleep_balances[-1] > sleep_balances[0] else "\u2198\ufe0f"
        report += f"  Sleep Balance: {sleep_balances[0]} \u2192 {sleep_balances[-1]} {balance_trend}\n"

    if len(recovery_indexes) >= 2:
        recovery_trend = "\u2197\ufe0f" if recovery_indexes[-1] > recovery_indexes[0] else "\u2198\ufe0f"
        if recovery_indexes[-1] < 30:
            report += f"  \u26a0\ufe0f\u26a0\ufe0f Recovery Index: {recovery_indexes[0]} \u2192 <b>{recovery_indexes[-1]}</b> {recovery_trend}\n"
        else:
            report += f"  Recovery Index: {recovery_indexes[0]} \u2192 {recovery_indexes[-1]} {recovery_trend}\n"

    hrvs = [s.get('average_hrv', 0) for s in sessions if s.get('average_hrv')]
    avg_hrv = statistics.mean(hrvs) if hrvs else 0
    report += f"  \u0421\u0440\u0435\u0434\u043d\u0438\u0439 HRV \u0441\u043d\u0430: {avg_hrv:.0f} \u043c\u0441\n\n"

    # Activity
    report += f"<b>\U0001f3c3 \u0410\u041a\u0422\u0418\u0412\u041d\u041e\u0421\u0422\u042c</b>\n"
    total_steps = sum(d.get('steps', 0) for d in activity_days)
    avg_steps = total_steps / len(activity_days) if activity_days else 0
    total_sedentary = sum(d.get('sedentary_time', 0) for d in activity_days)
    avg_sedentary_hours = (total_sedentary / len(activity_days) / 3600) if activity_days else 0
    high_activity = sum(d.get('high_activity_time', 0) for d in activity_days)

    report += f"  \u0412\u0441\u0435\u0433\u043e \u0448\u0430\u0433\u043e\u0432: <b>{total_steps:,}</b> ({avg_steps:.0f}/\u0434\u0435\u043d\u044c)\n"
    report += f"  \u0422\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u043e\u043a: <b>{len(workouts)}</b>\n"
    if workouts:
        workout_types = {}
        for w in workouts:
            activity_type = w.get('activity', 'unknown')
            workout_types[activity_type] = workout_types.get(activity_type, 0) + 1
        report += f"  \u0422\u0438\u043f\u044b: {', '.join(f'{k} ({v})' for k, v in workout_types.items())}\n"
    report += f"  \u0414\u043d\u0435\u0439 \u0431\u0435\u0437 \u0442\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u043a\u0438: <b>{7 - len(workouts)}</b>\n"
    report += f"  \u0421\u0440\u0435\u0434\u043d\u0435\u0435 sedentary: {avg_sedentary_hours:.1f}\u0447/\u0434\u0435\u043d\u044c\n"
    if high_activity == 0:
        report += f"  \u26a0\ufe0f High intensity: <b>0 \u043c\u0438\u043d\u0443\u0442</b>\n"
    report += "\n"

    # Stress
    if stress_days:
        report += f"<b>\U0001f9d8 \u0421\u0422\u0420\u0415\u0421\u0421</b>\n"
        stress_highs = [d.get('stress_high', 0) for d in stress_days]
        recovery_highs = [d.get('recovery_high', 0) for d in stress_days]
        avg_stress = statistics.mean(stress_highs) if stress_highs else 0
        avg_recovery = statistics.mean(recovery_highs) if recovery_highs else 0
        report += f"  \u0421\u0440\u0435\u0434\u043d\u0435\u0435 \u0432\u0440\u0435\u043c\u044f \u0432 \u0441\u0442\u0440\u0435\u0441\u0441\u0435: <b>{avg_stress:.0f} \u043c\u0438\u043d/\u0434\u0435\u043d\u044c</b>\n"
        report += f"  \u0421\u0440\u0435\u0434\u043d\u0435\u0435 \u0432\u0440\u0435\u043c\u044f \u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f: <b>{avg_recovery:.0f} \u043c\u0438\u043d/\u0434\u0435\u043d\u044c</b>\n"
        stressful_days = [d for d in stress_days if d.get('day_summary') == 'stressful']
        if stressful_days:
            dates = ", ".join(d['day'][5:] for d in stressful_days)
            report += f"  \U0001f534 \u0414\u043d\u0438 \u0441 \u0432\u044b\u0441\u043e\u043a\u0438\u043c \u0441\u0442\u0440\u0435\u0441\u0441\u043e\u043c ({len(stressful_days)}): {dates}\n"
        stress_sparkline = _sparkline(stress_highs)
        if stress_sparkline:
            report += f"  \u0422\u0440\u0435\u043d\u0434 \u0441\u0442\u0440\u0435\u0441\u0441\u0430: {stress_sparkline}\n"
        report += "\n"

    # Temperature
    temp_devs = [d.get('temperature_deviation', 0) for d in readiness_days]
    if temp_devs:
        min_temp = min(temp_devs)
        max_temp = max(temp_devs)
        report += f"<b>\U0001f321 \u0422\u0415\u041c\u041f\u0415\u0420\u0410\u0422\u0423\u0420\u0410 \u0422\u0415\u041b\u0410</b>\n"
        report += f"  \u0414\u0438\u0430\u043f\u0430\u0437\u043e\u043d: {min_temp:+.2f} \u0434\u043e {max_temp:+.2f}\u00b0C\n"
        anomalies = [d for d in readiness_days if abs(d.get('temperature_deviation', 0)) > 1.0]
        if anomalies:
            for anomaly in anomalies:
                date_str = anomaly['day'][5:]
                temp = anomaly.get('temperature_deviation', 0)
                report += f"  \u26a0\ufe0f \u0410\u043d\u043e\u043c\u0430\u043b\u0438\u044f {date_str}: {temp:+.2f}\u00b0C\n"
        report += "\n"

    # Weekday vs weekend
    ww_section = get_weekday_weekend_section()
    if ww_section:
        report += ww_section

    # Priorities
    report += f"<b>\U0001f3af \u0422\u041e\u041f-3 \u041f\u0420\u0418\u041e\u0420\u0418\u0422\u0415\u0422\u0410 \u041d\u0410 \u0421\u041b\u0415\u0414\u0423\u042e\u0429\u0423\u042e \u041d\u0415\u0414\u0415\u041b\u042e</b>\n"
    priorities = []
    if avg_sleep_hours < 7:
        priorities.append("\u0423\u0432\u0435\u043b\u0438\u0447\u0438\u0442\u044c \u0441\u043e\u043d \u0434\u043e 7.5\u0447: \u043e\u0442\u0431\u043e\u0439 \u0432 22:30")
    if avg_steps < 7000:
        priorities.append(f"\u041f\u043e\u0434\u043d\u044f\u0442\u044c \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0441\u0442\u044c: \u0446\u0435\u043b\u044c {int(avg_steps + 2000):,} \u0448\u0430\u0433\u043e\u0432/\u0434\u0435\u043d\u044c")
    if len(workouts) < 3:
        priorities.append("\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0440\u0435\u0433\u0443\u043b\u044f\u0440\u043d\u044b\u0435 \u043f\u0440\u043e\u0433\u0443\u043b\u043a\u0438: 3-4 \u0440\u0430\u0437\u0430 \u0432 \u043d\u0435\u0434\u0435\u043b\u044e")
    timing_issues = sum(1 for d in sleep_days if d['contributors'].get('timing', 100) < 70)
    if timing_issues >= 3:
        priorities.append("\u0421\u0442\u0430\u0431\u0438\u043b\u0438\u0437\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0440\u0435\u0436\u0438\u043c: \u043e\u0442\u0431\u043e\u0439 \u00b130 \u043c\u0438\u043d \u043e\u0442 22:30")
    if recovery_indexes and statistics.mean(recovery_indexes) < 50:
        priorities.append("\u0423\u043b\u0443\u0447\u0448\u0438\u0442\u044c recovery: \u0431\u0435\u0437 \u0435\u0434\u044b \u0437\u0430 3\u0447 \u0434\u043e \u0441\u043d\u0430")
    for i, priority in enumerate(priorities[:3], 1):
        report += f"  {i}. {priority}\n"
    if not priorities:
        report += f"  \u2705 \u041f\u0440\u043e\u0434\u043e\u043b\u0436\u0430\u0442\u044c \u0432 \u0442\u043e\u043c \u0436\u0435 \u0434\u0443\u0445\u0435!\n"

    return report


async def generate_claude_weekly_analysis() -> str | None:
    """Generate Claude AI analysis for weekly report."""
    if not CLAUDE_API_KEY:
        return None

    logger.info("Generating Claude weekly analysis...")
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=14)
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')

        sleep_data = await get_oura_data_range("usercollection/daily_sleep", start_str, end_str)
        readiness_data = await get_oura_data_range("usercollection/daily_readiness", start_str, end_str)
        activity_data = await get_oura_data_range("usercollection/daily_activity", start_str, end_str)

        if not all([sleep_data, readiness_data, activity_data]):
            return None

        analyzer = OuraClaudeAnalyzer(api_key=CLAUDE_API_KEY)
        analysis = analyzer.analyze_weekly_trends(
            sleep_data, readiness_data, activity_data, days=14,
        )

        return f"<b>\U0001f916 \u0415\u0416\u0415\u041d\u0415\u0414\u0415\u041b\u042c\u041d\u042b\u0419 \u0410\u041d\u0410\u041b\u0418\u0417 \u041e\u0422 CLAUDE AI</b>\n\n{analysis}"

    except Exception as e:
        logger.error("Claude weekly analysis error: %s", e)
        return None


async def run_weekly_report():
    """Generate and send weekly report + Claude analysis."""
    logger.info("Generating weekly report...")
    report = await generate_weekly_report()
    if report.startswith("\u274c"):
        logger.error(report)
        return False
    success = await send_telegram_message(report)
    if not success:
        logger.error("Failed to send weekly report")
        return False

    logger.info("Weekly report sent")

    # Claude analysis
    import asyncio
    claude_analysis = await generate_claude_weekly_analysis()
    if claude_analysis:
        await asyncio.sleep(2)
        success_claude = await send_telegram_message(claude_analysis)
        if success_claude:
            logger.info("Claude weekly analysis sent")
        else:
            logger.warning("Failed to send Claude weekly analysis")

    return success
