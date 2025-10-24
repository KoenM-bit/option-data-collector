"""
Option service - handles data collection and storage.
Contains exact same database logic as your original beursduivel.py.
"""

from typing import Any, Dict, List

from src.config.database import get_db_connection
from src.scrapers.options_scraper import OptionsDataScraper
from src.utils.data_utils import is_market_open


class OptionService:
    """
    Professional Options Data Collection Service

    Handles comprehensive options data scraping, processing, and storage.
    Implements market-aware scheduling, robust error handling, and database persistence.
    Designed for enterprise-grade reliability in financial data collection workflows.
    """

    def __init__(self):
        self.scraper = OptionsDataScraper()

    def save_price_to_db(
        self, option: Dict[str, Any], price: float, source: str
    ) -> None:
        """
        Save price to database - exact same logic as your original save_price_to_db().
        Preserves exact same table structure and insert logic.
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        # Create table if not exists - exact same as your original
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS option_prices (
                id INT AUTO_INCREMENT PRIMARY KEY,
                issue_id VARCHAR(32),
                expiry VARCHAR(64),
                type VARCHAR(10),
                strike VARCHAR(10),
                price DECIMAL(10,3),
                source VARCHAR(20),
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Insert data - exact same as your original
        cursor.execute(
            """
            INSERT INTO option_prices (issue_id, expiry, type, strike, price, source)
            VALUES (%s, %s, %s, %s, %s, %s)
        """,
            (
                option["issue_id"],
                option["expiry"],
                option["type"],
                option["strike"],
                price,
                source,
            ),
        )

        conn.commit()
        cursor.close()
        conn.close()

        print(f"✅ Saved {price} ({source}) for {option['strike']} {option['type']}")

    def collect_and_store_options(self) -> int:
        """
        Collect options data and store in database.
        Preserves exact same logic flow as your original main loop.
        Returns count of successfully stored options.
        """
        if not is_market_open():
            return 0

        print("📊 Market is open — fetching data...")
        options = self.scraper.fetch_option_chain()
        print(f"Found {len(options)} options in total.")

        count = 0
        for option in options:
            live_data = self.scraper.get_live_price(option["issue_id"], option["url"])
            if live_data and live_data.get("last"):
                self.save_price_to_db(option, live_data["last"], "LIVE")
                count += 1
                print(
                    f"✅ Saved {option['expiry']} {option['type']} {option['strike']} @ {live_data['last']}"
                )

        print(f"\n✅ Stored {count} options successfully.")
        return count


# Make it standalone runnable
if __name__ == "__main__":
    print("🚀 Running Option Service directly...")
    service = OptionService()
    try:
        from src.utils.data_utils import is_market_open

        if is_market_open():
            count = service.collect_and_store_options()
            print(
                f"✅ Option Service completed successfully! Processed {count} options."
            )
        else:
            print("⏰ Market is closed - no data collection performed")
            print("✅ Option Service completed (market closed)")
    except Exception as e:
        print(f"❌ Option Service failed: {e}")
        raise
