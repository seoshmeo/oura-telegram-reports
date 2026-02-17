FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application package
COPY bot/ bot/

# Create directories for logs and data
RUN mkdir -p /app/logs /app/data

# Set timezone
ENV TZ=Europe/Nicosia
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Run the bot
CMD ["python", "-u", "-m", "bot.main"]
