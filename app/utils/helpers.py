# app/utils/helpers.py
# -*- coding: utf-8 -*-
"""
Hulpfuncties voor parsing, dataconversie, scraping en tijdlogica.
Gebruikt door ETL-scripts, API’s en compute-modules.
"""

import re
import math
import pytz
import datetime as dt
import requests
from bs4 import BeautifulSoup

# -----------------------------
# 🌍 Algemene configuratie
# -----------------------------
BASE_URL = "https://www.beursduivel.be"
TIMEZONE = pytz.timezone("Europe/Amsterdam")
# Market hours: 9:16 AM - 5:45 PM Amsterdam time
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 16
MARKET_CLOSE_HOUR = 17
MARKET_CLOSE_MINUTE = 45

# =====================================================
# 🧮 NUMMER-CONVERSIES
# =====================================================


def _to_int(value):
    """Converteer Europese string naar int, retourneer None bij fout."""
    if not value or value in ("--", ""):
        return None
    try:
        s = str(value).replace(".", "").replace(",", "").replace(" ", "")
        return int(s)
    except ValueError:
        return None


def _to_float(value):
    """Converteer Europese string naar float, retourneer None bij fout."""
    if not value or value in ("--", ""):
        return None
    try:
        s = str(value).replace(".", "").replace(",", ".").replace("\xa0", "").strip()
        return float(s)
    except ValueError:
        return None


def _parse_eu_number(s: str) -> float | None:
    """Parseer getal met Europese notatie ('.' duizendtallen, ',' decimalen)."""
    if not s:
        return None
    s = s.strip().replace("\xa0", "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _to_float_nl(s: str) -> float | None:
    """Parseer floats met NL notatie (gebruikt in FD-scrapers)."""
    if not s:
        return None
    s = s.strip().replace(".", "").replace("\xa0", "").replace(" ", "").replace(",", ".")
    m = re.search(r"-?\d+(\.\d+)?", s)
    return float(m.group(0)) if m else None


def _to_int_nl(s: str) -> int | None:
    """Parseer ints met NL notatie (gebruikt in FD-scrapers)."""
    if not s:
        return None
    s = s.strip().replace(".", "").replace("\xa0", "").replace(" ", "")
    m = re.search(r"-?\d+", s)
    return int(m.group(0)) if m else None


def _to_date(value):
    """Converteer DD-MM-YY of DD-MM-YYYY string naar datetime.date."""
    if value in (None, "--", ""):
        return None
    for fmt in ("%d-%m-%y", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


# =====================================================
# 🕒 TIJD / MARKTLOGICA
# =====================================================


def is_market_open() -> bool:
    """
    Controleer of de huidige tijd binnen beursuren (09:16–17:45 Amsterdam, Ma-Vr) valt.
    """
    now = dt.datetime.now(TIMEZONE)
    # Check if it's a weekday (Monday=0, Sunday=6)
    is_weekday = now.weekday() < 5  # Monday=0 through Friday=4

    if not is_weekday:
        return False

    # Convert current time to minutes since midnight for easier comparison
    current_minutes = now.hour * 60 + now.minute
    market_open_minutes = MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MINUTE  # 9:16 = 556 minutes
    market_close_minutes = MARKET_CLOSE_HOUR * 60 + MARKET_CLOSE_MINUTE  # 17:45 = 1065 minutes

    return market_open_minutes <= current_minutes <= market_close_minutes


def wait_minutes(minutes: int):
    """
    Slaap helper (gebruikt voor loops/schedulers).
    """
    import time

    print(f"⏳ Wachten {minutes} minuten...")
    time.sleep(minutes * 60)


# =====================================================
# 🔗 URL / SCRAPING HELPERS
# =====================================================


def clean_href(href: str) -> str:
    """
    Maakt relatieve FD/Beursduivel URL’s compleet.
    Bijv: '../../../...' -> 'https://www.beursduivel.be/...'
    """
    if not href:
        return href
    href = href.replace("../../../", "/").lstrip("/")
    return f"{BASE_URL}/{href}"


def fetch_html(url: str, headers=None, timeout=20) -> BeautifulSoup:
    """
    Haalt HTML op met foutafhandeling en geeft BeautifulSoup-object terug.
    """
    headers = headers or {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


# =====================================================
# 💰 ECB / EURIBOR HELPERS
# =====================================================

EURIBOR_CACHE = {}


def get_current_euribor(months=1) -> float:
    """
    Haalt actuele Euribor-rente op (1m, 3m, 6m, 12m) via de ECB API.
    Valide fallbackwaarden bij netwerkfout.
    """
    try:
        if months == 12:
            url = "https://data-api.ecb.europa.eu/service/data/FM/M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA?format=jsondata&lastNObservations=1"
        else:
            url = f"https://data-api.ecb.europa.eu/service/data/FM/M.U2.EUR.RT.MM.EURIBOR{months}MD_.HSTA?format=jsondata&lastNObservations=1"

        r = requests.get(url, timeout=10)
        data = r.json()
        val = list(data["dataSets"][0]["series"].values())[0]["observations"]["0"][0]
        return float(val) / 100

    except Exception as e:
        print(f"⚠️ Euribor API mislukt ({months}m): {e}")
        return {1: 0.0187, 3: 0.0206, 6: 0.0210, 12: 0.0216}.get(months, 0.02)


def risk_free_rate_for_days(days: int) -> float:
    """
    Bepaalt risk-free rate (Euribor) op basis van looptijd in dagen.
    Cachet resultaten om API-calls te beperken.
    """
    global EURIBOR_CACHE
    if days <= 30:
        key = 1
    elif days <= 90:
        key = 3
    elif days <= 180:
        key = 6
    else:
        key = 12

    if key not in EURIBOR_CACHE:
        EURIBOR_CACHE[key] = get_current_euribor(key)

    return EURIBOR_CACHE[key]


# =====================================================
# 🧾 STRING HELPERS
# =====================================================


def safe_str(val) -> str:
    """Converteert None of NaN naar lege string voor veilige DB-ops."""
    if val is None:
        return ""
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return ""
    return str(val)


def normalize_expiry(expiry: str) -> str:
    """Maak expiry-strings consistent (titelcase, zonder %20)."""
    return expiry.replace("%20", " ").strip().title()


def normalize_strike(strike: str) -> str:
    """Normaliseer strikeprijs (verwijdert komma’s/punten en cast naar int-string)."""
    return strike.replace(",", ".").split(".")[0]


# =====================================================
# 🧰 PRINT / LOGGING HELPERS
# =====================================================


def log_section(title: str):
    """Druk nette sectiekop in console."""
    print("\n" + "=" * 60)
    print(f"🔹 {title}")
    print("=" * 60)
