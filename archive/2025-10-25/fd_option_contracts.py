# -*- coding: utf-8 -*-
"""
fd_options_scraper.py
Scraper voor FD.nl optie-data (bijv. AD.AS via /derivaten/opties/)
Automatisch opslaan in MySQL, met duplicate handling (upsert).
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import mysql.connector

# ---------- Database Config ----------
DB_CONFIG = {
    "host": "192.168.1.201",
    "user": "remoteuser",
    "password": "T3l3foon32#123",
    "database": "optionsdb",
    "port": 3306,
}


# ---------- Helper: Tabel aanmaken ----------
def create_fd_option_contracts_table():
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS fd_option_contracts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ticker VARCHAR(10),
            symbol_code VARCHAR(20),
            peildatum DATE,
            expiry DATE,
            strike FLOAT,
            type ENUM('Call', 'Put'),
            last FLOAT,
            previous FLOAT,
            change_value FLOAT,
            pct_change FLOAT,
            bid FLOAT,
            ask FLOAT,
            high FLOAT,
            low FLOAT,
            volume INT,
            open_interest INT,
            last_trade_date DATE,
            scraped_at DATETIME,
            source VARCHAR(255),
            UNIQUE KEY uniq_contract (ticker, peildatum, expiry, strike, type)
        );
    """
    )
    connection.commit()
    cursor.close()
    connection.close()
    print("✅ Database-tabel 'fd_option_contracts' gecontroleerd of aangemaakt.")


# ---------- Helperfuncties ----------
def _to_float(value):
    if value is None or value == "--" or value == "":
        return None
    try:
        value = str(value).replace(",", ".").replace(" ", "")
        return float(value)
    except:
        return None


def _to_int(value):
    if value is None or value == "--" or value == "":
        return None
    try:
        value = str(value).replace(".", "").replace(" ", "")
        return int(value)
    except:
        return None


def _to_date(value):
    if value in (None, "--", ""):
        return None
    for fmt in ("%d-%m-%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


# ---------- Scraper ----------
def fetch_fd_options(symbol_code="AEX.AH/O", option_type="call", peildatum=None):
    base_url = f"https://beurs.fd.nl/derivaten/opties/?{option_type}={symbol_code}"
    print(f"\n📡 Ophalen FD {option_type.upper()} data van {symbol_code} ...")

    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(base_url, headers=headers, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    table = soup.find("table", {"id": "m_Content_GridViewIssues"})
    if table is None:
        print("❌ Geen optie-tabel gevonden op FD.nl")
        return pd.DataFrame()

    rows = table.find_all("tr")[1:]
    data = []

    for tr in rows:
        cols = [c.get_text(strip=True).replace("\xa0", "") for c in tr.find_all("td")]
        if len(cols) < 13:
            continue
        data.append(
            {
                "expiry": cols[0],
                "open_interest": cols[1] or None,
                "strike": cols[2] or None,
                "last": cols[3] or None,
                "previous": cols[4] or None,
                "change_value": cols[5] or None,
                "pct_change": cols[6] or None,
                "bid": cols[7] or None,
                "ask": cols[8] or None,
                "high": cols[9] or None,
                "low": cols[10] or None,
                "volume": cols[11] or None,
                "last_trade_date": cols[12] or None,
            }
        )

    df = pd.DataFrame(data)
    if df.empty:
        print("⚠️ Geen data gevonden.")
        return df

    df["ticker"] = "AD.AS"
    df["symbol_code"] = symbol_code
    df["type"] = option_type.capitalize()
    df["peildatum"] = (peildatum or datetime.utcnow().date()) - timedelta(days=1)
    df["scraped_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    df["source"] = base_url

    print(f"✅ {len(df)} {option_type.upper()}-opties opgehaald van FD.nl")
    return df


# ---------- Opslaan in database ----------
def save_to_database(df):
    if df.empty:
        print("⚠️ Geen data om op te slaan.")
        return

    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()

    insert_query = """
        INSERT INTO fd_option_contracts (
            ticker, symbol_code, peildatum, expiry, strike, type,
            last, previous, change_value, pct_change,
            bid, ask, high, low,
            volume, open_interest, last_trade_date, scraped_at, source
        )
        VALUES (
            %(ticker)s, %(symbol_code)s, %(peildatum)s, %(expiry)s, %(strike)s, %(type)s,
            %(last)s, %(previous)s, %(change_value)s, %(pct_change)s,
            %(bid)s, %(ask)s, %(high)s, %(low)s,
            %(volume)s, %(open_interest)s, %(last_trade_date)s, %(scraped_at)s, %(source)s
        )
        ON DUPLICATE KEY UPDATE
            last = VALUES(last),
            previous = VALUES(previous),
            change_value = VALUES(change_value),
            pct_change = VALUES(pct_change),
            bid = VALUES(bid),
            ask = VALUES(ask),
            high = VALUES(high),
            low = VALUES(low),
            volume = VALUES(volume),
            open_interest = VALUES(open_interest),
            last_trade_date = VALUES(last_trade_date),
            scraped_at = VALUES(scraped_at),
            source = VALUES(source);
    """

    for _, row in df.iterrows():
        try:
            cursor.execute(
                insert_query,
                {
                    "ticker": row["ticker"],
                    "symbol_code": row["symbol_code"],
                    "peildatum": row["peildatum"],
                    "expiry": _to_date(row["expiry"]),
                    "strike": _to_float(row["strike"]),
                    "type": row["type"],
                    "last": _to_float(row["last"]),
                    "previous": _to_float(row["previous"]),
                    "change_value": _to_float(row["change_value"]),
                    "pct_change": _to_float(row["pct_change"]),
                    "bid": _to_float(row["bid"]),
                    "ask": _to_float(row["ask"]),
                    "high": _to_float(row["high"]),
                    "low": _to_float(row["low"]),
                    "volume": _to_int(row["volume"]),
                    "open_interest": _to_int(row["open_interest"]),
                    "last_trade_date": _to_date(row["last_trade_date"]),
                    "scraped_at": row["scraped_at"],
                    "source": row["source"],
                },
            )
        except Exception as e:
            print(f"⚠️ Fout bij invoegen: {e}")
            continue

    connection.commit()
    cursor.close()
    connection.close()
    print(f"💾 {len(df)} records opgeslagen (of bijgewerkt) in fd_option_contracts.")


# ---------- Main ----------
def fetch_all_fd_options(symbol_code="AEX.AH/O"):
    today = datetime.utcnow().date()
    calls = fetch_fd_options(symbol_code, "call", peildatum=today)
    puts = fetch_fd_options(symbol_code, "put", peildatum=today)
    if calls.empty and puts.empty:
        print("⚠️ Geen enkele data opgehaald.")
        return pd.DataFrame()
    df = pd.concat([calls, puts], ignore_index=True)
    print(f"\n📊 Totaal: {len(df)} optiecontracten ({df['type'].value_counts().to_dict()})")
    return df


if __name__ == "__main__":
    create_fd_option_contracts_table()
    df = fetch_all_fd_options("AEX.AH/O")
    if not df.empty:
        save_to_database(df)
        print("\n✅ Scrape + opslag voltooid (met upsert logica)!")
