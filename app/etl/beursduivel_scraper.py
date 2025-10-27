# -*- coding: utf-8 -*-
"""
app/etl/beursduivel_scraper.py
Scraper die ALLE AEX/AH opties ophaalt van Beursduivel (inclusief 'Meer opties'),
Greeks berekent en opslaat in de tabel `option_prices_live`.
"""

from __future__ import annotations
import os
import re
import math
import requests
from datetime import date, datetime
from bs4 import BeautifulSoup

from app.db import get_connection
from app.utils.helpers import (
    _parse_eu_number,
    risk_free_rate_for_days,
    is_market_open,
    wait_minutes,
)
from app.compute.option_greeks import implied_vol, bs_delta, bs_gamma, bs_vega, bs_theta

BASE = "https://www.beursduivel.be"
MAIN_URL = f"{BASE}/Aandeel-Koers/11755/Ahold-Delhaize-Koninklijke/Opties.aspx"
HEADERS = {"User-Agent": "Mozilla/5.0"}
VERBOSE = os.getenv("BD_VERBOSE", "0") == "1"


# ------------------------
# 🧩 BASIS SCRAPER FUNCTIES
# ------------------------


def parse_option_table(section_html: str, expiry_title: str):
    """Parse 1 optie-tabel (calls & puts)."""
    soup = BeautifulSoup(section_html, "html.parser")
    options = []
    for row in soup.select("tr"):
        strike_cell = row.select_one(".optiontable__focus")
        if not strike_cell:
            continue
        strike = strike_cell.get_text(strip=True).split()[0]

        bid_call = row.select_one(".optiontable__bidcall")
        ask_call = row.select_one(".optiontable__askcall")
        bid_put = row.select_one(".optiontable__bid")
        ask_put = row.select_one(".optiontable__askput")

        for opt_type in ["Call", "Put"]:
            link = row.select_one(f"a.optionlink.{opt_type}")
            if not link or "href" not in link.attrs:
                continue
            issue_id = next((p for p in link["href"].split("/") if p.isdigit()), None)
            bid_el, ask_el = (bid_call, ask_call) if opt_type == "Call" else (bid_put, ask_put)
            bid_val = _parse_eu_number(bid_el.get_text(strip=True)) if bid_el else None
            ask_val = _parse_eu_number(ask_el.get_text(strip=True)) if ask_el else None
            options.append(
                {
                    "type": opt_type,
                    "expiry": expiry_title,
                    "strike": strike,
                    "issue_id": issue_id,
                    "bid": bid_val,
                    "ask": ask_val,
                }
            )
    return options


def fetch_option_chain(timeout=10):
    """Haalt alle AH-expiraties op (inclusief de 'Meer opties' via POST)."""
    print("[scraper] Fetching option chain from Beursduivel...")
    r = requests.get(MAIN_URL, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # ASP.NET hidden fields voor postback
    viewstate = soup.find("input", {"id": "__VIEWSTATE"})
    event_validation = soup.find("input", {"id": "__EVENTVALIDATION"})
    hidden_fields = {}
    if viewstate:
        hidden_fields["__VIEWSTATE"] = viewstate["value"]
    if event_validation:
        hidden_fields["__EVENTVALIDATION"] = event_validation["value"]

    all_options = []

    for section in soup.select("section.contentblock"):
        title_el = section.find("h3", class_="titlecontent")
        expiry_title = title_el.get_text(strip=True) if title_el else "Unknown"
        if not re.search(r"\(AEX\s*/\s*AH\)", expiry_title):
            if VERBOSE:
                print(f"[skip] Ignoring expiry '{expiry_title}' (not main AH series)")
            continue

        print(f"[scraper] Processing expiry: {expiry_title}")
        partial = parse_option_table(str(section), expiry_title)
        all_options.extend(partial)

        # Simuleer 'Meer opties' klik via POST
        more_link = section.find("a", class_="morelink")
        if more_link and "id" in more_link.attrs:
            event_target = more_link["id"].replace("_", "$")
            payload = {
                "__EVENTTARGET": event_target,
                "__EVENTARGUMENT": "",
                **hidden_fields,
            }
            try:
                r2 = requests.post(MAIN_URL, headers=HEADERS, data=payload, timeout=timeout)
                r2.raise_for_status()
                more_options = parse_option_table(r2.text, expiry_title)
                if more_options:
                    print(f"  [expansion] Found +{len(more_options)} extra options via postback.")
                    all_options.extend(more_options)
            except Exception as e:
                print(f"  [warn] Could not load more for {expiry_title}: {e}")

    print(f"[scraper] Option chain fetched: {len(all_options)} total options.")
    return all_options


# ------------------------
# 💾 DATABASE OPSLAG
# ------------------------


def cleanup_old_records(days_to_keep=30):
    """Clean up records older than specified days to prevent database bloat."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            DELETE FROM option_prices_live 
            WHERE created_at < DATE_SUB(NOW(), INTERVAL %s DAY)
        """,
            (days_to_keep,),
        )
        deleted_count = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        if deleted_count > 0:
            print(f"🧹 Cleaned up {deleted_count} records older than {days_to_keep} days.")
        return deleted_count
    except Exception as e:
        print(f"⚠️ Error during cleanup: {e}")
        return 0


