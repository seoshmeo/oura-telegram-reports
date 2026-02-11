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

def run_daily_report():
    """Run daily report"""
    logger.info("Running daily report...")
    try:
        result = subprocess.run(
            ['python', '/app/oura_telegram_daily.py'],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            logger.info("Daily report completed successfully")
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

    # Schedule daily report
    daily_time = f"{daily_hour:02d}:{daily_minute:02d}"
    schedule.every().day.at(daily_time).do(run_daily_report)
    logger.info(f"Scheduled daily report at {daily_time}")

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
