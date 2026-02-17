"""
Event parser: regex for common events + Claude fallback.
"""

import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Regex patterns for common events (Russian + English)
EVENT_PATTERNS = [
    # Coffee
    (r'(?i)(кофе|coffee|капучино|латте|эспрессо|americano|американо)',
     'coffee', '\u2615', ['sleep_score', 'average_hrv', 'sleep_latency', 'resting_hr']),

    # Alcohol
    (r'(?i)(алкоголь|alcohol|пиво|вино|beer|wine|виски|водка|коктейль|выпил[аи]?)',
     'alcohol', '\U0001f37a', ['sleep_score', 'average_hrv', 'deep_sleep_duration', 'resting_hr', 'readiness_score']),

    # Hookah
    (r'(?i)(кальян|hookah|shisha)',
     'hookah', '\U0001f4a8', ['sleep_score', 'average_hrv', 'resting_hr', 'spo2']),

    # Walk
    (r'(?i)(прогулк[аи]|walk|гулял[аи]?|погулял[аи]?)',
     'walk', '\U0001f6b6', ['readiness_score', 'steps', 'stress_high']),

    # Workout
    (r'(?i)(тренировк[аи]|workout|gym|зал|бег|пробежк[аи]|run|плавани[ея]|swim)',
     'workout', '\U0001f3cb\ufe0f', ['readiness_score', 'average_hrv', 'deep_sleep_duration', 'sleep_score']),

    # Stress
    (r'(?i)(стресс|stress|нервнича[юл]|переживани[ея]|тревог[аи])',
     'stress', '\U0001f624', ['sleep_score', 'average_hrv', 'resting_hr', 'stress_high']),

    # Late meal
    (r'(?i)(поздн(яя|ий|ее) (еда|ужин|перекус)|late\s*(meal|dinner|snack)|поел[аи]?\s+поздно|ужин\s+после)',
     'late_meal', '\U0001f374', ['sleep_score', 'sleep_latency', 'deep_sleep_duration']),

    # Lisinopril (blood pressure medication)
    (r'(?i)(лизиноприл|lisinopril)',
     'med_lisinopril', '\U0001f48a', ['resting_hr', 'average_hrv', 'readiness_score', 'sleep_score']),

    # Glucophage / Metformin (blood sugar medication)
    (r'(?i)(глюкофаж|метформин|glucophage|metformin)',
     'med_glucophage', '\U0001f48a', ['sleep_score', 'readiness_score', 'average_hrv', 'stress_high']),

    # Supplement
    (r'(?i)(добавк[аи]|supplement|витамин|магний|мелатонин|глицин|omega|омега)',
     'supplement', '\U0001f48a', ['sleep_score', 'average_hrv', 'deep_sleep_duration']),

    # Meditation
    (r'(?i)(медитаци[яю]|meditation|дыхательн|breathwork)',
     'meditation', '\U0001f9d8', ['stress_high', 'average_hrv', 'resting_hr']),

    # Nap
    (r'(?i)(дневной\s*сон|nap|поспал|вздремнул|подремал)',
     'nap', '\U0001f634', ['readiness_score', 'stress_high']),

    # Cold shower
    (r'(?i)(холодный\s*душ|cold\s*shower|закаливани[ея]|контрастный)',
     'cold_shower', '\U0001f9ca', ['average_hrv', 'resting_hr', 'readiness_score']),

    # Sauna
    (r'(?i)(сауна|sauna|баня|парилк[аи])',
     'sauna', '\U0001f9d6', ['average_hrv', 'resting_hr', 'deep_sleep_duration', 'sleep_score']),

    # Travel
    (r'(?i)(перелет|путешестви[ея]|travel|flight|поездк[аи]|дорог[аи])',
     'travel', '\u2708\ufe0f', ['sleep_score', 'readiness_score', 'stress_high']),

    # Illness
    (r'(?i)(болезнь|illness|sick|заболел|простуд|температура|болит)',
     'illness', '\U0001f912', ['readiness_score', 'sleep_score', 'resting_hr', 'temperature_deviation']),

    # Party
    (r'(?i)(вечеринк[аи]|party|тусовк[аи]|клуб)',
     'party', '\U0001f389', ['sleep_score', 'readiness_score', 'average_hrv']),

    # Blood pressure
    (r'(?i)(давлени[ея]|blood\s*pressure|АД|ад|bp)\s*[:=]?\s*\d',
     'blood_pressure', '\U0001fa78', ['resting_hr', 'average_hrv', 'stress_high', 'readiness_score']),

    # Blood sugar / glucose
    (r'(?i)(сахар|глюкоз[аы]|glucose|sugar|blood\s*sugar)\s*[:=]?\s*\d',
     'blood_sugar', '\U0001fa78', ['sleep_score', 'readiness_score', 'stress_high', 'average_hrv']),
]


