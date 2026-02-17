"""
Correlation engine: events vs metrics.
"""

import logging
import statistics

from bot.core.database import fetchall, execute

logger = logging.getLogger(__name__)


def compute_correlations():
    """Compute correlations between events and metrics."""
    events = fetchall("SELECT DISTINCT event_type FROM events")
    if not events:
        return

    all_metrics = fetchall("SELECT * FROM daily_metrics ORDER BY day")
    if len(all_metrics) < 14:
        logger.info("Not enough metric data for correlations (%d days)", len(all_metrics))
        return

    metrics_by_day = {row['day']: row for row in all_metrics}

    metric_fields = [
        'sleep_score', 'readiness_score', 'total_sleep_duration',
        'deep_sleep_duration', 'rem_sleep_duration', 'average_hrv',
        'lowest_heart_rate', 'sleep_efficiency', 'sleep_latency',
        'stress_high', 'steps',
    ]

    for event_row in events:
        event_type = event_row['event_type']

        # Get days with this event
        event_entries = fetchall(
            "SELECT DISTINCT date(timestamp) as day FROM events WHERE event_type = ?",
            (event_type,),
        )
        event_days = {row['day'] for row in event_entries}

        if len(event_days) < 3:
            continue

        for metric_name in metric_fields:
            with_event = []
            without_event = []

            for day, metrics in metrics_by_day.items():
                val = metrics[metric_name]
                if val is None:
                    continue
                # Check next day's metrics for events that affect sleep
                if day in event_days:
                    with_event.append(val)
                else:
                    without_event.append(val)

            if len(with_event) < 3 or len(without_event) < 3:
                continue

            avg_with = statistics.mean(with_event)
            avg_without = statistics.mean(without_event)
            delta = avg_with - avg_without
            delta_pct = (delta / avg_without * 100) if avg_without != 0 else 0

            # Simple confidence: based on sample sizes
            total = len(with_event) + len(without_event)
            confidence = min(len(with_event), len(without_event)) / total

            execute(
                """INSERT INTO correlations
                   (event_type, metric_name, avg_with_event, avg_without_event,
                    delta, delta_pct, count_with, count_without, confidence, time_bucket, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'all', CURRENT_TIMESTAMP)
                   ON CONFLICT(event_type, metric_name, time_bucket) DO UPDATE SET
                   avg_with_event=excluded.avg_with_event, avg_without_event=excluded.avg_without_event,
                   delta=excluded.delta, delta_pct=excluded.delta_pct,
                   count_with=excluded.count_with, count_without=excluded.count_without,
                   confidence=excluded.confidence, updated_at=CURRENT_TIMESTAMP""",
                (event_type, metric_name, avg_with, avg_without, delta, delta_pct,
                 len(with_event), len(without_event), confidence),
            )

        # Time-bucket analysis (morning vs evening events)
        _compute_time_bucket_correlations(event_type, metrics_by_day, metric_fields)

    logger.info("Correlations recomputed")


def _compute_time_bucket_correlations(event_type: str, metrics_by_day: dict, metric_fields: list):
    """Compute correlations split by time of day (morning/afternoon/evening)."""
    buckets = {
        'morning': (6, 12),
        'afternoon': (12, 18),
        'evening': (18, 24),
    }

    for bucket_name, (hour_start, hour_end) in buckets.items():
        event_entries = fetchall(
            """SELECT DISTINCT date(timestamp) as day FROM events
               WHERE event_type = ? AND CAST(strftime('%H', timestamp) AS INTEGER) >= ?
               AND CAST(strftime('%H', timestamp) AS INTEGER) < ?""",
            (event_type, hour_start, hour_end),
        )
        event_days = {row['day'] for row in event_entries}

        if len(event_days) < 2:
            continue

        for metric_name in metric_fields:
            with_event = []
            without_event = []

            for day, metrics in metrics_by_day.items():
                val = metrics[metric_name]
                if val is None:
                    continue
                if day in event_days:
                    with_event.append(val)
                else:
                    without_event.append(val)

            if len(with_event) < 2 or len(without_event) < 3:
                continue

            avg_with = statistics.mean(with_event)
            avg_without = statistics.mean(without_event)
            delta = avg_with - avg_without
            delta_pct = (delta / avg_without * 100) if avg_without != 0 else 0
            total = len(with_event) + len(without_event)
            confidence = min(len(with_event), len(without_event)) / total

            execute(
                """INSERT INTO correlations
                   (event_type, metric_name, avg_with_event, avg_without_event,
                    delta, delta_pct, count_with, count_without, confidence, time_bucket, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(event_type, metric_name, time_bucket) DO UPDATE SET
                   avg_with_event=excluded.avg_with_event, avg_without_event=excluded.avg_without_event,
                   delta=excluded.delta, delta_pct=excluded.delta_pct,
                   count_with=excluded.count_with, count_without=excluded.count_without,
                   confidence=excluded.confidence, updated_at=CURRENT_TIMESTAMP""",
                (event_type, metric_name, avg_with, avg_without, delta, delta_pct,
                 len(with_event), len(without_event), confidence, bucket_name),
            )


