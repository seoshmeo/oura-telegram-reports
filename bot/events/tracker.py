"""
Event CRUD operations in SQLite.
"""

import json
import logging
from datetime import datetime

from bot.core.database import execute, fetchall, fetchone

logger = logging.getLogger(__name__)


def add_event(event_type: str, raw_text: str, details: dict | None = None,
              metrics_to_correlate: list | None = None, source: str = 'text',
              timestamp: datetime | None = None) -> int:
    """Add a new event. Returns event ID."""
    ts = timestamp or datetime.now()
    details_json = json.dumps(details or {}, ensure_ascii=False)
    metrics_json = json.dumps(metrics_to_correlate or [], ensure_ascii=False)

    cursor = execute(
        """INSERT INTO events (timestamp, event_type, raw_text, details, metrics_to_correlate, source)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (ts.isoformat(), event_type, raw_text, details_json, metrics_json, source),
    )
    event_id = cursor.lastrowid
    logger.info("Event added: id=%d type=%s raw='%s'", event_id, event_type, raw_text)
    return event_id


def get_today_events() -> list[dict]:
    """Get all events for today."""
    today = datetime.now().strftime('%Y-%m-%d')
    rows = fetchall(
        "SELECT * FROM events WHERE date(timestamp) = ? ORDER BY timestamp",
        (today,),
    )
    return [dict(row) for row in rows]


def get_events_range(start_date: str, end_date: str) -> list[dict]:
    """Get events in a date range."""
    rows = fetchall(
        "SELECT * FROM events WHERE date(timestamp) >= ? AND date(timestamp) <= ? ORDER BY timestamp",
        (start_date, end_date),
    )
    return [dict(row) for row in rows]


def delete_event(event_id: int) -> bool:
    """Delete an event by ID. Returns True if deleted."""
    row = fetchone("SELECT id FROM events WHERE id = ?", (event_id,))
    if not row:
        return False
    execute("DELETE FROM events WHERE id = ?", (event_id,))
    logger.info("Event deleted: id=%d", event_id)
    return True


def get_event_counts(days: int = 30) -> dict[str, int]:
    """Get event type counts for the last N days."""
    rows = fetchall(
        """SELECT event_type, COUNT(*) as cnt FROM events
           WHERE timestamp >= date('now', ?)
           GROUP BY event_type ORDER BY cnt DESC""",
        (f'-{days} days',),
    )
    return {row['event_type']: row['cnt'] for row in rows}


def get_days_with_event(event_type: str) -> set[str]:
    """Get set of days (YYYY-MM-DD) that have a specific event."""
    rows = fetchall(
        "SELECT DISTINCT date(timestamp) as day FROM events WHERE event_type = ?",
        (event_type,),
    )
    return {row['day'] for row in rows}


def add_measurement(measurement_type: str, value1: float, value2: float | None = None,
                    unit: str = '', note: str | None = None, source: str = 'text',
                    timestamp: datetime | None = None) -> int:
    """Add a health measurement. Returns measurement ID."""
    ts = timestamp or datetime.now()
    cursor = execute(
        """INSERT INTO health_measurements (timestamp, measurement_type, value1, value2, unit, note, source)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (ts.isoformat(), measurement_type, value1, value2, unit, note, source),
    )
    mid = cursor.lastrowid
    logger.info("Measurement added: id=%d type=%s val=%s/%s", mid, measurement_type, value1, value2)
    return mid


def get_recent_measurements(measurement_type: str, limit: int = 10) -> list[dict]:
    """Get recent measurements of a given type."""
    rows = fetchall(
        """SELECT * FROM health_measurements
           WHERE measurement_type = ?
           ORDER BY timestamp DESC LIMIT ?""",
        (measurement_type, limit),
    )
    return [dict(row) for row in rows]


def get_last_measurement(measurement_type: str) -> dict | None:
    """Get the most recent measurement of a given type."""
    row = fetchone(
        """SELECT * FROM health_measurements
           WHERE measurement_type = ?
           ORDER BY timestamp DESC LIMIT 1""",
        (measurement_type,),
    )
    return dict(row) if row else None


def get_measurement_stats(measurement_type: str, days: int = 30) -> dict | None:
    """Get stats (avg, min, max) for measurements over last N days."""
    row = fetchone(
        """SELECT AVG(value1) as avg1, MIN(value1) as min1, MAX(value1) as max1,
                  AVG(value2) as avg2, MIN(value2) as min2, MAX(value2) as max2,
                  COUNT(*) as cnt
           FROM health_measurements
           WHERE measurement_type = ? AND timestamp >= date('now', ?)""",
        (measurement_type, f'-{days} days'),
    )
    if not row or row['cnt'] == 0:
        return None
    return dict(row)