def parse_event(text: str) -> dict | None:
    """
    Parse event from user text using regex patterns.

    Returns:
        dict with event_type, emoji, details, metrics_to_correlate
        or None if no match
    """
    text = text.strip()

    for pattern, event_type, emoji, metrics in EVENT_PATTERNS:
        if re.search(pattern, text):
            # Extract time if mentioned
            time_match = re.search(r'(\d{1,2})[:\.](\d{2})', text)
            event_time = None
            if time_match:
                try:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2))
                    now = datetime.now()
                    event_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                except ValueError:
                    pass

            # Extract quantity if mentioned
            qty_match = re.search(r'(\d+)\s*(чашк|стакан|бокал|рюмк|порци|cup|glass|shot)', text, re.IGNORECASE)
            quantity = int(qty_match.group(1)) if qty_match else None

            details = {}
            if event_time:
                details['time'] = event_time.strftime('%H:%M')
            if quantity:
                details['quantity'] = quantity

            # Extract dosage for medications (e.g., "лизиноприл 10мг", "глюкофаж 500")
            if event_type.startswith('med_'):
                dose_match = re.search(r'(\d+)\s*(мг|mg|г|g)?', text)
                if dose_match:
                    dose_val = int(dose_match.group(1))
                    dose_unit = dose_match.group(2) or 'мг'
                    # Sanity check: typical dosages are 1-2000mg
                    if 1 <= dose_val <= 2000:
                        details['dosage'] = dose_val
                        details['dosage_unit'] = dose_unit

            # Extract blood pressure values (e.g., "120/80", "120 на 80")
            if event_type == 'blood_pressure':
                bp_match = re.search(r'(\d{2,3})\s*[/\\на]+\s*(\d{2,3})', text)
                if bp_match:
                    details['systolic'] = int(bp_match.group(1))
                    details['diastolic'] = int(bp_match.group(2))
                # Also check for pulse in bp message (e.g., "120/80 пульс 75")
                pulse_match = re.search(r'(?i)(?:пульс|pulse|чсс|hr)\s*(\d{2,3})', text)
                if pulse_match:
                    details['pulse'] = int(pulse_match.group(1))

            # Extract blood sugar value (e.g., "сахар 5.6", "глюкоза 6.2")
            if event_type == 'blood_sugar':
                sugar_match = re.search(r'(?i)(?:сахар|глюкоз[аы]?|glucose|sugar|blood\s*sugar)\s*[:=]?\s*(\d+[.,]\d+|\d+)', text)
                if sugar_match:
                    details['glucose'] = float(sugar_match.group(1).replace(',', '.'))

            return {
                'event_type': event_type,
                'emoji': emoji,
                'details': details,
                'metrics_to_correlate': metrics,
                'raw_text': text,
            }

    return None


def get_event_emoji(event_type: str) -> str:
    """Get emoji for an event type."""
    for _, etype, emoji, _ in EVENT_PATTERNS:
        if etype == event_type:
            return emoji
    return '\U0001f4cc'
