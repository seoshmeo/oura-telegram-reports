#!/usr/bin/env python3
"""
Oura Alert Monitor
Monitors health metrics and sends alerts on significant changes
"""

import requests
import json
import os
import statistics
from datetime import datetime, timedelta

# Configuration
OURA_TOKEN = os.environ.get('OURA_TOKEN', '')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

API_BASE_URL = "https://api.ouraring.com/v2"
BASELINES_FILE = os.environ.get('BASELINES_FILE', '/app/data/baselines.json')
ALERTS_HISTORY_FILE = os.environ.get('ALERTS_HISTORY_FILE', '/app/data/alerts_history.json')

# Alert thresholds
THRESHOLDS = {
    'readiness_score_drop': 20,       # points below average
    'sleep_score_drop': 20,           # points below average
    'hrv_drop_pct': 30,               # % below average
    'rhr_rise_bpm': 10,               # bpm above average
    'temperature_deviation': 1.0,     # °C deviation
    'stress_high_multiplier': 2.0,    # x times average
    'spo2_min': 95,                   # minimum SpO2 %
}

DEDUP_HOURS = 12  # Don't repeat same alert within this window


def get_oura_data(endpoint, params=None):
    """Fetch data from Oura API"""
    headers = {'Authorization': f'Bearer {OURA_TOKEN}'}
    url = f"{API_BASE_URL}/{endpoint}"
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error fetching {endpoint}: {response.status_code} - {response.text}")
        return None


def send_telegram_message(text):
    """Send message to Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials not set!")
        print(text)
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    response = requests.post(url, data=data)
    return response.status_code == 200


def load_json_file(filepath):
    """Load JSON file, return empty dict if not exists"""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_json_file(filepath, data):
    """Save data to JSON file"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)


def compute_baselines():
    """Compute 7-day baselines for all tracked metrics"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=8)  # 8 days to ensure 7 full days

    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    params = {'start_date': start_str, 'end_date': end_str}

    readiness_data = get_oura_data("usercollection/daily_readiness", params)
    sleep_data = get_oura_data("usercollection/daily_sleep", params)
    sleep_sessions = get_oura_data("usercollection/sleep", params)
    stress_data = get_oura_data("usercollection/daily_stress", params)
    spo2_data = get_oura_data("usercollection/daily_spo2", params)

    baselines = {}

    # Readiness score baseline
    if readiness_data and readiness_data.get('data'):
        scores = [d['score'] for d in readiness_data['data'] if d.get('score')]
        if scores:
            baselines['readiness_score'] = statistics.mean(scores)

        temp_devs = [d.get('temperature_deviation', 0) for d in readiness_data['data']
                     if d.get('temperature_deviation') is not None]
        if temp_devs:
            baselines['temperature_deviation'] = statistics.mean(temp_devs)

    # Sleep score baseline
    if sleep_data and sleep_data.get('data'):
        scores = [d['score'] for d in sleep_data['data'] if d.get('score')]
        if scores:
            baselines['sleep_score'] = statistics.mean(scores)

    # HRV and heart rate from sleep sessions
    if sleep_sessions and sleep_sessions.get('data'):
        hrvs = [s.get('average_hrv', 0) for s in sleep_sessions['data'] if s.get('average_hrv')]
        if hrvs:
            baselines['hrv'] = statistics.mean(hrvs)

        rhrs = [s.get('lowest_heart_rate', 0) for s in sleep_sessions['data'] if s.get('lowest_heart_rate')]
        if rhrs:
            baselines['resting_hr'] = statistics.mean(rhrs)

    # Stress baseline
    if stress_data and stress_data.get('data'):
        stress_highs = [d.get('stress_high', 0) for d in stress_data['data'] if d.get('stress_high') is not None]
        if stress_highs:
            baselines['stress_high'] = statistics.mean(stress_highs)

    # SpO2 baseline
    if spo2_data and spo2_data.get('data'):
        spo2_values = [d.get('spo2_percentage', {}).get('average', 0) for d in spo2_data['data']
                       if d.get('spo2_percentage', {}).get('average')]
        if spo2_values:
            baselines['spo2'] = statistics.mean(spo2_values)

    baselines['updated_at'] = datetime.now().isoformat()

    return baselines


def get_current_values():
    """Get today's/latest metric values"""
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')
    params = {'start_date': yesterday, 'end_date': today}

    current = {}

    readiness_data = get_oura_data("usercollection/daily_readiness", params)
    if readiness_data and readiness_data.get('data'):
        latest = readiness_data['data'][-1]
        current['readiness_score'] = latest.get('score')
        current['temperature_deviation'] = latest.get('temperature_deviation')

    sleep_data = get_oura_data("usercollection/daily_sleep", params)
    if sleep_data and sleep_data.get('data'):
        current['sleep_score'] = sleep_data['data'][-1].get('score')

    sleep_sessions = get_oura_data("usercollection/sleep", params)
    if sleep_sessions and sleep_sessions.get('data'):
        latest_session = sleep_sessions['data'][-1]
        current['hrv'] = latest_session.get('average_hrv')
        current['resting_hr'] = latest_session.get('lowest_heart_rate')

    stress_data = get_oura_data("usercollection/daily_stress", params)
    if stress_data and stress_data.get('data'):
        current['stress_high'] = stress_data['data'][-1].get('stress_high')

    spo2_data = get_oura_data("usercollection/daily_spo2", params)
    if spo2_data and spo2_data.get('data'):
        current['spo2'] = spo2_data['data'][-1].get('spo2_percentage', {}).get('average')

    return current


