# app/compute/compute_option_score.py
# -*- coding: utf-8 -*-
from app.db import get_connection

def compute_option_score(ticker="AD.AS"):
    conn = get_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fd_option_score (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ticker VARCHAR(10),
            peildatum DATE,
            call_put_ratio FLOAT,
            avg_skew FLOAT,
            price_skew FLOAT,
            macro_score FLOAT,
            micro_score FLOAT,
            total_score FLOAT,
            trend_signal VARCHAR(10),
            notes TEXT,
            iv_mean FLOAT,
            iv_skew FLOAT,
            iv_kurt FLOAT,
            atm_iv FLOAT,
            vega_total FLOAT,
            gamma_exposure FLOAT,
            delta_bias FLOAT,
            created_at DATETIME,
            UNIQUE KEY uniq_score (ticker, peildatum)
        )
    """)

    cur.execute("""
        SELECT DISTINCT g.peildatum
        FROM fd_option_greeks g
        LEFT JOIN fd_option_score s
          ON g.ticker = s.ticker AND g.peildatum = s.peildatum
        WHERE g.ticker = %s AND s.id IS NULL
        ORDER BY g.peildatum
    """, (ticker,))
    missing_days = [r["peildatum"] for r in cur.fetchall()]

    for d in missing_days:
        cur.execute("""
            SELECT call_put_ratio, delta, koers
            FROM fd_option_overview
            WHERE ticker=%s AND peildatum=%s
            LIMIT 1
        """, (ticker, d))
        macro = cur.fetchone()
        if not macro:
            continue

        cur.execute("""
            SELECT g.type, g.strike, g.iv, g.delta, g.gamma, g.vega, c.last
            FROM fd_option_greeks g
            JOIN fd_option_contracts c ON g.contract_id = c.id
            WHERE g.ticker=%s AND g.peildatum=%s
        """, (ticker, d))
        rows = cur.fetchall()
        if not rows:
            continue

        ivs = [r["iv"] for r in rows if r["iv"]]
        if not ivs:
            continue

        call_prices = [r["last"] for r in rows if r["type"].lower() == "call" and r["last"]]
        put_prices = [r["last"] for r in rows if r["type"].lower() == "put" and r["last"]]
        price_skew = (sum(put_prices)/len(put_prices)) / (sum(call_prices)/len(call_prices)) if call_prices and put_prices else None

        iv_mean = sum(ivs)/len(ivs)
        iv_skew = (sum([(x - iv_mean)**3 for x in ivs])/len(ivs)) / ((sum([(x - iv_mean)**2 for x in ivs])/len(ivs))**1.5)
        iv_kurt = (sum([(x - iv_mean)**4 for x in ivs])/len(ivs)) / ((sum([(x - iv_mean)**2 for x in ivs])/len(ivs))**2)

        vega_total = sum(r["vega"] for r in rows if r["vega"])
        gamma_exposure = sum(r["gamma"] * r["delta"] for r in rows if r["gamma"] and r["delta"])

        total_vega = sum(abs(r["vega"]) for r in rows if r["vega"])
        delta_bias = sum(r["delta"] * abs(r["vega"]) for r in rows if r["vega"]) / total_vega if total_vega else 0

        call_ivs = [r["iv"] for r in rows if r["type"].lower() == "call"]
        put_ivs = [r["iv"] for r in rows if r["type"].lower() == "put"]
        avg_skew = (sum(put_ivs)/len(put_ivs)) / (sum(call_ivs)/len(call_ivs)) if call_ivs and put_ivs else None

        macro_score = 0
        if macro["call_put_ratio"] > 1.2: macro_score += 1
        elif macro["call_put_ratio"] < 0.8: macro_score -= 1

        if macro["delta"] > 0.3: macro_score += 0.5
        elif macro["delta"] < -0.3: macro_score -= 0.5

        micro_score = 0
        if avg_skew:
            if avg_skew > 1.1: micro_score -= 0.5
            elif avg_skew < 0.9: micro_score += 0.5

        if delta_bias > 0.3: micro_score += 0.5
        elif delta_bias < -0.3: micro_score -= 0.5

        total_score = 0.6 * macro_score + 0.4 * micro_score
        signal = "Bullish" if total_score >= 0.3 else "Bearish" if total_score <= -0.3 else "Neutral"

        cur.execute("""
            INSERT INTO fd_option_score (
                ticker, peildatum, call_put_ratio, avg_skew, price_skew,
                macro_score, micro_score, total_score, trend_signal, notes,
                iv_mean, iv_skew, iv_kurt, atm_iv, vega_total, gamma_exposure, delta_bias, created_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            ON DUPLICATE KEY UPDATE
              call_put_ratio=VALUES(call_put_ratio),
              avg_skew=VALUES(avg_skew),
              price_skew=VALUES(price_skew),
              total_score=VALUES(total_score),
              trend_signal=VALUES(trend_signal),
              created_at=NOW()
        """, (
            ticker, d, macro["call_put_ratio"], avg_skew, price_skew,
            macro_score, micro_score, total_score, signal, f"IV={iv_mean:.2f}, skew={avg_skew:.2f}",
            iv_mean, iv_skew, iv_kurt, iv_mean, vega_total, gamma_exposure, delta_bias
        ))

        conn.commit()
        print(f"[{d}] {ticker} → {signal} ({total_score:.2f})")

    cur.close(); conn.close()
    print("✅ Alle nieuwe dagen verwerkt.")

if __name__ == "__main__":
    compute_option_score()