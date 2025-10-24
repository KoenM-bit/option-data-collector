"""
Test configuration and fixtures
"""

import os
from unittest.mock import Mock

import pytest


@pytest.fixture
def mock_db_connection():
    """Mock database connection for testing"""
    mock_conn = Mock()
    mock_cursor = Mock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn, mock_cursor


@pytest.fixture
def test_env_vars():
    """Set up test environment variables"""
    test_vars = {
        "ENV": "test",
        "DB_HOST": "localhost",
        "DB_USER": "test",
        "DB_PASS": "test",
        "DB_NAME": "test_db",
        "DB_PORT": "3306",
        "TICKER": "AD.AS",
        "SCRAPE_INTERVAL": "300",
        "MARKET_OPEN": "9",
        "MARKET_CLOSE": "17",
    }

    # Set environment variables
    for key, value in test_vars.items():
        os.environ[key] = value

    yield test_vars

    # Cleanup
    for key in test_vars.keys():
        os.environ.pop(key, None)
