# -*- coding: utf-8 -*-
"""
app/etl/beursduivel_scraper.py
Scrape live optieprijzen van Beursduivel en schrijf naar option_prices.

Geporteerd uit legacy beursduivel.py en aangepast voor app/ structuur.
"""

from __future__ import annotations

import time
import datetime as dt
import pytz
import requests
from bs4 import BeautifulSoup

from app.db import get_connection
from app.utils.helpers import clean_href, _parse_eu_number


BASE = "https://www.beursduivel.be"
URL = f"{BASE}/Aandeel-Koers/11755/Ahold-Delhaize-Koninklijke/opties-expiratiedatum.aspx"
HEADERS = {"User-Agent": "Mozilla/5.0"}

TIMEZONE = pytz.timezone("Europe/Amsterdam")
MARKET_OPEN = 9
MARKET_CLOSE = 17


def is_market_open() -> bool:
    now = dt.datetime.now(TIMEZONE)
    return MARKET_OPEN <= now.hour < MARKET_CLOSE


def fetch_option_chain():
    r = requests.get(URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    options = []
    for section in soup.select("section.contentblock"):
        expiry_el = section.find("h3", class_="titlecontent")
        expiry_text = expiry_el.get_text(strip=True) if expiry_el else "Unknown Expiry"
        for row in section.select("tr"):
            strike_cell = row.select_one(".optiontable__focus")
            strike = strike_cell.get_text(strip=True).split()[0] if strike_cell else None
            bid_call = row.select_one(".optiontable__bidcall")
            ask_call = row.select_one(".optiontable__askcall")
            bid_put = row.select_one(".optiontable__bid")
            ask_put = row.select_one(".optiontable__askput")
            for opt_type in ["Call", "Put"]:
                link = row.select_one(f"a.optionlink.{opt_type}")
                if not link or "href" not in link.attrs:
                    continue
                href = link["href"]
                parts = href.split("/")
                issue_id = next((p for p in parts if p.isdigit()), None)
                if not issue_id:
                    continue
                full_url = clean_href(href)
                bid_el, ask_el = (bid_call, ask_call) if opt_type == "Call" else (bid_put, ask_put)
                bid_val = _parse_eu_number(bid_el.get_text(strip=True)) if bid_el and bid_el.get_text(strip=True) else None
                ask_val = _parse_eu_number(ask_el.get_text(strip=True)) if ask_el and ask_el.get_text(strip=True) else None
                options.append({
                    "type": opt_type,
                    "expiry": expiry_text,
                    "strike": strike,
                    "issue_id": issue_id,
                    "url": full_url,
                    "bid": bid_val,
                    "ask": ask_val
                })
    return options


def get_live_price(issue_id: str, detail_url: str):
    r = requests.get(detail_url, headers=HEADERS, timeout=20)
    if not r.ok:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    price_el = soup.find("span", id=f"{issue_id}LastPrice")
    date_el = soup.find("time", id=f"{issue_id}LastDateTime")
    vol_el = soup.find("span", id=f"{issue_id}Volume")
    if not price_el:
        return None
    last_raw = price_el.get_text(strip=True)
    last_val = _parse_eu_number(last_raw)
    date_text = date_el.get_text(strip=True) if date_el else None
    volume_text = vol_el.get_text(strip=True).replace("\xa0", "") if vol_el else None
    volume = int(volume_text) if volume_text and volume_text.isdigit() else None
    return {"last_raw": last_raw, "last": last_val, "date_text": date_text, "volume": volume}


def save_price_to_db(option, price, source):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
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
    cur.execute(
        """
        INSERT INTO option_prices (issue_id, expiry, type, strike, price, source)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (option["issue_id"], option["expiry"], option["type"], option["strike"], price, source),
    )
    conn.commit(); cur.close(); conn.close()


def run_once():
    options = fetch_option_chain()
    count = 0
    for o in options:
        live = get_live_price(o["issue_id"], o["url"])
        if live and live.get("last"):
            save_price_to_db(o, live["last"], "LIVE")
            count += 1
    print(f"Stored {count} options.")


def run_loop(sleep_seconds: int = 3600):
    while True:
        if is_market_open():
            print("Market is open — fetching data...")
            run_once()
            print(f"Waiting {sleep_seconds//60} minutes...")
            time.sleep(sleep_seconds)
        else:
            now = dt.datetime.now(TIMEZONE).strftime("%H:%M")
            print(f"Market closed ({now}) — sleeping for 15 minutes...")
            time.sleep(900)


if __name__ == "__main__":
    run_loop()
