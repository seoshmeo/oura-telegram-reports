"""
Percentile calculations and top/worst day tracking.
"""

import logging
import statistics as stats

from bot.core.database import fetchall, fetchone, execute

logger = logging.getLogger(__name__)

TRACKED_METRICS = [
    'sleep_score', 'readiness_score', 'activity_score',
    'total_sleep_duration', 'deep_sleep_duration', 'rem_sleep_duration',
    'average_hrv', 'lowest_heart_rate', 'steps',
    'sleep_efficiency', 'sleep_latency', 'temperature_deviation',
    'stress_high',
]


def compute_percentiles():
    """Recompute percentiles for all tracked metrics from daily_metrics."""
    rows = fetchall("SELECT * FROM daily_metrics ORDER BY day")
    if len(rows) < 7:
        logger.info("Not enough data for percentiles (%d days)", len(rows))
        return

    for metric in TRACKED_METRICS:
        values = [row[metric] for row in rows if row[metric] is not None]
        if len(values) < 7:
            continue

        sorted_vals = sorted(values)
        n = len(sorted_vals)

        def percentile(p):
            k = (n - 1) * p / 100
            f = int(k)
            c = f + 1
            if c >= n:
                return sorted_vals[-1]
            return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])

        p10 = percentile(10)
        p25 = percentile(25)
        p50 = percentile(50)
        p75 = percentile(75)
        p90 = percentile(90)

        execute(
            """INSERT INTO percentile_cache (metric_name, p10, p25, p50, p75, p90, count, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(metric_name) DO UPDATE SET
               p10=excluded.p10, p25=excluded.p25, p50=excluded.p50,
               p75=excluded.p75, p90=excluded.p90, count=excluded.count,
               updated_at=CURRENT_TIMESTAMP""",
            (metric, p10, p25, p50, p75, p90, n),
        )

    logger.info("Percentiles recomputed for %d metrics", len(TRACKED_METRICS))


def get_percentile_label(metric_name: str, value: float) -> str | None:
    """Get percentile label for a value (e.g., 'top 10%', 'bottom 10%')."""
    row = fetchone("SELECT * FROM percentile_cache WHERE metric_name = ?", (metric_name,))
    if not row:
        return None

    # For metrics where lower is better (heart rate, latency, stress)
    lower_is_better = metric_name in ('lowest_heart_rate', 'sleep_latency', 'stress_high', 'temperature_deviation')

    if lower_is_better:
        if value <= row['p10']:
            return "\U0001f3c6 top 10%"
        elif value <= row['p25']:
            return "\U0001f7e2 top 25%"
        elif value >= row['p90']:
            return "\U0001f534 bottom 10%"
        elif value >= row['p75']:
            return "\U0001f7e1 bottom 25%"
    else:
        if value >= row['p90']:
            return "\U0001f3c6 top 10%"
        elif value >= row['p75']:
            return "\U0001f7e2 top 25%"
        elif value <= row['p10']:
            return "\U0001f534 bottom 10%"
        elif value <= row['p25']:
            return "\U0001f7e1 bottom 25%"

    return None


def get_percentile_context(sleep_score: int, readiness_score: int) -> str | None:
    """Get percentile context string for daily report summary."""
    parts = []

    sleep_label = get_percentile_label('sleep_score', sleep_score)
    if sleep_label:
        parts.append(f"\u0421\u043e\u043d: {sleep_label}")

    readiness_label = get_percentile_label('readiness_score', readiness_score)
    if readiness_label:
        parts.append(f"\u0413\u043e\u0442\u043e\u0432\u043d\u043e\u0441\u0442\u044c: {readiness_label}")

    if parts:
        return "  " + " | ".join(parts)
    return None


def get_top_worst_days(metric_name: str, n: int = 3) -> tuple[list, list]:
    """Get top N and worst N days for a metric."""
    lower_is_better = metric_name in ('lowest_heart_rate', 'sleep_latency', 'stress_high')

    order = "ASC" if lower_is_better else "DESC"
    top = fetchall(
        f"SELECT day, {metric_name} FROM daily_metrics WHERE {metric_name} IS NOT NULL ORDER BY {metric_name} {order} LIMIT ?",
        (n,),
    )

    reverse_order = "DESC" if lower_is_better else "ASC"
    worst = fetchall(
        f"SELECT day, {metric_name} FROM daily_metrics WHERE {metric_name} IS NOT NULL ORDER BY {metric_name} {reverse_order} LIMIT ?",
        (n,),
    )

    return list(top), list(worst)
