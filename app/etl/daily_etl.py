# -*- coding: utf-8 -*-
"""
app/etl/daily_etl.py
Dagelijkse orchestrator:
  1) FD overzicht ophalen en opslaan
  2) Optiecontracten scrapen en opslaan
  3) Greeks berekenen en opslaan
  4) Scores berekenen en opslaan

Geporteerd en opgeschoond vanuit de legacy daily_etl.py.
"""

from __future__ import annotations

import sys
from datetime import datetime

from app.db import get_connection
from app.etl.fd_overview_scraper import fetch_fd_overview, save_to_db
from app.etl.fd_options_scraper import (
    fetch_all_fd_options,
    save_to_database,
    create_fd_option_contracts_table,
)
from app.compute.option_greeks import compute_greeks_for_day
from app.compute.compute_option_score import compute_option_score


def peildatum_bestaat(peildatum) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM fd_option_overview WHERE peildatum = %s", (peildatum,))
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count > 0


def run_etl(symbol_code: str = "AEX.AH/O", ticker: str = "AD.AS"):
    print(f"\nETL gestart op {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        overview = fetch_fd_overview(symbol_code)
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
        # Ensure table exists before inserting
        create_fd_option_contracts_table()
        df = fetch_all_fd_options(symbol_code, peildatum=peildatum)
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
        compute_greeks_for_day(ticker=ticker, peildatum=peildatum)
        print("Greeks berekend en opgeslagen.")
    except Exception as e:
        print(f"Fout bij berekening Greeks: {e}")

    # Compute Scores (werkt incrementeel op ontbrekende dagen)
    try:
        compute_option_score(ticker)
        print("Scores berekend en opgeslagen.")
    except Exception as e:
        print(f"Fout bij berekening scores: {e}")

    print("ETL succesvol afgerond voor", peildatum)
    print("-" * 60)


if __name__ == "__main__":
    run_etl()
