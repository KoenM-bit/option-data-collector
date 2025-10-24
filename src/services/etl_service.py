"""
ETL Service - orchestrates the complete daily data pipeline.
Exact same functionality as your original daily_etl.py.
"""

import sys
from datetime import date, datetime
from typing import Any, Dict

from src.config.database import get_db_connection
from src.config.settings import settings


class ETLService:
    """
    Daily ETL orchestrator for FD option data.
    Preserves exact same logic and flow as your original daily_etl.py.
    """

    def __init__(self):
        # Import the FD modules from archive (keeping your existing imports)
        import os
        import sys

        sys.path.append(
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "archive",
                "original-files",
            )
        )

        from compute_option_score import compute_option_scores
        from fd_option_contracts import fetch_all_fd_options, save_to_database
        from fd_option_summary import fetch_fd_overview, save_to_db
        from option_greeks import compute_greeks_for_day

        self.fetch_fd_overview = fetch_fd_overview
        self.save_fd_overview = save_to_db
        self.fetch_all_fd_options = fetch_all_fd_options
        self.save_fd_contracts = save_to_database
        self.compute_greeks_for_day = compute_greeks_for_day
        self.compute_option_scores = compute_option_scores

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
        Main ETL flow - exact same logic as your original daily_etl.py.
        Preserves all error handling, logging, and exit codes.
        """
        print(f"\n⏰ ETL gestart op {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # 1. Fetch overview data
        try:
            overview = self.fetch_fd_overview("AEX.AH/O")
        except Exception as e:
            print(f"❌ Fout bij ophalen overview: {e}")
            sys.exit(1)

        # 2. Check peildatum
        peildatum = overview.get("totals", {}).get("peildatum")
        if not peildatum:
            print(
                "⚠️ Geen peildatum gevonden in FD overview — waarschijnlijk weekend of gesloten markt."
            )
            sys.exit(0)

        print(f"📅 Gevonden peildatum: {peildatum}")

        if self.peildatum_bestaat(peildatum):
            print(f"⏩ Peildatum {peildatum} bestaat al — ETL overslaan.")
            sys.exit(0)

        print(
            f"🚀 Nieuwe handelsdag ({peildatum}) gedetecteerd — starten met verwerking..."
        )

        # 3. Save overview
        try:
            self.save_fd_overview(overview)
            print("✅ Overview opgeslagen.")
        except Exception as e:
            print(f"⚠️ Fout bij opslaan overview: {e}")
            sys.exit(1)

        # 4. Fetch & save option contracts
        try:
            df = self.fetch_all_fd_options("AEX.AH/O")
            if not df.empty:
                self.save_fd_contracts(df)
                print(f"✅ {len(df)} optiecontracten opgeslagen.")
            else:
                print("⚠️ Geen optiecontracten gevonden — stop.")
                sys.exit(0)
        except Exception as e:
            print(f"❌ Fout bij ophalen/saven contracts: {e}")
            sys.exit(1)

        # 5. Compute Greeks
        try:
            self.compute_greeks_for_day(peildatum)
            print("✅ Greeks berekend en opgeslagen.")
        except Exception as e:
            print(f"⚠️ Fout bij berekening Greeks: {e}")

        # 6. Compute Scores
        try:
            self.compute_option_scores(peildatum)
            print("✅ Scores berekend en opgeslagen.")
        except Exception as e:
            print(f"⚠️ Fout bij berekening scores: {e}")

        print("🏁 ETL succesvol afgerond voor", peildatum)
        print("-" * 60)


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
