"""
Claude AI analyzer for Oura health data.
Refactored from claude_analyzer.py with extended capabilities.
"""

import os
from anthropic import Anthropic


class OuraClaudeAnalyzer:
    """Analyzes Oura data using Claude AI."""

    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get('CLAUDE_API_KEY')
        if not self.api_key:
            raise ValueError("Claude API key not provided")
        self.client = Anthropic(api_key=self.api_key)

    def analyze_daily_data(self, sleep_data, readiness_data, activity_data,
                           sleep_sessions, stress_data=None, historical_days=7,
                           weather_context=None, events_context=None):
        """Analyze daily Oura data with optional weather and event context."""
        data_summary = self._prepare_data_summary(
            sleep_data, readiness_data, activity_data,
            sleep_sessions, historical_days, stress_data=stress_data,
        )
        prompt = self._create_analysis_prompt(data_summary, weather_context, events_context)

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2000,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as e:
            return f"\u26a0\ufe0f \u041e\u0448\u0438\u0431\u043a\u0430 \u0430\u043d\u0430\u043b\u0438\u0437\u0430 Claude: {e}"

    def analyze_weekly_trends(self, sleep_data, readiness_data, activity_data, days=14):
        """Analyze weekly trends with more historical context."""
        prompt = f"""\u0422\u044b - \u044d\u043a\u0441\u043f\u0435\u0440\u0442 \u043f\u043e \u0430\u043d\u0430\u043b\u0438\u0437\u0443 \u0442\u0440\u0435\u043d\u0434\u043e\u0432 \u0437\u0434\u043e\u0440\u043e\u0432\u044c\u044f. \u041f\u0440\u043e\u0430\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u0443\u0439 \u0434\u0430\u043d\u043d\u044b\u0435 Oura Ring \u0437\u0430 \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 {days} \u0434\u043d\u0435\u0439.

\u0422\u0420\u0415\u041d\u0414\u042b \u0421\u041d\u0410:
"""
        if sleep_data and 'data' in sleep_data:
            sleep_scores = [d.get('score', 0) for d in sleep_data['data'][-days:]]
            prompt += f"Scores: {', '.join(map(str, sleep_scores[-7:]))}\n"
            prompt += f"\u0421\u0440\u0435\u0434\u043d\u0438\u0439: {sum(sleep_scores) / len(sleep_scores):.1f}\n"
            prompt += f"\u0414\u0438\u0430\u043f\u0430\u0437\u043e\u043d: {min(sleep_scores)}-{max(sleep_scores)}\n"

        prompt += "\n\u0422\u0420\u0415\u041d\u0414\u042b \u0413\u041e\u0422\u041e\u0412\u041d\u041e\u0421\u0422\u0418:\n"
        if readiness_data and 'data' in readiness_data:
            readiness_scores = [d.get('score', 0) for d in readiness_data['data'][-days:]]
            sleep_balances = [d.get('contributors', {}).get('sleep_balance', 0) for d in readiness_data['data'][-days:]]
            recovery_indexes = [d.get('contributors', {}).get('recovery_index', 0) for d in readiness_data['data'][-days:]]
            prompt += f"Readiness Scores: {', '.join(map(str, readiness_scores[-7:]))}\n"
            balance_arrow = "\u2197\ufe0f" if sleep_balances[-1] > sleep_balances[0] else "\u2198\ufe0f"
            prompt += f"Sleep Balance: {sleep_balances[0]} \u2192 {sleep_balances[-1]} (\u0442\u0440\u0435\u043d\u0434: {balance_arrow})\n"
            prompt += f"Recovery Index: \u0441\u0440\u0435\u0434\u043d\u0438\u0439 {sum(recovery_indexes) / len(recovery_indexes):.0f}\n"

        prompt += "\n\u0410\u041a\u0422\u0418\u0412\u041d\u041e\u0421\u0422\u042c:\n"
        if activity_data and 'data' in activity_data:
            steps = [d.get('steps', 0) for d in activity_data['data'][-days:]]
            activity_scores = [d.get('score', 0) for d in activity_data['data'][-days:]]
            prompt += f"\u0421\u0440\u0435\u0434\u043d\u0438\u0435 \u0448\u0430\u0433\u0438/\u0434\u0435\u043d\u044c: {sum(steps) / len(steps):.0f}\n"
            prompt += f"Activity Score \u0441\u0440\u0435\u0434\u043d\u0438\u0439: {sum(activity_scores) / len(activity_scores):.1f}\n"

        prompt += """

\u0417\u0410\u0414\u0410\u0427\u0410 - \u0435\u0436\u0435\u043d\u0435\u0434\u0435\u043b\u044c\u043d\u044b\u0439 \u0430\u043d\u0430\u043b\u0438\u0437:
1. \U0001f4ca \u041e\u0421\u041d\u041e\u0412\u041d\u042b\u0415 \u0422\u0420\u0415\u041d\u0414\u042b \u0437\u0430 \u043f\u0435\u0440\u0438\u043e\u0434 (\u0447\u0442\u043e \u0443\u043b\u0443\u0447\u0448\u0438\u043b\u043e\u0441\u044c, \u0447\u0442\u043e \u0443\u0445\u0443\u0434\u0448\u0438\u043b\u043e\u0441\u044c)
2. \U0001f50d \u041f\u0410\u0422\u0422\u0415\u0420\u041d\u042b \u0418 \u041a\u041e\u0420\u0420\u0415\u041b\u042f\u0426\u0418\u0418 (\u0441\u0432\u044f\u0437\u0438 \u043c\u0435\u0436\u0434\u0443 \u0441\u043d\u043e\u043c, \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0441\u0442\u044c\u044e, \u0433\u043e\u0442\u043e\u0432\u043d\u043e\u0441\u0442\u044c\u044e)
3. \u26a0\ufe0f \u0417\u041e\u041d\u042b \u0420\u0418\u0421\u041a\u0410 (\u0447\u0442\u043e \u0442\u0440\u0435\u0431\u0443\u0435\u0442 \u0432\u043d\u0438\u043c\u0430\u043d\u0438\u044f \u043d\u0430 \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0435\u0439 \u043d\u0435\u0434\u0435\u043b\u0435)
4. \U0001f3af \u041f\u0420\u0418\u041e\u0420\u0418\u0422\u0415\u0422\u042b \u041d\u0410 \u041d\u0415\u0414\u0415\u041b\u042e (3-4 \u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u044b\u0445 \u0446\u0435\u043b\u0438)

\u041e\u0442\u0432\u0435\u0442 \u043a\u0440\u0430\u0442\u043a\u0438\u0439 (\u0434\u043e 10 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0439), \u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u044b\u0439, \u0441 \u044d\u043c\u043e\u0434\u0437\u0438, \u043d\u0430 \u0440\u0443\u0441\u0441\u043a\u043e\u043c.
"""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1500,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as e:
            return f"\u26a0\ufe0f \u041e\u0448\u0438\u0431\u043a\u0430 \u0430\u043d\u0430\u043b\u0438\u0437\u0430: {e}"

    def parse_event(self, raw_text: str) -> dict | None:
        """Use Claude to parse unrecognized event text into structured data."""
        prompt = f"""\u0422\u044b - \u043f\u0430\u0440\u0441\u0435\u0440 \u0441\u043e\u0431\u044b\u0442\u0438\u0439 \u0434\u043b\u044f health-\u0442\u0440\u0435\u043a\u0435\u0440\u0430. \u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c \u043d\u0430\u043f\u0438\u0441\u0430\u043b: "{raw_text}"

\u041e\u043f\u0440\u0435\u0434\u0435\u043b\u0438 \u0442\u0438\u043f \u0441\u043e\u0431\u044b\u0442\u0438\u044f \u0438 \u043a\u0430\u043a\u0438\u0435 \u043c\u0435\u0442\u0440\u0438\u043a\u0438 \u0437\u0434\u043e\u0440\u043e\u0432\u044c\u044f \u043c\u043e\u0433\u0443\u0442 \u0431\u044b\u0442\u044c \u0437\u0430\u0442\u0440\u043e\u043d\u0443\u0442\u044b.

\u041e\u0442\u0432\u0435\u0442\u044c \u0422\u041e\u041b\u042c\u041a\u041e \u0432 \u0444\u043e\u0440\u043c\u0430\u0442\u0435 JSON:
{{"event_type": "\u0442\u0438\u043f_\u043d\u0430_\u0430\u043d\u0433\u043b\u0438\u0439\u0441\u043a\u043e\u043c", "emoji": "\u044d\u043c\u043e\u0434\u0437\u0438", "details": {{}}, "metrics_to_correlate": ["sleep_score", "hrv", ...]}}

\u0414\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0435 \u0442\u0438\u043f\u044b: coffee, alcohol, hookah, walk, workout, stress, late_meal, supplement, meditation, nap, cold_shower, sauna, travel, illness, party, argument
\u0414\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0435 \u043c\u0435\u0442\u0440\u0438\u043a\u0438: sleep_score, readiness_score, hrv, resting_hr, deep_sleep, rem_sleep, sleep_efficiency, sleep_latency, temperature, stress_high, steps

\u0415\u0441\u043b\u0438 \u0442\u0435\u043a\u0441\u0442 \u041d\u0415 \u043f\u043e\u0445\u043e\u0436 \u043d\u0430 \u0441\u043e\u0431\u044b\u0442\u0438\u0435, \u043e\u0442\u0432\u0435\u0442\u044c: {{"event_type": null}}"""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=300,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )
            import json
            text = response.content[0].text.strip()
            # Extract JSON from response
            if '{' in text:
                json_str = text[text.index('{'):text.rindex('}') + 1]
                result = json.loads(json_str)
                if result.get('event_type'):
                    return result
            return None
        except Exception:
            return None

    def _prepare_data_summary(self, sleep_data, readiness_data, activity_data,
                              sleep_sessions, days=7, stress_data=None):
        summary = {
            'period': f'\u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 {days} \u0434\u043d\u0435\u0439',
            'sleep': [],
            'readiness': [],
            'activity': [],
            'sessions': [],
            'stress': [],
        }
        if sleep_data and 'data' in sleep_data:
            summary['sleep'] = sleep_data['data'][-days:]
        if readiness_data and 'data' in readiness_data:
            summary['readiness'] = readiness_data['data'][-days:]
        if activity_data and 'data' in activity_data:
            summary['activity'] = activity_data['data'][-days:]
        if sleep_sessions and 'data' in sleep_sessions:
            summary['sessions'] = sleep_sessions['data'][-days:]
        if stress_data and 'data' in stress_data:
            summary['stress'] = stress_data['data'][-days:]
        return summary

    def _create_analysis_prompt(self, data_summary, weather_context=None, events_context=None):
        prompt = f"""\u0422\u044b - \u044d\u043a\u0441\u043f\u0435\u0440\u0442 \u043f\u043e \u0430\u043d\u0430\u043b\u0438\u0437\u0443 \u0434\u0430\u043d\u043d\u044b\u0445 \u0437\u0434\u043e\u0440\u043e\u0432\u044c\u044f \u0438 \u0441\u043d\u0430. \u041f\u0440\u043e\u0430\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u0443\u0439 \u0434\u0430\u043d\u043d\u044b\u0435 Oura Ring \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f \u0437\u0430 {data_summary['period']}.

\u0414\u0410\u041d\u041d\u042b\u0415 \u041f\u041e \u0421\u041d\u0423 (\u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 \u0434\u043d\u0438):
"""
        for day in data_summary['sleep'][-3:]:
            date = day.get('day', 'N/A')
            score = day.get('score', 'N/A')
            contributors = day.get('contributors', {})
            prompt += f"\n{date}: Score={score}/100"
            prompt += f" (Deep:{contributors.get('deep_sleep', 0)}, REM:{contributors.get('rem_sleep', 0)}, "
            prompt += f"Efficiency:{contributors.get('efficiency', 0)}, Timing:{contributors.get('timing', 0)})"

        prompt += "\n\n\u0414\u0415\u0422\u0410\u041b\u0418 \u0421\u0415\u0421\u0421\u0418\u0419 \u0421\u041d\u0410:"
        for session in data_summary['sessions'][-3:]:
            date = session.get('day', 'N/A')
            total_sleep = session.get('total_sleep_duration', 0) / 3600
            deep = session.get('deep_sleep_duration', 0) / 3600
            rem = session.get('rem_sleep_duration', 0) / 3600
            efficiency = session.get('efficiency', 0)
            hrv = session.get('average_hrv', 0)
            hr = session.get('lowest_heart_rate', 0)
            prompt += f"\n{date}: {total_sleep:.1f}\u0447 \u0441\u043d\u0430 (Deep:{deep:.1f}\u0447, REM:{rem:.1f}\u0447, Eff:{efficiency}%, HRV:{hrv}ms, MinHR:{hr}bpm)"

        prompt += "\n\n\u0413\u041e\u0422\u041e\u0412\u041d\u041e\u0421\u0422\u042c (\u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 \u0434\u043d\u0438):"
        for day in data_summary['readiness'][-3:]:
            date = day.get('day', 'N/A')
            score = day.get('score', 'N/A')
            contributors = day.get('contributors', {})
            temp_dev = day.get('temperature_deviation', 0)
            prompt += f"\n{date}: Score={score}/100 "
            prompt += f"(Recovery:{contributors.get('recovery_index', 0)}, "
            prompt += f"HRV_balance:{contributors.get('hrv_balance', 0)}, "
            prompt += f"Sleep_balance:{contributors.get('sleep_balance', 0)}, "
            prompt += f"Temp:{temp_dev:+.2f}\u00b0C)"

        prompt += "\n\n\u0410\u041a\u0422\u0418\u0412\u041d\u041e\u0421\u0422\u042c (\u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 \u0434\u043d\u0438):"
        for day in data_summary['activity'][-3:]:
            date = day.get('day', 'N/A')
            score = day.get('score', 'N/A')
            steps = day.get('steps', 0)
            calories = day.get('active_calories', 0)
            prompt += f"\n{date}: Score={score}/100 (\u0428\u0430\u0433\u0438:{steps:,}, \u041a\u0430\u043b\u043e\u0440\u0438\u0438:{calories})"

        if data_summary['stress']:
            prompt += "\n\n\u0421\u0422\u0420\u0415\u0421\u0421 (\u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 \u0434\u043d\u0438):"
            for day in data_summary['stress'][-3:]:
                date = day.get('day', 'N/A')
                day_summary = day.get('day_summary', 'N/A')
                stress_high_sec = day.get('stress_high', 0)
                recovery_high_sec = day.get('recovery_high', 0)
                stress_high = stress_high_sec / 60
                recovery_high = recovery_high_sec / 60
                ratio = f"{stress_high_sec / recovery_high_sec:.1f}" if recovery_high_sec > 0 else "N/A"
                prompt += f"\n{date}: \u0421\u0442\u0430\u0442\u0443\u0441={day_summary}, \u0421\u0442\u0440\u0435\u0441\u0441={stress_high:.0f}\u043c\u0438\u043d, \u0412\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435={recovery_high:.0f}\u043c\u0438\u043d, \u0421\u043e\u043e\u0442\u043d\u043e\u0448\u0435\u043d\u0438\u0435={ratio}"

        # Weather context
        if weather_context:
            prompt += f"\n\n\u041f\u041e\u0413\u041e\u0414\u0410 (\u041a\u0438\u043f\u0440, \u041b\u0430\u0440\u043d\u0430\u043a\u0430):\n{weather_context}"

        # Events context
        if events_context:
            prompt += f"\n\n\u0421\u041e\u0411\u042b\u0422\u0418\u042f \u041f\u041e\u041b\u042c\u0417\u041e\u0412\u0410\u0422\u0415\u041b\u042f:\n{events_context}"

        # Trends
        if len(data_summary['sleep']) >= 3:
            sleep_scores = [d.get('score', 0) for d in data_summary['sleep']]
            trend = "\u2197\ufe0f \u0440\u0430\u0441\u0442\u0451\u0442" if sleep_scores[-1] > sleep_scores[0] else "\u2198\ufe0f \u043f\u0430\u0434\u0430\u0435\u0442" if sleep_scores[-1] < sleep_scores[0] else "\u2192 \u0441\u0442\u0430\u0431\u0438\u043b\u0435\u043d"
            avg_score = sum(sleep_scores) / len(sleep_scores)
            prompt += f"\n\n\u0422\u0420\u0415\u041d\u0414 \u0421\u041d\u0410: {trend} (\u0441\u0440\u0435\u0434\u043d\u0438\u0439 score: {avg_score:.1f})"

        if len(data_summary['readiness']) >= 3:
            sleep_balances = [d.get('contributors', {}).get('sleep_balance', 0) for d in data_summary['readiness']]
            recovery_indexes = [d.get('contributors', {}).get('recovery_index', 0) for d in data_summary['readiness']]
            prompt += f"\nSleep Balance \u0442\u0440\u0435\u043d\u0434: {sleep_balances[0]} \u2192 {sleep_balances[-1]}"
            prompt += f"\nRecovery Index \u0442\u0440\u0435\u043d\u0434: {recovery_indexes[0]} \u2192 {recovery_indexes[-1]}"

        prompt += """

\u0417\u0410\u0414\u0410\u0427\u0410:
\u041f\u0440\u043e\u0430\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u0443\u0439 \u0434\u0430\u043d\u043d\u044b\u0435 \u0438 \u043f\u0440\u0435\u0434\u043e\u0441\u0442\u0430\u0432\u044c:

1. \U0001f3af \u0413\u041b\u0410\u0412\u041d\u042b\u0419 \u0418\u041d\u0421\u0410\u0419\u0422 (1-2 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u044f) - \u0441\u0430\u043c\u043e\u0435 \u0432\u0430\u0436\u043d\u043e\u0435 \u0447\u0442\u043e \u043d\u0443\u0436\u043d\u043e \u0437\u043d\u0430\u0442\u044c
2. \u26a0\ufe0f \u041d\u0410 \u0427\u0422\u041e \u041e\u0411\u0420\u0410\u0422\u0418\u0422\u042c \u0412\u041d\u0418\u041c\u0410\u041d\u0418\u0415 (2-3 \u043f\u0443\u043d\u043a\u0442\u0430) - \u0442\u0440\u0435\u0432\u043e\u0436\u043d\u044b\u0435 \u0441\u0438\u0433\u043d\u0430\u043b\u044b \u0438\u043b\u0438 \u043f\u0430\u0442\u0442\u0435\u0440\u043d\u044b
3. \u2705 \u0427\u0422\u041e \u0425\u041e\u0420\u041e\u0428\u041e (1-2 \u043f\u0443\u043d\u043a\u0442\u0430) - \u043f\u043e\u0437\u0438\u0442\u0438\u0432\u043d\u044b\u0435 \u0442\u0435\u043d\u0434\u0435\u043d\u0446\u0438\u0438
4. \U0001f4a1 \u0420\u0415\u041a\u041e\u041c\u0415\u041d\u0414\u0410\u0426\u0418\u0418 \u041d\u0410 \u0421\u0415\u0413\u041e\u0414\u041d\u042f (2-3 \u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u044b\u0445 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f)
5. \U0001f4ca \u0422\u0420\u0415\u041d\u0414\u042b (\u0435\u0441\u043b\u0438 \u0432\u0438\u0434\u043d\u044b \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u044f \u0437\u0430 \u043f\u0435\u0440\u0438\u043e\u0434)

\u0424\u043e\u0440\u043c\u0430\u0442 \u043e\u0442\u0432\u0435\u0442\u0430 - \u043a\u0440\u0430\u0442\u043a\u0438\u0439, \u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u044b\u0439, \u043d\u0430 \u0440\u0443\u0441\u0441\u043a\u043e\u043c. \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 \u044d\u043c\u043e\u0434\u0437\u0438 \u0434\u043b\u044f \u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u044b.
\u0424\u043e\u043a\u0443\u0441 \u043d\u0430 \u0414\u0415\u0419\u0421\u0422\u0412\u0418\u042f\u0425, \u043a\u043e\u0442\u043e\u0440\u044b\u0435 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c \u043c\u043e\u0436\u0435\u0442 \u043f\u0440\u0435\u0434\u043f\u0440\u0438\u043d\u044f\u0442\u044c \u0421\u0415\u0413\u041e\u0414\u041d\u042f.
"""
        return prompt
