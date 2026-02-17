"""
All scheduled jobs for APScheduler.
"""

import logging
from datetime import datetime, timedelta

from bot.core.oura_api import check_sleep_completed, get_oura_data_range
from bot.core.database import execute, fetchone
from bot.reports.daily import run_daily_report
from bot.reports.weekly import run_weekly_report
from bot.reports.monthly import run_monthly_report
from bot.alerts.monitor import run_alert_check
from bot.alerts.intraday import send_morning_signal
from bot.weather.alerts import check_weather_alerts
from bot.analysis.percentiles import compute_percentiles
from bot.analysis.correlator import compute_correlations
from bot.habits.streaks import update_streaks

logger = logging.getLogger(__name__)

# Track daily report state
_daily_report_sent_date = None


async def job_daily_report():
    """Smart daily report with sleep completion check."""
    global _daily_report_sent_date

    current_date = datetime.now().date()
    if _daily_report_sent_date == current_date:
        logger.info("Daily report already sent today")
        return

    is_completed, end_time, minutes = await check_sleep_completed(30)
    if not is_completed:
        logger.info("Sleep not yet completed (ended at %s, %.0f min ago)", end_time, minutes or 0)
        return

    logger.info("Sleep completed. Sending daily report...")
    success = await run_daily_report()
    if success:
        _daily_report_sent_date = current_date
        # Cache today's metrics
        await _cache_daily_metrics()


async def job_force_daily_report():
    """Force daily report at final attempt time."""
    global _daily_report_sent_date

    current_date = datetime.now().date()
    if _daily_report_sent_date == current_date:
        return

    logger.info("Forcing daily report (final attempt)...")
    success = await run_daily_report()
    if success:
        _daily_report_sent_date = current_date
        await _cache_daily_metrics()


async def job_weekly_report():
    """Weekly report on Sundays."""
    await run_weekly_report()


async def job_monthly_report():
    """Monthly report on the 1st."""
    from bot.config import MONTHLY_REPORT_DAY
    if datetime.now().day == MONTHLY_REPORT_DAY:
        await run_monthly_report()


async def job_alert_check():
    """Alert monitor check every 30 minutes."""
    await run_alert_check()


async def job_morning_signal():
    """Morning readiness signal."""
    global _daily_report_sent_date
    current_date = datetime.now().date()
    if _daily_report_sent_date == current_date:
        # Only send if daily report was already sent
        await send_morning_signal()


async def job_weather_alert():
    """Check weather conditions."""
    await check_weather_alerts()


async def job_recompute_analytics():
    """Recompute percentiles, correlations, and streaks (nightly)."""
    logger.info("Recomputing analytics...")
    try:
        compute_percentiles()
        compute_correlations()
        update_streaks()
        logger.info("Analytics recomputed")
    except Exception as e:
        logger.error("Analytics recompute error: %s", e)


async def job_backfill_metrics():
    """Backfill historical metrics into SQLite (runs once on first start)."""
    # Check if we already have data
    row = fetchone("SELECT COUNT(*) as cnt FROM daily_metrics")
    if row and row['cnt'] > 0:
        logger.info("Metrics already cached (%d days)", row['cnt'])
        return

    logger.info("Backfilling 90 days of metrics...")
    await _backfill_metrics(90)
    compute_percentiles()
    update_streaks()
    logger.info("Backfill complete")


async def _backfill_metrics(days: int):
    """Backfill N days of metrics from Oura API."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    sleep_data = await get_oura_data_range("usercollection/daily_sleep", start_str, end_str)
    readiness_data = await get_oura_data_range("usercollection/daily_readiness", start_str, end_str)
    activity_data = await get_oura_data_range("usercollection/daily_activity", start_str, end_str)
    sleep_sessions = await get_oura_data_range("usercollection/sleep", start_str, end_str)
    stress_data = await get_oura_data_range("usercollection/daily_stress", start_str, end_str)

    # Index by day
    readiness_by_day = {}
    if readiness_data and readiness_data.get('data'):
        for d in readiness_data['data']:
            readiness_by_day[d['day']] = d

    activity_by_day = {}
    if activity_data and activity_data.get('data'):
        for d in activity_data['data']:
            activity_by_day[d['day']] = d

    sessions_by_day = {}
    if sleep_sessions and sleep_sessions.get('data'):
        for s in sleep_sessions['data']:
            sessions_by_day[s['day']] = s

    stress_by_day = {}
    if stress_data and stress_data.get('data'):
        for d in stress_data['data']:
            stress_by_day[d['day']] = d

    if not sleep_data or not sleep_data.get('data'):
        logger.warning("No sleep data for backfill")
        return

    count = 0
    for sleep in sleep_data['data']:
        day = sleep['day']
        readiness = readiness_by_day.get(day, {})
        activity = activity_by_day.get(day, {})
        session = sessions_by_day.get(day, {})
        stress = stress_by_day.get(day, {})

        _insert_daily_metric(day, sleep, readiness, activity, session, stress)
        count += 1

    logger.info("Backfilled %d days of metrics", count)


async def _cache_daily_metrics():
    """Cache yesterday's metrics into SQLite."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')

    # Check if already cached
    existing = fetchone("SELECT day FROM daily_metrics WHERE day = ?", (yesterday,))
    if existing:
        return

    sleep_data = await get_oura_data_range("usercollection/daily_sleep", yesterday, today)
    readiness_data = await get_oura_data_range("usercollection/daily_readiness", yesterday, today)
    activity_data = await get_oura_data_range("usercollection/daily_activity", yesterday, today)
    sleep_sessions = await get_oura_data_range("usercollection/sleep", yesterday, today)
    stress_data = await get_oura_data_range("usercollection/daily_stress", yesterday, today)

    sleep = sleep_data['data'][-1] if sleep_data and sleep_data.get('data') else {}
    readiness = readiness_data['data'][-1] if readiness_data and readiness_data.get('data') else {}
    activity = activity_data['data'][-1] if activity_data and activity_data.get('data') else {}
    session = sleep_sessions['data'][-1] if sleep_sessions and sleep_sessions.get('data') else {}
    stress = stress_data['data'][-1] if stress_data and stress_data.get('data') else {}

    if sleep:
        _insert_daily_metric(yesterday, sleep, readiness, activity, session, stress)
        logger.info("Cached metrics for %s", yesterday)