def ensure_option_prices_live_table():
    """Maak de tabel option_prices_live aan als deze nog niet bestaat."""
    print("[table] Connecting to database to create table...")
    try:
        conn = get_connection()
        cur = conn.cursor()
        print("[table] Executing CREATE TABLE IF NOT EXISTS...")
        # Check if table exists and has old unique constraint
        cur.execute("SHOW TABLES LIKE 'option_prices_live'")
        table_exists = cur.fetchone()

        if table_exists:
            # Check if the old unique constraint exists
            cur.execute(
                """
                SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS 
                WHERE TABLE_NAME='option_prices_live' 
                AND CONSTRAINT_NAME='unique_option' 
                AND TABLE_SCHEMA=DATABASE()
            """
            )
            has_old_constraint = cur.fetchone()[0] > 0

            if has_old_constraint:
                print("[table] Dropping old unique constraint to enable historical records...")
                cur.execute("ALTER TABLE option_prices_live DROP INDEX unique_option")

                # Add new indexes if they don't exist
                try:
                    cur.execute(
                        "ALTER TABLE option_prices_live ADD INDEX idx_option_time (ticker, type, expiry, strike, created_at)"
                    )
                except:
                    pass  # Index might already exist
                try:
                    cur.execute(
                        "ALTER TABLE option_prices_live ADD INDEX idx_created_at (created_at)"
                    )
                except:
                    pass  # Index might already exist
        else:
            # Create new table with proper schema
            cur.execute(
                """
                CREATE TABLE option_prices_live (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    ticker VARCHAR(20) DEFAULT 'AD.AS',
                    type ENUM('Call', 'Put') NOT NULL,
                    expiry VARCHAR(50) NOT NULL,
                    strike DECIMAL(10,3) NOT NULL,
                    price DECIMAL(10,4),
                    bid DECIMAL(10,4),
                    ask DECIMAL(10,4),
                    iv DECIMAL(10,6),
                    delta DECIMAL(10,6),
                    gamma DECIMAL(10,6),
                    vega DECIMAL(10,6),
                    theta DECIMAL(10,6),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_option_time (ticker, type, expiry, strike, created_at),
                    INDEX idx_created_at (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            )
        print("[table] Committing table creation...")
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Table 'option_prices_live' verified or created.")
    except Exception as e:
        print(f"❌ Database connection or table creation failed: {e}")
        raise


def save_option_prices_live(options, spot_price):
    conn = get_connection()
    cur = conn.cursor()
    insert_query = """
        INSERT INTO option_prices_live (
            issue_id, expiry, type, strike, bid, ask, price,
            iv, delta, gamma, vega, theta, spot_price, fetched_at
        ) VALUES (
            %(issue_id)s, %(expiry)s, %(type)s, %(strike)s, %(bid)s, %(ask)s, %(price)s,
            %(iv)s, %(delta)s, %(gamma)s, %(vega)s, %(theta)s, %(spot_price)s, %(fetched_at)s
        )
        ON DUPLICATE KEY UPDATE
            bid=VALUES(bid),
            ask=VALUES(ask),
            price=VALUES(price),
            iv=VALUES(iv),
            delta=VALUES(delta),
            gamma=VALUES(gamma),
            vega=VALUES(vega),
            theta=VALUES(theta),
            spot_price=VALUES(spot_price),
            fetched_at=VALUES(fetched_at);
    """
    for o in options:
        cur.execute(insert_query, o)
    conn.commit()
    cur.close()
    conn.close()
    print(f"[db] Saved/updated {len(options)} records in option_prices_live.")


# ------------------------
# ⚙️ LIVE GREEKS BEREKENING
# ------------------------


def compute_and_store_live_greeks(options, spot_price):
    """Bereken Greeks en sla op in DB."""
    from datetime import datetime

    print(f"[greeks] Starting Greeks calculation for {len(options)} options...")
    print("[greeks] Creating table if needed...")
    ensure_option_prices_live_table()
    print("[greeks] Connecting to database...")
    conn = get_connection()
    cur = conn.cursor()
    print("[greeks] Database connection established.")

    today = date.today()
    results = []
    processed = 0

    for o in options:
        processed += 1
        if processed % 50 == 0:
            print(f"[greeks] Processed {processed}/{len(options)} options...")

        bid, ask = o.get("bid"), o.get("ask")
        if not bid or not ask or bid <= 0 or ask <= 0:
            continue

        price = 0.5 * (bid + ask)
        expiry_text = o["expiry"].split("(")[0].strip()

        try:
            month_map = {
                "Januari": 1,
                "Februari": 2,
                "Maart": 3,
                "April": 4,
                "Mei": 5,
                "Juni": 6,
                "Juli": 7,
                "Augustus": 8,
                "September": 9,
                "Oktober": 10,
                "November": 11,
                "December": 12,
            }
            parts = expiry_text.split()
            if len(parts) < 2:
                continue
            month = month_map.get(parts[0], 12)
            year = int(parts[1])
            expiry_date = date(year, month, 15)
        except Exception as e:
            if VERBOSE:
                print(f"[greeks] Failed to parse expiry '{expiry_text}': {e}")
            continue

        days = (expiry_date - today).days
        if days <= 0:
            continue

        t = max(days / 365, 0.001)
        r = risk_free_rate_for_days(days)
        is_call = o["type"].lower() == "call"

        try:
            K = float(str(o["strike"]).replace(",", "."))
        except (ValueError, TypeError):
            continue

        if K <= 0 or spot_price <= 0:
            continue

        try:
            sigma = implied_vol(price, spot_price, K, t, r, is_call)
            if math.isnan(sigma) or sigma <= 0:
                continue

            delta = bs_delta(spot_price, K, t, r, sigma, is_call)
            gamma = bs_gamma(spot_price, K, t, r, sigma)
            vega = bs_vega(spot_price, K, t, r, sigma)
            theta = bs_theta(spot_price, K, t, r, sigma, is_call)

            results.append(
                (o["type"], expiry_text, K, price, bid, ask, sigma, delta, gamma, vega, theta)
            )
        except Exception as e:
            if VERBOSE:
                print(f"[greeks] Error calculating Greeks for {o['type']} {K} {expiry_text}: {e}")
            continue

    print(
        f"[greeks] Calculated Greeks for {len(results)} valid options out of {len(options)} total."
    )

    if results:
        insert_query = """
            INSERT INTO option_prices_live
                (type, expiry, strike, price, bid, ask, iv, delta, gamma, vega, theta, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """
        # Add timestamp to each result
        timestamped_results = []
        current_time = datetime.now()
        for result in results:
            timestamped_results.append(result + (current_time,))

        cur.executemany(insert_query, timestamped_results)
        conn.commit()
        print(
            f"✅ {len(results)} historical records inserted into option_prices_live at {current_time.strftime('%H:%M:%S')}."
        )
    else:
        print("⚠️ No valid options to store.")
    cur.close()
    conn.close()


# ------------------------
# 🚀 ENTRYPOINT
# ------------------------


def run_once():
    """Run the scraper once (for testing or one-off execution)."""
    if not is_market_open():
        print("[scraper] ⏰ Market is closed (outside 9:00-17:00 CET, Mon-Fri). Skipping scrape.")
        return

    print("Fetching Beursduivel data...")
    options = fetch_option_chain()
    if not options:
        print("No options found.")
        return

    print(f"[scraper] Fetched {len(options)} options. Starting Greeks calculation...")
    spot_price = 36.84  # voorbeeld — je kunt later live fetchen met yfinance

    try:
        compute_and_store_live_greeks(options, spot_price)
        print("[scraper] ✅ Complete!")
    except Exception as e:
        print(f"[scraper] ❌ Failed to store Greeks in database: {e}")
        print(f"[scraper] Successfully fetched {len(options)} options, but could not store to DB.")
        # For debugging, show first few options
        print("[scraper] Sample options fetched:")
        for i, opt in enumerate(options[:5]):
            print(
                f"  {i+1}. {opt['type']} {opt['strike']} {opt['expiry']} - bid:{opt.get('bid')} ask:{opt.get('ask')}"
            )
        if len(options) > 5:
            print(f"  ... and {len(options)-5} more options")


def run_continuous():
    """Run the scraper continuously every 15 minutes during market hours."""
    print("[scraper] 🚀 Starting continuous live scraper (15min intervals during market hours)")
    print("[scraper] Market hours: 9:00-17:00 CET, Monday-Friday")
    print("[scraper] 📊 Historical mode: Every scrape creates a new timestamped record")

    last_cleanup_date = None

    while True:
        try:
            # Daily cleanup check (run once per day)
            today = datetime.now().date()
            if last_cleanup_date != today:
                print("[scraper] 🧹 Running daily cleanup...")
                cleanup_old_records(days_to_keep=30)
                last_cleanup_date = today

            if is_market_open():
                print(
                    f"[scraper] 📈 Market is open - running scrape at {datetime.now().strftime('%H:%M:%S')}"
                )
                run_once()
                print("[scraper] ⏳ Waiting 15 minutes until next scrape...")
                wait_minutes(15)
            else:
                import pytz

                now = datetime.now(pytz.timezone("Europe/Amsterdam"))
                print(
                    f"[scraper] 😴 Market closed ({now.strftime('%a %H:%M')}). Checking again in 30 minutes..."
                )
                wait_minutes(30)
        except KeyboardInterrupt:
            print("\n[scraper] 🛑 Scraper stopped by user")
            break
        except Exception as e:
            print(f"[scraper] ❌ Unexpected error in continuous loop: {e}")
            print("[scraper] Waiting 5 minutes before retrying...")
            wait_minutes(5)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--continuous":
        run_continuous()
    else:
        run_once()
