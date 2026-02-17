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
