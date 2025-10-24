#!/usr/bin/env python3
"""
Main Beursduivel Scraper - New Structured Version
Entry point for Ahold Delhaize options data collection.
"""

import time

from src.config.settings import settings
from src.services.option_service import OptionService
from src.utils.data_utils import format_amsterdam_time, is_market_open


def main():
    """Main execution loop - same logic as original beursduivel.py"""
    option_service = OptionService()

    print(f"🚀 Ahold Delhaize Options Scraper v2.0")
    print(f"📍 Environment: {settings.environment}")
    print(f"🗄️  Database: {settings.db_host}:{settings.db_port}")
    print(
        f"⏰ Market Hours: {settings.market_open_hour}:00-{settings.market_close_hour}:00 Amsterdam"
    )
    print("-" * 60)

    while True:
        if is_market_open():
            count = option_service.collect_and_store_options()
            print(
                f"⏳ Waiting {settings.scrape_interval//60} minutes for next update...\n"
            )
            time.sleep(settings.scrape_interval)
        else:
            now_time = format_amsterdam_time()
            print(
                f"⏰ Market closed ({now_time}) — sleeping for {settings.sleep_interval//60} minutes..."
            )
            time.sleep(settings.sleep_interval)


if __name__ == "__main__":
    main()
