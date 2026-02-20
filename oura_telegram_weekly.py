#!/usr/bin/env python3
"""
Oura Weekly/Monthly Telegram Report
Отправляет еженедельные и ежемесячные отчёты с трендами
"""

import requests
import json
from datetime import datetime, timedelta
import os
import statistics
from claude_analyzer import OuraClaudeAnalyzer

# Конфигурация
OURA_TOKEN = os.environ.get('OURA_TOKEN', '')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY', '')

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

def create_sparkline(values):
    """Создать мини-график из значений"""
    if not values:
        return ""

    bars = "▁▂▃▄▅▆▇█"
    min_val = min(values)
    max_val = max(values)

    if max_val == min_val:
        return bars[4] * len(values)

    normalized = [(v - min_val) / (max_val - min_val) for v in values]
    return ''.join(bars[min(int(n * 7), 7)] for n in normalized)

def create_bar_chart(value, max_value=100):
    """Создать простую столбчатую диаграмму"""
    filled = int(value / max_value * 10)
    return "█" * filled + "░" * (10 - filled)

def send_telegram_message(text):
    """Отправить сообщение в Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials not set!")
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

def generate_weekly_report():
    """Генерация еженедельного отчёта"""

    # Последние 7 дней
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    # Получаем данные
    sleep_data = get_oura_data("usercollection/daily_sleep",
                               {'start_date': start_str, 'end_date': end_str})
    readiness_data = get_oura_data("usercollection/daily_readiness",
                                   {'start_date': start_str, 'end_date': end_str})
    activity_data = get_oura_data("usercollection/daily_activity",
                                  {'start_date': start_str, 'end_date': end_str})
    workouts_data = get_oura_data("usercollection/workout",
                                  {'start_date': start_str, 'end_date': end_str})
    sleep_sessions = get_oura_data("usercollection/sleep",
                                   {'start_date': start_str, 'end_date': end_str})
    stress_data = get_oura_data("usercollection/daily_stress",
                                {'start_date': start_str, 'end_date': end_str})

    if not all([sleep_data, readiness_data, activity_data]):
        return "❌ Ошибка получения данных из Oura API"

    sleep_days = sleep_data['data']
    readiness_days = readiness_data['data']
    activity_days = activity_data['data']
    workouts = workouts_data['data'] if workouts_data else []
    sessions = sleep_sessions['data'] if sleep_sessions else []
    stress_days = stress_data['data'] if stress_data and stress_data.get('data') else []

    # Формируем отчёт
    report = f"<b>📊 OURA ЕЖЕНЕДЕЛЬНЫЙ ОТЧЁТ</b>\n"
    report += f"Неделя: {start_date.strftime('%d.%m')} - {end_date.strftime('%d.%m.%Y')}\n\n"

    # Средние оценки
    avg_sleep = statistics.mean([d['score'] for d in sleep_days]) if sleep_days else 0
    avg_readiness = statistics.mean([d['score'] for d in readiness_days]) if readiness_days else 0
    avg_activity = statistics.mean([d['score'] for d in activity_days]) if activity_days else 0

    report += f"<b>ОБЩИЕ ОЦЕНКИ (среднее за неделю)</b>\n"
    report += f"  Сон:        <b>{avg_sleep:.1f}</b>\n"
    report += f"  Готовность: <b>{avg_readiness:.1f}</b>\n"
    report += f"  Активность: <b>{avg_activity:.1f}</b>\n\n"

    # Тренд сна
    report += f"<b>💤 ТРЕНД СНА</b>\n"

    for day in sleep_days[:7]:  # Показываем все 7 дней
        date_obj = datetime.fromisoformat(day['day'])
        score = day['score']
        bar = create_bar_chart(score)
        report += f"  {date_obj.strftime('%d.%m')}: {bar} {score}\n"

    # Статистика сна
    sleep_durations = [s.get('total_sleep_duration', 0) / 3600 for s in sessions if s.get('total_sleep_duration')]
    avg_sleep_hours = statistics.mean(sleep_durations) if sleep_durations else 0
    days_over_7h = sum(1 for d in sleep_durations if d >= 7)

    best_sleep_day = max(sleep_days, key=lambda x: x['score']) if sleep_days else None
    worst_sleep_day = min(sleep_days, key=lambda x: x['score']) if sleep_days else None

    report += f"\n  Среднее время сна: <b>{avg_sleep_hours:.1f}ч</b>\n"
    if best_sleep_day:
        report += f"  Лучшая ночь: {best_sleep_day['day'][5:]} (score: {best_sleep_day['score']})\n"
    if worst_sleep_day:
        report += f"  Худшая ночь: {worst_sleep_day['day'][5:]} (score: {worst_sleep_day['score']})\n"
    report += f"  Дней с целевым сном (≥7ч): <b>{days_over_7h} из {len(sleep_durations)}</b>\n\n"

    # Тренд готовности
    report += f"<b>❤️ ТРЕНД ГОТОВНОСТИ</b>\n"

    sleep_balances = [d['contributors'].get('sleep_balance', 0) for d in readiness_days]
    recovery_indexes = [d['contributors'].get('recovery_index', 0) for d in readiness_days]

    if len(sleep_balances) >= 2:
        balance_trend = "↗️" if sleep_balances[-1] > sleep_balances[0] else "↘️"
        report += f"  Sleep Balance: {sleep_balances[0]} → {sleep_balances[-1]} {balance_trend}\n"
    else:
        report += f"  Sleep Balance: недостаточно данных\n"

    if len(recovery_indexes) >= 2:
        recovery_trend = "↗️" if recovery_indexes[-1] > recovery_indexes[0] else "↘️"
        if recovery_indexes[-1] < 30:
            report += f"  ⚠️⚠️ Recovery Index: {recovery_indexes[0]} → <b>{recovery_indexes[-1]}</b> {recovery_trend}\n"
        else:
            report += f"  Recovery Index: {recovery_indexes[0]} → {recovery_indexes[-1]} {recovery_trend}\n"

    # HRV
    hrvs = [s.get('average_hrv', 0) for s in sessions if s.get('average_hrv')]
    avg_hrv = statistics.mean(hrvs) if hrvs else 0
    report += f"  Средний HRV сна: {avg_hrv:.0f} мс\n\n"

    # Активность
    report += f"<b>🏃 АКТИВНОСТЬ</b>\n"

    total_steps = sum(d.get('steps', 0) for d in activity_days)
    avg_steps = total_steps / len(activity_days) if activity_days else 0

    total_sedentary = sum(d.get('sedentary_time', 0) for d in activity_days)
    avg_sedentary_hours = (total_sedentary / len(activity_days) / 3600) if activity_days else 0

    high_activity = sum(d.get('high_activity_time', 0) for d in activity_days)

    report += f"  Всего шагов: <b>{total_steps:,}</b> ({avg_steps:.0f}/день)\n"
    report += f"  Тренировок: <b>{len(workouts)}</b>\n"

    if workouts:
        workout_types = {}
        for w in workouts:
            activity_type = w.get('activity', 'unknown')
            workout_types[activity_type] = workout_types.get(activity_type, 0) + 1

        workout_summary = ", ".join([f"{k} ({v})" for k, v in workout_types.items()])
        report += f"  Типы: {workout_summary}\n"

    report += f"  Дней без тренировки: <b>{7 - len(workouts)}</b>\n"
    report += f"  Среднее sedentary: {avg_sedentary_hours:.1f}ч/день\n"

    if high_activity == 0:
        report += f"  ⚠️ High intensity: <b>0 минут</b>\n"

    report += f"\n"

    # Стресс
    if stress_days:
        report += f"<b>🧘 СТРЕСС</b>\n"

        stress_highs = [d.get('stress_high', 0) for d in stress_days]
        recovery_highs = [d.get('recovery_high', 0) for d in stress_days]
        avg_stress = statistics.mean(stress_highs) if stress_highs else 0
        avg_recovery = statistics.mean(recovery_highs) if recovery_highs else 0

        report += f"  Среднее время в стрессе: <b>{avg_stress:.0f} мин/день</b>\n"
        report += f"  Среднее время восстановления: <b>{avg_recovery:.0f} мин/день</b>\n"

        stressful_days = [d for d in stress_days if d.get('day_summary') == 'stressful']
        if stressful_days:
            dates = ", ".join(d['day'][5:] for d in stressful_days)
            report += f"  🔴 Дни с высоким стрессом ({len(stressful_days)}): {dates}\n"

        stress_sparkline = create_sparkline(stress_highs)
        if stress_sparkline:
            report += f"  Тренд стресса: {stress_sparkline}\n"

        report += f"\n"

    # Температура тела
    temp_devs = [d.get('temperature_deviation', 0) for d in readiness_days]
    if temp_devs:
        min_temp = min(temp_devs)
        max_temp = max(temp_devs)

        report += f"<b>🌡 ТЕМПЕРАТУРА ТЕЛА</b>\n"
        report += f"  Диапазон: {min_temp:+.2f} до {max_temp:+.2f}°C\n"

        anomalies = [d for d in readiness_days if abs(d.get('temperature_deviation', 0)) > 1.0]
        if anomalies:
            for anomaly in anomalies:
                date_str = anomaly['day'][5:]
                temp = anomaly.get('temperature_deviation', 0)
                report += f"  ⚠️ Аномалия {date_str}: {temp:+.2f}°C\n"

        report += f"\n"

    # Топ-3 приоритета
    report += f"<b>🎯 ТОП-3 ПРИОРИТЕТА НА СЛЕДУЮЩУЮ НЕДЕЛЮ</b>\n"

    priorities = []

    # Анализ проблем
    if avg_sleep_hours < 7:
        priorities.append("Увеличить сон до 7.5ч: отбой в 22:30")

    if avg_steps < 7000:
        priorities.append(f"Поднять активность: цель {int(avg_steps + 2000):,} шагов/день")

    if len(workouts) < 3:
        priorities.append("Добавить регулярные прогулки: 3-4 раза в неделю")

    timing_issues = sum(1 for d in sleep_days if d['contributors'].get('timing', 100) < 70)
    if timing_issues >= 3:
        priorities.append("Стабилизировать режим: отбой ±30 мин от 22:30")

    if statistics.mean(recovery_indexes) < 50:
        priorities.append("Улучшить recovery: без еды за 3ч до сна")

    # Берём топ-3
    for i, priority in enumerate(priorities[:3], 1):
        report += f"  {i}. {priority}\n"

    if not priorities:
        report += f"  ✅ Продолжать в том же духе!\n"

    return report

def generate_monthly_report():
    """Генерация ежемесячного отчёта"""

    # Последние 30 дней
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    # Получаем данные
    sleep_data = get_oura_data("usercollection/daily_sleep",
                               {'start_date': start_str, 'end_date': end_str})
    readiness_data = get_oura_data("usercollection/daily_readiness",
                                   {'start_date': start_str, 'end_date': end_str})
    activity_data = get_oura_data("usercollection/daily_activity",
                                  {'start_date': start_str, 'end_date': end_str})
    workouts_data = get_oura_data("usercollection/workout",
                                  {'start_date': start_str, 'end_date': end_str})
    stress_data = get_oura_data("usercollection/daily_stress",
                                {'start_date': start_str, 'end_date': end_str})

    if not all([sleep_data, readiness_data, activity_data]):
        return "❌ Ошибка получения данных из Oura API"

    sleep_days = sleep_data['data']
    readiness_days = readiness_data['data']
    activity_days = activity_data['data']
    workouts = workouts_data['data'] if workouts_data else []
    stress_days = stress_data['data'] if stress_data and stress_data.get('data') else []

    # Формируем отчёт
    month_name = end_date.strftime('%B %Y')
    report = f"<b>📈 OURA МЕСЯЧНЫЙ ОТЧЁТ</b>\n"
    report += f"{month_name}\n\n"

    # Средние оценки
    avg_sleep = statistics.mean([d['score'] for d in sleep_days]) if sleep_days else 0
    avg_readiness = statistics.mean([d['score'] for d in readiness_days]) if readiness_days else 0
    avg_activity = statistics.mean([d['score'] for d in activity_days]) if activity_days else 0

    report += f"<b>СРЕДНИЕ ОЦЕНКИ</b>\n"
    report += f"  Сон:        <b>{avg_sleep:.1f}</b>\n"
    report += f"  Готовность: <b>{avg_readiness:.1f}</b>\n"
    report += f"  Активность: <b>{avg_activity:.1f}</b>\n\n"

    # Тренды (последние 8 недель для sparkline)
    sleep_scores = [d['score'] for d in sleep_days[-56:]]  # 8 недель
    readiness_scores = [d['score'] for d in readiness_days[-56:]]
    activity_scores = [d['score'] for d in activity_days[-56:]]

    # Группируем по неделям для sparkline
    sleep_weekly = [statistics.mean(sleep_scores[i:i+7]) for i in range(0, len(sleep_scores), 7) if len(sleep_scores[i:i+7]) == 7]
    readiness_weekly = [statistics.mean(readiness_scores[i:i+7]) for i in range(0, len(readiness_scores), 7) if len(readiness_scores[i:i+7]) == 7]
    activity_weekly = [statistics.mean(activity_scores[i:i+7]) for i in range(0, len(activity_scores), 7) if len(activity_scores[i:i+7]) == 7]

    report += f"<b>ТРЕНДЫ (по неделям)</b>\n"
    report += f"  Sleep:     {create_sparkline(sleep_weekly)}\n"
    report += f"  Readiness: {create_sparkline(readiness_weekly)}\n"
    report += f"  Activity:  {create_sparkline(activity_weekly)}\n\n"

    # Инсайты по активности
    total_steps = sum(d.get('steps', 0) for d in activity_days)
    avg_steps = total_steps / len(activity_days) if activity_days else 0

    days_over_8k_steps = sum(1 for d in activity_days if d.get('steps', 0) >= 8000)
    pct_active = (days_over_8k_steps / len(activity_days) * 100) if activity_days else 0

    report += f"<b>🏃 АКТИВНОСТЬ</b>\n"
    report += f"  Среднее шагов/день: <b>{avg_steps:.0f}</b>\n"
    report += f"  Всего тренировок: <b>{len(workouts)}</b>\n"

    if workouts:
        workout_types = {}
        for w in workouts:
            activity_type = w.get('activity', 'unknown')
            workout_types[activity_type] = workout_types.get(activity_type, 0) + 1

        report += f"  Типы: {', '.join([f'{k} ({v})' for k, v in workout_types.items()])}\n"

    report += f"  % дней с целевой активностью (≥8000 шагов): <b>{pct_active:.0f}%</b>\n\n"

    # Стресс за месяц
    if stress_days:
        report += f"<b>🧘 СТРЕСС</b>\n"

        stress_highs = [d.get('stress_high', 0) for d in stress_days]
        recovery_highs = [d.get('recovery_high', 0) for d in stress_days]
        avg_stress = statistics.mean(stress_highs) if stress_highs else 0
        avg_recovery = statistics.mean(recovery_highs) if recovery_highs else 0

        report += f"  Среднее время в стрессе: <b>{avg_stress:.0f} мин/день</b>\n"
        report += f"  Среднее время восстановления: <b>{avg_recovery:.0f} мин/день</b>\n"

        stressful_count = sum(1 for d in stress_days if d.get('day_summary') == 'stressful')
        normal_count = sum(1 for d in stress_days if d.get('day_summary') == 'normal')
        restored_count = sum(1 for d in stress_days if d.get('day_summary') == 'restored')

        report += f"  Дни: 🟢 {restored_count} восст. | 🟡 {normal_count} норм. | 🔴 {stressful_count} стресс.\n"

        # Sparkline по неделям
        stress_weekly = [statistics.mean(stress_highs[i:i+7]) for i in range(0, len(stress_highs), 7) if len(stress_highs[i:i+7]) == 7]
        if stress_weekly:
            report += f"  Тренд (по неделям): {create_sparkline(stress_weekly)}\n"

        report += f"\n"

    # Рекомендации
    report += f"<b>💡 РЕКОМЕНДАЦИИ НА СЛЕДУЮЩИЙ МЕСЯЦ</b>\n"

    if avg_sleep < 75:
        report += f"  • Приоритет: улучшить сон (текущий {avg_sleep:.0f} → цель 80+)\n"

    if avg_activity < 70:
        report += f"  • Увеличить ежедневную активность до 8000+ шагов\n"

    if len(workouts) < 12:  # Меньше 3 в неделю
        report += f"  • Стабилизировать частоту тренировок: 3-4/неделю\n"

    return report

def generate_claude_analysis(report_type='weekly'):
    """Генерация анализа от Claude AI для weekly/monthly отчётов"""

    if not CLAUDE_API_KEY:
        print("⚠️ Claude API key не установлен, пропускаем AI анализ")
        return None

    print("🤖 Генерация анализа Claude AI...")

    try:
        days = 14 if report_type == 'weekly' else 45
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        params = {'start_date': start_str, 'end_date': end_str}

        sleep_data = get_oura_data("usercollection/daily_sleep", params)
        readiness_data = get_oura_data("usercollection/daily_readiness", params)
        activity_data = get_oura_data("usercollection/daily_activity", params)
        stress_data = get_oura_data("usercollection/daily_stress", params)

        if not all([sleep_data, readiness_data, activity_data]):
            return None

        analyzer = OuraClaudeAnalyzer(api_key=CLAUDE_API_KEY)
        analysis = analyzer.analyze_weekly_trends(
            sleep_data, readiness_data, activity_data,
            stress_data=stress_data,
            days=days
        )

        label = "ЕЖЕНЕДЕЛЬНЫЙ" if report_type == 'weekly' else "МЕСЯЧНЫЙ"
        message = f"<b>🤖 {label} АНАЛИЗ ОТ CLAUDE AI</b>\n\n"
        message += analysis

        return message

    except Exception as e:
        print(f"⚠️ Ошибка генерации анализа Claude: {e}")
        return None

def main():
    """Основная функция"""
    import sys
    import time

    report_type = sys.argv[1] if len(sys.argv) > 1 else 'weekly'

    if report_type == 'weekly':
        print("Генерация еженедельного отчёта Oura...\n")
        report = generate_weekly_report()
    elif report_type == 'monthly':
        print("Генерация ежемесячного отчёта Oura...\n")
        report = generate_monthly_report()
    else:
        print(f"Неизвестный тип отчёта: {report_type}")
        print("Использование: python3 oura_telegram_weekly.py [weekly|monthly]")
        return

    if report.startswith("❌"):
        print(report)
        return

    # Отправка в Telegram
    success = send_telegram_message(report)

    if success:
        print(f"✅ {report_type.capitalize()} отчёт успешно отправлен в Telegram!")
    else:
        print("⚠️ Не удалось отправить в Telegram (см. вывод выше)")
        return

    # Генерация и отправка анализа Claude
    claude_analysis = generate_claude_analysis(report_type)

    if claude_analysis:
        time.sleep(2)
        success_claude = send_telegram_message(claude_analysis)
        if success_claude:
            print("✅ Анализ Claude успешно отправлен в Telegram!")
        else:
            print("⚠️ Не удалось отправить анализ Claude")

    # Сохранение в файл
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"oura_{report_type}_report_{timestamp}.txt"

    with open(filename, 'w', encoding='utf-8') as f:
        clean_report = report.replace('<b>', '').replace('</b>', '')
        f.write(clean_report)
        if claude_analysis:
            f.write("\n\n" + "="*50 + "\n")
            f.write(claude_analysis.replace('<b>', '').replace('</b>', ''))

    print(f"📝 Отчёт сохранён в {filename}")

if __name__ == "__main__":
    main()
