"""
Open-Meteo API client for weather data (free, no API key needed).
Location: Larnaca, Cyprus (34.92°N, 33.62°E)
"""

import logging
from datetime import datetime

import aiohttp

from bot.config import WEATHER_LAT, WEATHER_LON
from bot.weather.cache import get_cached_weather, cache_weather

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# Critical thresholds for Cyprus
THRESHOLDS = {
    'temp_max': 40,      # °C - extreme heat
    'pm10': 50,          # µg/m³
    'pm2_5': 25,         # µg/m³
    'aqi': 100,          # AQI index
    'wind_max': 60,      # km/h
    'uv_max': 8,         # UV index
}


async def fetch_weather() -> dict | None:
    """Fetch today's weather from Open-Meteo."""
    today = datetime.now().strftime('%Y-%m-%d')

    # Check cache first
    cached = get_cached_weather(today)
    if cached:
        return cached

    try:
        weather_data = await _fetch_weather_api(today)
        air_data = await _fetch_air_quality_api(today)

        if not weather_data:
            return None

        result = _parse_weather(weather_data, air_data, today)
        if result:
            cache_weather(today, result)

        return result

    except Exception as e:
        logger.error("Weather fetch failed: %s", e)
        return None


async def _fetch_weather_api(date: str) -> dict | None:
    """Fetch weather data from Open-Meteo."""
    params = {
        'latitude': WEATHER_LAT,
        'longitude': WEATHER_LON,
        'daily': 'temperature_2m_max,temperature_2m_min,temperature_2m_mean,'
                 'relative_humidity_2m_mean,wind_speed_10m_max,'
                 'precipitation_sum,uv_index_max',
        'timezone': 'auto',
        'start_date': date,
        'end_date': date,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(OPEN_METEO_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.error("Open-Meteo weather error: %d", resp.status)
                return None
    except Exception as e:
        logger.error("Open-Meteo weather request failed: %s", e)
        return None


async def _fetch_air_quality_api(date: str) -> dict | None:
    """Fetch air quality data from Open-Meteo."""
    params = {
        'latitude': WEATHER_LAT,
        'longitude': WEATHER_LON,
        'daily': 'pm10_mean,pm2_5_mean,european_aqi',
        'timezone': 'auto',
        'start_date': date,
        'end_date': date,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(AIR_QUALITY_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.debug("Air quality API error: %d", resp.status)
                return None
    except Exception as e:
        logger.debug("Air quality request failed: %s", e)
        return None


def _parse_weather(weather: dict, air: dict | None, date: str) -> dict | None:
    """Parse weather and air quality responses into unified format."""
    try:
        daily = weather.get('daily', {})
        if not daily.get('temperature_2m_max'):
            return None

        result = {
            'day': date,
            'temp_max': daily['temperature_2m_max'][0],
            'temp_min': daily['temperature_2m_min'][0],
            'temp_mean': daily.get('temperature_2m_mean', [None])[0],
            'humidity_mean': daily.get('relative_humidity_2m_mean', [None])[0],
            'wind_max': daily.get('wind_speed_10m_max', [None])[0],
            'precipitation': daily.get('precipitation_sum', [0])[0],
            'uv_index_max': daily.get('uv_index_max', [None])[0],
            'pm10': None,
            'pm2_5': None,
            'aqi': None,
            'is_critical': False,
            'critical_reasons': [],
        }

        # Air quality
        if air and air.get('daily'):
            air_daily = air['daily']
            result['pm10'] = air_daily.get('pm10_mean', [None])[0]
            result['pm2_5'] = air_daily.get('pm2_5_mean', [None])[0]
            aqi_vals = air_daily.get('european_aqi', [None])
            result['aqi'] = aqi_vals[0] if aqi_vals else None

        # Check critical thresholds
        reasons = []
        if result['temp_max'] and result['temp_max'] >= THRESHOLDS['temp_max']:
            reasons.append(f"\U0001f525 \u0416\u0430\u0440\u0430 {result['temp_max']:.0f}\u00b0C")
        if result['pm10'] and result['pm10'] >= THRESHOLDS['pm10']:
            reasons.append(f"\U0001f32b\ufe0f PM10: {result['pm10']:.0f}")
        if result['pm2_5'] and result['pm2_5'] >= THRESHOLDS['pm2_5']:
            reasons.append(f"\U0001f32b\ufe0f PM2.5: {result['pm2_5']:.0f}")
        if result['aqi'] and result['aqi'] >= THRESHOLDS['aqi']:
            reasons.append(f"\u26a0\ufe0f AQI: {result['aqi']}")
        if result['wind_max'] and result['wind_max'] >= THRESHOLDS['wind_max']:
            reasons.append(f"\U0001f32a\ufe0f \u0412\u0435\u0442\u0435\u0440 {result['wind_max']:.0f} \u043a\u043c/\u0447")
        if result['uv_index_max'] and result['uv_index_max'] >= THRESHOLDS['uv_max']:
            reasons.append(f"\u2600\ufe0f UV: {result['uv_index_max']:.0f}")

        result['is_critical'] = len(reasons) > 0
        result['critical_reasons'] = reasons

        return result

    except (KeyError, IndexError, TypeError) as e:
        logger.error("Weather parse error: %s", e)
        return None


async def get_weather_summary() -> str | None:
    """Get formatted weather section for daily report."""
    data = await fetch_weather()
    if not data:
        return None

    section = "<b>\U0001f326\ufe0f \u041f\u041e\u0413\u041e\u0414\u0410 (\u041b\u0430\u0440\u043d\u0430\u043a\u0430)</b>\n"
    section += f"  \U0001f321\ufe0f {data['temp_min']:.0f}\u00b0..{data['temp_max']:.0f}\u00b0C"
    if data.get('humidity_mean'):
        section += f" | \U0001f4a7 {data['humidity_mean']:.0f}%"
    if data.get('wind_max'):
        section += f" | \U0001f4a8 {data['wind_max']:.0f}\u043a\u043c/\u0447"
    section += "\n"

    if data.get('uv_index_max'):
        section += f"  UV: {data['uv_index_max']:.0f}"
        if data['uv_index_max'] >= 8:
            section += " \u26a0\ufe0f"
        section += "\n"

    if data.get('aqi'):
        section += f"  AQI: {data['aqi']}"
        if data.get('pm10'):
            section += f" | PM10: {data['pm10']:.0f}"
        if data.get('pm2_5'):
            section += f" | PM2.5: {data['pm2_5']:.0f}"
        section += "\n"

    if data['is_critical']:
        section += f"  \u26a0\ufe0f {' | '.join(data['critical_reasons'])}\n"

    section += "\n"
    return section
