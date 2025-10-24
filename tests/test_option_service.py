"""
Tests for Option Service
"""

import unittest
from unittest.mock import Mock, patch

import pytest


class TestOptionService(unittest.TestCase):
    """Test cases for OptionService"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_env_patcher = patch.dict(
            "os.environ",
            {
                "ENV": "test",
                "DB_HOST": "localhost",
                "DB_USER": "test",
                "DB_PASS": "test",
                "DB_NAME": "test_db",
            },
        )
        self.mock_env_patcher.start()

    def tearDown(self):
        """Clean up after tests"""
        self.mock_env_patcher.stop()

    @patch("src.config.database.get_db_connection")
    @patch("src.scrapers.options_scraper.OptionsDataScraper")
    def test_service_initialization(self, mock_scraper, mock_db):
        """Test that OptionService initializes correctly"""
        from src.services.option_service import OptionService

        service = OptionService()
        self.assertIsNotNone(service)
        self.assertIsNotNone(service.scraper)

    @patch("src.utils.data_utils.is_market_open")
    def test_market_hours_check(self, mock_market_open):
        """Test market hours functionality"""
        from src.utils.data_utils import is_market_open

        # Test market closed
        mock_market_open.return_value = False
        self.assertFalse(is_market_open())

        # Test market open
        mock_market_open.return_value = True
        self.assertTrue(is_market_open())


if __name__ == "__main__":
    unittest.main()
