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


def d1_d2(S, K, t, r, sigma):
    if S <= 0 or K <= 0 or t <= 0 or sigma <= 0:
        return None, None
    vol_sqrt_t = sigma * math.sqrt(t)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * t) / vol_sqrt_t
    return d1, d1 - vol_sqrt_t


def bs_price(S, K, t, r, sigma, call=True):
    d1, d2 = d1_d2(S, K, t, r, sigma)
    df = math.exp(-r * t)
    return (S * Phi(d1) - K * df * Phi(d2)) if call else (K * df * Phi(-d2) - S * Phi(-d1))


def bs_delta(S, K, t, r, sigma, call=True):
    d1, _ = d1_d2(S, K, t, r, sigma)
    return Phi(d1) if call else (Phi(d1) - 1)


def bs_gamma(S, K, t, r, sigma):
    d1, _ = d1_d2(S, K, t, r, sigma)
    return phi(d1) / (S * sigma * math.sqrt(t))


def bs_vega(S, K, t, r, sigma):
    d1, _ = d1_d2(S, K, t, r, sigma)
    return S * phi(d1) * math.sqrt(t)


def implied_vol(price, S, K, t, r, call=True, tol=1e-6, max_iter=100):
    """Berekent implied volatility via Newton-Raphson."""
    sigma = 0.3
    for _ in range(max_iter):
        model = bs_price(S, K, t, r, sigma, call)
        diff = model - price
        if abs(diff) < tol:
            return sigma
        vega = bs_vega(S, K, t, r, sigma)
        if vega < 1e-8:
            break
        sigma -= diff / vega
        if sigma <= 0 or sigma > 5:
            break
    return float("nan")


def compute_greeks_for_day(ticker: str = "AD.AS", peildatum=None):
    """Bereken en sla Greeks op voor alle opties van één dag.
    - Neemt mid price (bid/ask) als beschikbaar, anders last.
    - Risk-free rate via Euribor helpers.
    """
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    if not peildatum:
        cur.execute(
            "SELECT MAX(peildatum) AS d FROM fd_option_contracts WHERE ticker=%s",
            (ticker,),
        )
        row = cur.fetchone()
        peildatum = row["d"] if row else None
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

    # Probeer spotprijs (S) uit overview, met fallbacks
    S: Optional[float] = None
    cur.execute(
        "SELECT koers FROM fd_option_overview WHERE ticker=%s AND peildatum=%s LIMIT 1",
        (ticker, peildatum),
    )
    row = cur.fetchone()
    if row and row.get("koers"):
        S = float(row["koers"])
    if not S:
        cur.execute(
            "SELECT koers FROM fd_option_overview WHERE ticker=%s ORDER BY peildatum DESC LIMIT 1",
            (ticker,),
        )
        row = cur.fetchone()
        if row and row.get("koers"):
            S = float(row["koers"])
    if not S:
        # Laatste redmiddel: yfinance slotkoers
        try:
            hist = yf.Ticker(ticker).history(period="5d")
            close = hist["Close"] if "Close" in hist else None
            if close is not None and not close.empty:
                S = float(close.iloc[-1])
        except Exception:
            S = None
    if not S or S <= 0:
        cur.close()
        conn.close()
        print(
            f"Geen geldige spotprijs gevonden voor {ticker} (peildatum {peildatum}); Greeks overgeslagen"
        )
        return
    cur.close()

    results = []
    for c in contracts:
        # prijs: mid(bid,ask) of last
        price = None
        if c.get("bid") and c.get("ask") and c["bid"] > 0 and c["ask"] > 0:
            price = 0.5 * (c["bid"] + c["ask"])
        elif c.get("last") and c["last"] > 0:
            price = c["last"]
        if not price:
            continue

        K = c["strike"]
        days = (c["expiry"] - peildatum).days
        t = max(days / 365.0, 0.001)
        r = risk_free_rate_for_days(days)
        is_call = c["type"].lower() == "call"

        sigma = implied_vol(price, S, K, t, r, is_call)
        if math.isnan(sigma):
            continue
        delta = bs_delta(S, K, t, r, sigma, is_call)
        gamma = bs_gamma(S, K, t, r, sigma)
        vega = bs_vega(S, K, t, r, sigma)

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
                "created_at": datetime.now(),
            }
        )

    # Opslaan
    if results:
        cur = conn.cursor()
        for r in results:
            cur.execute(
                """
                INSERT INTO fd_option_greeks
                  (contract_id, ticker, peildatum, expiry, strike, type, price, iv, delta, gamma, vega, created_at)
                VALUES
                  (%(contract_id)s,%(ticker)s,%(peildatum)s,%(expiry)s,%(strike)s,%(type)s,%(price)s,%(iv)s,%(delta)s,%(gamma)s,%(vega)s,%(created_at)s)
                ON DUPLICATE KEY UPDATE
                  price=VALUES(price), iv=VALUES(iv), delta=VALUES(delta),
                  gamma=VALUES(gamma), vega=VALUES(vega), created_at=VALUES(created_at)
                """,
                r,
            )
        conn.commit()
        cur.close()

    conn.close()
    print(f"{len(results)} Greeks berekend voor {ticker} ({peildatum})")


if __name__ == "__main__":
    compute_greeks_for_day()