def check_alerts(baselines, current):
    """Compare current values against baselines, return list of alerts"""
    alerts = []

    # Readiness score drop
    if baselines.get('readiness_score') and current.get('readiness_score'):
        baseline = baselines['readiness_score']
        value = current['readiness_score']
        drop = baseline - value
        if drop >= THRESHOLDS['readiness_score_drop']:
            alerts.append({
                'metric': 'readiness_score',
                'severity': 'red' if drop >= 30 else 'yellow',
                'message': f"Readiness ниже нормы: {value:.0f} (обычно ~{baseline:.0f})",
            })

    # Sleep score drop
    if baselines.get('sleep_score') and current.get('sleep_score'):
        baseline = baselines['sleep_score']
        value = current['sleep_score']
        drop = baseline - value
        if drop >= THRESHOLDS['sleep_score_drop']:
            alerts.append({
                'metric': 'sleep_score',
                'severity': 'red' if drop >= 30 else 'yellow',
                'message': f"Sleep Score упал: {value:.0f} (обычно ~{baseline:.0f})",
            })

    # HRV drop
    if baselines.get('hrv') and current.get('hrv'):
        baseline = baselines['hrv']
        value = current['hrv']
        drop_pct = (baseline - value) / baseline * 100
        if drop_pct >= THRESHOLDS['hrv_drop_pct']:
            alerts.append({
                'metric': 'hrv',
                'severity': 'red' if drop_pct >= 40 else 'yellow',
                'message': f"HRV резко упал: {value:.0f}ms (обычно ~{baseline:.0f}ms, -{drop_pct:.0f}%)",
            })

    # Resting heart rate rise
    if baselines.get('resting_hr') and current.get('resting_hr'):
        baseline = baselines['resting_hr']
        value = current['resting_hr']
        rise = value - baseline
        if rise >= THRESHOLDS['rhr_rise_bpm']:
            alerts.append({
                'metric': 'resting_hr',
                'severity': 'red' if rise >= 15 else 'yellow',
                'message': f"Пульс покоя вырос: {value:.0f} bpm (обычно ~{baseline:.0f} bpm, +{rise:.0f})",
            })

    # Temperature deviation
    if current.get('temperature_deviation') is not None:
        temp = current['temperature_deviation']
        if abs(temp) > THRESHOLDS['temperature_deviation']:
            alerts.append({
                'metric': 'temperature',
                'severity': 'red' if abs(temp) > 1.5 else 'yellow',
                'message': f"Температура тела: {temp:+.2f}°C (норма: ±1.0°C)",
            })

    # Stress high
    if baselines.get('stress_high') and current.get('stress_high'):
        baseline = baselines['stress_high']
        value = current['stress_high']
        if baseline > 0 and value >= baseline * THRESHOLDS['stress_high_multiplier']:
            alerts.append({
                'metric': 'stress_high',
                'severity': 'red' if value >= baseline * 3 else 'yellow',
                'message': f"Стресс повышен: {value:.0f} мин (обычно ~{baseline:.0f} мин, x{value/baseline:.1f})",
            })

    # SpO2
    if current.get('spo2') is not None:
        value = current['spo2']
        if value < THRESHOLDS['spo2_min']:
            alerts.append({
                'metric': 'spo2',
                'severity': 'red' if value < 92 else 'yellow',
                'message': f"SpO2 низкий: {value:.1f}% (норма: ≥95%)",
            })

    return alerts


