# app/compute/option_greeks.py
# -*- coding: utf-8 -*-
import math
from datetime import datetime
from typing import Optional
import yfinance as yf
from app.db import get_connection
from app.utils.helpers import risk_free_rate_for_days

SQRT_2PI = math.sqrt(2 * math.pi)


def phi(x):
    return math.exp(-0.5 * x * x) / SQRT_2PI


def Phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


# -------------------------------
# Black-Scholes met dividend yield (q)
# -------------------------------
def d1_d2(S, K, t, r, sigma, q=0.034):
    """Bereken d1 en d2 met dividend yield q."""
    if S <= 0 or K <= 0 or t <= 0 or sigma <= 0:
        return None, None
    vol_sqrt_t = sigma * math.sqrt(t)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * t) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    return d1, d2


def bs_price(S, K, t, r, sigma, call=True, q=0.034):
    """Optieprijs met dividend yield."""
    d1, d2 = d1_d2(S, K, t, r, sigma, q)
    if d1 is None or d2 is None:
        return float("nan")
    df_r = math.exp(-r * t)
    df_q = math.exp(-q * t)
    if call:
        return S * df_q * Phi(d1) - K * df_r * Phi(d2)
    else:
        return K * df_r * Phi(-d2) - S * df_q * Phi(-d1)


def bs_delta(S, K, t, r, sigma, call=True, q=0.034):
    d1, _ = d1_d2(S, K, t, r, sigma, q)
    df_q = math.exp(-q * t)
    if call:
        return df_q * Phi(d1)
    else:
        return -df_q * Phi(-d1)


def bs_gamma(S, K, t, r, sigma, q=0.034):
    d1, _ = d1_d2(S, K, t, r, sigma, q)
    df_q = math.exp(-q * t)
    return (df_q * phi(d1)) / (S * sigma * math.sqrt(t))


def bs_vega(S, K, t, r, sigma, q=0.034):
    """Vega per 1 vol punt (0.01) en per contract (×100)."""
    d1, _ = d1_d2(S, K, t, r, sigma, q)
    df_q = math.exp(-q * t)
    return df_q * S * phi(d1) * math.sqrt(t) * 0.01


def bs_theta(S, K, t, r, sigma, call=True, q=0.034):
    """Theta per dag, per contract (×100 / 365)."""
    d1, d2 = d1_d2(S, K, t, r, sigma, q)
    if d1 is None or d2 is None:
        return float("nan")
    df_q = math.exp(-q * t)
    df_r = math.exp(-r * t)
    first_term = -(S * df_q * phi(d1) * sigma) / (2 * math.sqrt(t))
    if call:
        second_term = q * S * df_q * Phi(d1) - r * K * df_r * Phi(d2)
    else:
        second_term = -q * S * df_q * Phi(-d1) + r * K * df_r * Phi(-d2)
    theta_annual = first_term + second_term
    return theta_annual / 365.0  # per dag, per contract


# -------------------------------
# Implied Volatility
# -------------------------------
def implied_vol(price, S, K, t, r, call=True, q=0.034, tol=1e-6, max_iter=100):
    """Berekent implied volatility via Newton-Raphson."""
    sigma = 0.3
    for _ in range(max_iter):
        model = bs_price(S, K, t, r, sigma, call, q)
        diff = model - price
        if abs(diff) < tol:
            return sigma

        # Calculate raw vega for Newton-Raphson (not scaled for contracts/vol points)
        d1, _ = d1_d2(S, K, t, r, sigma, q)
        if d1 is None:
            break
        df_q = math.exp(-q * t)
        vega = df_q * S * phi(d1) * math.sqrt(t)  # raw vega

        if vega < 1e-8:
            break
        sigma -= diff / vega
        if sigma <= 0 or sigma > 5:
            break
    return float("nan")


