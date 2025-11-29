#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
daily_etl.py
-------------
Dagelijkse orchestrator voor FD optie-data:
1. Haalt overzichtsdata op (incl. peildatum)
2. Checkt of peildatum al bestaat in de database
3. Alleen bij nieuwe peildatum:
   - Scrape alle call/put-contracten
   - Sla ze op
   - Bereken Greeks
   - Bereken Score
4. Logt het resultaat

Kan 1x per dag gedraaid worden via cron of Docker scheduler.
"""

import sys
import mysql.connector
from datetime import datetime
from fd_option_summary import fetch_fd_overview, save_to_db
from fd_option_contracts import fetch_all_fd_options, save_to_database
from option_greeks import compute_greeks_for_day
from compute_option_score import compute_option_scores


# ---------- DATABASE CONFIG ----------
DB_CONFIG = {
    "host": "192.168.1.201",
    "user": "remoteuser",
    "password": "T3l3foon32#123",
    "database": "optionsdb",
    "port": 3306,
}


# ---------- HELPER: CHECK BESTAANDE PEILDATUM ----------
def peildatum_bestaat(peildatum: datetime.date) -> bool:
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM fd_option_overview WHERE peildatum = %s", (peildatum,))
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count > 0


# ---------- MAIN ETL FLOW ----------
def run_etl():
    print(f"\nETL gestart op {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        overview = fetch_fd_overview("AEX.AH/O")
    except Exception as e:
        print(f"Fout bij ophalen overview: {e}")
        sys.exit(1)

    peildatum = overview.get("totals", {}).get("peildatum")
    if not peildatum:
        print("Geen peildatum gevonden in FD overview — waarschijnlijk weekend of gesloten markt.")
        sys.exit(0)

    print(f"Gevonden peildatum: {peildatum}")

    if peildatum_bestaat(peildatum):
        print(f"Peildatum {peildatum} bestaat al — ETL overslaan.")
        sys.exit(0)

    print(f"Nieuwe handelsdag ({peildatum}) gedetecteerd — starten met verwerking...")

    # Save overview
    try:
        save_to_db(overview)
        print("Overview opgeslagen.")
    except Exception as e:
        print(f"Fout bij opslaan overview: {e}")
        sys.exit(1)

    # Fetch & save option contracts
    try:
        df = fetch_all_fd_options("AEX.AH/O")
        if not df.empty:
            save_to_database(df)
            print(f"{len(df)} optiecontracten opgeslagen.")
        else:
            print("Geen optiecontracten gevonden — stop.")
            sys.exit(0)
    except Exception as e:
        print(f"Fout bij ophalen/saven contracts: {e}")
        sys.exit(1)

    # Compute Greeks
    try:
        compute_greeks_for_day(peildatum)
        print("Greeks berekend en opgeslagen.")
    except Exception as e:
        print(f"Fout bij berekening Greeks: {e}")

    # Compute Scores
    try:
        compute_option_scores(peildatum)
        print("Scores berekend en opgeslagen.")
    except Exception as e:
        print(f"Fout bij berekening scores: {e}")

    print("ETL succesvol afgerond voor", peildatum)
    print("-" * 60)


if __name__ == "__main__":
    run_etl()
