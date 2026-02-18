"""
AI chat: answer health questions using user's data as context.
"""

import logging
import re
from datetime import datetime, timedelta

from anthropic import AsyncAnthropic

from bot.config import CLAUDE_API_KEY
from bot.core.database import fetchall, fetchone

logger = logging.getLogger(__name__)

# --- Question detection ---

_QUESTION_WORDS = re.compile(
    r'(?:как|что|какой|какая|какое|какие|каков|сколько|почему|зачем|когда|где|'
    r'думаешь|считаешь|можешь|'
    r'расскажи|покажи|сравни|подскажи|объясни|проанализируй|оцени|посоветуй)',
    re.IGNORECASE,
)

_HEALTH_WORDS = re.compile(
    r'(?:сон|сна|сну|снов|спать|спал|sleep|hrv|давлен|пульс|кофе|'
    r'стресс|алкогол|кальян|тренировк|шаг|активност|готовност|readiness|'
    r'глубок|rem|засып|бессонн|восстановл|калор|температур|'
    r'сахар|глюкоз|метформин|глюкофаж|лизиноприл|гипертон|'
    r'вес|здоров|самочувств|энерги|усталост|утомл|'
    r'привычк|серия|streak|корреляц|влия|связ|зависи|'
    r'тренд|динамик|погод|норм|средн|будн|выходн|'
    r'данн|метрик|oura|отчёт|отчет|анализ|показател)',
    re.IGNORECASE,
)

_IMPERATIVE_START = re.compile(
    r'^(?:расскажи|покажи|объясни|проанализируй|оцени|сравни|подскажи|посоветуй|посмотри)\b',
    re.IGNORECASE,
)


def is_health_question(text: str) -> bool:
    """Light filter: is this text likely a health question (not a command/event)?"""
    if len(text) < 8:
        return False

    # Ends with ? — very likely a question
    if text.rstrip().endswith('?'):
        return True

    # Starts with imperative health-related verb
    if _IMPERATIVE_START.search(text):
        return True

    # Contains question word + health word
    if _QUESTION_WORDS.search(text) and _HEALTH_WORDS.search(text):
        return True

    # Long text that wasn't parsed as event — likely a free-form question
    if len(text) > 25 and _QUESTION_WORDS.search(text):
        return True

    return False


# --- Context gathering ---

def _gather_context(question: str) -> str:
    """Build compact data context from DB based on question keywords."""
    q = question.lower()
    blocks = []

    # Always: last 7 days of daily_metrics
    blocks.append(_format_recent_metrics())

    # Always: today's events (with details)
    blocks.append(_format_today_events())

    # Always: measurements (BP, sugar, weight) — Claude needs actual values
    blocks.append(_format_bp_context())
    blocks.append(_format_sugar_context())
    blocks.append(_format_weight_context())

    # Conditional blocks based on keywords
    if _kw(q, 'влия', 'корреляц', 'связ', 'зависи', 'кофе', 'алкогол', 'кальян', 'тренировк', 'стресс'):
        blocks.append(_format_correlations())

    if _kw(q, 'сон', 'спать', 'спал', 'глубок', 'rem', 'засып', 'бессонн', 'sleep'):
        blocks.append(_format_sleep_detail())

    if _kw(q, 'будн', 'выходн'):
        blocks.append(_format_weekday_weekend())

    if _kw(q, 'привычк', 'серия', 'streak'):
        blocks.append(_format_streaks())

    if _kw(q, 'норм', 'средн', 'обычн', 'персональн'):
        blocks.append(_format_percentiles())

    if _kw(q, 'погод', 'температур', 'влажн'):
        blocks.append(_format_weather())

    if _kw(q, 'тренд', 'динамик', 'за месяц'):
        blocks.append(_format_trends())

    if _kw(q, 'сколько раз', 'как часто'):
        blocks.append(_format_event_frequency())

    return '\n'.join(b for b in blocks if b)


def _kw(q: str, *keywords: str) -> bool:
    """Check if any keyword substring is found in question."""
    return any(k in q for k in keywords)


# --- Claude API call ---

