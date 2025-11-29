# -*- coding: utf-8 -*-
"""
fd_overview_scraper.py
Haalt overzichtsdata (header + totalen) op van FD.nl voor een onderliggende waarde.
Slaat de resultaten automatisch op in de MySQL database (met upsert-logica).
"""

import re
import json
import requests
import mysql.connector
from bs4 import BeautifulSoup
from datetime import datetime

# ---------------------------------------------------
# 🔧 Database instellingen
# ---------------------------------------------------
DB_CONFIG = {
    "host": "192.168.1.201",
    "user": "remoteuser",
    "password": "T3l3foon32#123",
    "database": "optionsdb",
    "port": 3306,
}

# ---------------------------------------------------
# 🌍 Basis-URL
# ---------------------------------------------------
FD_BASE = "https://beurs.fd.nl/derivaten/opties/"


# ---------------------------------------------------
# 🔢 Helpers
# ---------------------------------------------------
def _to_int(s: str) -> int | None:
    if not s:
        return None
    s = s.strip().replace(".", "").replace("\xa0", "").replace(" ", "")
    m = re.search(r"-?\d+", s)
    return int(m.group(0)) if m else None


def _to_float_nl(s: str) -> float | None:
    if not s:
        return None
    s = s.strip().replace(".", "").replace("\xa0", "").replace(" ", "").replace(",", ".")
    m = re.search(r"-?\d+(\.\d+)?", s)
    return float(m.group(0)) if m else None


# ---------------------------------------------------
# 🕵️‍♂️ Scraper-functie
# ---------------------------------------------------
def fetch_fd_overview(symbol_code: str = "AEX.AH/O") -> dict:
    url = f"{FD_BASE}?call={symbol_code}"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # 1️⃣ Header-tabel
    header_tbl = soup.find("table", id="m_Content_GridViewSingleUnderlyingIssue")
    if not header_tbl:
        raise RuntimeError("Header-tabel niet gevonden")

    rows = header_tbl.find_all("tr")
    data_tds = rows[-1].find_all("td")

    name = data_tds[0].get_text(strip=True)
    koers = _to_float_nl(data_tds[1].get_text())
    vorige = _to_float_nl(data_tds[2].get_text())
    delta = _to_float_nl(data_tds[3].get_text())
    delta_pct = _to_float_nl(data_tds[4].get_text(strip=True).replace("%", ""))
    hoog = _to_float_nl(data_tds[5].get_text())
    laag = _to_float_nl(data_tds[6].get_text())
    volume_ul = _to_int(data_tds[7].get_text())
    tijd = data_tds[8].get_text(strip=True)

    header = {
        "onderliggende_waarde": name,
        "koers": koers,
        "vorige": vorige,
        "delta": delta,
        "delta_pct": delta_pct,
        "hoog": hoog,
        "laag": laag,
        "volume_ul": volume_ul,
        "tijd": tijd,
    }

    # 2️⃣ Totalen
    totals_tbl = soup.find("table", class_="fAr11 mb10 mt10")
    if not totals_tbl:
        raise RuntimeError("Totalen-tabel niet gevonden")

    totalen = {
        "totaal_volume": None,
        "totaal_volume_calls": None,
        "totaal_volume_puts": None,
        "totaal_oi_opening": None,
        "totaal_oi_calls": None,
        "totaal_oi_puts": None,
        "call_put_ratio": None,
        "peildatum": None,
    }

    subtitle_td = totals_tbl.find("tr").find("td")
    if subtitle_td:
        m = re.search(r"\((?:op\s)?(\d{2}-\d{2}-\d{4})\)", subtitle_td.get_text())
        if m:
            totalen["peildatum"] = datetime.strptime(m.group(1), "%d-%m-%Y").date()

    trs = totals_tbl.find_all("tr")[1:]
    for tr in trs:
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        label = tds[0].get_text(strip=True).lower()
        val = tds[1].get_text(" ", strip=True)

        if "totaal volume" in label:
            m = re.search(r"([\d\.\s]+)\s*\(\s*([\d\.\s]+)\s*Calls,\s*([\d\.\s]+)\s*Puts\)", val)
            if m:
                totalen["totaal_volume"] = _to_int(m.group(1))
                totalen["totaal_volume_calls"] = _to_int(m.group(2))
                totalen["totaal_volume_puts"] = _to_int(m.group(3))
        elif "totaal open interest" in label:
            m = re.search(r"([\d\.\s]+)\s*\(\s*([\d\.\s]+)\s*Calls,\s*([\d\.\s]+)\s*Puts\)", val)
            if m:
                totalen["totaal_oi_opening"] = _to_int(m.group(1))
                totalen["totaal_oi_calls"] = _to_int(m.group(2))
                totalen["totaal_oi_puts"] = _to_int(m.group(3))
        elif "call" in label and "put" in label:
            totalen["call_put_ratio"] = _to_float_nl(val)

    return {
        "ticker": "AD.AS" if symbol_code.upper().startswith("AEX.AH") else symbol_code,
        "symbol_code": symbol_code,
        "scraped_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "header": header,
        "totals": totalen,
        "source": url,
    }