def _insert_daily_metric(day: str, sleep: dict, readiness: dict,
                          activity: dict, session: dict, stress: dict):
    """Insert a single day's metrics into the database."""
    from datetime import date as date_type

    try:
        d = datetime.strptime(day, '%Y-%m-%d')
        day_of_week = d.weekday()  # 0=Monday
        is_weekend = 1 if day_of_week >= 5 else 0
    except ValueError:
        day_of_week = 0
        is_weekend = 0

    execute(
        """INSERT INTO daily_metrics (
            day, sleep_score, readiness_score, activity_score,
            total_sleep_duration, deep_sleep_duration, rem_sleep_duration,
            light_sleep_duration, sleep_efficiency, sleep_latency,
            average_hrv, lowest_heart_rate, average_heart_rate,
            temperature_deviation, recovery_index, sleep_balance, hrv_balance,
            steps, active_calories, total_calories,
            medium_activity_time, high_activity_time,
            stress_high, stress_recovery, stress_day_summary,
            spo2_average, bedtime_start, bedtime_end,
            is_weekend, day_of_week
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(day) DO UPDATE SET
            sleep_score=excluded.sleep_score, readiness_score=excluded.readiness_score,
            activity_score=excluded.activity_score,
            total_sleep_duration=excluded.total_sleep_duration,
            deep_sleep_duration=excluded.deep_sleep_duration,
            rem_sleep_duration=excluded.rem_sleep_duration,
            light_sleep_duration=excluded.light_sleep_duration,
            sleep_efficiency=excluded.sleep_efficiency,
            sleep_latency=excluded.sleep_latency,
            average_hrv=excluded.average_hrv,
            lowest_heart_rate=excluded.lowest_heart_rate,
            average_heart_rate=excluded.average_heart_rate,
            temperature_deviation=excluded.temperature_deviation,
            recovery_index=excluded.recovery_index,
            sleep_balance=excluded.sleep_balance,
            hrv_balance=excluded.hrv_balance,
            steps=excluded.steps, active_calories=excluded.active_calories,
            total_calories=excluded.total_calories,
            medium_activity_time=excluded.medium_activity_time,
            high_activity_time=excluded.high_activity_time,
            stress_high=excluded.stress_high, stress_recovery=excluded.stress_recovery,
            stress_day_summary=excluded.stress_day_summary,
            spo2_average=excluded.spo2_average,
            bedtime_start=excluded.bedtime_start, bedtime_end=excluded.bedtime_end,
            is_weekend=excluded.is_weekend, day_of_week=excluded.day_of_week""",
        (
            day,
            sleep.get('score'),
            readiness.get('score'),
            activity.get('score'),
            session.get('total_sleep_duration'),
            session.get('deep_sleep_duration'),
            session.get('rem_sleep_duration'),
            session.get('light_sleep_duration'),
            session.get('efficiency'),
            session.get('latency'),
            session.get('average_hrv'),
            session.get('lowest_heart_rate'),
            session.get('average_heart_rate'),
            readiness.get('temperature_deviation'),
            readiness.get('contributors', {}).get('recovery_index'),
            readiness.get('contributors', {}).get('sleep_balance'),
            readiness.get('contributors', {}).get('hrv_balance'),
            activity.get('steps'),
            activity.get('active_calories'),
            activity.get('calories'),
            activity.get('medium_activity_time'),
            activity.get('high_activity_time'),
            stress.get('stress_high'),
            stress.get('recovery_high'),
            stress.get('day_summary'),
            None,  # spo2 - separate API call, not always available
            session.get('bedtime_start'),
            session.get('bedtime_end'),
            is_weekend,
            day_of_week,
        ),
    )
