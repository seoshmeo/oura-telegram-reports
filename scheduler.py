#!/usr/bin/env python3
"""
Oura Telegram Reports Scheduler
Runs daily, weekly, and monthly reports on schedule
"""

import schedule
import time
import subprocess
import os
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/scheduler.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def check_if_sleep_completed():
    """Check if sleep is completed by running check function"""
    try:
        result = subprocess.run(
            ['python', '-c',
             'from oura_telegram_daily import check_sleep_completed; '
             'completed, end_time, minutes = check_sleep_completed(30); '
             'print(f"{completed}|{end_time}|{minutes}")'],
            capture_output=True,
            text=True,
            timeout=30,
            cwd='/app'
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            parts = output.split('|')
            is_completed = parts[0] == 'True'
            end_time = parts[1] if len(parts) > 1 and parts[1] != 'None' else None
            minutes = float(parts[2]) if len(parts) > 2 and parts[2] != 'None' else None
            return is_completed, end_time, minutes
        return True, None, None  # В случае ошибки считаем что сон завершён
    except Exception as e:
        logger.error(f"Error checking sleep completion: {e}")
        return True, None, None

# Track if daily report was already sent today
last_daily_report_date = None

def run_daily_report():
    """Run daily report with smart sleep completion check"""
    global last_daily_report_date

    current_date = datetime.now().date()

    # Если отчёт уже был отправлен сегодня, пропускаем
    if last_daily_report_date == current_date:
        logger.info("Daily report already sent today, skipping")
        return

    logger.info("Checking if sleep is completed...")
    is_completed, end_time, minutes_since = check_if_sleep_completed()

    if not is_completed:
        logger.info(f"Sleep not yet completed (ended at {end_time}, {minutes_since:.0f} min ago). Will retry later.")
        return

    logger.info(f"Sleep completed (ended at {end_time}, {minutes_since:.0f} min ago). Running daily report...")

    try:
        result = subprocess.run(
            ['python', '/app/oura_telegram_daily.py'],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            logger.info("Daily report completed successfully")
            last_daily_report_date = current_date  # Отмечаем что отчёт отправлен
        else:
            logger.error(f"Daily report failed: {result.stderr}")
    except Exception as e:
        logger.error(f"Error running daily report: {e}")

def force_daily_report():
    """Force send daily report regardless of sleep status (final attempt)"""
    global last_daily_report_date

    current_date = datetime.now().date()

    if last_daily_report_date == current_date:
        logger.info("Daily report already sent today, skipping forced run")
        return

    logger.info("Forcing daily report (final attempt at 10:30)...")
    try:
        result = subprocess.run(
            ['python', '/app/oura_telegram_daily.py'],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            logger.info("Daily report completed successfully (forced)")
            last_daily_report_date = current_date
        else:
            logger.error(f"Daily report failed: {result.stderr}")
    except Exception as e:
        logger.error(f"Error running daily report: {e}")

def run_weekly_report():
    """Run weekly report"""
    logger.info("Running weekly report...")
    try:
        result = subprocess.run(
            ['python', '/app/oura_telegram_weekly.py', 'weekly'],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            logger.info("Weekly report completed successfully")
        else:
            logger.error(f"Weekly report failed: {result.stderr}")
    except Exception as e:
        logger.error(f"Error running weekly report: {e}")

def run_monthly_report():
    """Run monthly report"""
    logger.info("Running monthly report...")
    try:
        result = subprocess.run(
            ['python', '/app/oura_telegram_weekly.py', 'monthly'],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            logger.info("Monthly report completed successfully")
        else:
            logger.error(f"Monthly report failed: {result.stderr}")
    except Exception as e:
        logger.error(f"Error running monthly report: {e}")

def main():
    """Main scheduler function"""
    logger.info("Starting Oura Telegram Reports Scheduler")

    # Get schedule configuration from environment
    daily_hour = int(os.getenv('DAILY_REPORT_HOUR', '7'))
    daily_minute = int(os.getenv('DAILY_REPORT_MINUTE', '30'))
    weekly_hour = int(os.getenv('WEEKLY_REPORT_HOUR', '20'))
    monthly_day = int(os.getenv('MONTHLY_REPORT_DAY', '1'))
    monthly_hour = int(os.getenv('MONTHLY_REPORT_HOUR', '20'))

    # Schedule daily report with smart retry logic
    # Первая попытка в настроенное время (обычно 7:30)
    daily_time = f"{daily_hour:02d}:{daily_minute:02d}"
    schedule.every().day.at(daily_time).do(run_daily_report)
    logger.info(f"Scheduled daily report (attempt 1) at {daily_time}")

    # Дополнительные попытки каждые 30 минут: 8:00, 8:30, 9:00, 9:30, 10:00
    retry_times = ["08:00", "08:30", "09:00", "09:30", "10:00"]
    for retry_time in retry_times:
        schedule.every().day.at(retry_time).do(run_daily_report)
        logger.info(f"Scheduled daily report retry at {retry_time}")

    # Финальная попытка в 10:30 - отправляем в любом случае
    schedule.every().day.at("10:30").do(force_daily_report)
    logger.info(f"Scheduled forced daily report (final attempt) at 10:30")

    # Schedule weekly report (Sunday)
    weekly_time = f"{weekly_hour:02d}:00"
    schedule.every().sunday.at(weekly_time).do(run_weekly_report)
    logger.info(f"Scheduled weekly report on Sundays at {weekly_time}")

    # Schedule monthly report (1st of month)
    # For monthly, we'll check daily at the specified hour
    def check_and_run_monthly():
        if datetime.now().day == monthly_day:
            run_monthly_report()

    monthly_time = f"{monthly_hour:02d}:00"
    schedule.every().day.at(monthly_time).do(check_and_run_monthly)
    logger.info(f"Scheduled monthly report on day {monthly_day} at {monthly_time}")

    # Run the scheduler
    logger.info("Scheduler is running. Press Ctrl+C to exit.")

    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
            break
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
