#!/usr/bin/env python3
"""
Main Daily ETL - New Structured Version
Entry point for comprehensive daily options data processing.
"""

from src.services.etl_service import ETLService


def main():
    """Main execution - same logic as original daily_etl.py"""
    etl_service = ETLService()

    print(f"⚙️ Daily Options ETL v2.0")
    print(f"📊 Processing FD data, Greeks, and Scores")
    print("-" * 50)

    etl_service.run_etl()


if __name__ == "__main__":
    main()
