#!/bin/bash
# Quick deployment script for Oura Telegram Reports
# Usage: curl -fsSL https://raw.githubusercontent.com/seoshmeo/oura-telegram-reports/master/quick-deploy.sh | bash

set -e

echo "╔═══════════════════════════════════════════════════════╗"
echo "║   🏃 Oura Telegram Reports - Quick Deploy            ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "❌ This script should NOT be run as root"
   echo "Run as regular user: curl -fsSL ... | bash"
   exit 1
fi

# Step 1: Check/Install Docker
echo "📦 Step 1/5: Checking Docker..."
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo "✅ Docker installed"
    echo "⚠️  Note: You may need to log out and back in for Docker group changes"
else
    echo "✅ Docker already installed"
fi

# Step 2: Check/Install Docker Compose
echo ""
echo "📦 Step 2/5: Checking Docker Compose..."
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null 2>&1; then
    echo "Installing Docker Compose..."
    sudo apt-get update
    sudo apt-get install -y docker-compose-plugin
    echo "✅ Docker Compose installed"
else
    echo "✅ Docker Compose already installed"
fi

# Step 3: Clone repository
echo ""
echo "📥 Step 3/5: Cloning repository..."
cd ~
if [ -d "oura-telegram-reports" ]; then
    echo "Directory exists, updating..."
    cd oura-telegram-reports
    git pull
else
    git clone https://github.com/seoshmeo/oura-telegram-reports.git
    cd oura-telegram-reports
fi
echo "✅ Repository ready"

# Step 4: Configure .env
echo ""
echo "🔧 Step 4/5: Configuration..."
if [ ! -f .env ]; then
    cp .env.example .env

    echo ""
    echo "Please provide your credentials:"
    echo "────────────────────────────────────────────────"

    # Oura Token
    echo ""
    echo "1️⃣  OURA TOKEN"
    echo "Get it from: https://cloud.ouraring.com/personal-access-tokens"
    read -p "Enter Oura Token: " OURA_TOKEN
    sed -i "s/OURA_TOKEN=.*/OURA_TOKEN=$OURA_TOKEN/" .env

    # Telegram Bot Token
    echo ""
    echo "2️⃣  TELEGRAM BOT TOKEN"
    echo "Get it from @BotFather in Telegram:"
    echo "  1. Open Telegram -> @BotFather"
    echo "  2. Send: /newbot"
    echo "  3. Follow instructions"
    read -p "Enter Telegram Bot Token: " TELEGRAM_BOT_TOKEN
    sed -i "s/TELEGRAM_BOT_TOKEN=.*/TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN/" .env

    # Telegram Chat ID
    echo ""
    echo "3️⃣  TELEGRAM CHAT ID"
    echo "Get it by:"
    echo "  1. Send /start to your bot"
    echo "  2. Visit: https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates"
    echo "  3. Find 'id' in 'chat' section"
    read -p "Enter Telegram Chat ID: " TELEGRAM_CHAT_ID
    sed -i "s/TELEGRAM_CHAT_ID=.*/TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID/" .env

    # Schedule
    echo ""
    echo "4️⃣  SCHEDULE (optional, press Enter for defaults)"
    read -p "Daily report hour (0-23, default 7): " DAILY_HOUR
    DAILY_HOUR=${DAILY_HOUR:-7}
    read -p "Daily report minute (0-59, default 30): " DAILY_MINUTE
    DAILY_MINUTE=${DAILY_MINUTE:-30}

    sed -i "s/DAILY_REPORT_HOUR=.*/DAILY_REPORT_HOUR=$DAILY_HOUR/" .env
    sed -i "s/DAILY_REPORT_MINUTE=.*/DAILY_REPORT_MINUTE=$DAILY_MINUTE/" .env

    chmod 600 .env
    echo "✅ Configuration saved"
else
    echo "⚠️  .env already exists, skipping configuration"
fi

# Step 5: Deploy
echo ""
echo "🚀 Step 5/5: Deploying container..."
docker-compose down 2>/dev/null || true
docker-compose up -d --build

# Wait for container to start
echo "⏳ Waiting for container to start..."
sleep 5

# Check status
echo ""
echo "📊 Container status:"
docker-compose ps

# Test
echo ""
echo "🧪 Testing..."
echo "Sending test report to Telegram..."
docker-compose exec -T oura-reports python oura_telegram_daily.py || echo "⚠️  Test failed, check logs"

# Show logs
echo ""
echo "╔═══════════════════════════════════════════════════════╗"
echo "║   ✅ DEPLOYMENT COMPLETE!                             ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""
echo "📅 Schedule:"
echo "  🌅 Daily:   Every day at $(printf '%02d:%02d' $DAILY_HOUR $DAILY_MINUTE)"
echo "  📊 Weekly:  Sundays at 20:00"
echo "  📈 Monthly: 1st of month at 20:00"
echo ""
echo "🔧 Management commands:"
echo "  cd ~/oura-telegram-reports"
echo "  docker-compose ps       # Status"
echo "  docker-compose logs -f  # View logs"
echo "  docker-compose restart  # Restart"
echo "  docker-compose down     # Stop"
echo ""
echo "📝 Check if you received test message in Telegram!"
echo ""
echo "📖 Full docs: ~/oura-telegram-reports/SERVER_DEPLOY.md"
echo ""
echo "Viewing logs (Ctrl+C to exit)..."
docker-compose logs -f
