# -*- coding: utf-8 -*-
from flask import Flask, jsonify
import mysql.connector
import datetime as dt
import json
from flasgger import Swagger

app = Flask(__name__)

# Swagger configuratie
app.config["SWAGGER"] = {
    "title": "KoenMarijt API",
    "uiversion": 3,
    "description": "Endpoints voor optieprijzen, sentimentdata en trendanalyse",
}
swagger = Swagger(app)


# ------------------------
# DATABASE CONNECTIE
# ------------------------
def get_connection():
    """Open een MySQL-verbinding"""
    return mysql.connector.connect(
        host="192.168.1.201",
        user="remoteuser",
        password="T3l3foon32#123",
        database="optionsdb",
        port=3306,
    )


# ------------------------
# OPTIE ENDPOINTS
# ------------------------


@app.route("/api/latest")
def latest_price():
    """
    Haal de laatste optieprijs op.
    ---
    responses:
      200:
        description: Laatste optieprijs
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM option_prices ORDER BY timestamp DESC LIMIT 1")
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return jsonify(row or {"error": "No data yet"})


@app.route("/api/recent/<int:limit>")
def recent_prices(limit):
    """
    Haal recente optieprijzen op.
    ---
    parameters:
      - name: limit
        in: path
        type: integer
        required: true
        description: Aantal records om op te halen
    responses:
      200:
        description: Lijst van recente prijzen
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM option_prices ORDER BY timestamp DESC LIMIT %s", (limit,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(rows)


@app.route("/api/latest/<string:expiry>/<string:strike>", methods=["GET"])
def latest_by_expiry_and_strike(expiry, strike):
    """
    Haal de laatste prijs op basis van expiry en strike.
    ---
    parameters:
      - name: expiry
        in: path
        type: string
        required: true
        description: Expiry maand (bijv. 'November 2025')
      - name: strike
        in: path
        type: string
        required: true
        description: Strike prijs (bijv. '38')
    responses:
      200:
        description: Laatste optieprijs voor deze combinatie
    """
    expiry = expiry.replace("%20", " ").strip().title()
    strike_normalized = strike.replace(",", ".").split(".")[0]

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT * FROM option_prices
        WHERE expiry LIKE %s
          AND (REPLACE(REPLACE(strike, ',', ''), '.', '') LIKE %s)
        ORDER BY timestamp DESC
        LIMIT 1
    """
    cursor.execute(query, (f"%{expiry}%", f"%{strike_normalized}%"))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return jsonify(row or {"error": f"No data found for {expiry} strike {strike}"})


@app.route("/api/latest/<string:expiry>/<string:strike>/<string:option_type>", methods=["GET"])
def latest_by_expiry_strike_and_type(expiry, strike, option_type):
    """
    Haal de laatste prijs op voor een specifieke optie (Call of Put).
    ---
    parameters:
      - name: expiry
        in: path
        type: string
        required: true
        description: Expiry maand (bijv. 'November 2025')
      - name: strike
        in: path
        type: string
        required: true
        description: Strike prijs (bijv. '38')
      - name: option_type
        in: path
        type: string
        required: true
        description: Type optie (Call of Put)
    responses:
      200:
        description: Laatste optieprijs voor deze combinatie
    """
    expiry = expiry.replace("%20", " ").strip().title()
    option_type = option_type.capitalize()
    strike_normalized = strike.replace(",", ".").split(".")[0]

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT * FROM option_prices
        WHERE expiry LIKE %s
          AND (REPLACE(REPLACE(strike, ',', ''), '.', '') LIKE %s)
          AND type = %s
        ORDER BY timestamp DESC
        LIMIT 1
    """
    cursor.execute(query, (f"%{expiry}%", f"%{strike_normalized}%", option_type))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return jsonify(
        row
        or {
            "error": f"No {option_type} found for expiry like '{expiry}' and strike like '{strike}'"
        }
    )


@app.route("/api/contracts", methods=["GET"])
def list_contracts():
    """
    Lijst alle beschikbare optiecontracten.
    ---
    responses:
      200:
        description: Unieke expiries, strikes en types
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT DISTINCT expiry, strike, type
        FROM option_prices
        ORDER BY expiry, strike
    """
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(rows)


