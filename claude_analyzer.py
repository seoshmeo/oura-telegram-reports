#!/usr/bin/env python3
"""
Claude AI Analyzer for Oura Data
Provides deep insights and personalized recommendations
"""

import os
from anthropic import Anthropic
import json
from datetime import datetime, timedelta


class OuraClaudeAnalyzer:
    """Analyzes Oura data using Claude AI"""

    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get('CLAUDE_API_KEY')
        if not self.api_key:
            raise ValueError("Claude API key not provided")

        self.client = Anthropic(api_key=self.api_key)

    def analyze_daily_data(self, sleep_data, readiness_data, activity_data, sleep_sessions, historical_days=7):
        """
        Analyze daily Oura data with Claude AI

        Args:
            sleep_data: Sleep data for recent days
            readiness_data: Readiness data for recent days
            activity_data: Activity data for recent days
            sleep_sessions: Detailed sleep sessions
            historical_days: Number of days to analyze for trends

        Returns:
            str: Claude's analysis and recommendations
        """

        # Prepare data summary
        data_summary = self._prepare_data_summary(
            sleep_data,
            readiness_data,
            activity_data,
            sleep_sessions,
            historical_days
        )

        # Create prompt for Claude
        prompt = self._create_analysis_prompt(data_summary)

        # Get Claude's analysis
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2000,
                temperature=0.7,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            return response.content[0].text

        except Exception as e:
            return f"⚠️ Ошибка анализа Claude: {str(e)}"

    def _prepare_data_summary(self, sleep_data, readiness_data, activity_data, sleep_sessions, days=7):
        """Prepare concise data summary for Claude"""

        summary = {
            'period': f'последние {days} дней',
            'sleep': [],
            'readiness': [],
            'activity': [],
            'sessions': []
        }

        # Take last N days
        if sleep_data and 'data' in sleep_data:
            summary['sleep'] = sleep_data['data'][-days:]

        if readiness_data and 'data' in readiness_data:
            summary['readiness'] = readiness_data['data'][-days:]

        if activity_data and 'data' in activity_data:
            summary['activity'] = activity_data['data'][-days:]

        if sleep_sessions and 'data' in sleep_sessions:
            summary['sessions'] = sleep_sessions['data'][-days:]

        return summary

    def _create_analysis_prompt(self, data_summary):
        """Create analysis prompt for Claude"""

        prompt = f"""Ты - эксперт по анализу данных здоровья и сна. Проанализируй данные Oura Ring пользователя за {data_summary['period']}.

ДАННЫЕ ПО СНУ (последние дни):
"""

        # Add sleep data
        for day in data_summary['sleep'][-3:]:  # Last 3 days
            date = day.get('day', 'N/A')
            score = day.get('score', 'N/A')
            contributors = day.get('contributors', {})
            prompt += f"\n{date}: Score={score}/100"
            prompt += f" (Deep:{contributors.get('deep_sleep', 0)}, REM:{contributors.get('rem_sleep', 0)}, "
            prompt += f"Efficiency:{contributors.get('efficiency', 0)}, Timing:{contributors.get('timing', 0)})"

        # Add sleep sessions with details
        prompt += "\n\nДЕТАЛИ СЕССИЙ СНА:"
        for session in data_summary['sessions'][-3:]:
            date = session.get('day', 'N/A')
            total_sleep = session.get('total_sleep_duration', 0) / 3600
            deep = session.get('deep_sleep_duration', 0) / 3600
            rem = session.get('rem_sleep_duration', 0) / 3600
            efficiency = session.get('efficiency', 0)
            hrv = session.get('average_hrv', 0)
            hr = session.get('lowest_heart_rate', 0)

            prompt += f"\n{date}: {total_sleep:.1f}ч сна (Deep:{deep:.1f}ч, REM:{rem:.1f}ч, Eff:{efficiency}%, HRV:{hrv}ms, MinHR:{hr}bpm)"

        # Add readiness data
        prompt += "\n\nГОТОВНОСТЬ (последние дни):"
        for day in data_summary['readiness'][-3:]:
            date = day.get('day', 'N/A')
            score = day.get('score', 'N/A')
            contributors = day.get('contributors', {})
            temp_dev = day.get('temperature_deviation', 0)

            prompt += f"\n{date}: Score={score}/100 "
            prompt += f"(Recovery:{contributors.get('recovery_index', 0)}, "
            prompt += f"HRV_balance:{contributors.get('hrv_balance', 0)}, "
            prompt += f"Sleep_balance:{contributors.get('sleep_balance', 0)}, "
            prompt += f"Temp:{temp_dev:+.2f}°C)"

        # Add activity data
        prompt += "\n\nАКТИВНОСТЬ (последние дни):"
        for day in data_summary['activity'][-3:]:
            date = day.get('day', 'N/A')
            score = day.get('score', 'N/A')
            steps = day.get('steps', 0)
            calories = day.get('active_calories', 0)

            prompt += f"\n{date}: Score={score}/100 (Шаги:{steps:,}, Калории:{calories})"

        # Add trends calculation
        if len(data_summary['sleep']) >= 3:
            sleep_scores = [d.get('score', 0) for d in data_summary['sleep']]
            trend = "↗️ растёт" if sleep_scores[-1] > sleep_scores[0] else "↘️ падает" if sleep_scores[-1] < sleep_scores[0] else "→ стабилен"
            avg_score = sum(sleep_scores) / len(sleep_scores)
            prompt += f"\n\nТРЕНД СНА: {trend} (средний score: {avg_score:.1f})"

        if len(data_summary['readiness']) >= 3:
            readiness_scores = [d.get('score', 0) for d in data_summary['readiness']]
            sleep_balances = [d.get('contributors', {}).get('sleep_balance', 0) for d in data_summary['readiness']]
            recovery_indexes = [d.get('contributors', {}).get('recovery_index', 0) for d in data_summary['readiness']]

            prompt += f"\nSleep Balance тренд: {sleep_balances[0]} → {sleep_balances[-1]}"
            prompt += f"\nRecovery Index тренд: {recovery_indexes[0]} → {recovery_indexes[-1]}"

        prompt += """

ЗАДАЧА:
Проанализируй данные и предоставь:

1. 🎯 ГЛАВНЫЙ ИНСАЙТ (1-2 предложения) - самое важное что нужно знать
2. ⚠️ НА ЧТО ОБРАТИТЬ ВНИМАНИЕ (2-3 пункта) - тревожные сигналы или паттерны
3. ✅ ЧТО ХОРОШО (1-2 пункта) - позитивные тенденции
4. 💡 РЕКОМЕНДАЦИИ НА СЕГОДНЯ (2-3 конкретных действия)
5. 📊 ТРЕНДЫ (если видны изменения за период)

Формат ответа - краткий, конкретный, на русском. Используй эмодзи для структуры.
Фокус на ДЕЙСТВИЯХ, которые пользователь может предпринять СЕГОДНЯ.
"""

        return prompt

    def analyze_weekly_trends(self, sleep_data, readiness_data, activity_data, days=14):
        """
        Analyze weekly trends with more historical context

        Args:
            sleep_data: Sleep data for recent weeks
            readiness_data: Readiness data for recent weeks
            activity_data: Activity data for recent weeks
            days: Number of days to analyze

        Returns:
            str: Claude's weekly trend analysis
        """

        prompt = f"""Ты - эксперт по анализу трендов здоровья. Проанализируй данные Oura Ring за последние {days} дней.

ТРЕНДЫ СНА:
"""

        if sleep_data and 'data' in sleep_data:
            sleep_scores = [d.get('score', 0) for d in sleep_data['data'][-days:]]
            prompt += f"Scores: {', '.join(map(str, sleep_scores[-7:]))}\n"
            prompt += f"Средний: {sum(sleep_scores)/len(sleep_scores):.1f}\n"
            prompt += f"Диапазон: {min(sleep_scores)}-{max(sleep_scores)}\n"

        prompt += "\nТРЕНДЫ ГОТОВНОСТИ:\n"
        if readiness_data and 'data' in readiness_data:
            readiness_scores = [d.get('score', 0) for d in readiness_data['data'][-days:]]
            sleep_balances = [d.get('contributors', {}).get('sleep_balance', 0) for d in readiness_data['data'][-days:]]
            recovery_indexes = [d.get('contributors', {}).get('recovery_index', 0) for d in readiness_data['data'][-days:]]

            prompt += f"Readiness Scores: {', '.join(map(str, readiness_scores[-7:]))}\n"
            prompt += f"Sleep Balance: {sleep_balances[0]} → {sleep_balances[-1]} (тренд: {'↗️' if sleep_balances[-1] > sleep_balances[0] else '↘️'})\n"
            prompt += f"Recovery Index: средний {sum(recovery_indexes)/len(recovery_indexes):.0f}\n"

        prompt += "\nАКТИВНОСТЬ:\n"
        if activity_data and 'data' in activity_data:
            steps = [d.get('steps', 0) for d in activity_data['data'][-days:]]
            activity_scores = [d.get('score', 0) for d in activity_data['data'][-days:]]

            prompt += f"Средние шаги/день: {sum(steps)/len(steps):.0f}\n"
            prompt += f"Activity Score средний: {sum(activity_scores)/len(activity_scores):.1f}\n"

        prompt += """

ЗАДАЧА - еженедельный анализ:
1. 📊 ОСНОВНЫЕ ТРЕНДЫ за период (что улучшилось, что ухудшилось)
2. 🔍 ПАТТЕРНЫ И КОРРЕЛЯЦИИ (связи между сном, активностью, готовностью)
3. ⚠️ ЗОНЫ РИСКА (что требует внимания на следующей неделе)
4. 🎯 ПРИОРИТЕТЫ НА НЕДЕЛЮ (3-4 конкретных цели)

Ответ краткий (до 10 предложений), конкретный, с эмодзи, на русском.
"""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1500,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            return f"⚠️ Ошибка анализа: {str(e)}"
