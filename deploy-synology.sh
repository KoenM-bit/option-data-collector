#!/bin/bash

# Quick deployment script for Synology with fallback options
# This script should be run from the project root directory on your Synology

set -e  # Exit on any error

echo "🚀 Starting Synology deployment..."

# Check for network issues and offer minimal build option
if [ "$1" = "--minimal" ]; then
    echo "🔧 Using minimal build (no system packages) for network compatibility"
    COMPOSE_FILE="docker/docker-compose.synology.yml"
else
    echo "📦 Using standard build (use --minimal if network issues occur)"
    COMPOSE_FILE="docker/docker-compose.prod.yml"
fi

# Check if we're in the right directory
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "❌ Error: $COMPOSE_FILE not found"
    echo "Please run this script from the project root directory"
    exit 1
fi

# Pull latest code
echo "📥 Pulling latest code from GitHub..."
git fetch origin main
git pull origin main

# Stop existing containers
echo "🛑 Stopping existing containers..."
sudo docker-compose -f $COMPOSE_FILE down || true

# Clean up old images (optional)
echo "🧹 Cleaning up old Docker images..."
sudo docker system prune -f

# Build and start containers
echo "🔨 Building and starting containers..."
echo "📝 Using compose file: $COMPOSE_FILE"
sudo docker-compose -f $COMPOSE_FILE build --no-cache
sudo docker-compose -f $COMPOSE_FILE up -d

# Wait for services to start
echo "⏳ Waiting for services to initialize..."
sleep 20

# Check container status
echo "📊 Container status:"
sudo docker-compose -f $COMPOSE_FILE ps

echo ""
echo "🎉 Deployment complete!"
echo ""
echo "📋 Useful commands:"
echo "  View logs: sudo docker-compose -f $COMPOSE_FILE logs -f"
echo "  Check status: sudo docker-compose -f $COMPOSE_FILE ps"
echo "  Stop services: sudo docker-compose -f $COMPOSE_FILE down"
echo "  Restart service: sudo docker-compose -f $COMPOSE_FILE restart [service-name]"
echo ""

# Test basic connectivity
echo "🔍 Testing basic connectivity..."
if sudo docker-compose -f $COMPOSE_FILE exec -T option-api python -c "import requests; print('✅ Python imports working')" 2>/dev/null; then
    echo "✅ Services appear to be working"
else
    echo "⚠️  Services may still be starting up - check logs if issues persist"
fi