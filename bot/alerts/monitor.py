"""
Alert monitor - detects anomalies in health metrics.
Refactored from alert_monitor.py.
"""

import json
import logging
import os
import statistics
from datetime import datetime, timedelta

from bot.config import BASELINES_FILE, ALERTS_HISTORY_FILE, DEDUP_HOURS
from bot.core.oura_api import get_oura_data_range
from bot.core.telegram import send_telegram_message

logger = logging.getLogger(__name__)

THRESHOLDS = {
    'readiness_score_drop': 20,
    'sleep_score_drop': 20,
    'hrv_drop_pct': 30,
    'rhr_rise_bpm': 10,
    'temperature_deviation': 1.0,
    'stress_high_multiplier': 2.0,
    'spo2_min': 95,
}


def _load_json(filepath: str) -> dict:
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_json(filepath: str, data: dict):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)


async def compute_baselines() -> dict:
    """Compute 7-day rolling baselines."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=8)
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    readiness_data = await get_oura_data_range("usercollection/daily_readiness", start_str, end_str)
    sleep_data = await get_oura_data_range("usercollection/daily_sleep", start_str, end_str)
    sleep_sessions = await get_oura_data_range("usercollection/sleep", start_str, end_str)
    stress_data = await get_oura_data_range("usercollection/daily_stress", start_str, end_str)
    spo2_data = await get_oura_data_range("usercollection/daily_spo2", start_str, end_str)

    baselines = {}

    if readiness_data and readiness_data.get('data'):
        scores = [d['score'] for d in readiness_data['data'] if d.get('score')]
        if scores:
            baselines['readiness_score'] = statistics.mean(scores)
        temp_devs = [d.get('temperature_deviation', 0) for d in readiness_data['data'] if d.get('temperature_deviation') is not None]
        if temp_devs:
            baselines['temperature_deviation'] = statistics.mean(temp_devs)

    if sleep_data and sleep_data.get('data'):
        scores = [d['score'] for d in sleep_data['data'] if d.get('score')]
        if scores:
            baselines['sleep_score'] = statistics.mean(scores)

    if sleep_sessions and sleep_sessions.get('data'):
        hrvs = [s.get('average_hrv', 0) for s in sleep_sessions['data'] if s.get('average_hrv')]
        if hrvs:
            baselines['hrv'] = statistics.mean(hrvs)
        rhrs = [s.get('lowest_heart_rate', 0) for s in sleep_sessions['data'] if s.get('lowest_heart_rate')]
        if rhrs:
            baselines['resting_hr'] = statistics.mean(rhrs)

    if stress_data and stress_data.get('data'):
        stress_highs = [d.get('stress_high', 0) for d in stress_data['data'] if d.get('stress_high') is not None]
        if stress_highs:
            baselines['stress_high'] = statistics.mean(stress_highs)

    if spo2_data and spo2_data.get('data'):
        spo2_values = [d.get('spo2_percentage', {}).get('average', 0) for d in spo2_data['data']
                       if d.get('spo2_percentage', {}).get('average')]
        if spo2_values:
            baselines['spo2'] = statistics.mean(spo2_values)

    baselines['updated_at'] = datetime.now().isoformat()
    return baselines


async def get_current_values() -> dict:
    """Get today's/latest metric values."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')

    current = {}

    readiness = await get_oura_data_range("usercollection/daily_readiness", yesterday, today)
    if readiness and readiness.get('data'):
        latest = readiness['data'][-1]
        current['readiness_score'] = latest.get('score')
        current['temperature_deviation'] = latest.get('temperature_deviation')

    sleep = await get_oura_data_range("usercollection/daily_sleep", yesterday, today)
    if sleep and sleep.get('data'):
        current['sleep_score'] = sleep['data'][-1].get('score')

    sessions = await get_oura_data_range("usercollection/sleep", yesterday, today)
    if sessions and sessions.get('data'):
        latest = sessions['data'][-1]
        current['hrv'] = latest.get('average_hrv')
        current['resting_hr'] = latest.get('lowest_heart_rate')

    stress = await get_oura_data_range("usercollection/daily_stress", yesterday, today)
    if stress and stress.get('data'):
        current['stress_high'] = stress['data'][-1].get('stress_high')

    spo2 = await get_oura_data_range("usercollection/daily_spo2", yesterday, today)
    if spo2 and spo2.get('data'):
        current['spo2'] = spo2['data'][-1].get('spo2_percentage', {}).get('average')

    return current


