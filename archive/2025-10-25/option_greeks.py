    # test_option_greeks.py
    # Testscript: haalt optie-data uit MySQL en berekent implied volatility en Greeks.
    # Resultaten worden alleen getoond, niet opgeslagen.
    # to do: werken aan de r rate voor de langere expiratie opties. Nu is het max 12maanden

    import math
    import mysql.connector
    from datetime import datetime, date
    import requests

    euribor_cache = {}

    def get_current_euribor(months=1):
        """
        Haalt actuele Euribor-rente (1, 3, 6 of 12 maanden) via de ECB data API.
        """
        try:
            # 🩵 12M heeft een andere code bij de ECB
            if months == 12:
                    url = "https://data-api.ecb.europa.eu/service/data/FM/M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA?format=jsondata&lastNObservations=1"
            else:
                url = f"https://data-api.ecb.europa.eu/service/data/FM/M.U2.EUR.RT.MM.EURIBOR{months}MD_.HSTA?format=jsondata&lastNObservations=1"

            resp = requests.get(url, timeout=10)
            data = resp.json()
            val = list(data["dataSets"][0]["series"].values())[0]["observations"]["0"][0]
            rate = float(val) / 100
            print(f"📈 Euribor {months}m: {rate*100:.3f}%")
            return rate

        except Exception as e:
            print(f"⚠️ Kon geen actuele Euribor ophalen ({months}m):", e)
            fallback = {1: 0.0187, 3: 0.0206, 6: 0.0210, 12: 0.0216}.get(months, 0.02)
            print(f"➡️ Gebruik fallback Euribor {months}m = {fallback*100:.3f}%")
            return fallback


    def risk_free_rate_for_days(days):
        """
        Bepaalt de juiste Euribor-termijn op basis van looptijd (in dagen)
        en gebruikt caching om dubbele API-calls te voorkomen.
        """
        global euribor_cache

        if days <= 30:
            key = 1
        elif days <= 90:
            key = 3
        elif days <= 180:
            key = 6
        else:
            key = 12

        if key not in euribor_cache:
            euribor_cache[key] = get_current_euribor(key)

        return euribor_cache[key]

    # ============================================
    # BLACK–SCHOLES FUNCTIES
    # ============================================

    SQRT_2PI = math.sqrt(2 * math.pi)

    def phi(x):  # PDF
        return math.exp(-0.5 * x * x) / SQRT_2PI

    def Phi(x):  # CDF
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def d1_d2(S, K, t, r, sigma):
        if S <= 0 or K <= 0 or t <= 0 or sigma <= 0:
            return None, None
        vol_sqrt_t = sigma * math.sqrt(t)
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * t) / vol_sqrt_t
        d2 = d1 - vol_sqrt_t
        return d1, d2

    def bs_price(S, K, t, r, sigma, is_call):
        d1, d2 = d1_d2(S, K, t, r, sigma)
        if d1 is None:
            return float("nan")
        df = math.exp(-r * t)
        if is_call:
            return S * Phi(d1) - K * df * Phi(d2)
        else:
            return K * df * Phi(-d2) - S * Phi(-d1)

    def bs_delta(S, K, t, r, sigma, is_call):
        d1, _ = d1_d2(S, K, t, r, sigma)
        return Phi(d1) if is_call else (Phi(d1) - 1)

    def bs_gamma(S, K, t, r, sigma):
        d1, _ = d1_d2(S, K, t, r, sigma)
        return phi(d1) / (S * sigma * math.sqrt(t))

    def bs_vega(S, K, t, r, sigma):
        d1, _ = d1_d2(S, K, t, r, sigma)
        return S * phi(d1) * math.sqrt(t)

    def bs_theta(S, K, t, r, sigma, is_call):
        d1, d2 = d1_d2(S, K, t, r, sigma)
        df = math.exp(-r * t)
        first = -(S * phi(d1) * sigma) / (2 * math.sqrt(t))
        if is_call:
            return first - r * K * df * Phi(d2)
        else:
            return first + r * K * df * Phi(-d2)

    def implied_vol(price, S, K, t, r, is_call, tol=1e-6, max_iter=100):
        """Newton-Raphson implied vol calculator."""
        if not (S > 0 and K > 0 and t > 0 and price > 0):
            return float("nan")
        sigma = 0.3
        for _ in range(max_iter):
            model = bs_price(S, K, t, r, sigma, is_call)
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

    # ============================================
    # DATABASE CONNECTIE EN DATA
    # ============================================

    def get_connection():
        return mysql.connector.connect(
            host="192.168.1.201",
            user="remoteuser",
            password="T3l3foon32#123",
            database="optionsdb",
            port=3306
        )

    def fetch_contracts(ticker="AD.AS", peildatum=None):
        conn = get_connection()
        cur = conn.cursor(dictionary=True)

        # ✅ Vind de laatste datum die in beide tabellen voorkomt
        if not peildatum:
            cur.execute("""
                SELECT MAX(c.peildatum) AS d
                FROM fd_option_contracts c
                JOIN fd_option_overview o
                ON c.peildatum = o.peildatum AND c.ticker = o.ticker
                WHERE c.ticker = %s
            """, (ticker,))
            row = cur.fetchone()
            peildatum = row["d"]

        # Als er nog steeds geen datum is, stoppen
        if not peildatum:
            raise ValueError(f"Geen overlappende peildatum gevonden voor {ticker}")

        # ✅ Haal alle contracts voor die dag op
        cur.execute("""
            SELECT id, expiry, strike, type, bid, ask, last
            FROM fd_option_contracts
            WHERE ticker=%s AND peildatum=%s
        """, (ticker, peildatum))
        contracts = cur.fetchall()

        # ✅ Haal de koers (onderliggende waarde)
        cur.execute("""
            SELECT koers
            FROM fd_option_overview
            WHERE ticker=%s AND peildatum=%s
            LIMIT 1
        """, (ticker, peildatum))
        koers_row = cur.fetchone()
        conn.close()

        if not koers_row or koers_row["koers"] is None:
            raise ValueError(f"Geen koers gevonden voor {ticker} op {peildatum}")

        return contracts, koers_row["koers"], peildatum

    def fetch_available_dates(ticker):
        """Haalt alle peildatums op waarvoor contracten + overview bestaan."""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT c.peildatum
            FROM fd_option_contracts c
            JOIN fd_option_overview o
            ON c.ticker = o.ticker AND c.peildatum = o.peildatum
            WHERE c.ticker = %s
            ORDER BY c.peildatum
        """, (ticker,))
        dates = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
        return dates


    def fetch_existing_greek_dates(ticker):
        """Haalt peildatums op die al Greeks hebben."""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT peildatum FROM fd_option_greeks WHERE ticker=%s", (ticker,))
        done = {r[0] for r in cur.fetchall()}
        cur.close()
        conn.close()
        return done

    # ============================================
    # TEST EN OUTPUT + OPSLAAN IN DATABASE
    # ============================================

    def main():
        ticker = "AD.AS"

        available_dates = fetch_available_dates(ticker)
        existing_dates = fetch_existing_greek_dates(ticker)

        todo_dates = [d for d in available_dates if d not in existing_dates]
        if not todo_dates:
            print("✅ Alle beschikbare dagen al verwerkt.")
            return

        print(f"📅 Nieuwe dagen zonder Greeks: {todo_dates}")

        for peildatum in todo_dates:
            print(f"\n--- Verwerken {ticker} | {peildatum} ---")
            try:
                contracts, S, _ = fetch_contracts(ticker, peildatum)
            except Exception as e:
                print(f"⚠️ Fout bij ophalen data voor {peildatum}: {e}")
                continue

            results = []

            for c in contracts:
                last = c["last"]
                bid, ask = c["bid"], c["ask"]
                price = None

                if bid and ask and bid > 0 and ask > 0:
                    price = 0.5 * (bid + ask)
                elif last and last > 0:
                    price = last
                if not price:
                    continue

                expiry = c["expiry"]
                days = (expiry - peildatum).days
                t = max(days / 365.0, 0)
                if t <= 0:
                    continue

                r = risk_free_rate_for_days(days)
                is_call = c["type"].lower() == "call"
                K = float(c["strike"])
                sigma = implied_vol(price, S, K, t, r, is_call)
                if math.isnan(sigma):
                    continue

                delta = bs_delta(S, K, t, r, sigma, is_call)
                gamma = bs_gamma(S, K, t, r, sigma)
                vega = bs_vega(S, K, t, r, sigma)
                theta = bs_theta(S, K, t, r, sigma, is_call)

                results.append({
                    "contract_id": c["id"],
                    "type": c["type"],
                    "strike": K,
                    "price": price,
                    "iv": sigma,
                    "delta": delta,
                    "gamma": gamma,
                    "vega": vega,
                    "theta": theta,
                    "expiry": c["expiry"]
                })

            if not results:
                print(f"⚠️ Geen resultaten voor {peildatum}, overslaan.")
                continue

            conn = get_connection()
            cur = conn.cursor()

            for rdata in results:
                cur.execute("""
                    INSERT INTO fd_option_greeks (
                        contract_id, ticker, peildatum, expiry, strike, type, price,
                        iv, delta, gamma, vega, theta
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                        price=VALUES(price),
                        iv=VALUES(iv),
                        delta=VALUES(delta),
                        gamma=VALUES(gamma),
                        vega=VALUES(vega),
                        theta=VALUES(theta),
                        created_at=NOW()
                """, (
                    rdata["contract_id"],
                    ticker,
                    peildatum,
                    rdata["expiry"],
                    rdata["strike"],
                    rdata["type"],
                    rdata["price"],
                    rdata["iv"],
                    rdata["delta"],
                    rdata["gamma"],
                    rdata["vega"],
                    rdata["theta"]
                ))

            conn.commit()
            cur.close()
            conn.close()
            print(f"✅ {len(results)} Greeks opgeslagen voor {ticker} ({peildatum})")

        print("\n🎯 Alle ontbrekende dagen zijn nu berekend en opgeslagen.")


    def compute_greeks_for_day(ticker="AD.AS"):
        main()

    if __name__ == "__main__":
        compute_greeks_for_day()