# -------------------------------
# Hoofdfunctie
# -------------------------------
def compute_greeks_for_day(ticker: str = "AD.AS", peildatum=None):
    """Bereken en sla Greeks op voor alle opties van één dag."""
    conn = get_connection()
    cur = conn.cursor(dictionary=True)

    # Bepaal peildatum
    if not peildatum:
        cur.execute(
            "SELECT MAX(peildatum) AS d FROM fd_option_contracts WHERE ticker=%s",
            (ticker,),
        )
        row = cur.fetchone()
        peildatum = row["d"] if row else None

    # Convert string to date if needed
    if isinstance(peildatum, str):
        peildatum = datetime.strptime(peildatum, "%Y-%m-%d").date()

    if not peildatum:
        cur.close()
        conn.close()
        print(f"Geen contracten gevonden voor {ticker}; geen peildatum beschikbaar")
        return

    cur.execute(
        """
        SELECT id, expiry, strike, type, bid, ask, last
        FROM fd_option_contracts
        WHERE ticker=%s AND peildatum=%s
        """,
        (ticker, peildatum),
    )
    contracts = cur.fetchall() or []
    if not contracts:
        cur.close()
        conn.close()
        print(f"Geen opties gevonden voor {ticker} op {peildatum}; niets te berekenen")
        return

    # Spotprijs bepalen
    S: Optional[float] = None
    print(f"  Zoeken spotprijs voor {ticker} op {peildatum}")

    # Eerst proberen voor specifieke datum
    cur.execute(
        "SELECT koers FROM fd_option_overview WHERE ticker=%s AND peildatum=%s LIMIT 1",
        (ticker, peildatum),
    )
    row = cur.fetchone()
    if row and row.get("koers"):
        S = float(row["koers"])
        print(f"  ✓ Spotprijs gevonden voor datum: {S}")

    # Als niet gevonden, neem meest recente
    if not S:
        print("  Geen spotprijs voor datum, zoeken meest recente...")
        cur.execute(
            "SELECT koers, peildatum FROM fd_option_overview WHERE ticker=%s ORDER BY peildatum DESC LIMIT 1",
            (ticker,),
        )
        row = cur.fetchone()
        if row and row.get("koers"):
            S = float(row["koers"])
            print(f"  ✓ Meest recente spotprijs: {S} (van {row.get('peildatum')})")

    # Als nog steeds niet gevonden, probeer yfinance
    if not S:
        print("  Geen DB spotprijs, proberen yfinance...")
        try:
            hist = yf.Ticker(ticker).history(period="5d")
            if "Close" in hist and not hist["Close"].empty:
                S = float(hist["Close"].iloc[-1])
                print(f"  ✓ yfinance spotprijs: {S}")
        except Exception as e:
            print(f"  ✗ yfinance error: {e}")
            S = None

    if not S or S <= 0:
        cur.close()
        conn.close()
        print(
            f"  ✗ Geen geldige spotprijs gevonden voor {ticker} (peildatum {peildatum}); Greeks overgeslagen"
        )
        return
    cur.close()

    # Berekeningen uitvoeren
    results = []
    contracts_without_price = 0
    contracts_without_iv = 0

    print(f"  Verwerken {len(contracts)} contracten met spotprijs {S}")

    for c in contracts:
        price = None
        if c.get("bid") and c.get("ask") and c["bid"] > 0 and c["ask"] > 0:
            price = 0.5 * (c["bid"] + c["ask"])
        elif c.get("last") and c["last"] > 0:
            price = c["last"]
        if not price:
            contracts_without_price += 1
            continue

        K = c["strike"]
        days = (c["expiry"] - peildatum).days
        t = max(days / 365.0, 0.001)
        rf = risk_free_rate_for_days(days)
        is_call = c["type"].lower() == "call"

        sigma = implied_vol(price, S, K, t, rf, is_call)
        if math.isnan(sigma):
            contracts_without_iv += 1
            continue

        delta = bs_delta(S, K, t, rf, sigma, is_call)
        gamma = bs_gamma(S, K, t, rf, sigma)
        vega = bs_vega(S, K, t, rf, sigma)
        theta = bs_theta(S, K, t, rf, sigma, is_call)

        # Check for NaN values and skip if any Greek is NaN
        if any(math.isnan(x) for x in [delta, gamma, vega, theta]):
            contracts_without_iv += 1
            continue

        results.append(
            {
                "contract_id": c["id"],
                "ticker": ticker,
                "peildatum": peildatum,
                "expiry": c["expiry"],
                "strike": K,
                "type": c["type"],
                "price": price,
                "iv": sigma,
                "delta": delta,
                "gamma": gamma,
                "vega": vega,
                "theta": theta,
                "created_at": datetime.now(),
            }
        )

    # Opslaan in DB
    if results:
        cur = conn.cursor()
        insert_query = """
            INSERT INTO fd_option_greeks (
                contract_id, ticker, peildatum, expiry, strike, type, price, iv, delta, gamma, vega, theta, created_at
            )
            VALUES (
                %(contract_id)s, %(ticker)s, %(peildatum)s, %(expiry)s, %(strike)s, %(type)s,
                %(price)s, %(iv)s, %(delta)s, %(gamma)s, %(vega)s, %(theta)s, %(created_at)s
            )
            ON DUPLICATE KEY UPDATE
                price = VALUES(price),
                iv = VALUES(iv),
                delta = VALUES(delta),
                gamma = VALUES(gamma),
                vega = VALUES(vega),
                theta = VALUES(theta),
                created_at = VALUES(created_at)
        """
        for r in results:
            cur.execute(insert_query, r)
        conn.commit()
        cur.close()

    conn.close()
    print(f"  {len(results)} Greeks berekend voor {ticker} ({peildatum})")
    if contracts_without_price > 0:
        print(f"  ⚠️ {contracts_without_price} contracten overgeslagen (geen prijs)")
    if contracts_without_iv > 0:
        print(f"  ⚠️ {contracts_without_iv} contracten overgeslagen (geen IV convergentie)")


