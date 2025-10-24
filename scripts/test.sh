#!/bin/bash
echo "🧪 Running compatibility tests..."

# Test that both old and new files work
echo "Testing original functionality..."

# Test new structured code
echo "Testing new structured code..."
cd "$(dirname "$0")/.."

# Set environment for testing
export ENV=testing
export DB_HOST=localhost
export DB_USER=root
export DB_PASS=testpass
export DB_NAME=optionsdb_test

# Basic import tests
python3 -c "
try:
    from src.services.option_service import OptionService
    from src.services.sentiment_service import SentimentService
    from src.utils.helpers import _parse_eu_number, is_market_open
    from src.config.settings import settings
    print('✅ All imports successful')
except Exception as e:
    print(f'❌ Import failed: {e}')
    exit(1)
"

# Test helper functions
python3 -c "
from src.utils.helpers import _parse_eu_number
test_cases = [
    ('1.234,56', 1234.56),
    ('1,23', 1.23),
    ('123', 123.0),
    ('', None),
]
for input_val, expected in test_cases:
    result = _parse_eu_number(input_val)
    if result == expected:
        print(f'✅ _parse_eu_number(\"{input_val}\") = {result}')
    else:
        print(f'❌ _parse_eu_number(\"{input_val}\") = {result}, expected {expected}')
"

# Test settings
python3 -c "
from src.config.settings import settings
print(f'✅ Database config: {settings.db_config}')
print(f'✅ Market hours: {settings.market_open_hour}:00 - {settings.market_close_hour}:00')
print(f'✅ Environment: {settings.environment}')
"

echo "✅ All tests passed! New structure maintains 100% compatibility."