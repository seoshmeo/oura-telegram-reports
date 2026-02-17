"""
Database schema migrations with versioning.
"""

import logging

from bot.core.database import get_connection

logger = logging.getLogger(__name__)

MIGRATIONS = [
    # Migration 1: Core tables
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        event_type TEXT NOT NULL,
        raw_text TEXT,
        details TEXT DEFAULT '{}',
        metrics_to_correlate TEXT DEFAULT '[]',
        source TEXT DEFAULT 'text',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS daily_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day TEXT NOT NULL UNIQUE,
        sleep_score INTEGER,
        readiness_score INTEGER,
        activity_score INTEGER,
        total_sleep_duration REAL,
        deep_sleep_duration REAL,
        rem_sleep_duration REAL,
        light_sleep_duration REAL,
        sleep_efficiency INTEGER,
        sleep_latency INTEGER,
        average_hrv REAL,
        lowest_heart_rate INTEGER,
        average_heart_rate REAL,
        temperature_deviation REAL,
        recovery_index INTEGER,
        sleep_balance INTEGER,
        hrv_balance INTEGER,
        steps INTEGER,
        active_calories INTEGER,
        total_calories INTEGER,
        medium_activity_time INTEGER,
        high_activity_time INTEGER,
        stress_high INTEGER,
        stress_recovery INTEGER,
        stress_day_summary TEXT,
        spo2_average REAL,
        bedtime_start TEXT,
        bedtime_end TEXT,
        is_weekend INTEGER DEFAULT 0,
        day_of_week INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_daily_metrics_day ON daily_metrics(day);

    CREATE TABLE IF NOT EXISTS weather (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day TEXT NOT NULL UNIQUE,
        temp_max REAL,
        temp_min REAL,
        temp_mean REAL,
        humidity_mean REAL,
        wind_max REAL,
        precipitation REAL,
        uv_index_max REAL,
        pm10 REAL,
        pm2_5 REAL,
        aqi INTEGER,
        is_critical INTEGER DEFAULT 0,
        critical_reasons TEXT DEFAULT '[]',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_weather_day ON weather(day);

    CREATE TABLE IF NOT EXISTS correlations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        metric_name TEXT NOT NULL,
        avg_with_event REAL,
        avg_without_event REAL,
        delta REAL,
        delta_pct REAL,
        count_with INTEGER,
        count_without INTEGER,
        confidence REAL,
        time_bucket TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(event_type, metric_name, time_bucket)
    );

    CREATE TABLE IF NOT EXISTS intraday_hr (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TIMESTAMP NOT NULL,
        heart_rate INTEGER NOT NULL,
        event_id INTEGER,
        FOREIGN KEY (event_id) REFERENCES events(id)
    );
    CREATE INDEX IF NOT EXISTS idx_intraday_hr_ts ON intraday_hr(timestamp);

    CREATE TABLE IF NOT EXISTS percentile_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        metric_name TEXT NOT NULL UNIQUE,
        p10 REAL,
        p25 REAL,
        p50 REAL,
        p75 REAL,
        p90 REAL,
        count INTEGER,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS habit_streaks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        habit_name TEXT NOT NULL UNIQUE,
        current_streak INTEGER DEFAULT 0,
        best_streak INTEGER DEFAULT 0,
        last_day TEXT,
        target_value REAL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,

    # Migration 2: Health measurements (blood pressure, blood sugar)
    """
    CREATE TABLE IF NOT EXISTS health_measurements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        measurement_type TEXT NOT NULL,
        value1 REAL NOT NULL,
        value2 REAL,
        unit TEXT NOT NULL,
        note TEXT,
        source TEXT DEFAULT 'text',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_health_measurements_type_ts ON health_measurements(measurement_type, timestamp);
    """,
]


def run_migrations():
    """Apply pending migrations."""
    conn = get_connection()

    # Create schema_version table if not exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # Get current version
    row = conn.execute("SELECT MAX(version) as v FROM schema_version").fetchone()
    current_version = row['v'] if row and row['v'] is not None else 0

    # Apply pending migrations
    for i, migration_sql in enumerate(MIGRATIONS, 1):
        if i > current_version:
            logger.info("Applying migration %d...", i)
            # Split by semicolons for multi-statement migrations
            for statement in migration_sql.split(';'):
                statement = statement.strip()
                if statement:
                    conn.execute(statement)

            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (i,))
            conn.commit()
            logger.info("Migration %d applied", i)

    logger.info("Database schema is up to date (version %d)", len(MIGRATIONS))
