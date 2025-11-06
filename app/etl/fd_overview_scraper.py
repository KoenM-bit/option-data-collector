# -*- coding: utf-8 -*-
"""
app/etl/fd_overview_scraper.py
Scraper voor FD overzichtsdata (header + totalen) en opslag in MySQL.

Geporteerd vanuit de legacy fd_option_summary.py naar de app/ structuur.
Gebruikt app.db.get_connection en utils helpers.
"""

from __future__ import annotations

import re
import json
from datetime import datetime
from bs4 import BeautifulSoup

from app.db import get_connection
from app.utils.helpers import fetch_html


# Basis-URL voor FD overzicht
FD_BASE = "https://beurs.fd.nl/derivaten/opties/"


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


def fetch_fd_overview(symbol_code: str = "AEX.AH/O") -> dict:
    """Scrape overzichtsdata van FD voor een symboolcode (bijv. AEX.AH/O)."""
    url = f"{FD_BASE}?call={symbol_code}"
    soup: BeautifulSoup = fetch_html(url)

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

    # Probeer peildatum te extraheren uit eerste td
    first_row = totals_tbl.find("tr")
    if first_row:
        subtitle_td = first_row.find("td")
        if subtitle_td:
            subtitle_text = subtitle_td.get_text()

            # Zoek datum in formaat DD-MM-YYYY (flexibelere regex)
            m = re.search(r"(\d{1,2}-\d{1,2}-\d{4})", subtitle_text)
            if m:
                date_str = m.group(1)
                try:
                    peildatum = datetime.strptime(date_str, "%d-%m-%Y").date()
                except ValueError:
                    print(f"Kon datum niet parsen: {date_str}")
                    peildatum = None
            else:
                print(f"Geen datum gevonden in subtitle: {subtitle_text}")
                peildatum = None

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

    # Voeg de peildatum toe aan totalen
    totalen["peildatum"] = peildatum

    return {
        "ticker": "AD.AS" if symbol_code.upper().startswith("AEX.AH") else symbol_code,
        "symbol_code": symbol_code,
        "scraped_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "header": header,
        "totals": totalen,
        "source": url,
    }


def save_to_db(data: dict):
    """Sla overzicht op in MySQL (met upsert)."""
    conn = get_connection()
    cur = conn.cursor()

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
			source = VALUES(source)
		;
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
    print("Overview opgeslagen in fd_option_overview.")


if __name__ == "__main__":
    res = fetch_fd_overview("AEX.AH/O")
    print(json.dumps(res, indent=2, ensure_ascii=False, default=str))
    save_to_db(res)
    print("Scrape + opslag voltooid.")