def compute_all_missing_greeks(ticker: str = "AD.AS"):
    """Bereken Greeks voor alle dagen waar ze nog ontbreken."""
    conn = get_connection()
    cur = conn.cursor(dictionary=True)

    # Vind peildata waar vega waarden ontbreken (ook voor bestaande Greeks records)
    cur.execute(
        """
        SELECT
            c.peildatum,
            COUNT(c.id) as total_contracts,
            COUNT(g.contract_id) as existing_greeks,
            COUNT(g.vega) as vega_count,
            COUNT(g.theta) as theta_count,
            ROUND(COUNT(g.vega) / COUNT(c.id) * 100, 1) as vega_pct
        FROM fd_option_contracts c
        LEFT JOIN fd_option_greeks g ON c.id = g.contract_id
        WHERE c.ticker = %s
        GROUP BY c.peildatum
        HAVING vega_pct < 50
        ORDER BY c.peildatum
    """,
        (ticker,),
    )

    missing_dates = cur.fetchall()

    # Debug: laat zien wat we gevonden hebben
    print(f"Query resultaat: {len(missing_dates)} datums met ontbrekende vega waarden")
    for date in missing_dates:
        print(
            f"  - {date['peildatum']}: {date['vega_count']}/{date['total_contracts']} vega ({date['vega_pct']}%), theta: {date['theta_count']}"
        )

    cur.close()
    conn.close()

    if not missing_dates:
        print(f"Alle Greeks hebben voldoende vega coverage voor {ticker}")
        return

    print(f"Gevonden {len(missing_dates)} datums met <50% vega coverage voor {ticker}")

    # Bereken Greeks voor elke datum met ontbrekende vega waarden
    for row in missing_dates:
        peildatum = row["peildatum"]
        vega_pct = row["vega_pct"]
        print(f"Berekenen Greeks voor {ticker} op {peildatum} (huidige vega coverage: {vega_pct}%)")
        compute_greeks_for_day(ticker, peildatum)


if __name__ == "__main__":
    # Gebruik compute_all_missing_greeks() om alle ontbrekende Greeks te berekenen
    # of compute_greeks_for_day() voor één specifieke datum
    compute_all_missing_greeks()
