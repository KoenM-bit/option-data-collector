# app/api/routes.py
# -*- coding: utf-8 -*-
from flask import Flask, jsonify
from flasgger import Swagger
from app.db import get_connection
import datetime as dt
import json

app = Flask(__name__)

# Swagger configuratie
app.config['SWAGGER'] = {
    'title': 'KoenMarijt API',
    'uiversion': 3,
    'description': 'Endpoints voor optieprijzen, sentimentdata en trendanalyse'
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
    cur.close(); conn.close()
    return jsonify(row or {"error": "No data yet"})

@app.route("/api/recent/<int:limit>")
def recent_prices(limit):
    """Laatste N optieprijzen."""
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM option_prices ORDER BY timestamp DESC LIMIT %s", (limit,))
    rows = cur.fetchall()
    cur.close(); conn.close()
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
    cur.close(); conn.close()
    return jsonify(row or {"error": f"No data found for {expiry} {strike}"})

@app.route("/api/contracts")
def list_contracts():
    """Lijst van alle beschikbare optiecontracten."""
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT DISTINCT expiry, strike, type FROM option_prices ORDER BY expiry, strike")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)

# ------------------------
# SENTIMENT ENDPOINTS
# ------------------------

@app.route("/api/sentiment/<string:ticker>")
def latest_sentiment(ticker):
    """Laatste sentimentanalyse voor een ticker."""
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM sentiment_data WHERE ticker=%s ORDER BY timestamp DESC LIMIT 1", (ticker.upper(),))
    row = cur.fetchone()
    cur.close(); conn.close()
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

@app.route("/api/status")
def status():
    """API-status."""
    return jsonify({
        "status": "running",
        "timestamp": dt.datetime.now().isoformat(),
        "services": ["option-api", "sentiment-tracker", "option-scraper"]
    })

# ------------------------
# RUN APP
# ------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)