# -*- coding: utf-8 -*-
"""
app/etl/beursduivel_scraper.py
Scraper die ALLE AEX/AH opties ophaalt van Beursduivel (incl. 'Meer opties'),
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


def _safe_float(value):
    """Convert value to float or None if NaN/invalid."""
    if value is None:
        return None
    try:
        if math.isnan(float(value)) or math.isinf(float(value)):
            return None
        return float(value)
    except (ValueError, TypeError):
        return None


def _fetch_prev_iv_mid(cur, ticker, opt_type, expiry, strike):
    """Haal vorige iv_mid op voor dezelfde optie (laatste record)."""
    from decimal import Decimal

    # Convert strike to Decimal to match database format
    strike_decimal = Decimal(str(strike))
    cur.execute(
        """
        SELECT iv_mid FROM option_prices_live
        WHERE ticker=%s AND type=%s AND expiry=%s AND strike=%s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (ticker, opt_type, expiry, strike_decimal),
    )
    row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else None


# ------------------------
# 🧩 PARSER
# ------------------------


def fetch_spot_price(timeout=10):
    """Scrape de actuele spotprijs (laatste koers) van de Ahold Delhaize pagina."""
    try:
        print("[scraper] Fetching live spot price from Beursduivel...")
        r = requests.get(MAIN_URL, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        el = soup.find(id="11755LastPrice")
        if not el:
            print("[spot] ❌ Kon geen element met id='11755LastPrice' vinden.")
            return None

        txt = el.get_text(strip=True).replace(",", ".")
        spot = float(txt)
        print(f"[spot] ✅ Spotprijs gevonden: {spot:.3f} EUR")
        return spot
    except Exception as e:
        print(f"[spot] ⚠️ Fout bij het ophalen van spotprijs: {e}")
        return None


def parse_option_table(section_html: str, expiry_title: str):
    """Parse 1 optie-tabel (calls & puts) incl. sizes, last, volume & trades."""

    def _subline_text(el):
        if not el:
            return None
        sub = el.select_one(".optiontable--subline")
        return sub.get_text(strip=True) if sub else None

    def _subline_int(el):
        txt = _subline_text(el)
        if not txt:
            return None
        s = re.sub(r"[^\d]", "", txt)
        return int(s) if s.isdigit() else None

    def _main_number(el):
        """Grote getal in de cel (prijs of trades)."""
        if not el:
            return None
        txt = el.get_text(separator="|", strip=True).split("|")[0]
        return _parse_eu_number(txt)

    soup = BeautifulSoup(section_html, "html.parser")
    options = []

    for row in soup.select("tr"):
        strike_cell = row.select_one(".optiontable__focus")
        if not strike_cell:
            continue
        strike = strike_cell.get_text(strip=True).split()[0]

        # Cellen voor Call
        bid_call = row.select_one(".optiontable__bidcall")
        ask_call = row.select_one(".optiontable__askcall")
        last_call = row.select_one(".optiontable__pricecall")
        vol_call = row.select_one(".optiontable__volumecall")

        # Cellen voor Put
        bid_put = row.select_one(".optiontable__bid")
        ask_put = row.select_one(".optiontable__askput")
        # Soms 'priceput' of 'tradeput'
        last_put = row.select_one(".optiontable__priceput, .optiontable__tradeput")
        vol_put = row.select_one(".optiontable__volumeput")

        # Links / issue_id
        link_call = row.select_one("a.optionlink.Call")
        link_put = row.select_one("a.optionlink.Put")
        issue_call = next(
            (
                p
                for p in (
                    link_call["href"].split("/")
                    if link_call and "href" in link_call.attrs
                    else []
                )
                if p.isdigit()
            ),
            None,
        )
        issue_put = next(
            (
                p
                for p in (
                    link_put["href"].split("/")
                    if link_put and "href" in link_put.attrs
                    else []
                )
                if p.isdigit()
            ),
            None,
        )

        # --- CALL ---
        if link_call:
            options.append(
                {
                    "type": "Call",
                    "expiry": expiry_title,
                    "strike": strike,
                    "issue_id": issue_call,
                    "bid": _main_number(bid_call),
                    "ask": _main_number(ask_call),
                    "bid_size": _subline_int(bid_call),  # size onder bid
                    "ask_size": _subline_int(ask_call),  # size onder ask
                    "last_price": _main_number(last_call),
                    "last_time": _subline_text(last_call),  # "09:33"
                    # volume-kolom: groot getal = trades, subline = volume
                    "trades": int(_main_number(vol_call) or 0) if vol_call else None,
                    "volume": _subline_int(vol_call),
                }
            )

        # --- PUT ---
        if link_put:
            options.append(
                {
                    "type": "Put",
                    "expiry": expiry_title,
                    "strike": strike,
                    "issue_id": issue_put,
                    "bid": _main_number(bid_put),
                    "ask": _main_number(ask_put),
                    "bid_size": _subline_int(bid_put),
                    "ask_size": _subline_int(ask_put),
                    "last_price": _main_number(last_put),
                    "last_time": _subline_text(last_put),  # "10:18"
                    "trades": int(_main_number(vol_put) or 0) if vol_put else None,
                    "volume": _subline_int(vol_put),
                }
            )

    return options


def fetch_option_chain(timeout=10):
    """Haalt alle AH-expiraties op (incl. 'Meer opties' via POST)."""
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

        # 'Meer opties' via POST simuleren
        more_link = section.find("a", class_="morelink")
        if more_link and "id" in more_link.attrs:
            event_target = more_link["id"].replace("_", "$")
            payload = {
                "__EVENTTARGET": event_target,
                "__EVENTARGUMENT": "",
                **hidden_fields,
            }
            try:
                r2 = requests.post(
                    MAIN_URL, headers=HEADERS, data=payload, timeout=timeout
                )
                r2.raise_for_status()
                more_options = parse_option_table(r2.text, expiry_title)
                if more_options:
                    print(
                        f"  [expansion] Found +{len(more_options)} extra options via postback."
                    )
                    all_options.extend(more_options)
            except Exception as e:
                print(f"  [warn] Could not load more for {expiry_title}: {e}")

    print(f"[scraper] Option chain fetched: {len(all_options)} total options.")
    return all_options


# ------------------------
# 💾 DATABASE
# ------------------------


def cleanup_old_records(days_to_keep=30):
    """Verwijder oude records om de DB slank te houden."""
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
        deleted = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        if deleted > 0:
            print(f"🧹 Cleaned up {deleted} records older than {days_to_keep} days.")
        return deleted
    except Exception as e:
        print(f"⚠️ Error during cleanup: {e}")
        return 0


def ensure_option_prices_live_table():
    """Maak/upgrade de tabel `option_prices_live`."""
    print("[table] Connecting to database to verify/create table...")
    conn = get_connection()
    cur = conn.cursor()

    # Bestaat de tabel?
    cur.execute("SHOW TABLES LIKE 'option_prices_live'")
    exists = cur.fetchone()

    if not exists:
        print("[table] Creating fresh table with full schema...")
        cur.execute(
            """
            CREATE TABLE option_prices_live (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ticker VARCHAR(20) DEFAULT 'AD.AS',
                issue_id VARCHAR(32) NULL,
                type ENUM('Call','Put') NOT NULL,
                expiry VARCHAR(50) NOT NULL,
                strike DECIMAL(10,3) NOT NULL,

                -- quotes
                price DECIMAL(10,4),
                bid DECIMAL(10,4),
                ask DECIMAL(10,4),
                bid_size INT NULL,
                ask_size INT NULL,
                last_price DECIMAL(10,4) NULL,
                last_time DATETIME NULL,
                trades INT NULL,
                volume INT NULL,

                -- greeks
                iv DECIMAL(10,6),
                delta DECIMAL(10,6),
                gamma DECIMAL(10,6),
                vega DECIMAL(10,6),
                theta DECIMAL(10,6),

                spot_price DECIMAL(10,4) NULL,
                fetched_at DATETIME NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                -- moneyness and liquidity metrics
                moneyness DECIMAL(10,6) NULL,
                bidask_spread_pct DECIMAL(10,6) NULL,
                size_imbalance DECIMAL(10,6) NULL,

                INDEX idx_option_time (ticker, type, expiry, strike, created_at),
                INDEX idx_issue_time (issue_id, created_at),
                INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )
    else:
        # Oudere installs upgraden met ontbrekende kolommen/indexen
        print("[table] Upgrading table schema if needed...")
        alters = [
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS issue_id VARCHAR(32) NULL",
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS bid_size INT NULL",
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS ask_size INT NULL",
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS last_price DECIMAL(10,4) NULL",
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS last_time DATETIME NULL",
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS trades INT NULL",
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS volume INT NULL",
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS spot_price DECIMAL(10,4) NULL",
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS fetched_at DATETIME NULL",
            "ALTER TABLE option_prices_live ADD INDEX IF NOT EXISTS idx_option_time (ticker, type, expiry, strike, created_at)",
            "ALTER TABLE option_prices_live ADD INDEX IF NOT EXISTS idx_issue_time (issue_id, created_at)",
            "ALTER TABLE option_prices_live ADD INDEX IF NOT EXISTS idx_created_at (created_at)",
            # Nieuwe IV-velden + afgeleiden
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS iv_bid DECIMAL(10,6) NULL",
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS iv_ask DECIMAL(10,6) NULL",
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS iv_mid DECIMAL(10,6) NULL",
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS iv_spread DECIMAL(10,6) NULL",
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS iv_delta_15m DECIMAL(10,6) NULL",
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS vpi DECIMAL(10,6) NULL",
            # Greek exposure columns (Greeks * position size)
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS delta_exposure DECIMAL(15,6) NULL",
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS gamma_exposure DECIMAL(15,6) NULL",
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS vega_exposure DECIMAL(15,6) NULL",
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS theta_exposure DECIMAL(15,6) NULL",
            # Moneyness and liquidity metrics
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS moneyness DECIMAL(10,6) NULL",
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS bidask_spread_pct DECIMAL(10,6) NULL",
            "ALTER TABLE option_prices_live ADD COLUMN IF NOT EXISTS size_imbalance DECIMAL(10,6) NULL",
        ]
        for stmt in alters:
            try:
                cur.execute(stmt)
            except Exception:
                pass

        # Verwijder evt. oude unieke index op (ticker,type,expiry,strike)
        try:
            cur.execute(
                """
                SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
                WHERE TABLE_NAME='option_prices_live'
                  AND CONSTRAINT_TYPE='UNIQUE'
                  AND CONSTRAINT_NAME='unique_option'
                  AND TABLE_SCHEMA=DATABASE()
                """
            )
            if cur.fetchone()[0] > 0:
                print("[table] Dropping legacy UNIQUE index unique_option...")
                cur.execute("ALTER TABLE option_prices_live DROP INDEX unique_option")
        except Exception:
            pass

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Table 'option_prices_live' verified/created.")


# (Historische) upsert-helper wordt niet gebruikt in deze live variant,
# laten we hem laten staan voor compatibiliteit maar niet aanroepen.
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
            bid=VALUES(bid), ask=VALUES(ask), price=VALUES(price),
            iv=VALUES(iv), delta=VALUES(delta), gamma=VALUES(gamma),
            vega=VALUES(vega), theta=VALUES(theta),
            spot_price=VALUES(spot_price), fetched_at=VALUES(fetched_at)
    """
    for o in options:
        cur.execute(insert_query, o)
    conn.commit()
    cur.close()
    conn.close()
    print(f"[db] Saved/updated {len(options)} records in option_prices_live.")


# ------------------------
# ⚙️ GREEKS + INSERT
# ------------------------


def compute_and_store_live_greeks(options, spot_price):
    """Bereken Greeks en sla volledige snapshot op."""
    print(f"[greeks] Starting Greeks calculation for {len(options)} options...")
    ensure_option_prices_live_table()
    conn = get_connection()
    cur = conn.cursor()

    today = date.today()
    rows = []
    processed = 0

    # helper: parse HH:MM -> DATETIME (vandaag)
    def _dt_from_hhmm(hhmm: str):
        if not hhmm or not re.match(r"^\d{2}:\d{2}$", hhmm):
            return None
        hh, mm = map(int, hhmm.split(":"))
        return datetime(today.year, today.month, today.day, hh, mm, 0)

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

    for o in options:
        processed += 1
        if processed % 50 == 0:
            print(f"[greeks] Processed {processed}/{len(options)} options...")

        bid, ask = o.get("bid"), o.get("ask")
        if not bid or not ask or bid is None or ask is None or bid <= 0 or ask <= 0:
            continue

        price_mid = 0.5 * (bid + ask)
        expiry_text = o["expiry"].split("(")[0].strip()

        # ruw: gebruik 15e vd maand als expiry-dag (zoals eerder)
        try:
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
            # Round to 3 decimal places to avoid floating-point precision issues
            K = round(K, 3)
        except (ValueError, TypeError):
            continue
        if K <= 0 or spot_price <= 0:
            continue

        try:
            # 1) IV's per kant en mid
            sigma_mid = implied_vol(price_mid, spot_price, K, t, r, is_call)
            if sigma_mid is None or math.isnan(sigma_mid) or sigma_mid <= 0:
                continue

            sigma_bid = (
                implied_vol(bid, spot_price, K, t, r, is_call)
                if bid and bid > 0
                else None
            )
            sigma_ask = (
                implied_vol(ask, spot_price, K, t, r, is_call)
                if ask and ask > 0
                else None
            )

            iv_spread = None
            if sigma_bid and sigma_ask and (sigma_bid > 0) and (sigma_ask > 0):
                iv_spread = max(sigma_ask - sigma_bid, 0.0)

            # 2) Greeks op basis van mid-IV (consistent)
            delta = bs_delta(spot_price, K, t, r, sigma_mid, is_call)
            gamma = bs_gamma(spot_price, K, t, r, sigma_mid)
            vega = bs_vega(spot_price, K, t, r, sigma_mid)
            theta = bs_theta(spot_price, K, t, r, sigma_mid, is_call)

            # 3) ΔIV vs vorige snapshot (zelfde optie)
            prev_iv_mid = _fetch_prev_iv_mid(cur, "AD.AS", o["type"], expiry_text, K)
            iv_delta_15m = None
            if prev_iv_mid is not None:
                iv_delta_15m = sigma_mid - prev_iv_mid

            # 4) VPI = ΔIV / IV_spread
            vpi = None
            if iv_spread is not None and iv_spread > 0 and iv_delta_15m is not None:
                vpi = iv_delta_15m / iv_spread

            # 5) Greek Exposures (assume standard 100-share contract size)
            contract_size = 100.0  # Standard option contract represents 100 shares

            # Calculate exposures based on standard option exposure formulas
            delta_exposure = (
                delta * contract_size * spot_price if delta is not None else None
            )
            gamma_exposure = (
                gamma * contract_size * (spot_price**2) if gamma is not None else None
            )
            vega_exposure = (
                vega * contract_size if vega is not None else None
            )  # Vega already in dollar terms
            theta_exposure = (
                theta * contract_size if theta is not None else None
            )  # Theta already in dollar terms

            # 6) Moneyness (S/K ratio)
            moneyness = spot_price / K if K and K > 0 else None

            # 7) Liquidity Proxies
            bidask_spread_pct = None
            if bid is not None and ask is not None and bid > 0 and ask > 0:
                mid_price = (bid + ask) / 2.0
                if mid_price > 0:
                    bidask_spread_pct = ((ask - bid) / mid_price) * 100.0

            size_imbalance = None
            if (
                o.get("bid_size") is not None
                and o.get("ask_size") is not None
                and o.get("bid_size") > 0
                and o.get("ask_size") > 0
            ):
                bid_size = float(o.get("bid_size"))
                ask_size = float(o.get("ask_size"))
                total_size = bid_size + ask_size
                if total_size > 0:
                    size_imbalance = (ask_size - bid_size) / total_size

            rows.append(
                {
                    "ticker": "AD.AS",
                    "issue_id": o.get("issue_id"),
                    "type": o["type"],
                    "expiry": expiry_text,
                    "strike": K,
                    "price": _safe_float(price_mid),  # bewaar mid
                    "bid": _safe_float(bid),
                    "ask": _safe_float(ask),
                    "bid_size": o.get("bid_size"),
                    "ask_size": o.get("ask_size"),
                    "last_price": _safe_float(o.get("last_price")),
                    "last_time": _dt_from_hhmm(o.get("last_time")),
                    "trades": o.get("trades"),
                    "volume": o.get("volume"),
                    # IV's en afgeleiden
                    "iv": _safe_float(sigma_mid),  # backward-compat (iv = iv_mid)
                    "iv_bid": _safe_float(sigma_bid),
                    "iv_ask": _safe_float(sigma_ask),
                    "iv_mid": _safe_float(sigma_mid),
                    "iv_spread": _safe_float(iv_spread),
                    "iv_delta_15m": _safe_float(iv_delta_15m),
                    "vpi": _safe_float(vpi),
                    # Greeks
                    "delta": _safe_float(delta),
                    "gamma": _safe_float(gamma),
                    "vega": _safe_float(vega),
                    "theta": _safe_float(theta),
                    # Greek Exposures (100-share contract basis)
                    "delta_exposure": _safe_float(delta_exposure),
                    "gamma_exposure": _safe_float(gamma_exposure),
                    "vega_exposure": _safe_float(vega_exposure),
                    "theta_exposure": _safe_float(theta_exposure),
                    # Moneyness and liquidity metrics
                    "moneyness": _safe_float(moneyness),
                    "bidask_spread_pct": _safe_float(bidask_spread_pct),
                    "size_imbalance": _safe_float(size_imbalance),
                    "spot_price": _safe_float(spot_price),
                    "fetched_at": datetime.now(),
                    "created_at": datetime.now(),
                }
            )
        except Exception as e:
            if VERBOSE:
                print(
                    f"[greeks] Error calculating Greeks for {o['type']} {K} {expiry_text}: {e}"
                )
            continue

    print(f"[greeks] Calculated + prepared {len(rows)} rows for insert.")

    if rows:
        insert_sql = """
            INSERT INTO option_prices_live
            (ticker, issue_id, type, expiry, strike,
             price, bid, ask, bid_size, ask_size,
             last_price, last_time, trades, volume,
             iv, iv_bid, iv_ask, iv_mid, iv_spread, iv_delta_15m, vpi,
             delta, gamma, vega, theta,
             delta_exposure, gamma_exposure, vega_exposure, theta_exposure,
             moneyness, bidask_spread_pct, size_imbalance,
             spot_price, fetched_at, created_at)
            VALUES
            (%(ticker)s, %(issue_id)s, %(type)s, %(expiry)s, %(strike)s,
             %(price)s, %(bid)s, %(ask)s, %(bid_size)s, %(ask_size)s,
             %(last_price)s, %(last_time)s, %(trades)s, %(volume)s,
             %(iv)s, %(iv_bid)s, %(iv_ask)s, %(iv_mid)s, %(iv_spread)s, %(iv_delta_15m)s, %(vpi)s,
             %(delta)s, %(gamma)s, %(vega)s, %(theta)s,
             %(delta_exposure)s, %(gamma_exposure)s, %(vega_exposure)s, %(theta_exposure)s,
             %(moneyness)s, %(bidask_spread_pct)s, %(size_imbalance)s,
             %(spot_price)s, %(fetched_at)s, %(created_at)s)
        """
        cur.executemany(insert_sql, rows)
        conn.commit()
        print(f"✅ {len(rows)} historical records inserted into option_prices_live.")
    else:
        print("⚠️ No valid options to store.")

    cur.close()
    conn.close()


# ------------------------
# 🚀 ENTRYPOINTS
# ------------------------


def run_once():
    """Run de scraper één keer."""
    if not is_market_open():
        print(
            "[scraper] ⏰ Market is closed (outside 9:16-17:45 CET, Mon-Fri). Skipping scrape."
        )
        return

    print("Fetching Beursduivel data...")
    options = fetch_option_chain()
    if not options:
        print("No options found.")
        return

    print(f"[scraper] Fetched {len(options)} options. Starting Greeks calculation...")
    spot_price = fetch_spot_price() or 36.84
    print(f"[scraper] Gebruik spotprijs = {spot_price:.3f}")

    try:
        compute_and_store_live_greeks(options, spot_price)
        print("[scraper] ✅ Complete!")
    except Exception as e:
        print(f"[scraper] ❌ Failed to store Greeks in database: {e}")
        print(
            f"[scraper] Successfully fetched {len(options)} options, but could not store to DB."
        )
        print("[scraper] Sample options fetched:")
        for i, opt in enumerate(options[:5]):
            print(
                f"  {i+1}. {opt['type']} {opt['strike']} {opt['expiry']} - bid:{opt.get('bid')} ask:{opt.get('ask')}"
            )
        if len(options) > 5:
            print(f"  ... and {len(options)-5} more options")


def run_continuous():
    """Run elke 15 min tijdens beursuren (met dagelijkse cleanup)."""
    print(
        "[scraper] 🚀 Starting continuous live scraper (15min intervals during market hours)"
    )
    print("[scraper] Market hours: 9:00-17:00 CET, Monday-Friday")
    print("[scraper] 📊 Historical mode: Every scrape creates a new timestamped record")

    last_cleanup_date = None
    while True:
        try:
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


def backfill_iv_fields_full():
    """
    Backfill iv_bid, iv_ask, iv_mid, iv_spread, iv_delta_15m, vpi
    voor bestaande records, o.b.v. bid/ask/spot/strike/expiry/type.
    """
    print("[backfill] Starting full IV backfill...")
    from app.compute.option_greeks import (
        implied_vol,
    )
    from app.utils.helpers import risk_free_rate_for_days
    from datetime import date
    import math

    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    today = date.today()

    cur.execute("SELECT COUNT(*) AS total FROM option_prices_live")
    total = cur.fetchone()["total"]
    batch_size = 500
    offset = 0
    updated = 0

    # maanden om expiry te parsen
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

    while True:
        cur.execute(
            """
            SELECT id, type, expiry, strike, bid, ask, spot_price, iv, iv_delta_15m
            FROM option_prices_live
            ORDER BY id ASC
            LIMIT %s OFFSET %s
        """,
            (batch_size, offset),
        )
        rows = cur.fetchall()
        if not rows:
            break

        updates = []
        for r in rows:
            try:
                bid = r["bid"]
                ask = r["ask"]
                if not bid or not ask or bid <= 0 or ask <= 0:
                    continue
                price_mid = 0.5 * (bid + ask)
                spot = r["spot_price"]
                if not spot or spot <= 0:
                    continue

                # expiry-date bepalen
                parts = r["expiry"].split()
                if len(parts) < 2:
                    continue
                month = month_map.get(parts[0], 12)
                year = int(parts[1])
                expiry_date = date(year, month, 15)
                days = (expiry_date - today).days
                if days <= 0:
                    continue
                t = max(days / 365, 0.001)
                rfr = risk_free_rate_for_days(days)
                is_call = r["type"].lower() == "call"

                K = float(r["strike"])
                sigma_bid = implied_vol(bid, spot, K, t, rfr, is_call)
                sigma_ask = implied_vol(ask, spot, K, t, rfr, is_call)
                sigma_mid = implied_vol(price_mid, spot, K, t, rfr, is_call)
                if any(
                    math.isnan(x) or x <= 0 for x in [sigma_bid, sigma_ask, sigma_mid]
                ):
                    continue

                iv_spread = max(sigma_ask - sigma_bid, 0.0)
                iv_delta = r["iv_delta_15m"]
                vpi = iv_delta / iv_spread if iv_delta and iv_spread > 0 else None

                updates.append(
                    (sigma_bid, sigma_ask, sigma_mid, iv_spread, vpi, r["id"])
                )

            except Exception:
                continue

        if updates:
            cur.executemany(
                """
                UPDATE option_prices_live
                SET iv_bid=%s, iv_ask=%s, iv_mid=%s, iv_spread=%s, vpi=%s
                WHERE id=%s
            """,
                updates,
            )
            conn.commit()
            updated += len(updates)
            print(f"[backfill] Updated {updated}/{total} records...")

        offset += batch_size

    cur.close()
    conn.close()
    print(
        f"[backfill] ✅ Done — updated ~{updated} records with full IV + VPI backfill."
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--continuous":
        run_continuous()
    else:
        run_once()