def check_alerts(baselines: dict, current: dict) -> list[dict]:
    """Compare current values against baselines."""
    alerts = []

    if baselines.get('readiness_score') and current.get('readiness_score'):
        drop = baselines['readiness_score'] - current['readiness_score']
        if drop >= THRESHOLDS['readiness_score_drop']:
            alerts.append({
                'metric': 'readiness_score',
                'severity': 'red' if drop >= 30 else 'yellow',
                'message': f"Readiness \u043d\u0438\u0436\u0435 \u043d\u043e\u0440\u043c\u044b: {current['readiness_score']:.0f} (\u043e\u0431\u044b\u0447\u043d\u043e ~{baselines['readiness_score']:.0f})",
            })

    if baselines.get('sleep_score') and current.get('sleep_score'):
        drop = baselines['sleep_score'] - current['sleep_score']
        if drop >= THRESHOLDS['sleep_score_drop']:
            alerts.append({
                'metric': 'sleep_score',
                'severity': 'red' if drop >= 30 else 'yellow',
                'message': f"Sleep Score \u0443\u043f\u0430\u043b: {current['sleep_score']:.0f} (\u043e\u0431\u044b\u0447\u043d\u043e ~{baselines['sleep_score']:.0f})",
            })

    if baselines.get('hrv') and current.get('hrv'):
        drop_pct = (baselines['hrv'] - current['hrv']) / baselines['hrv'] * 100
        if drop_pct >= THRESHOLDS['hrv_drop_pct']:
            alerts.append({
                'metric': 'hrv',
                'severity': 'red' if drop_pct >= 40 else 'yellow',
                'message': f"HRV \u0440\u0435\u0437\u043a\u043e \u0443\u043f\u0430\u043b: {current['hrv']:.0f}ms (\u043e\u0431\u044b\u0447\u043d\u043e ~{baselines['hrv']:.0f}ms, -{drop_pct:.0f}%)",
            })

    if baselines.get('resting_hr') and current.get('resting_hr'):
        rise = current['resting_hr'] - baselines['resting_hr']
        if rise >= THRESHOLDS['rhr_rise_bpm']:
            alerts.append({
                'metric': 'resting_hr',
                'severity': 'red' if rise >= 15 else 'yellow',
                'message': f"\u041f\u0443\u043b\u044c\u0441 \u043f\u043e\u043a\u043e\u044f \u0432\u044b\u0440\u043e\u0441: {current['resting_hr']:.0f} bpm (\u043e\u0431\u044b\u0447\u043d\u043e ~{baselines['resting_hr']:.0f} bpm, +{rise:.0f})",
            })

    if current.get('temperature_deviation') is not None:
        temp = current['temperature_deviation']
        if abs(temp) > THRESHOLDS['temperature_deviation']:
            alerts.append({
                'metric': 'temperature',
                'severity': 'red' if abs(temp) > 1.5 else 'yellow',
                'message': f"\u0422\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430 \u0442\u0435\u043b\u0430: {temp:+.2f}\u00b0C (\u043d\u043e\u0440\u043c\u0430: \u00b11.0\u00b0C)",
            })

    if baselines.get('stress_high') and current.get('stress_high'):
        baseline = baselines['stress_high']
        value = current['stress_high']
        if baseline > 0 and value >= baseline * THRESHOLDS['stress_high_multiplier']:
            alerts.append({
                'metric': 'stress_high',
                'severity': 'red' if value >= baseline * 3 else 'yellow',
                'message': f"\u0421\u0442\u0440\u0435\u0441\u0441 \u043f\u043e\u0432\u044b\u0448\u0435\u043d: {value:.0f} \u043c\u0438\u043d (\u043e\u0431\u044b\u0447\u043d\u043e ~{baseline:.0f} \u043c\u0438\u043d, x{value / baseline:.1f})",
            })

    if current.get('spo2') is not None:
        value = current['spo2']
        if value < THRESHOLDS['spo2_min']:
            alerts.append({
                'metric': 'spo2',
                'severity': 'red' if value < 92 else 'yellow',
                'message': f"SpO2 \u043d\u0438\u0437\u043a\u0438\u0439: {value:.1f}% (\u043d\u043e\u0440\u043c\u0430: \u226595%)",
            })

    return alerts


