#!/bin/bash
echo "🚀 Starting local development environment..."

# Navigate to docker directory
cd "$(dirname "$0")/../docker"

# Start local development services
docker compose -f docker compose.dev.yml up -d mysql-dev

# Wait for MySQL to be ready
echo "⏳ Waiting for MySQL to start..."
sleep 10

# Start all services in development mode
docker compose -f docker compose.dev.yml up

echo "✅ Development environment ready!"
echo "📊 Services running:"
echo "  - Option Scraper: http://localhost:8000"
echo "  - MySQL: localhost:3306"
echo "  - Logs: docker compose -f docker/docker compose.dev.yml logs -f"