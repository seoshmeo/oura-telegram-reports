"""
Central configuration - all environment variables in one place.
"""

import os


# Oura API
OURA_TOKEN = os.environ.get('OURA_TOKEN', '')
OURA_API_BASE_URL = "https://api.ouraring.com/v2"

# Telegram
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

# Claude AI
CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY', '')

# OpenAI (Whisper)
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

# Schedule
DAILY_REPORT_HOUR = int(os.environ.get('DAILY_REPORT_HOUR', '7'))
DAILY_REPORT_MINUTE = int(os.environ.get('DAILY_REPORT_MINUTE', '30'))
WEEKLY_REPORT_HOUR = int(os.environ.get('WEEKLY_REPORT_HOUR', '20'))
MONTHLY_REPORT_DAY = int(os.environ.get('MONTHLY_REPORT_DAY', '1'))
MONTHLY_REPORT_HOUR = int(os.environ.get('MONTHLY_REPORT_HOUR', '20'))

# Weather (Larnaca, Cyprus)
WEATHER_LAT = float(os.environ.get('WEATHER_LAT', '34.92'))
WEATHER_LON = float(os.environ.get('WEATHER_LON', '33.62'))

# Timezone
TZ = os.environ.get('TZ', 'Europe/Nicosia')

# Database
DB_PATH = os.environ.get('DB_PATH', '/app/data/oura_bot.db')

# Paths
DATA_DIR = os.environ.get('DATA_DIR', '/app/data')
LOGS_DIR = os.environ.get('LOGS_DIR', '/app/logs')

# Image compression (food photo)
IMAGE_MAX_SIZE = int(os.environ.get('IMAGE_MAX_SIZE', '1024'))
IMAGE_QUALITY = int(os.environ.get('IMAGE_QUALITY', '80'))

# Alert config
DEDUP_HOURS = int(os.environ.get('DEDUP_HOURS', '12'))
BASELINES_FILE = os.environ.get('BASELINES_FILE', '/app/data/baselines.json')
ALERTS_HISTORY_FILE = os.environ.get('ALERTS_HISTORY_FILE', '/app/data/alerts_history.json')
