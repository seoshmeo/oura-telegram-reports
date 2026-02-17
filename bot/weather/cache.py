"""
Weather data cache in SQLite.
"""

import json
import logging

from bot.core.database import fetchone, execute

logger = logging.getLogger(__name__)


def get_cached_weather(day: str) -> dict | None:
    """Get cached weather for a specific day."""
    row = fetchone("SELECT * FROM weather WHERE day = ?", (day,))
    if not row:
        return None

    result = dict(row)
    try:
        result['critical_reasons'] = json.loads(result.get('critical_reasons', '[]'))
    except (json.JSONDecodeError, TypeError):
        result['critical_reasons'] = []

    return result


def cache_weather(day: str, data: dict):
    """Cache weather data for a day."""
    critical_reasons = json.dumps(data.get('critical_reasons', []), ensure_ascii=False)

    execute(
        """INSERT INTO weather (day, temp_max, temp_min, temp_mean, humidity_mean,
           wind_max, precipitation, uv_index_max, pm10, pm2_5, aqi, is_critical, critical_reasons)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(day) DO UPDATE SET
           temp_max=excluded.temp_max, temp_min=excluded.temp_min, temp_mean=excluded.temp_mean,
           humidity_mean=excluded.humidity_mean, wind_max=excluded.wind_max,
           precipitation=excluded.precipitation, uv_index_max=excluded.uv_index_max,
           pm10=excluded.pm10, pm2_5=excluded.pm2_5, aqi=excluded.aqi,
           is_critical=excluded.is_critical, critical_reasons=excluded.critical_reasons""",
        (day, data.get('temp_max'), data.get('temp_min'), data.get('temp_mean'),
         data.get('humidity_mean'), data.get('wind_max'), data.get('precipitation'),
         data.get('uv_index_max'), data.get('pm10'), data.get('pm2_5'),
         data.get('aqi'), int(data.get('is_critical', False)), critical_reasons),
    )
