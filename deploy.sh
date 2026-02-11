#!/bin/bash
# Deployment script for Oura Telegram Reports

set -e

echo "🚀 Deploying Oura Telegram Reports"
echo "=================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo ""
    echo "Please create .env file from .env.example:"
    echo "  cp .env.example .env"
    echo "  nano .env  # Add your tokens"
    echo ""
    exit 1
fi

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found!"
    echo ""
    echo "Install Docker:"
    echo "  curl -fsSL https://get.docker.com -o get-docker.sh"
    echo "  sudo sh get-docker.sh"
    echo ""
    exit 1
fi

# Check Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose not found!"
    echo ""
    echo "Install Docker Compose:"
    echo "  sudo apt-get install docker-compose-plugin"
    echo ""
    exit 1
fi

echo "✅ Docker is installed"
echo "✅ .env file exists"
echo ""

# Stop existing container
echo "🛑 Stopping existing container..."
docker-compose down 2>/dev/null || true

# Build and start
echo "🔨 Building Docker image..."
docker-compose build

echo "▶️  Starting container..."
docker-compose up -d

# Wait a bit
sleep 3

# Check status
echo ""
echo "📊 Container status:"
docker-compose ps

echo ""
echo "📝 Viewing logs (Ctrl+C to exit):"
echo "=================================="
docker-compose logs -f