def filter_duplicate_alerts(alerts, history):
    """Filter out alerts that were sent recently (within DEDUP_HOURS)"""
    now = datetime.now()
    cutoff = now - timedelta(hours=DEDUP_HOURS)

    filtered = []
    for alert in alerts:
        metric = alert['metric']
        last_sent = history.get(metric)
        if last_sent:
            last_sent_time = datetime.fromisoformat(last_sent)
            if last_sent_time > cutoff:
                continue
        filtered.append(alert)

    return filtered


def format_alert_message(alerts):
    """Format alerts into a Telegram message"""
    severity_icons = {'red': '🔴', 'yellow': '🟡'}

    message = "<b>⚠️ OURA АЛЕРТ</b>\n\n"

    for alert in alerts:
        icon = severity_icons.get(alert['severity'], '🟡')
        message += f"{icon} {alert['message']}\n"

    # Add recommendation based on severity
    has_red = any(a['severity'] == 'red' for a in alerts)
    message += "\n<b>💡 Рекомендация:</b> "
    if has_red:
        message += "Снизьте нагрузку, ложитесь раньше. Обратите внимание на восстановление."
    else:
        message += "Следите за показателями. Избегайте перенапряжения."

    return message


def run_alert_check():
    """Main alert check routine"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Running alert check...")

    # Load or compute baselines
    baselines = load_json_file(BASELINES_FILE)

    # Recompute baselines if older than 24 hours or missing
    should_update = True
    if baselines.get('updated_at'):
        last_update = datetime.fromisoformat(baselines['updated_at'])
        if (datetime.now() - last_update).total_seconds() < 86400:
            should_update = False

    if should_update:
        print("Computing fresh baselines...")
        baselines = compute_baselines()
        save_json_file(BASELINES_FILE, baselines)
        print(f"Baselines saved: {json.dumps({k: f'{v:.1f}' for k, v in baselines.items() if isinstance(v, (int, float))}, indent=2)}")

    # Get current values
    current = get_current_values()
    if not current:
        print("No current data available")
        return

    print(f"Current values: {json.dumps({k: f'{v:.1f}' if isinstance(v, float) else v for k, v in current.items() if v is not None}, indent=2)}")

    # Check for alerts
    alerts = check_alerts(baselines, current)

    if not alerts:
        print("No alerts triggered")
        return

    print(f"Alerts triggered: {len(alerts)}")

    # Deduplicate
    history = load_json_file(ALERTS_HISTORY_FILE)
    alerts = filter_duplicate_alerts(alerts, history)

    if not alerts:
        print("All alerts were deduplicated (sent recently)")
        return

    # Send alert
    message = format_alert_message(alerts)
    success = send_telegram_message(message)

    if success:
        print(f"Alert sent successfully ({len(alerts)} alerts)")
        # Update history
        now_str = datetime.now().isoformat()
        for alert in alerts:
            history[alert['metric']] = now_str
        save_json_file(ALERTS_HISTORY_FILE, history)
    else:
        print("Failed to send alert")


if __name__ == "__main__":
    run_alert_check()
