#!/usr/bin/env python3
"""
Oura Daily Telegram Report
Отправляет ежедневный утренний отчёт с анализом данных Oura Ring
"""

import requests
import json
from datetime import datetime, timedelta
import os

# Конфигурация
OURA_TOKEN = os.environ.get('OURA_TOKEN', 'A7N3JSL6YZM7UXDUUJUQG4WJMLWDCUB5')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')  # Получить от @BotFather
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')     # Ваш chat ID

API_BASE_URL = "https://api.ouraring.com/v2"

def get_oura_data(endpoint, params=None):
    """Получить данные из Oura API"""
    headers = {'Authorization': f'Bearer {OURA_TOKEN}'}
    url = f"{API_BASE_URL}/{endpoint}"
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return None

def get_emoji_indicator(score):
    """Эмодзи-индикатор на основе оценки"""
    if score >= 85:
        return "🟢"
    elif score >= 70:
        return "🟡"
    else:
        return "🔴"

def format_time_diff(hours):
    """Форматировать разницу во времени"""
    if hours > 0:
        return f"+{hours:.1f}ч"
    else:
        return f"{hours:.1f}ч"

def send_telegram_message(text):
    """Отправить сообщение в Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials not set!")
        print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables")
        print("\nMessage that would be sent:")
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

def generate_daily_report():
    """Генерация ежедневного отчёта"""

    # Получаем данные за вчерашний день
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')

    # Получаем данные
    sleep_data = get_oura_data("usercollection/daily_sleep",
                               {'start_date': yesterday, 'end_date': today})
    readiness_data = get_oura_data("usercollection/daily_readiness",
                                   {'start_date': yesterday, 'end_date': today})
    activity_data = get_oura_data("usercollection/daily_activity",
                                  {'start_date': yesterday, 'end_date': yesterday})

    # Последняя сессия сна
    sleep_sessions = get_oura_data("usercollection/sleep",
                                   {'start_date': yesterday, 'end_date': today})

    if not all([sleep_data, readiness_data, activity_data]):
        return "❌ Ошибка получения данных из Oura API"

    # Извлекаем данные
    sleep = sleep_data['data'][-1] if sleep_data['data'] else None
    readiness = readiness_data['data'][-1] if readiness_data['data'] else None
    activity = activity_data['data'][-1] if activity_data['data'] else None
    last_session = sleep_sessions['data'][-1] if sleep_sessions and sleep_sessions['data'] else None

    if not all([sleep, readiness, activity]):
        return "❌ Недостаточно данных за последний день"

    # Формируем отчёт
    report_date = datetime.now().strftime('%d.%m.%Y')

    # Заголовок
    report = f"<b>🌅 OURA УТРЕННИЙ ОТЧЁТ</b>\n"
    report += f"📅 {report_date}\n\n"

    # Сводка
    sleep_score = sleep['score']
    readiness_score = readiness['score']

    report += f"<b>СВОДКА</b>\n"
    report += f"{get_emoji_indicator(sleep_score)} Сон: <b>{sleep_score}/100</b>  |  "
    report += f"{get_emoji_indicator(readiness_score)} Готовность: <b>{readiness_score}/100</b>\n\n"

    # Сон
    report += f"<b>💤 СОН</b>\n"

    if last_session:
        bedtime_start = datetime.fromisoformat(last_session['bedtime_start'].replace('Z', '+00:00'))
        bedtime_end = datetime.fromisoformat(last_session['bedtime_end'].replace('Z', '+00:00'))

        total_sleep_hours = last_session.get('total_sleep_duration', 0) / 3600
        deep_sleep_hours = last_session.get('deep_sleep_duration', 0) / 3600
        rem_sleep_hours = last_session.get('rem_sleep_duration', 0) / 3600
        light_sleep_hours = last_session.get('light_sleep_duration', 0) / 3600

        sleep_diff = total_sleep_hours - 7.5
        efficiency = last_session.get('efficiency', 0)

        report += f"  Общий сон: <b>{total_sleep_hours:.1f}ч</b> (цель: 7.5ч) [{format_time_diff(sleep_diff)}]\n"
        report += f"  Засыпание: {bedtime_start.strftime('%H:%M')} → Подъём: {bedtime_end.strftime('%H:%M')}\n"
        report += f"  Deep: {deep_sleep_hours:.1f}ч | REM: {rem_sleep_hours:.1f}ч | Light: {light_sleep_hours:.1f}ч\n"

        # Время засыпания
        sleep_onset_latency = last_session.get('latency', 0)
        if sleep_onset_latency > 1800:  # > 30 минут
            report += f"  ⚠️ Засыпание за: <b>{sleep_onset_latency//60} мин</b>\n"
        else:
            report += f"  Засыпание за: {sleep_onset_latency//60} мин\n"

        report += f"  Efficiency: {efficiency}%\n"
    else:
        report += f"  Данные о сессии сна недоступны\n"

    report += f"\n"

    # Восстановление
    report += f"<b>❤️ ВОССТАНОВЛЕНИЕ</b>\n"

    if last_session:
        hrv = last_session.get('average_hrv', 0)
        lowest_hr = last_session.get('lowest_heart_rate', 0)
        avg_hr = last_session.get('average_heart_rate', 0)

        report += f"  HRV за ночь: {hrv} мс\n"
        report += f"  Мин. пульс: {lowest_hr} bpm\n"
        report += f"  Средний пульс сна: {avg_hr:.0f} bpm\n"

    recovery_index = readiness['contributors'].get('recovery_index', 0)
    if recovery_index < 30:
        report += f"  ⚠️⚠️⚠️ Recovery Index: <b>{recovery_index}</b> [КРИТИЧНО]\n"
    elif recovery_index < 50:
        report += f"  ⚠️ Recovery Index: <b>{recovery_index}</b>\n"
    else:
        report += f"  Recovery Index: {recovery_index}\n"

    temp_dev = readiness.get('temperature_deviation', 0)
    if abs(temp_dev) > 1.0:
        report += f"  ⚠️ Температура: <b>{temp_dev:+.2f}°C</b>\n"
    else:
        report += f"  Температура: {temp_dev:+.2f}°C\n"

    report += f"\n"

    # Баланс сна
    sleep_balance = readiness['contributors'].get('sleep_balance', 0)
    report += f"<b>⚖️ БАЛАНС СНА</b>\n"

    if sleep_balance < 70:
        report += f"  ⚠️ Sleep Balance: <b>{sleep_balance}/100</b>\n"
    else:
        report += f"  Sleep Balance: {sleep_balance}/100\n"

    report += f"\n"

    # Рекомендация дня
    report += f"<b>💡 РЕКОМЕНДАЦИЯ ДНЯ</b>\n"

    recommendations = []

    if sleep_score < 70:
        recommendations.append("Приоритет: восстановление. Ложитесь до 23:00.")

    if recovery_index < 30:
        recommendations.append("Recovery критически низкий - избегайте интенсивных нагрузок.")
    elif recovery_index < 50:
        recommendations.append("Восстановление неполное - лёгкая активность (прогулка).")

    if sleep['contributors'].get('timing', 100) < 50:
        recommendations.append("Режим сна сбит - вернитесь к 22:30 отбой.")

    if temp_dev < -1.0:
        recommendations.append("Температура понижена - следите за самочувствием.")

    if not recommendations:
        if readiness_score >= 85:
            recommendations.append("Отличное восстановление! Можно планировать тренировку.")
        else:
            recommendations.append("Поддерживайте режим. Цель: сон 7.5ч, отбой в 22:30.")

    for rec in recommendations:
        report += f"  • {rec}\n"

    report += f"\n"

    # Вчерашняя активность
    report += f"<b>🏃 ВЧЕРАШНЯЯ АКТИВНОСТЬ</b>\n"

    steps = activity.get('steps', 0)
    active_cal = activity.get('active_calories', 0)
    total_cal = activity.get('calories', 0)
    medium_activity = activity.get('medium_activity_time', 0) // 60

    steps_emoji = "✅" if steps >= 8000 else "⚠️"
    activity_emoji = "✅" if medium_activity >= 30 else "⚠️"

    report += f"  {steps_emoji} Шаги: <b>{steps:,}</b> (цель: 8000)\n"
    report += f"  Калории: {active_cal} акт. / {total_cal} всего\n"
    report += f"  {activity_emoji} Medium activity: <b>{medium_activity} мин</b> (цель: 30 мин)\n"

    return report

def main():
    """Основная функция"""
    print("Генерация ежедневного отчёта Oura...\n")

    report = generate_daily_report()

    if report.startswith("❌"):
        print(report)
        return

    # Отправка в Telegram
    success = send_telegram_message(report)

    if success:
        print("✅ Отчёт успешно отправлен в Telegram!")
    else:
        print("⚠️ Не удалось отправить в Telegram (см. вывод выше)")

    # Сохранение в файл для истории
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"oura_daily_report_{timestamp}.txt"

    with open(filename, 'w', encoding='utf-8') as f:
        # Убираем HTML теги для текстового файла
        clean_report = report.replace('<b>', '').replace('</b>', '')
        f.write(clean_report)

    print(f"📝 Отчёт сохранён в {filename}")

if __name__ == "__main__":
    main()