async def answer_health_question(question: str) -> str | None:
    """Call Claude with user data context to answer a health question."""
    if not CLAUDE_API_KEY:
        return None

    context = _gather_context(question)
    if not context.strip():
        return None

    system_prompt = (
        "Ты — персональный health-аналитик пользователя. "
        "Данные с Oura Ring, давление, сахар, события.\n\n"
        "ПРАВИЛА:\n"
        "- Отвечай ТОЛЬКО на основе предоставленных данных. Не выдумывай цифры.\n"
        "- Если данных недостаточно — скажи прямо.\n"
        "- Кратко и конкретно (до 15 предложений).\n"
        "- Эмодзи для структуры. Язык: русский. Plain text (без HTML/markdown).\n"
        "- Рекомендации на основе данных пользователя, не общие советы.\n"
        "- Не давай медицинских диагнозов — ты аналитик данных, не врач.\n"
        "- Указывай конкретные числа и тренды.\n\n"
        f"ДАННЫЕ ПОЛЬЗОВАТЕЛЯ:\n{context}"
    )

    try:
        client = AsyncAnthropic(api_key=CLAUDE_API_KEY)
        response = await client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1500,
            temperature=0.5,
            system=system_prompt,
            messages=[{"role": "user", "content": question}],
        )
        answer = response.content[0].text.strip()
        # Telegram message limit is 4096 chars
        if len(answer) > 3900:
            answer = answer[:3900] + '...'
        return answer
    except Exception as e:
        logger.error("AI chat error: %s", e)
        return None


async def answer_alert_followup(alert_context: str, user_response: str) -> str | None:
    """Claude analyzes user's response to a health alert."""
    if not CLAUDE_API_KEY:
        return None

    data_context = _gather_context(user_response)

    system_prompt = (
        "\u0422\u044b \u2014 AI-\u043c\u043e\u043d\u0438\u0442\u043e\u0440\u0438\u043d\u0433 \u0437\u0434\u043e\u0440\u043e\u0432\u044c\u044f. "
        "\u0420\u0430\u043d\u0435\u0435 \u043e\u0431\u043d\u0430\u0440\u0443\u0436\u0438\u043b \u0430\u043d\u043e\u043c\u0430\u043b\u0438\u044e \u0438 \u0441\u043f\u0440\u043e\u0441\u0438\u043b \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f \u043e \u0441\u0430\u043c\u043e\u0447\u0443\u0432\u0441\u0442\u0432\u0438\u0438.\n\n"
        f"\u041a\u041e\u041d\u0422\u0415\u041a\u0421\u0422 \u0410\u041b\u0415\u0420\u0422\u0410:\n{alert_context}\n\n"
        f"\u0414\u0410\u041d\u041d\u042b\u0415 \u041f\u041e\u041b\u042c\u0417\u041e\u0412\u0410\u0422\u0415\u041b\u042f:\n{data_context}\n\n"
        "\u041f\u0420\u0410\u0412\u0418\u041b\u0410:\n"
        "- \u0423\u0447\u0442\u0438 \u043e\u0442\u0432\u0435\u0442 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f + \u0434\u0430\u043d\u043d\u044b\u0435\n"
        "- \u0414\u0430\u0439 \u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u044b\u0435 \u0440\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0430\u0446\u0438\u0438 \u043d\u0430 \u043e\u0441\u043d\u043e\u0432\u0435 \u0432\u0441\u0435\u0439 \u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u0438\n"
        "- \u041d\u0435 \u0434\u0438\u0430\u0433\u043d\u043e\u0437. \u041a\u0440\u0430\u0442\u043a\u043e (\u0434\u043e 10 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0439). \u0420\u0443\u0441\u0441\u043a\u0438\u0439. \u042d\u043c\u043e\u0434\u0437\u0438. Plain text (\u0431\u0435\u0437 HTML).\n"
    )

    try:
        client = AsyncAnthropic(api_key=CLAUDE_API_KEY)
        response = await client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1000,
            temperature=0.5,
            system=system_prompt,
            messages=[{"role": "user", "content": user_response}],
        )
        answer = response.content[0].text.strip()
        if len(answer) > 3900:
            answer = answer[:3900] + '...'
        return answer
    except Exception as e:
        logger.error("Alert followup error: %s", e)
        return None


