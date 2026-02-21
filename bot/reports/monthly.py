"""
Monthly report generation.
Refactored from oura_telegram_weekly.py (monthly part).
"""

import logging
import statistics
from datetime import datetime, timedelta

from bot.core.oura_api import get_oura_data_range
from bot.core.telegram import send_telegram_message
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


async def generate_monthly_report() -> str:
    """Generate monthly report for the last 30 days."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    sleep_data = await get_oura_data_range("usercollection/daily_sleep", start_str, end_str)
    readiness_data = await get_oura_data_range("usercollection/daily_readiness", start_str, end_str)
    activity_data = await get_oura_data_range("usercollection/daily_activity", start_str, end_str)
    workouts_data = await get_oura_data_range("usercollection/workout", start_str, end_str)
    stress_data = await get_oura_data_range("usercollection/daily_stress", start_str, end_str)

    if not all([sleep_data, readiness_data, activity_data]):
        return "\u274c \u041e\u0448\u0438\u0431\u043a\u0430 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u044f \u0434\u0430\u043d\u043d\u044b\u0445 \u0438\u0437 Oura API"

    sleep_days = sleep_data['data']
    readiness_days = readiness_data['data']
    activity_days = activity_data['data']
    workouts = workouts_data['data'] if workouts_data else []
    stress_days = stress_data['data'] if stress_data and stress_data.get('data') else []

    month_name = end_date.strftime('%B %Y')
    report = f"<b>\U0001f4c8 OURA \u041c\u0415\u0421\u042f\u0427\u041d\u042b\u0419 \u041e\u0422\u0427\u0401\u0422</b>\n"
    report += f"{month_name}\n\n"

    # Averages
    avg_sleep = statistics.mean([d['score'] for d in sleep_days]) if sleep_days else 0
    avg_readiness = statistics.mean([d['score'] for d in readiness_days]) if readiness_days else 0
    avg_activity = statistics.mean([d['score'] for d in activity_days]) if activity_days else 0

    report += f"<b>\u0421\u0420\u0415\u0414\u041d\u0418\u0415 \u041e\u0426\u0415\u041d\u041a\u0418</b>\n"
    report += f"  \u0421\u043e\u043d:        <b>{avg_sleep:.1f}</b>\n"
    report += f"  \u0413\u043e\u0442\u043e\u0432\u043d\u043e\u0441\u0442\u044c: <b>{avg_readiness:.1f}</b>\n"
    report += f"  \u0410\u043a\u0442\u0438\u0432\u043d\u043e\u0441\u0442\u044c: <b>{avg_activity:.1f}</b>\n\n"

    # Weekly sparklines
    sleep_scores = [d['score'] for d in sleep_days]
    readiness_scores = [d['score'] for d in readiness_days]
    activity_scores = [d['score'] for d in activity_days]

    sleep_weekly = [statistics.mean(sleep_scores[i:i + 7]) for i in range(0, len(sleep_scores), 7) if len(sleep_scores[i:i + 7]) == 7]
    readiness_weekly = [statistics.mean(readiness_scores[i:i + 7]) for i in range(0, len(readiness_scores), 7) if len(readiness_scores[i:i + 7]) == 7]
    activity_weekly = [statistics.mean(activity_scores[i:i + 7]) for i in range(0, len(activity_scores), 7) if len(activity_scores[i:i + 7]) == 7]

    report += f"<b>\u0422\u0420\u0415\u041d\u0414\u042b (\u043f\u043e \u043d\u0435\u0434\u0435\u043b\u044f\u043c)</b>\n"
    report += f"  Sleep:     {_sparkline(sleep_weekly)}\n"
    report += f"  Readiness: {_sparkline(readiness_weekly)}\n"
    report += f"  Activity:  {_sparkline(activity_weekly)}\n\n"

    # Activity
    total_steps = sum(d.get('steps', 0) for d in activity_days)
    avg_steps = total_steps / len(activity_days) if activity_days else 0
    days_over_8k = sum(1 for d in activity_days if d.get('steps', 0) >= 8000)
    pct_active = (days_over_8k / len(activity_days) * 100) if activity_days else 0

    report += f"<b>\U0001f3c3 \u0410\u041a\u0422\u0418\u0412\u041d\u041e\u0421\u0422\u042c</b>\n"
    report += f"  \u0421\u0440\u0435\u0434\u043d\u0435\u0435 \u0448\u0430\u0433\u043e\u0432/\u0434\u0435\u043d\u044c: <b>{avg_steps:.0f}</b>\n"
    report += f"  \u0412\u0441\u0435\u0433\u043e \u0442\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u043e\u043a: <b>{len(workouts)}</b>\n"
    if workouts:
        workout_types = {}
        for w in workouts:
            activity_type = w.get('activity', 'unknown')
            workout_types[activity_type] = workout_types.get(activity_type, 0) + 1
        report += f"  \u0422\u0438\u043f\u044b: {', '.join(f'{k} ({v})' for k, v in workout_types.items())}\n"
    report += f"  % \u0434\u043d\u0435\u0439 \u0441 \u0446\u0435\u043b\u0435\u0432\u043e\u0439 \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0441\u0442\u044c\u044e (\u22658000 \u0448\u0430\u0433\u043e\u0432): <b>{pct_active:.0f}%</b>\n\n"

    # Stress
    if stress_days:
        report += f"<b>\U0001f9d8 \u0421\u0422\u0420\u0415\u0421\u0421</b>\n"
        stress_highs = [d.get('stress_high', 0) for d in stress_days]
        recovery_highs = [d.get('recovery_high', 0) for d in stress_days]
        avg_stress = statistics.mean(stress_highs) if stress_highs else 0
        avg_recovery = statistics.mean(recovery_highs) if recovery_highs else 0
        report += f"  \u0421\u0440\u0435\u0434\u043d\u0435\u0435 \u0432\u0440\u0435\u043c\u044f \u0432 \u0441\u0442\u0440\u0435\u0441\u0441\u0435: <b>{avg_stress:.0f} \u043c\u0438\u043d/\u0434\u0435\u043d\u044c</b>\n"
        report += f"  \u0421\u0440\u0435\u0434\u043d\u0435\u0435 \u0432\u0440\u0435\u043c\u044f \u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f: <b>{avg_recovery:.0f} \u043c\u0438\u043d/\u0434\u0435\u043d\u044c</b>\n"

        stressful_count = sum(1 for d in stress_days if d.get('day_summary') == 'stressful')
        normal_count = sum(1 for d in stress_days if d.get('day_summary') == 'normal')
        restored_count = sum(1 for d in stress_days if d.get('day_summary') == 'restored')
        report += f"  \u0414\u043d\u0438: \U0001f7e2 {restored_count} \u0432\u043e\u0441\u0441\u0442. | \U0001f7e1 {normal_count} \u043d\u043e\u0440\u043c. | \U0001f534 {stressful_count} \u0441\u0442\u0440\u0435\u0441\u0441.\n"

        stress_weekly = [statistics.mean(stress_highs[i:i + 7]) for i in range(0, len(stress_highs), 7) if len(stress_highs[i:i + 7]) == 7]
        if stress_weekly:
            report += f"  \u0422\u0440\u0435\u043d\u0434 (\u043f\u043e \u043d\u0435\u0434\u0435\u043b\u044f\u043c): {_sparkline(stress_weekly)}\n"
        report += "\n"

    # Recommendations
    report += f"<b>\U0001f4a1 \u0420\u0415\u041a\u041e\u041c\u0415\u041d\u0414\u0410\u0426\u0418\u0418 \u041d\u0410 \u0421\u041b\u0415\u0414\u0423\u042e\u0429\u0418\u0419 \u041c\u0415\u0421\u042f\u0426</b>\n"
    if avg_sleep < 75:
        report += f"  \u2022 \u041f\u0440\u0438\u043e\u0440\u0438\u0442\u0435\u0442: \u0443\u043b\u0443\u0447\u0448\u0438\u0442\u044c \u0441\u043e\u043d (\u0442\u0435\u043a\u0443\u0449\u0438\u0439 {avg_sleep:.0f} \u2192 \u0446\u0435\u043b\u044c 80+)\n"
    if avg_activity < 70:
        report += f"  \u2022 \u0423\u0432\u0435\u043b\u0438\u0447\u0438\u0442\u044c \u0435\u0436\u0435\u0434\u043d\u0435\u0432\u043d\u0443\u044e \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0441\u0442\u044c \u0434\u043e 8000+ \u0448\u0430\u0433\u043e\u0432\n"
    if len(workouts) < 12:
        report += f"  \u2022 \u0421\u0442\u0430\u0431\u0438\u043b\u0438\u0437\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0447\u0430\u0441\u0442\u043e\u0442\u0443 \u0442\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u043e\u043a: 3-4/\u043d\u0435\u0434\u0435\u043b\u044e\n"

    return report


async def generate_claude_monthly_analysis() -> str | None:
    """Generate Claude AI analysis for monthly report."""
    if not CLAUDE_API_KEY:
        return None

    logger.info("Generating Claude monthly analysis...")
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=45)
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')

        sleep_data = await get_oura_data_range("usercollection/daily_sleep", start_str, end_str)
        readiness_data = await get_oura_data_range("usercollection/daily_readiness", start_str, end_str)
        activity_data = await get_oura_data_range("usercollection/daily_activity", start_str, end_str)

        if not all([sleep_data, readiness_data, activity_data]):
            return None

        analyzer = OuraClaudeAnalyzer(api_key=CLAUDE_API_KEY)
        analysis = analyzer.analyze_weekly_trends(
            sleep_data, readiness_data, activity_data, days=45,
        )

        return f"<b>\U0001f916 \u041c\u0415\u0421\u042f\u0427\u041d\u042b\u0419 \u0410\u041d\u0410\u041b\u0418\u0417 \u041e\u0422 CLAUDE AI</b>\n\n{analysis}"

    except Exception as e:
        logger.error("Claude monthly analysis error: %s", e)
        return None


async def run_monthly_report():
    """Generate and send monthly report + Claude analysis."""
    logger.info("Generating monthly report...")
    report = await generate_monthly_report()
    if report.startswith("\u274c"):
        logger.error(report)
        return False
    success = await send_telegram_message(report)
    if not success:
        logger.error("Failed to send monthly report")
        return False

    logger.info("Monthly report sent")

    # Claude analysis
    import asyncio
    claude_analysis = await generate_claude_monthly_analysis()
    if claude_analysis:
        await asyncio.sleep(2)
        success_claude = await send_telegram_message(claude_analysis)
        if success_claude:
            logger.info("Claude monthly analysis sent")
        else:
            logger.warning("Failed to send Claude monthly analysis")

    return success
