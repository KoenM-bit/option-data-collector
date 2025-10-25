# -*- coding: utf-8 -*-
"""
compute_option_score.py — verbeterde versie
Berekent dagelijkse optiemarkt-scores met Greeks-data (IV, Vega, Gamma)
en slaat resultaten op in fd_option_score, inclusief price skew.
"""

import mysql.connector
from datetime import datetime
import math

def get_connection():
    return mysql.connector.connect(
        host="192.168.1.200",
        user="remoteuser",
        password="T3l3foon32#123",
        database="optionsdb",
        port=3306
    )

def compute_option_score(ticker="AD.AS"):
    conn = get_connection()
    cur = conn.cursor(dictionary=True)

    # ✅ Tabeldefinitie met nieuwe kolom price_skew
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

    # Alle dagen met Greeks maar nog geen score
    cur.execute("""
        SELECT DISTINCT g.peildatum
        FROM fd_option_greeks g
        LEFT JOIN fd_option_score s
          ON g.ticker = s.ticker AND g.peildatum = s.peildatum
        WHERE g.ticker = %s AND s.id IS NULL
        ORDER BY g.peildatum
    """, (ticker,))
    missing_days = [r["peildatum"] for r in cur.fetchall()]

    if not missing_days:
        print("Alle beschikbare dagen zijn al gescoord.")
        cur.close()
        conn.close()
        return

    print(f"{len(missing_days)} dag(en) zonder score voor {ticker}: {missing_days}")

    for d in missing_days:
        # Haal macrodata
        cur.execute("""
            SELECT call_put_ratio, delta, koers
            FROM fd_option_overview
            WHERE ticker=%s AND peildatum=%s
            LIMIT 1
        """, (ticker, d))
        macro = cur.fetchone()
        if not macro:
            print(f"⚠️ Geen macrodata voor {d}")
            continue

        # Haal Greeks + contractprijzen
        cur.execute("""
            SELECT g.type, g.strike, g.iv, g.delta, g.gamma, g.vega, c.last
            FROM fd_option_greeks g
            JOIN fd_option_contracts c
              ON g.contract_id = c.id
            WHERE g.ticker=%s AND g.peildatum=%s
        """, (ticker, d))
        rows = cur.fetchall()
        if not rows:
            print(f"⚠️ Geen Greeks-data voor {d}")
            continue

        ivs = [r["iv"] for r in rows if r["iv"] and not math.isnan(r["iv"])]
        if not ivs:
            continue

        # ---- Price skew (gemiddelde prijs van puts vs calls) ----
        call_prices = [r["last"] for r in rows if r["type"].lower() == "call" and r["last"]]
        put_prices  = [r["last"] for r in rows if r["type"].lower() == "put" and r["last"]]
        price_skew = (sum(put_prices)/len(put_prices)) / (sum(call_prices)/len(call_prices)) if call_prices and put_prices else None

        # ---- Implied volatility distributie ----
        iv_mean = sum(ivs) / len(ivs)
        iv_skew = (sum([(x - iv_mean)**3 for x in ivs]) / len(ivs)) / (sum([(x - iv_mean)**2 for x in ivs]) / len(ivs))**1.5 if len(ivs) > 2 else 0
        iv_kurt = (sum([(x - iv_mean)**4 for x in ivs]) / len(ivs)) / (sum([(x - iv_mean)**2 for x in ivs]) / len(ivs))**2 if len(ivs) > 3 else 0

        # ---- Vega / Gamma Exposure ----
        vega_total = sum(r["vega"] for r in rows if r["vega"])
        gamma_exposure = sum(r["gamma"] * r["delta"] for r in rows if r["gamma"] and r["delta"])

        # ---- Delta Bias (gewogen op Vega) ----
        total_vega = sum(abs(r["vega"]) for r in rows if r["vega"])
        delta_bias = sum(r["delta"] * abs(r["vega"]) for r in rows if r["vega"]) / total_vega if total_vega > 0 else 0

        # ---- ATM IV ----
        spot = macro["koers"]
        atm_strike = min(rows, key=lambda r: abs(r["strike"] - spot))["strike"]
        atm_iv = next((r["iv"] for r in rows if abs(r["strike"] - atm_strike) < 0.001), iv_mean)

        # ---- Call-Put IV skew ----
        call_ivs = [r["iv"] for r in rows if r["type"].lower() == "call"]
        put_ivs = [r["iv"] for r in rows if r["type"].lower() == "put"]
        avg_skew = 0
        if call_ivs and put_ivs:
            avg_skew = (sum(put_ivs) / len(put_ivs)) / (sum(call_ivs) / len(call_ivs))

        # ---- Scores ----
        macro_score = 0
        if macro["call_put_ratio"] > 1.2:
            macro_score += 1
        elif macro["call_put_ratio"] < 0.8:
            macro_score -= 1

        if macro["delta"] > 0.3:
            macro_score += 0.5
        elif macro["delta"] < -0.3:
            macro_score -= 0.5

        micro_score = 0
        if avg_skew:
            if avg_skew > 1.1:
                micro_score -= 0.5
            elif avg_skew < 0.9:
                micro_score += 0.5

        if delta_bias > 0.3:
            micro_score += 0.5
        elif delta_bias < -0.3:
            micro_score -= 0.5

        total_score = 0.6 * macro_score + 0.4 * micro_score

        if total_score >= 0.3:
            signal = "Bullish"
        elif total_score <= -0.3:
            signal = "Bearish"
        else:
            signal = "Neutral"

        # ✅ Format veilig een string voor price_skew
        if price_skew is not None and not math.isnan(price_skew):
            price_skew_str = f"{price_skew:.2f}"
        else:
            price_skew_str = "NA"

        notes = (
            f"CP={macro['call_put_ratio']:.2f}, IVskew={avg_skew:.2f}, "
            f"PriceSkew={price_skew_str}, IV={iv_mean:.2f}, "
            f"Δbias={delta_bias:.2f}, Vega={vega_total:.1f}, Γexp={gamma_exposure:.3f}"
        )


        # ✅ Opslaan inclusief price_skew
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
              macro_score=VALUES(macro_score),
              micro_score=VALUES(micro_score),
              total_score=VALUES(total_score),
              trend_signal=VALUES(trend_signal),
              notes=VALUES(notes),
              iv_mean=VALUES(iv_mean),
              iv_skew=VALUES(iv_skew),
              iv_kurt=VALUES(iv_kurt),
              atm_iv=VALUES(atm_iv),
              vega_total=VALUES(vega_total),
              gamma_exposure=VALUES(gamma_exposure),
              delta_bias=VALUES(delta_bias),
              created_at=NOW()
        """, (
            ticker, d,
            macro["call_put_ratio"], avg_skew, price_skew,
            macro_score, micro_score, total_score, signal, notes,
            iv_mean, iv_skew, iv_kurt, atm_iv, vega_total, gamma_exposure, delta_bias
        ))

        conn.commit()
        if price_skew is not None and not math.isnan(price_skew):
            price_skew_print = f"{price_skew:.2f}"
        else:
            price_skew_print = "NA"

        print(f"[SCORE] {ticker} {d} → {signal} | total={total_score:.2f} | PriceSkew={price_skew_print}")
    
    cur.close()
    conn.close()
    print("✅ Alle nieuwe optiedagen gescoord en opgeslagen.")

def compute_option_scores(ticker="AD.AS"):
    compute_option_score(ticker)

if __name__ == "__main__":
    compute_option_score()