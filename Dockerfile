FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY oura_telegram_daily.py .
COPY oura_telegram_weekly.py .
COPY scheduler.py .
COPY claude_analyzer.py .

# Create directory for logs
RUN mkdir -p /app/logs

# Set timezone
ENV TZ=Europe/Kiev
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Run the scheduler
CMD ["python", "-u", "scheduler.py"]
