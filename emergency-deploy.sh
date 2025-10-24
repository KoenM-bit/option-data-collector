#!/bin/bash

# Emergency minimal deployment for Synology (no apt-get, Python only)
echo "🚨 Emergency minimal deployment - skipping all system packages"

cd /volume1/docker/option-data-collector || { echo "❌ Wrong directory"; exit 1; }

echo "📥 Pulling latest code..."
git pull origin main

echo "🛑 Stopping any running containers..."
sudo docker-compose -f docker/docker-compose.prod.yml down 2>/dev/null || true
sudo docker-compose -f docker/docker-compose.synology.yml down 2>/dev/null || true

echo "🧹 Cleaning up..."
sudo docker system prune -f

echo "🔨 Building with minimal configuration (Python packages only)..."
sudo docker-compose -f docker/docker-compose.synology.yml build --no-cache

echo "🚀 Starting services..."
sudo docker-compose -f docker/docker-compose.synology.yml up -d

echo "⏳ Waiting for startup..."
sleep 20

echo "📊 Status:"
sudo docker-compose -f docker/docker-compose.synology.yml ps

echo "✅ Minimal deployment complete!"
echo "🔍 Check logs with: sudo docker-compose -f docker/docker-compose.synology.yml logs -f"