def get_correlation_report() -> str:
    """Generate correlation report for /correlations command."""
    rows = fetchall(
        """SELECT * FROM correlations
           WHERE time_bucket = 'all' AND confidence >= 0.1 AND count_with >= 3
           ORDER BY ABS(delta_pct) DESC"""
    )

    if not rows:
        return "\U0001f4ca \u041d\u0435\u0434\u043e\u0441\u0442\u0430\u0442\u043e\u0447\u043d\u043e \u0434\u0430\u043d\u043d\u044b\u0445 \u0434\u043b\u044f \u043a\u043e\u0440\u0440\u0435\u043b\u044f\u0446\u0438\u0439. \u041f\u0440\u043e\u0434\u043e\u043b\u0436\u0430\u0439\u0442\u0435 \u043e\u0442\u043c\u0435\u0447\u0430\u0442\u044c \u0441\u043e\u0431\u044b\u0442\u0438\u044f!"

    event_emojis = {
        'coffee': '\u2615', 'alcohol': '\U0001f37a', 'hookah': '\U0001f4a8',
        'walk': '\U0001f6b6', 'workout': '\U0001f3cb\ufe0f', 'stress': '\U0001f624',
        'late_meal': '\U0001f374', 'supplement': '\U0001f48a', 'meditation': '\U0001f9d8',
        'nap': '\U0001f634', 'cold_shower': '\U0001f9ca', 'sauna': '\U0001f9d6',
        'blood_pressure': '\U0001fa78', 'blood_sugar': '\U0001fa78',
        'med_lisinopril': '\U0001f48a', 'med_glucophage': '\U0001f48a',
    }

    metric_labels = {
        'sleep_score': '\u0421\u043e\u043d', 'readiness_score': '\u0413\u043e\u0442\u043e\u0432\u043d.', 'average_hrv': 'HRV',
        'lowest_heart_rate': '\u041f\u0443\u043b\u044c\u0441', 'deep_sleep_duration': 'Deep',
        'total_sleep_duration': '\u0414\u043b\u0438\u0442.\u0441\u043d\u0430', 'steps': '\u0428\u0430\u0433\u0438',
        'sleep_efficiency': '\u042d\u0444\u0444\u0435\u043a\u0442.', 'sleep_latency': '\u0417\u0430\u0441\u044b\u043f.',
        'stress_high': '\u0421\u0442\u0440\u0435\u0441\u0441', 'rem_sleep_duration': 'REM',
    }

    report = "<b>\U0001f4ca \u041a\u041e\u0420\u0420\u0415\u041b\u042f\u0426\u0418\u0418 \u0421\u041e\u0411\u042b\u0422\u0418\u0419 \u0418 \u041c\u0415\u0422\u0420\u0418\u041a</b>\n\n"

    # Group by event
    current_event = None
    for row in rows[:30]:  # Limit to top 30
        event = row['event_type']
        if event != current_event:
            emoji = event_emojis.get(event, '\U0001f4cc')
            report += f"\n<b>{emoji} {event.upper()}</b> ({row['count_with']} \u0434\u043d\u0435\u0439)\n"
            current_event = event

        metric_label = metric_labels.get(row['metric_name'], row['metric_name'])
        delta_pct = row['delta_pct']
        arrow = "\u2197\ufe0f" if delta_pct > 0 else "\u2198\ufe0f"
        sign = "+" if delta_pct > 0 else ""

        report += f"  {metric_label}: {sign}{delta_pct:.1f}% {arrow}\n"

    return report
