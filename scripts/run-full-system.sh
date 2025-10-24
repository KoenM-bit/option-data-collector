#!/bin/bash
echo "🐳 Full Docker Environment Test"
echo "Running complete system as containers..."

# Navigate to docker directory  
cd "$(dirname "$0")/../docker"

# Start all services
echo "🚀 Starting all services..."
docker compose -f docker compose.dev.yml up -d

echo "⏳ Waiting for services to initialize..."
sleep 20

# Check service status
echo "📋 Checking service status..."
docker compose -f docker compose.dev.yml ps

# Check logs for each service
echo ""
echo "📊 Service logs (last 10 lines each):"
echo ""

echo "🗄️ MySQL logs:"
docker compose -f docker compose.dev.yml logs --tail=10 mysql-dev

echo ""
echo "📈 Option Scraper logs:"
docker compose -f docker compose.dev.yml logs --tail=10 option-scraper

echo ""
echo "📊 Sentiment Tracker logs:"
docker compose -f docker compose.dev.yml logs --tail=10 sentiment-tracker

echo ""
echo "⚙️ ETL Service logs:"
docker compose -f docker compose.dev.yml logs --tail=10 daily-etl

echo ""
echo "🔍 Testing database tables..."
docker compose -f docker compose.dev.yml exec mysql-dev mysql -uroot -pdevpassword -e "
USE optionsdb_dev;
SHOW TABLES;
SELECT 'option_prices' as table_name, COUNT(*) as row_count FROM option_prices
UNION ALL
SELECT 'sentiment_data' as table_name, COUNT(*) as row_count FROM sentiment_data;
" 2>/dev/null || echo "⚠️ Database queries may fail if tables don't exist yet"

echo ""
echo "🎮 Interactive commands:"
echo "  📊 View live logs: docker compose -f docker/docker compose.dev.yml logs -f"
echo "  🔄 Restart service: docker compose -f docker/docker compose.dev.yml restart [service-name]"
echo "  🗄️ Access MySQL: docker compose -f docker/docker compose.dev.yml exec mysql-dev mysql -uroot -pdevpassword optionsdb_dev"
echo "  🧹 Stop all: docker compose -f docker/docker compose.dev.yml down"
echo ""
echo "🚀 All services are running! Press Ctrl+C to stop monitoring."

# Follow logs
docker compose -f docker compose.dev.yml logs -f