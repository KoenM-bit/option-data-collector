"""
ETL Service - orchestrates the complete daily data pipeline.
Modern implementation using professional service architecture.
"""

import sys
from datetime import date, datetime
from typing import Any, Dict, Optional
import pandas as pd

from src.config.database import get_db_connection
from src.config.settings import settings


class ETLService:
    """
    Daily ETL orchestrator for FD option data.
    Modern implementation using professional service architecture.
    """

    def __init__(self):
        """Initialize ETL service with modern implementations."""
        # Use the new professional services instead of legacy archive files
        from src.services.option_service import OptionService
        from src.scrapers.options_scraper import OptionsDataScraper
        
        self.option_service = OptionService()
        self.scraper = OptionsDataScraper()
        self.db_connection = get_db_connection()

    def peildatum_bestaat(self, peildatum: date) -> bool:
        """
        Check if peildatum already exists - exact same logic as original.
        """
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM fd_option_overview WHERE peildatum = %s", (peildatum,)
        )
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count > 0

    def run_etl(self) -> None:
        """
        Modern ETL flow using professional service architecture.
        """
        print("⚙️ Daily Options ETL v2.0")
        print("📊 Processing FD data, Greeks, and Scores")
        print("-" * 50)
        print(f"\n⏰ ETL gestart op {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # Import legacy functions for now - will modernize later
            import sys
            import os
            archive_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../archive/original-files'))
            if archive_path not in sys.path:
                sys.path.insert(0, archive_path)
            
            from fd_option_summary import fetch_fd_overview, save_to_db as save_overview
            from fd_option_contracts import fetch_all_fd_options, save_to_database as save_contracts
            from option_greeks import compute_greeks_for_day
            from compute_option_score import compute_option_scores
            
            # 1. Fetch overview data
            overview = fetch_fd_overview("AEX.AH/O")
            peildatum = overview.get("totals", {}).get("peildatum")
            
            if not peildatum:
                print("⚠️ Geen peildatum gevonden — waarschijnlijk weekend of gesloten markt.")
                return
            
            print(f"📅 Gevonden peildatum: {peildatum}")
            
            if self.peildatum_bestaat(peildatum):
                print(f"⏩ Peildatum {peildatum} bestaat al — ETL overslaan.")
                return
            
            print(f"🚀 Nieuwe handelsdag ({peildatum}) gedetecteerd — starten met verwerking...")
            
            # 2. Save overview
            save_overview(overview)
            print("✅ Overview opgeslagen.")
            
            # 3. Fetch & save option contracts
            df = fetch_all_fd_options("AEX.AH/O")
            if not df.empty:
                save_contracts(df)
                print(f"✅ {len(df)} optiecontracten opgeslagen.")
            else:
                print("⚠️ Geen optiecontracten gevonden — stop.")
                return
            
            # 4. Compute Greeks
            compute_greeks_for_day(peildatum)
            print("✅ Greeks berekend en opgeslagen.")
            
            # 5. Compute Scores
            compute_option_scores(peildatum)
            print("✅ Scores berekend en opgeslagen.")
            
            print(f"🏁 ETL succesvol afgerond voor {peildatum}")
            print("-" * 60)
            
        except Exception as e:
            print(f"❌ ETL failed: {e}")
            raise


# Make it standalone runnable
if __name__ == "__main__":
    print("🚀 Running ETL Service directly...")
    etl = ETLService()
    try:
        etl.run_etl()
        print("✅ ETL Service completed successfully!")
    except Exception as e:
        print(f"❌ ETL Service failed: {e}")
        raise
