"""
Configuration management for option data collector.
Preserves all existing database settings and functionality.
"""

import os
from typing import Any, Dict


class Settings:
    """
    Settings class that handles environment variables while maintaining
    exact same defaults as your current hardcoded values.
    """

    def __init__(self):
        # Environment
        self.environment = os.getenv(
            "ENV", "production"
        )  # Default to production like your current setup
        self.timezone = os.getenv("TZ", "Europe/Amsterdam")

        # Database - exact same values as your current beursduivel.py and sentiment_tracker.py
        self.db_host = os.getenv("DB_HOST", "192.168.1.200")
        self.db_user = os.getenv("DB_USER", "remoteuser")
        self.db_password = os.getenv(
            "DB_PASS", "T3l3foon32#123"
        )  # Using DB_PASS to match docker-compose
        self.db_name = os.getenv("DB_NAME", "optionsdb")
        self.db_port = int(os.getenv("DB_PORT", 3306))

        # Market hours - exact same as your current setup
        self.market_open_hour = int(os.getenv("MARKET_OPEN", 9))
        self.market_close_hour = int(os.getenv("MARKET_CLOSE", 17))

        # Scraping settings - exact same as your current setup
        self.scrape_interval = int(os.getenv("SCRAPE_INTERVAL", 3600))  # 1 hour
        self.sleep_interval = int(
            os.getenv("SLEEP_INTERVAL", 900)
        )  # 15 minutes when market closed
        self.user_agent = os.getenv("USER_AGENT", "Mozilla/5.0")

        # Ticker symbol - same as your sentiment_tracker.py
        self.ticker = os.getenv("TICKER", "AD.AS")

    @property
    def db_config(self) -> Dict[str, Any]:
        """
        Returns database config dict exactly as used in your current files.
        This ensures 100% compatibility with existing mysql.connector.connect() calls.
        """
        return {
            "host": self.db_host,
            "user": self.db_user,
            "password": self.db_password,
            "database": self.db_name,
            "port": self.db_port,
        }

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


# Global settings instance - can be imported anywhere
settings = Settings()