# --- Formatters ---

def _format_recent_metrics() -> str:
    """Last 7 days of daily_metrics."""
    rows = fetchall(
        "SELECT * FROM daily_metrics ORDER BY day DESC LIMIT 7"
    )
    if not rows:
        return ""

    lines = ["МЕТРИКИ ЗА 7 ДНЕЙ:"]
    for r in reversed(rows):
        sleep_h = r['total_sleep_duration'] / 3600 if r['total_sleep_duration'] else 0
        deep_h = r['deep_sleep_duration'] / 3600 if r['deep_sleep_duration'] else 0
        rem_h = r['rem_sleep_duration'] / 3600 if r['rem_sleep_duration'] else 0
        stress_min = r['stress_high'] / 60 if r['stress_high'] else 0
        lines.append(
            f"{r['day']}: сон={r['sleep_score']} готовн={r['readiness_score']} "
            f"HRV={r['average_hrv']}мс пульс={r['lowest_heart_rate']}bpm "
            f"сон={sleep_h:.1f}ч(deep={deep_h:.1f} rem={rem_h:.1f}) "
            f"шаги={r['steps']} стресс={stress_min:.0f}мин"
        )
    return '\n'.join(lines)


def _format_today_events() -> str:
    """Today's events with details."""
    from bot.events.tracker import get_today_events
    import json as _json
    events = get_today_events()
    if not events:
        return ""

    lines = ["СОБЫТИЯ СЕГОДНЯ:"]
    for ev in events:
        ts = datetime.fromisoformat(ev['timestamp']).strftime('%H:%M')
        line = f"  {ts} — {ev['event_type']}"

        # Add details (dosage, values, etc.)
        details = {}
        try:
            details = _json.loads(ev.get('details', '{}'))
        except Exception:
            pass

        detail_parts = []
        if details.get('dosage'):
            unit = details.get('dosage_unit', 'мг')
            detail_parts.append(f"{details['dosage']}{unit}")
        if details.get('systolic') and details.get('diastolic'):
            bp_str = f"{details['systolic']}/{details['diastolic']}"
            if details.get('pulse'):
                bp_str += f" пульс {details['pulse']}"
            detail_parts.append(bp_str)
        if details.get('glucose'):
            detail_parts.append(f"{details['glucose']} ммоль/л")
        if details.get('weight_kg'):
            detail_parts.append(f"{details['weight_kg']} кг")
        if details.get('quantity'):
            detail_parts.append(f"x{details['quantity']}")

        if detail_parts:
            line += f" ({', '.join(detail_parts)})"
        elif ev.get('raw_text') and ev['raw_text'] != ev['event_type']:
            # Show raw text if no structured details
            raw = ev['raw_text'][:60]
            line += f" «{raw}»"

        lines.append(line)
    return '\n'.join(lines)


def _format_correlations() -> str:
    """Top correlations from DB."""
    rows = fetchall(
        """SELECT event_type, metric_name, delta_pct, count_with
           FROM correlations
           WHERE time_bucket = 'all' AND confidence >= 0.1 AND count_with >= 3
           ORDER BY ABS(delta_pct) DESC LIMIT 15"""
    )
    if not rows:
        return ""

    lines = ["КОРРЕЛЯЦИИ СОБЫТИЙ И МЕТРИК:"]
    for r in rows:
        sign = "+" if r['delta_pct'] > 0 else ""
        lines.append(
            f"  {r['event_type']} -> {r['metric_name']}: {sign}{r['delta_pct']:.1f}% ({r['count_with']} дней)"
        )
    return '\n'.join(lines)


