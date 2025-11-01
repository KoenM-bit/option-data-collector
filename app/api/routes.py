# app/api/routes.py
# -*- coding: utf-8 -*-
from flask import Flask, jsonify
from flasgger import Swagger
from app.db import get_connection
import datetime as dt
import json

app = Flask(__name__)

# Swagger configuratie
app.config["SWAGGER"] = {
    "title": "KoenMarijt API",
    "uiversion": 3,
    "description": "Endpoints voor optieprijzen, sentimentdata en trendanalyse",
}
swagger = Swagger(app)

# ------------------------
# OPTIE ENDPOINTS
# ------------------------


@app.route("/api/latest")
def latest_price():
    """Laatste optieprijs."""
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM option_prices ORDER BY timestamp DESC LIMIT 1")
    row = cur.fetchone()
    cur.close()
    conn.close()
    return jsonify(row or {"error": "No data yet"})


@app.route("/api/recent/<int:limit>")
def recent_prices(limit):
    """Laatste N optieprijzen."""
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM option_prices ORDER BY timestamp DESC LIMIT %s", (limit,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(rows)


@app.route("/api/latest/<string:expiry>/<string:strike>")
def latest_by_expiry_and_strike(expiry, strike):
    """Laatste prijs voor een specifieke expiry en strike."""
    expiry = expiry.replace("%20", " ").strip().title()
    strike_norm = strike.replace(",", ".").split(".")[0]
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    query = """
        SELECT * FROM option_prices
        WHERE expiry LIKE %s
          AND (REPLACE(REPLACE(strike, ',', ''), '.', '') LIKE %s)
        ORDER BY timestamp DESC LIMIT 1
    """
    cur.execute(query, (f"%{expiry}%", f"%{strike_norm}%"))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return jsonify(row or {"error": f"No data found for {expiry} {strike}"})


@app.route("/api/contracts")
def list_contracts():
    """Lijst van alle beschikbare optiecontracten."""
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT DISTINCT expiry, strike, type FROM option_prices ORDER BY expiry, strike")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(rows)


# ------------------------
# SENTIMENT ENDPOINTS
# ------------------------


@app.route("/api/sentiment/<string:ticker>")
def latest_sentiment(ticker):
    """Laatste sentimentanalyse voor een ticker."""
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT * FROM sentiment_data WHERE ticker=%s ORDER BY timestamp DESC LIMIT 1",
        (ticker.upper(),),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return jsonify({"error": f"No sentiment found for {ticker.upper()}"})

    # Parse JSON veld
    trend_json = []
    if row.get("trend_json"):
        try:
            val = row["trend_json"]
            if isinstance(val, (bytes, bytearray)):
                val = val.decode("utf-8")
            trend_json = json.loads(val)
        except Exception:
            trend_json = []

    row["trend_json"] = trend_json
    return jsonify(row)


