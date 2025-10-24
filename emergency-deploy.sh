#!/bin/bash

# Emergency deployment with DNS fixes for Synology Docker issues  
echo "🚨 Emergency deployment with DNS fixes for Synology"

# Check for deployment option
if [ "$1" = "--dns-fix" ]; then
    echo "🌐 Using DNS-fix approach (hardcoded PyPI IPs)"
    COMPOSE_FILE="docker/docker-compose.dns-fix.yml"
elif [ "$1" = "--offline" ]; then
    echo "📦 Using offline approach (no network during build)"
    COMPOSE_FILE="docker/docker-compose.offline.yml"
elif [ "$1" = "--portainer" ]; then
    echo "🐳 Using Portainer-optimized configuration"
    COMPOSE_FILE="docker/docker-compose.portainer.yml"
    echo "💡 After this build, you can manage via Portainer Web UI"
else
    echo "🔧 Using minimal approach (no system packages)"
    COMPOSE_FILE="docker/docker-compose.synology.yml"
fi

cd /volume1/docker/option-data-collector || { echo "❌ Wrong directory"; exit 1; }

echo "📥 Pulling latest code..."
git pull origin main

echo "🛑 Stopping any running containers..."
sudo docker-compose -f docker/docker-compose.prod.yml down 2>/dev/null || true
sudo docker-compose -f docker/docker-compose.synology.yml down 2>/dev/null || true
sudo docker-compose -f docker/docker-compose.dns-fix.yml down 2>/dev/null || true
sudo docker-compose -f docker/docker-compose.offline.yml down 2>/dev/null || true

echo "🧹 Cleaning up..."
sudo docker system prune -f

echo "🔨 Building with configuration: $COMPOSE_FILE"
sudo docker-compose -f $COMPOSE_FILE build --no-cache

echo "🚀 Starting services..."
sudo docker-compose -f $COMPOSE_FILE up -d

echo "⏳ Waiting for startup..."
sleep 20

echo "📊 Status:"
sudo docker-compose -f $COMPOSE_FILE ps

echo "✅ Deployment complete!"
echo "🔍 Check logs with: sudo docker-compose -f $COMPOSE_FILE logs -f"
echo ""
echo "💡 If this approach failed, try:"
echo "  ./emergency-deploy.sh --dns-fix     (hardcoded PyPI IPs)"
echo "  ./emergency-deploy.sh --portainer   (Portainer-optimized)"
echo "  ./emergency-deploy.sh --offline     (no network during build)"
echo ""
echo "🐳 For Portainer users: After successful build, manage containers via Portainer UI"