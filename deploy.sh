# UrbanAI - Quick Deploy Script for Linux
# Run this on your server to deploy

#!/bin/bash
set -e

echo "🚀 UrbanAI Quick Deploy"
echo "======================"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not installed. Installing..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo "✅ Docker installed. Please logout and login again, then re-run this script."
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y docker-compose-plugin
fi

# Create .env if not exists
if [ ! -f .env ]; then
    echo "📝 Creating .env from example..."
    cp .env.example .env
    
    # Generate random secret key
    SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))" 2>/dev/null || openssl rand -base64 50)
    sed -i "s/your-super-secret-key-change-me-in-production-use-long-random-string/$SECRET/" .env
    
    echo "⚠️  Please edit .env and set your ALLOWED_HOSTS and GEMINI_API_KEY"
    echo "    nano .env"
    exit 0
fi

# Build and start
echo "🐳 Building Docker image..."
docker-compose build

echo "🚀 Starting container..."
docker-compose up -d

echo ""
echo "✅ UrbanAI deployed!"
echo "📍 URL: http://$(hostname -I | awk '{print $1}'):8001/"
echo ""
echo "Useful commands:"
echo "  docker-compose logs -f    # View logs"
echo "  docker-compose restart    # Restart"
echo "  docker-compose down       # Stop"
