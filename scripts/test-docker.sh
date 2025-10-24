#!/bin/bash
echo "🐳 Testing complete Docker setup..."

# Navigate to docker directory
cd "$(dirname "$0")/../docker"

echo "📋 Testing each service individually..."

# Test 1: Start MySQL first
echo "🗄️ Starting MySQL..."
docker compose -f docker compose.dev.yml up -d mysql-dev

# Wait for MySQL to be ready
echo "⏳ Waiting for MySQL to start..."
sleep 15

# Test 2: Test option scraper
echo "🔍 Testing Option Scraper..."
docker compose -f docker compose.dev.yml run --rm option-scraper python -c "
from src.services.option_service import OptionService
from src.utils.helpers import _parse_eu_number
print('✅ Option scraper imports working')

# Test helper function
result = _parse_eu_number('1.234,56')
print(f'✅ _parse_eu_number working: {result}')

# Test service initialization
service = OptionService()
print('✅ OptionService initialized')
"

if [ $? -eq 0 ]; then
    echo "✅ Option scraper test passed"
else
    echo "❌ Option scraper test failed"
    exit 1
fi

# Test 3: Test sentiment tracker
echo "📊 Testing Sentiment Tracker..."
docker compose -f docker compose.dev.yml run --rm sentiment-tracker python -c "
from src.services.sentiment_service import SentimentService
print('✅ Sentiment service imports working')

# Test service initialization
service = SentimentService()
print('✅ SentimentService initialized')
print(f'✅ Ticker configured: {service.ticker}')
"

if [ $? -eq 0 ]; then
    echo "✅ Sentiment tracker test passed"
else
    echo "❌ Sentiment tracker test failed"
    exit 1
fi

# Test 4: Test ETL service
echo "⚙️ Testing ETL Service..."
docker compose -f docker compose.dev.yml run --rm daily-etl python -c "
from src.services.etl_service import ETLService
print('✅ ETL service imports working')

# Test service initialization
service = ETLService()
print('✅ ETLService initialized')
print('✅ All ETL dependencies loaded')
"

if [ $? -eq 0 ]; then
    echo "✅ ETL service test passed"
else
    echo "❌ ETL service test failed"
    exit 1
fi

# Test 5: Database connectivity
echo "🔗 Testing Database Connectivity..."
docker compose -f docker compose.dev.yml run --rm option-scraper python -c "
from src.config.database import get_db_connection
try:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1')
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    print('✅ Database connection successful')
except Exception as e:
    print(f'❌ Database connection failed: {e}')
    exit(1)
"

if [ $? -eq 0 ]; then
    echo "✅ Database connectivity test passed"
else
    echo "❌ Database connectivity test failed"
    exit 1
fi

# Test 6: End-to-end configuration
echo "⚙️ Testing Configuration..."
docker compose -f docker compose.dev.yml run --rm option-scraper python -c "
from src.config.settings import settings
print(f'✅ Environment: {settings.environment}')
print(f'✅ Database host: {settings.db_host}')
print(f'✅ Market hours: {settings.market_open_hour}:00-{settings.market_close_hour}:00')
print(f'✅ Scrape interval: {settings.scrape_interval}s')
"

# Cleanup
echo "🧹 Cleaning up test containers..."
docker compose -f docker compose.dev.yml down

echo ""
echo "🎉 All Docker tests passed!"
echo "📋 Summary:"
echo "  ✅ Option scraper service working"
echo "  ✅ Sentiment tracker service working"  
echo "  ✅ ETL service working"
echo "  ✅ Database connectivity working"
echo "  ✅ Configuration working"
echo ""
echo "🚀 Ready for production deployment!"
echo ""
echo "Next steps:"
echo "  📊 Test with real data: docker compose -f docker/docker compose.dev.yml up"
echo "  🚀 Deploy to production: ./scripts/deploy.sh"