def _format_bp_context() -> str:
    """Recent blood pressure readings + stats."""
    from bot.events.tracker import get_recent_measurements, get_measurement_stats

    readings = get_recent_measurements('blood_pressure', 7)
    if not readings:
        return ""

    lines = ["ДАВЛЕНИЕ (последние):"]
    for r in readings:
        ts = datetime.fromisoformat(r['timestamp']).strftime('%d.%m %H:%M')
        pulse = ""
        if r.get('note') and r['note'].startswith('pulse:'):
            pulse = f" пульс={r['note'].split(':')[1]}"
        lines.append(f"  {ts}: {r['value1']:.0f}/{r['value2']:.0f}{pulse}")

    stats = get_measurement_stats('blood_pressure', 30)
    if stats and stats['cnt'] >= 3:
        lines.append(
            f"Статистика 30д: ср {stats['avg1']:.0f}/{stats['avg2']:.0f} "
            f"мин {stats['min1']:.0f}/{stats['min2']:.0f} "
            f"макс {stats['max1']:.0f}/{stats['max2']:.0f} (n={stats['cnt']})"
        )
    return '\n'.join(lines)


def _format_sugar_context() -> str:
    """Recent blood sugar readings + stats."""
    from bot.events.tracker import get_recent_measurements, get_measurement_stats

    readings = get_recent_measurements('blood_sugar', 7)
    if not readings:
        return ""

    lines = ["САХАР (последние):"]
    for r in readings:
        ts = datetime.fromisoformat(r['timestamp']).strftime('%d.%m %H:%M')
        lines.append(f"  {ts}: {r['value1']:.1f} ммоль/л")

    stats = get_measurement_stats('blood_sugar', 30)
    if stats and stats['cnt'] >= 3:
        lines.append(
            f"Статистика 30д: ср {stats['avg1']:.1f} "
            f"мин {stats['min1']:.1f} макс {stats['max1']:.1f} (n={stats['cnt']})"
        )
    return '\n'.join(lines)


def _format_weight_context() -> str:
    """Recent weight readings + stats."""
    from bot.events.tracker import get_recent_measurements, get_measurement_stats

    readings = get_recent_measurements('weight', 7)
    if not readings:
        return ""

    lines = ["ВЕС (последние):"]
    for r in readings:
        ts = datetime.fromisoformat(r['timestamp']).strftime('%d.%m %H:%M')
        bmi_str = f" ИМТ={r['value2']:.1f}" if r.get('value2') else ""
        lines.append(f"  {ts}: {r['value1']:.1f} кг{bmi_str}")

    stats = get_measurement_stats('weight', 30)
    if stats and stats['cnt'] >= 3:
        lines.append(
            f"Статистика 30д: ср {stats['avg1']:.1f} кг "
            f"мин {stats['min1']:.1f} макс {stats['max1']:.1f} (n={stats['cnt']})"
        )
    return '\n'.join(lines)


def _format_sleep_detail() -> str:
    """Sleep debt + circadian stability."""
    parts = []

    try:
        from bot.habits.sleep_debt import calculate_sleep_debt
        debt = calculate_sleep_debt()
        if debt:
            parts.append(
                f"ДОЛГ СНА: {debt['debt_hours']:.1f}ч, ср сон={debt['avg_sleep']:.1f}ч, "
                f"погашение ~{debt['days_to_payoff']}д, {debt['label']}"
            )
    except Exception:
        pass

    try:
        from bot.habits.circadian import get_circadian_stability
        circ = get_circadian_stability()
        if circ:
            parts.append(
                f"ЦИРКАДНЫЙ РИТМ: ср отбой={circ['avg_bedtime']}, "
                f"разброс=±{circ['bedtime_stdev_min']:.0f}мин, {circ['label']}"
            )
    except Exception:
        pass

    return '\n'.join(parts)


def _format_weekday_weekend() -> str:
    """Weekday vs weekend comparison."""
    try:
        from bot.analysis.weekday_weekend import get_weekday_weekend_stats
        data = get_weekday_weekend_stats()
        if not data:
            return ""

        lines = ["БУДНИ vs ВЫХОДНЫЕ:"]
        labels = {
            'sleep_score': 'Сон', 'total_sleep_duration': 'Длит.сна(сек)',
            'average_hrv': 'HRV', 'steps': 'Шаги',
        }
        for metric, label in labels.items():
            if metric in data:
                d = data[metric]
                wd = d['weekday']
                we = d['weekend']
                if metric == 'total_sleep_duration':
                    wd /= 3600
                    we /= 3600
                    label = 'Длит.сна(ч)'
                lines.append(f"  {label}: будни={wd:.1f} выходные={we:.1f} ({d['delta_pct']:+.1f}%)")
        return '\n'.join(lines)
    except Exception:
        return ""


