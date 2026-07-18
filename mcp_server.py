#!/usr/bin/env python3
"""Oura MCP Server — exposes Oura health data to Hermes agent via SSE."""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, '/app')

from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import uvicorn

import bot.core.database as db
from bot.core.oura_api import get_oura_data_range

MCP_AUTH_TOKEN = os.environ.get('MCP_AUTH_TOKEN', '')
MCP_PORT = int(os.environ.get('MCP_PORT', '8765'))

mcp = FastMCP("oura-hermes")


# ── DB tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def get_daily_metrics(date: str) -> dict:
    """Get full health metrics for a specific date (YYYY-MM-DD)."""
    row = db.fetchone("SELECT * FROM daily_metrics WHERE day = ?", (date,))
    return dict(row) if row else {"error": f"No data for {date}"}


@mcp.tool()
def get_recent_metrics(days: int = 7) -> list:
    """Get daily health metrics for the last N days."""
    rows = db.fetchall(
        "SELECT * FROM daily_metrics ORDER BY day DESC LIMIT ?", (days,)
    )
    return [dict(r) for r in rows]


@mcp.tool()
def get_events(date_from: str, date_to: str, event_type: str = "") -> list:
    """
    Get tracked events for a date range (YYYY-MM-DD to YYYY-MM-DD).
    event_type examples: coffee, alcohol, workout, stress, hookah, walk, meds
    Leave empty for all event types.
    """
    if event_type:
        rows = db.fetchall(
            """SELECT * FROM events
               WHERE date(timestamp) BETWEEN ? AND ? AND event_type = ?
               ORDER BY timestamp DESC""",
            (date_from, date_to, event_type),
        )
    else:
        rows = db.fetchall(
            """SELECT * FROM events
               WHERE date(timestamp) BETWEEN ? AND ?
               ORDER BY timestamp DESC""",
            (date_from, date_to),
        )
    return [dict(r) for r in rows]


@mcp.tool()
def get_today_events() -> list:
    """Get all events logged today."""
    today = datetime.now().strftime('%Y-%m-%d')
    rows = db.fetchall(
        "SELECT * FROM events WHERE date(timestamp) = ? ORDER BY timestamp",
        (today,),
    )
    return [dict(r) for r in rows]


@mcp.tool()
def get_food_logs(date: str) -> list:
    """Get food logs (calories, protein, carbs, fat) for a specific date (YYYY-MM-DD)."""
    rows = db.fetchall(
        "SELECT * FROM food_logs WHERE date(timestamp) = ? ORDER BY timestamp",
        (date,),
    )
    return [dict(r) for r in rows]


@mcp.tool()
def get_health_measurements(measurement_type: str = "", days: int = 30) -> list:
    """
    Get health measurements for the last N days.
    measurement_type: blood_pressure, blood_sugar (empty = all types)
    """
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    if measurement_type:
        rows = db.fetchall(
            """SELECT * FROM health_measurements
               WHERE measurement_type = ? AND date(timestamp) >= ?
               ORDER BY timestamp DESC""",
            (measurement_type, cutoff),
        )
    else:
        rows = db.fetchall(
            """SELECT * FROM health_measurements
               WHERE date(timestamp) >= ?
               ORDER BY timestamp DESC""",
            (cutoff,),
        )
    return [dict(r) for r in rows]


@mcp.tool()
def get_correlations(event_type: str = "") -> list:
    """
    Get event-to-metric correlations sorted by impact.
    Filter by event_type (coffee, alcohol, workout, etc.) or leave empty for top 100.
    """
    if event_type:
        rows = db.fetchall(
            "SELECT * FROM correlations WHERE event_type = ? ORDER BY ABS(delta_pct) DESC",
            (event_type,),
        )
    else:
        rows = db.fetchall(
            "SELECT * FROM correlations ORDER BY ABS(delta_pct) DESC LIMIT 100"
        )
    return [dict(r) for r in rows]


@mcp.tool()
def get_habit_streaks() -> list:
    """Get current and best streaks for all tracked habits."""
    rows = db.fetchall("SELECT * FROM habit_streaks ORDER BY current_streak DESC")
    return [dict(r) for r in rows]


@mcp.tool()
def get_weather(date: str) -> dict:
    """Get weather data for a specific date (YYYY-MM-DD)."""
    row = db.fetchone("SELECT * FROM weather WHERE day = ?", (date,))
    return dict(row) if row else {"error": f"No weather data for {date}"}


@mcp.tool()
def search_events(keyword: str, days: int = 30) -> list:
    """Search events by keyword in raw text or details for the last N days."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    rows = db.fetchall(
        """SELECT * FROM events
           WHERE date(timestamp) >= ? AND (raw_text LIKE ? OR details LIKE ?)
           ORDER BY timestamp DESC LIMIT 50""",
        (cutoff, f"%{keyword}%", f"%{keyword}%"),
    )
    return [dict(r) for r in rows]


@mcp.tool()
def get_event_type_counts(days: int = 30) -> dict:
    """Get count of each event type logged in the last N days."""
    rows = db.fetchall(
        """SELECT event_type, COUNT(*) as cnt FROM events
           WHERE date(timestamp) >= date('now', ?)
           GROUP BY event_type ORDER BY cnt DESC""",
        (f'-{days} days',),
    )
    return {r['event_type']: r['cnt'] for r in rows}


# ── Live Oura API ───────────────────────────────────────────────────────────

@mcp.tool()
async def get_oura_live(endpoint: str, days: int = 1) -> dict:
    """
    Fetch live data directly from Oura API (bypasses local DB cache).
    endpoint: daily_sleep | daily_readiness | daily_activity | daily_stress |
              daily_spo2 | daily_resilience | workout | sleep
    """
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    result = await get_oura_data_range(
        f"usercollection/{endpoint}", start_date, end_date
    )
    return result or {"error": "No data returned from Oura API"}


# ── Auth middleware + entrypoint ────────────────────────────────────────────

class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if MCP_AUTH_TOKEN:
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {MCP_AUTH_TOKEN}":
                return Response("Unauthorized", status_code=401)
        return await call_next(request)


if __name__ == "__main__":
    app = mcp.sse_app()
    app.add_middleware(BearerAuthMiddleware)
    uvicorn.run(app, host="0.0.0.0", port=MCP_PORT, log_level="info")
