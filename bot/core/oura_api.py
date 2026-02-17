"""
Unified Oura API v2 client.
"""

import logging
from datetime import datetime, timedelta, timezone

import aiohttp

from bot.config import OURA_TOKEN, OURA_API_BASE_URL

logger = logging.getLogger(__name__)


async def get_oura_data(endpoint: str, params: dict | None = None) -> dict | None:
    """Fetch data from Oura API v2."""
    if not OURA_TOKEN:
        logger.error("OURA_TOKEN not set")
        return None

    headers = {'Authorization': f'Bearer {OURA_TOKEN}'}
    url = f"{OURA_API_BASE_URL}/{endpoint}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    text = await resp.text()
                    logger.error("Oura API error %d for %s: %s", resp.status, endpoint, text)
                    return None
    except Exception as e:
        logger.error("Oura API request failed for %s: %s", endpoint, e)
        return None


async def get_oura_data_range(endpoint: str, start_date: str, end_date: str) -> dict | None:
    """Fetch data from Oura API for a date range."""
    return await get_oura_data(endpoint, {'start_date': start_date, 'end_date': end_date})


async def check_sleep_completed(minutes_threshold: int = 30) -> tuple[bool, str | None, float | None]:
    """
    Check if sleep session has ended.

    Returns:
        (is_completed, bedtime_end_time_str, minutes_since_wakeup)
    """
    try:
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        today = datetime.now().strftime('%Y-%m-%d')

        sleep_sessions = await get_oura_data_range("usercollection/sleep", yesterday, today)

        if not sleep_sessions or not sleep_sessions.get('data'):
            return False, None, None

        last_session = sleep_sessions['data'][-1]
        bedtime_end_str = last_session['bedtime_end'].replace('Z', '+00:00')
        bedtime_end = datetime.fromisoformat(bedtime_end_str)

        now_utc = datetime.now(timezone.utc)
        minutes_since_wakeup = (now_utc - bedtime_end).total_seconds() / 60

        is_completed = minutes_since_wakeup > minutes_threshold

        bedtime_end_local = bedtime_end.astimezone()
        bedtime_end_time = bedtime_end_local.strftime('%H:%M')

        return is_completed, bedtime_end_time, minutes_since_wakeup

    except Exception as e:
        logger.error("Error checking sleep completion: %s", e)
        return True, None, None


async def fetch_days(endpoint: str, days: int) -> dict | None:
    """Fetch data for the last N days."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    return await get_oura_data_range(
        endpoint,
        start_date.strftime('%Y-%m-%d'),
        end_date.strftime('%Y-%m-%d'),
    )


async def fetch_all_metrics(start_date: str, end_date: str) -> dict:
    """Fetch all standard metrics for a date range."""
    endpoints = {
        'sleep': 'usercollection/daily_sleep',
        'readiness': 'usercollection/daily_readiness',
        'activity': 'usercollection/daily_activity',
        'sleep_sessions': 'usercollection/sleep',
        'stress': 'usercollection/daily_stress',
        'workouts': 'usercollection/workout',
        'spo2': 'usercollection/daily_spo2',
    }

    results = {}
    async with aiohttp.ClientSession() as session:
        for key, endpoint in endpoints.items():
            data = await get_oura_data_range(endpoint, start_date, end_date)
            results[key] = data

    return results