def _format_streaks() -> str:
    """Current habit streaks."""
    rows = fetchall("SELECT * FROM habit_streaks ORDER BY habit_name")
    if not rows:
        return ""

    labels = {
        'sleep_7h': 'Сон>=7ч', 'steps_8k': 'Шаги>=8K',
        'bedtime_2300': 'Отбой до 23:00', 'hrv_above_avg': 'HRV>среднего',
    }

    lines = ["СЕРИИ ПРИВЫЧЕК:"]
    for r in rows:
        label = labels.get(r['habit_name'], r['habit_name'])
        lines.append(f"  {label}: текущая={r['current_streak']}д рекорд={r['best_streak']}д")
    return '\n'.join(lines)


def _format_percentiles() -> str:
    """Personal norms (percentiles)."""
    rows = fetchall("SELECT * FROM percentile_cache")
    if not rows:
        return ""

    lines = ["ПЕРСОНАЛЬНЫЕ НОРМЫ (перцентили):"]
    labels = {
        'sleep_score': 'Сон', 'readiness_score': 'Готовность', 'average_hrv': 'HRV(мс)',
        'lowest_heart_rate': 'Мин.пульс', 'steps': 'Шаги',
        'deep_sleep_duration': 'Deep(сек)', 'rem_sleep_duration': 'REM(сек)',
        'stress_high': 'Стресс(мин)',
    }
    for r in rows:
        label = labels.get(r['metric_name'])
        if not label:
            continue
        lines.append(
            f"  {label}: p10={r['p10']:.0f} p25={r['p25']:.0f} p50={r['p50']:.0f} "
            f"p75={r['p75']:.0f} p90={r['p90']:.0f} (n={r['count']})"
        )
    return '\n'.join(lines)


def _format_weather() -> str:
    """Today's weather."""
    try:
        from bot.weather.cache import get_cached_weather
        today = datetime.now().strftime('%Y-%m-%d')
        w = get_cached_weather(today)
        if not w:
            return ""
        return (
            f"ПОГОДА СЕГОДНЯ: {w.get('temp_mean', '?')}°C "
            f"(мин {w.get('temp_min', '?')} макс {w.get('temp_max', '?')}) "
            f"влажность={w.get('humidity_mean', '?')}% "
            f"ветер={w.get('wind_max', '?')}км/ч "
            f"AQI={w.get('aqi', '?')}"
        )
    except Exception:
        return ""


def _format_trends() -> str:
    """30-day trends for key metrics."""
    rows = fetchall(
        "SELECT * FROM daily_metrics ORDER BY day DESC LIMIT 30"
    )
    if len(rows) < 7:
        return ""

    rows_asc = list(reversed(rows))

    def avg_vals(field, subset):
        vals = [r[field] for r in subset if r[field] is not None]
        return sum(vals) / len(vals) if vals else None

    first_week = rows_asc[:7]
    last_week = rows_asc[-7:]

    lines = ["ТРЕНДЫ ЗА МЕСЯЦ (первая неделя -> последняя):"]
    for field, label in [
        ('sleep_score', 'Сон'), ('readiness_score', 'Готовность'),
        ('average_hrv', 'HRV'), ('steps', 'Шаги'),
    ]:
        a1 = avg_vals(field, first_week)
        a2 = avg_vals(field, last_week)
        if a1 is not None and a2 is not None:
            delta = a2 - a1
            sign = "+" if delta > 0 else ""
            lines.append(f"  {label}: {a1:.0f} -> {a2:.0f} ({sign}{delta:.0f})")
    return '\n'.join(lines)


def _format_event_frequency() -> str:
    """Event frequency for the last 30 days."""
    from bot.events.tracker import get_event_counts
    counts = get_event_counts(30)
    if not counts:
        return ""

    lines = ["ЧАСТОТА СОБЫТИЙ (30 дней):"]
    for event_type, cnt in counts.items():
        lines.append(f"  {event_type}: {cnt} раз")
    return '\n'.join(lines)