# ---------------------------------------------------
# 💾 Opslaan in MySQL (met upsert)
# ---------------------------------------------------
def save_to_db(data: dict):
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Tabel aanmaken + unieke key (ticker + peildatum)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fd_option_overview (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ticker VARCHAR(10),
            symbol_code VARCHAR(20),
            koers FLOAT,
            vorige FLOAT,
            delta FLOAT,
            delta_pct FLOAT,
            hoog FLOAT,
            laag FLOAT,
            volume_ul INT,
            tijd VARCHAR(10),
            totaal_volume INT,
            totaal_volume_calls INT,
            totaal_volume_puts INT,
            totaal_oi_opening INT,
            totaal_oi_calls INT,
            totaal_oi_puts INT,
            call_put_ratio FLOAT,
            peildatum DATE,
            scraped_at DATETIME,
            source VARCHAR(255),
            UNIQUE KEY uniq_overview (ticker, peildatum)
        )
    """
    )

    q = """
        INSERT INTO fd_option_overview (
            ticker, symbol_code, koers, vorige, delta, delta_pct, hoog, laag, volume_ul,
            tijd, totaal_volume, totaal_volume_calls, totaal_volume_puts, totaal_oi_opening,
            totaal_oi_calls, totaal_oi_puts, call_put_ratio, peildatum, scraped_at, source
        ) VALUES (
            %(ticker)s, %(symbol_code)s, %(koers)s, %(vorige)s, %(delta)s, %(delta_pct)s,
            %(hoog)s, %(laag)s, %(volume_ul)s, %(tijd)s, %(totaal_volume)s,
            %(totaal_volume_calls)s, %(totaal_volume_puts)s, %(totaal_oi_opening)s,
            %(totaal_oi_calls)s, %(totaal_oi_puts)s, %(call_put_ratio)s,
            %(peildatum)s, %(scraped_at)s, %(source)s
        )
        ON DUPLICATE KEY UPDATE
            koers = VALUES(koers),
            vorige = VALUES(vorige),
            delta = VALUES(delta),
            delta_pct = VALUES(delta_pct),
            hoog = VALUES(hoog),
            laag = VALUES(laag),
            volume_ul = VALUES(volume_ul),
            tijd = VALUES(tijd),
            totaal_volume = VALUES(totaal_volume),
            totaal_volume_calls = VALUES(totaal_volume_calls),
            totaal_volume_puts = VALUES(totaal_volume_puts),
            totaal_oi_opening = VALUES(totaal_oi_opening),
            totaal_oi_calls = VALUES(totaal_oi_calls),
            totaal_oi_puts = VALUES(totaal_oi_puts),
            call_put_ratio = VALUES(call_put_ratio),
            scraped_at = VALUES(scraped_at),
            source = VALUES(source);
    """

    params = {
        **data["header"],
        **data["totals"],
        "ticker": data["ticker"],
        "symbol_code": data["symbol_code"],
        "scraped_at": data["scraped_at"],
        "source": data["source"],
    }

    cur.execute(q, params)
    conn.commit()
    cur.close()
    conn.close()
    print("✅ Data opgeslagen of bijgewerkt in fd_option_overview")


# ---------------------------------------------------
# 🚀 Main
# ---------------------------------------------------
if __name__ == "__main__":
    result = fetch_fd_overview("AEX.AH/O")
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    save_to_db(result)
    print("✅ Scrape + opslag voltooid (met upsert)!")