# ------------------------
# SENTIMENT ENDPOINTS
# ------------------------


@app.route("/api/sentiment/<string:ticker>", methods=["GET"])
def get_latest_sentiment(ticker):
    """
    Haal het laatste sentimentrecord op voor een aandeel.
    ---
    parameters:
      - name: ticker
        in: path
        type: string
        required: true
        description: Aandelticker (bijv. AD.AS)
    responses:
      200:
        description: Laatste sentimentanalyse inclusief trenddata
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT *
        FROM sentiment_data
        WHERE ticker = %s
        ORDER BY timestamp DESC
        LIMIT 1
    """,
        (ticker.upper(),),
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row:
        return jsonify({"error": f"No sentiment data found for {ticker.upper()}"})

    trend_data = []
    if row.get("trend_json"):
        try:
            val = row["trend_json"]
            if isinstance(val, (bytes, bytearray)):
                val = val.decode("utf-8")
            trend_data = json.loads(val)
        except Exception:
            trend_data = []

    latest_entry = next((x for x in trend_data if x.get("period") == "0m"), None)
    buy_count = latest_entry.get("buy", 0) + latest_entry.get("strongBuy", 0) if latest_entry else 0
    hold_count = latest_entry.get("hold", 0) if latest_entry else 0
    sell_count = (
        latest_entry.get("sell", 0) + latest_entry.get("strongSell", 0) if latest_entry else 0
    )

    result = {
        "ticker": row["ticker"],
        "rating_avg": row.get("rating_avg"),
        "rating_label": row.get("rating_label"),
        "target_avg": row.get("target_avg"),
        "target_high": row.get("target_high"),
        "target_low": row.get("target_low"),
        "sentiment_score": row.get("sentiment_score"),
        "buy_count": buy_count,
        "hold_count": hold_count,
        "sell_count": sell_count,
        "months_considered": len(trend_data),
        "trend_json": trend_data,
        "timestamp": row.get("timestamp"),
    }

    return jsonify(result)


@app.route("/api/sentiment/trend/<string:ticker>", methods=["GET"])
def get_sentiment_trend(ticker):
    """
    Haal de sentimenttrend van een aandeel op.
    ---
    parameters:
      - name: ticker
        in: path
        type: string
        required: true
        description: Aandelticker (bijv. AD.AS)
    responses:
      200:
        description: Trendgegevens en samenvatting voor de ticker
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT trend_json, timestamp
        FROM sentiment_data
        WHERE ticker = %s
        ORDER BY timestamp DESC
        LIMIT 1
    """,
        (ticker.upper(),),
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row:
        return jsonify({"error": f"No sentiment trend data found for {ticker.upper()}"})

    trend_data = []
    if row.get("trend_json"):
        try:
            val = row["trend_json"]
            if isinstance(val, (bytes, bytearray)):
                val = val.decode("utf-8")
            trend_data = json.loads(val)
        except Exception:
            trend_data = []

    latest_entry = next((x for x in trend_data if x.get("period") == "0m"), None)
    buy_count = latest_entry.get("buy", 0) + latest_entry.get("strongBuy", 0) if latest_entry else 0
    hold_count = latest_entry.get("hold", 0) if latest_entry else 0
    sell_count = (
        latest_entry.get("sell", 0) + latest_entry.get("strongSell", 0) if latest_entry else 0
    )

    result = {
        "ticker": ticker.upper(),
        "trend": trend_data,
        "summary": {
            "buy_count": buy_count,
            "hold_count": hold_count,
            "sell_count": sell_count,
            "months_considered": len(trend_data),
        },
        "timestamp": row.get("timestamp"),
    }

    return jsonify(result)


@app.route("/api/status", methods=["GET"])
def status():
    """
    Controleer of de API actief is.
    ---
    responses:
      200:
        description: Statusinformatie over de API
    """
    return jsonify(
        {
            "status": "running",
            "timestamp": dt.datetime.now().isoformat(),
            "services": ["option-api", "option-scraper", "sentiment-tracker"],
        }
    )


# ------------------------
# START DE APP
# ------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