@app.route("/api/greeks/summary/<string:ticker>")
def greeks_summary(ticker):
    """
    Geeft een overzicht van de totale Greeks voor alle posities van een ticker,
    plus een strategische suggestie (hedge / hold / adjust).
    ---
    parameters:
      - name: ticker
        in: path
        type: string
        required: true
        description: De ticker (bijv. AD.AS)
    responses:
      200:
        description: Overzicht van totale Greeks en suggesties
    """
    import yfinance as yf

    conn = get_connection()
    cur = conn.cursor(dictionary=True)

    # Haal laatste Greeks per contract (laatste record per strike/type/expiry)
    cur.execute(
        """
        WITH latest AS (
            SELECT
                g.ticker, g.expiry, g.strike, g.type,
                g.delta, g.gamma, g.vega, g.theta, g.price,
                ROW_NUMBER() OVER (
                    PARTITION BY g.ticker, g.expiry, g.strike, g.type
                    ORDER BY g.created_at DESC
                ) rn
            FROM fd_option_greeks g
            WHERE g.ticker = %s
        )
        SELECT p.ticker, p.expiry, p.strike, p.type, p.quantity,
               g.delta, g.gamma, g.vega, g.theta, g.price
        FROM fd_positions p
        JOIN latest g
          ON p.ticker = g.ticker
         AND p.expiry = g.expiry
         AND p.strike = g.strike
         AND p.type = g.type
        WHERE g.rn = 1;
    """,
        (ticker,),
    )

    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return jsonify({"error": f"Geen posities gevonden voor {ticker}"}), 404

    # Totale Greeks berekenen (met ×100 omdat 1 contract = 100 aandelen)
    total_delta = sum(r["delta"] * r["quantity"] * 100 for r in rows)
    total_gamma = sum(r["gamma"] * r["quantity"] * 100 for r in rows)
    total_vega = sum(r["vega"] * r["quantity"] for r in rows)
    total_theta = sum(r["theta"] * r["quantity"] for r in rows)

    # Spot ophalen (via Yahoo Finance)
    try:
        spot = float(yf.Ticker(ticker).history(period="1d")["Close"].iloc[-1])
    except Exception:
        spot = None

    # Analyse / suggesties genereren
    suggestion = []
    if abs(total_delta) > 300:
        suggestion.append("⚠️ Hoge delta-exposure — overweeg (gedeeltelijke) hedge met aandelen.")
    elif abs(total_delta) < 100:
        suggestion.append("✅ Delta-neutraal — prima uitgebalanceerd.")
    else:
        suggestion.append("ℹ️ Licht directioneel, maar beheersbaar.")

    if total_gamma < -0.5:
        suggestion.append(
            "⚠️ Short gamma — risico bij grote bewegingen, wees alert op volatiliteit."
        )
    elif total_gamma > 0.5:
        suggestion.append("✅ Long gamma — profiteert van snelle bewegingen.")
    else:
        suggestion.append("ℹ️ Neutrale gamma-positie.")

    if total_theta > 0:
        suggestion.append(f"✅ Positieve theta ({total_theta:.2f}) — verdient tijdswaarde per dag.")
    else:
        suggestion.append("⚠️ Negatieve theta — kost tijdswaarde per dag.")

    if total_vega > 0:
        suggestion.append("✅ Long vega — profiteert van hogere implied volatility.")
    elif total_vega < 0:
        suggestion.append("⚠️ Short vega — gevoelig voor stijgende implied volatility.")
    else:
        suggestion.append("ℹ️ Neutrale volatiliteitsblootstelling.")

    return jsonify(
        {
            "ticker": ticker,
            "spot": spot,
            "positions": rows,
            "totals": {
                "delta": round(total_delta, 2),
                "gamma": round(total_gamma, 4),
                "vega": round(total_vega, 4),
                "theta": round(total_theta, 4),
            },
            "suggestions": suggestion,
        }
    )


@app.route("/api/live")
def all_live_options():
    """Alle live optieprijzen met optionele filters (voor Power BI)."""
    from flask import request

    limit = request.args.get("limit", default=None, type=int)
    expiry = request.args.get("expiry", default=None, type=str)

    conn = get_connection()
    cur = conn.cursor(dictionary=True)

    query = "SELECT * FROM option_prices_live"
    params = []

    if expiry:
        query += " WHERE expiry = %s"
        params.append(expiry)

    # ✅ Sorteer op fetched_at (beste tijdskolom voor 'live' data)
    query += " ORDER BY fetched_at DESC"

    if limit and isinstance(limit, int):
        query += f" LIMIT {limit}"

    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(rows)


@app.route("/api/status")
def status():
    """API-status."""
    return jsonify(
        {
            "status": "running",
            "timestamp": dt.datetime.now().isoformat(),
            "services": ["option-api", "sentiment-tracker", "option-scraper"],
        }
    )


# ------------------------
# RUN APP
# ------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090)