def _filter_duplicates(alerts: list[dict], history: dict) -> list[dict]:
    """Filter out recently sent alerts."""
    now = datetime.now()
    cutoff = now - timedelta(hours=DEDUP_HOURS)
    filtered = []
    for alert in alerts:
        last_sent = history.get(alert['metric'])
        if last_sent:
            last_sent_time = datetime.fromisoformat(last_sent)
            if last_sent_time > cutoff:
                continue
        filtered.append(alert)
    return filtered


def _format_alert_message(alerts: list[dict]) -> str:
    severity_icons = {'red': '\U0001f534', 'yellow': '\U0001f7e1'}
    message = "<b>\u26a0\ufe0f OURA \u0410\u041b\u0415\u0420\u0422</b>\n\n"
    for alert in alerts:
        icon = severity_icons.get(alert['severity'], '\U0001f7e1')
        message += f"{icon} {alert['message']}\n"
    has_red = any(a['severity'] == 'red' for a in alerts)
    message += "\n<b>\U0001f4a1 \u0420\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0430\u0446\u0438\u044f:</b> "
    if has_red:
        message += "\u0421\u043d\u0438\u0437\u044c\u0442\u0435 \u043d\u0430\u0433\u0440\u0443\u0437\u043a\u0443, \u043b\u043e\u0436\u0438\u0442\u0435\u0441\u044c \u0440\u0430\u043d\u044c\u0448\u0435. \u041e\u0431\u0440\u0430\u0442\u0438\u0442\u0435 \u0432\u043d\u0438\u043c\u0430\u043d\u0438\u0435 \u043d\u0430 \u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435."
    else:
        message += "\u0421\u043b\u0435\u0434\u0438\u0442\u0435 \u0437\u0430 \u043f\u043e\u043a\u0430\u0437\u0430\u0442\u0435\u043b\u044f\u043c\u0438. \u0418\u0437\u0431\u0435\u0433\u0430\u0439\u0442\u0435 \u043f\u0435\u0440\u0435\u043d\u0430\u043f\u0440\u044f\u0436\u0435\u043d\u0438\u044f."
    return message


async def run_alert_check():
    """Main alert check routine."""
    logger.info("Running alert check...")

    baselines = _load_json(BASELINES_FILE)

    # Recompute baselines if stale
    should_update = True
    if baselines.get('updated_at'):
        last_update = datetime.fromisoformat(baselines['updated_at'])
        if (datetime.now() - last_update).total_seconds() < 86400:
            should_update = False

    if should_update:
        logger.info("Computing fresh baselines...")
        baselines = await compute_baselines()
        _save_json(BASELINES_FILE, baselines)

    current = await get_current_values()
    if not current:
        logger.info("No current data available")
        return

    alerts = check_alerts(baselines, current)
    if not alerts:
        logger.info("No alerts triggered")
        return

    logger.info("Alerts triggered: %d", len(alerts))

    history = _load_json(ALERTS_HISTORY_FILE)
    alerts = _filter_duplicates(alerts, history)
    if not alerts:
        logger.info("All alerts deduplicated")
        return

    message = _format_alert_message(alerts)
    success = await send_telegram_message(message)

    if success:
        logger.info("Alert sent (%d alerts)", len(alerts))
        now_str = datetime.now().isoformat()
        for alert in alerts:
            history[alert['metric']] = now_str
        _save_json(ALERTS_HISTORY_FILE, history)
    else:
        logger.error("Failed to send alert")
