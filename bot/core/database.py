"""
SQLite database connection and utilities.
"""

import logging
import os
import sqlite3
from contextlib import contextmanager

from bot.config import DB_PATH

logger = logging.getLogger(__name__)

_connection: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    """Get or create the SQLite connection (singleton)."""
    global _connection
    if _connection is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _connection = sqlite3.connect(DB_PATH, check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA journal_mode=WAL")
        _connection.execute("PRAGMA foreign_keys=ON")
        logger.info("SQLite connected: %s", DB_PATH)
    return _connection


@contextmanager
def get_cursor():
    """Context manager for database cursor with auto-commit."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    """Execute SQL and return cursor."""
    conn = get_connection()
    cursor = conn.execute(sql, params)
    conn.commit()
    return cursor


def executemany(sql: str, params_list: list[tuple]) -> None:
    """Execute SQL for multiple parameter sets."""
    conn = get_connection()
    conn.executemany(sql, params_list)
    conn.commit()


def fetchone(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    """Execute SQL and fetch one row."""
    conn = get_connection()
    return conn.execute(sql, params).fetchone()


def fetchall(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    """Execute SQL and fetch all rows."""
    conn = get_connection()
    return conn.execute(sql, params).fetchall()


def close():
    """Close the database connection."""
    global _connection
    if _connection:
        _connection.close()
        _connection = None
        logger.info("SQLite connection closed")
