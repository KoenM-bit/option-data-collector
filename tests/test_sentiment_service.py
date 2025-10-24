"""
Tests for Sentiment Service
"""

import json
import unittest
from unittest.mock import Mock, patch


class TestSentimentService(unittest.TestCase):
    """Test cases for SentimentService"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_env_patcher = patch.dict(
            "os.environ",
            {
                "ENV": "test",
                "TICKER": "AD.AS",
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
    def test_service_initialization(self, mock_db):
        """Test that SentimentService initializes correctly"""
        from src.services.sentiment_service import SentimentService

        service = SentimentService()
        self.assertIsNotNone(service)
        self.assertEqual(service.ticker, "AD.AS")

    def test_records_differ(self):
        """Test record comparison logic"""
        from src.services.sentiment_service import SentimentService

        service = SentimentService()

        # Test with no old record
        old_record = None
        new_record = {"rating_avg": 2.5, "buy_count": 5}
        self.assertTrue(service.records_differ(old_record, new_record))

        # Test with identical records
        old_record = {"rating_avg": 2.5, "buy_count": 5, "hold_count": 3}
        new_record = {"rating_avg": 2.5, "buy_count": 5, "hold_count": 3}
        self.assertFalse(service.records_differ(old_record, new_record))

        # Test with different records
        old_record = {"rating_avg": 2.5, "buy_count": 5}
        new_record = {"rating_avg": 3.0, "buy_count": 5}
        self.assertTrue(service.records_differ(old_record, new_record))


if __name__ == "__main__":
    unittest.main()
