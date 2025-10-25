# -*- coding: utf-8 -*-
"""
sentiment_tracker.py
Haalt analisten-sentiment en koersdoelen op via Yahoo Finance (yfinance)
en schrijft deze naar de bestaande MariaDB-tabel 'sentiment_data'.
"""

import yfinance as yf
import pandas as pd
import mysql.connector
import json
from datetime import datetime, timezone

DB_CONFIG = {
    "host": "192.168.1.200",
    "user": "remoteuser",
    "password": "T3l3foon32#123",
    "database": "optionsdb",
    "port": 3306,
}

TICKER = "AD.AS"  # Koninklijke Ahold Delhaize

# ---------------------------
# Database hulpfuncties
# ---------------------------

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)

def get_last_record(conn, ticker):
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM sentiment_data WHERE ticker = %s ORDER BY timestamp DESC LIMIT 1",
        (ticker,)
    )
    row = cursor.fetchone()
    cursor.close()
    return row

def records_differ(old, new):
    """Controleer of het nieuwe record inhoudelijk verschilt van het oude."""
    if not old:
        return True
    keys_to_compare = [
        "rating_avg", "rating_label", "target_avg",
        "target_high", "target_low", "sentiment_score",
        "buy_count", "hold_count", "sell_count"
    ]
    for k in keys_to_compare:
        if str(old.get(k)) != str(new.get(k)):
            return True
    return False

def save_to_db(data):
    conn = get_connection()
    cursor = conn.cursor()

    # Zorg dat tabel bestaat
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sentiment_data (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ticker VARCHAR(32),
            rating_avg FLOAT,
            rating_label VARCHAR(32),
            target_avg FLOAT,
            target_high FLOAT,
            target_low FLOAT,
            sentiment_score FLOAT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            buy_count INT,
            hold_count INT,
            sell_count INT,
            months_considered INT,
            trend_json JSON
        )
    """)

    last = get_last_record(conn, data["ticker"])
    if not records_differ(last, data):
        print(f"Geen wijzigingen voor {data['ticker']}, overslaan.")
        cursor.close()
        conn.close()
        return

    cursor.execute("""
        INSERT INTO sentiment_data
        (ticker, rating_avg, rating_label, target_avg, target_high, target_low,
         sentiment_score, timestamp, buy_count, hold_count, sell_count,
         months_considered, trend_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        data["ticker"],
        data["rating_avg"],
        data["rating_label"],
        data["target_avg"],
        data["target_high"],
        data["target_low"],
        data["sentiment_score"],
        datetime.now(timezone.utc),
        data["buy_count"],
        data["hold_count"],
        data["sell_count"],
        data["months_considered"],
        data["trend_json"],
    ))

    conn.commit()
    cursor.close()
    conn.close()
    print(f"Nieuw sentimentrecord opgeslagen voor {data['ticker']}.")

# ---------------------------
# Yahoo Finance sentiment
# ---------------------------

def get_yf_sentiment(ticker: str = TICKER):
    print(f"Ophalen van sentimentdata voor {ticker} ...")

    t = yf.Ticker(ticker)

    try:
        info = t.info or {}
    except Exception:
        info = {}

    recommendation_mean = info.get("recommendationMean")
    recommendation_key = info.get("recommendationKey")
    target_mean_price = info.get("targetMeanPrice")
    target_high_price = info.get("targetHighPrice")
    target_low_price = info.get("targetLowPrice")

    sentiment_score = None
    sentiment_label = "Onbekend"
    if recommendation_mean is not None:
        sentiment_score = round((3 - recommendation_mean) / 2, 2)
        if sentiment_score > 0.2:
            sentiment_label = "Bullish"
        elif sentiment_score < -0.2:
            sentiment_label = "Bearish"
        else:
            sentiment_label = "Neutraal"

    rec_summary = getattr(t, "recommendations_summary", None)
    recs = getattr(t, "recommendations", None)

    buy_count = hold_count = sell_count = 0
    months_considered = 0
    trend_data = {}

    if rec_summary is not None and not rec_summary.empty:
        df = rec_summary.copy()
        df = df.head(6)
        months_considered = len(df)
        trend_data = df.to_dict(orient="records")

        # Laatste maand (0m)
        latest = df.iloc[0] if not df.empty else None
        if latest is not None:
            buy_count = int(latest.get("strongBuy", 0) + latest.get("buy", 0))
            hold_count = int(latest.get("hold", 0))
            sell_count = int(latest.get("sell", 0) + latest.get("strongSell", 0))

    elif recs is not None and not recs.empty:
        recs_recent = recs.tail(10)
        buy_count = len(recs_recent[recs_recent["To Grade"].str.contains("Buy", case=False, na=False)])
        hold_count = len(recs_recent[recs_recent["To Grade"].str.contains("Hold", case=False, na=False)])
        sell_count = len(recs_recent[recs_recent["To Grade"].str.contains("Sell", case=False, na=False)])
        months_considered = 1
        trend_data = recs_recent.to_dict(orient="records")

    result = {
        "ticker": ticker.upper(),
        "rating_avg": recommendation_mean,
        "rating_label": recommendation_key,
        "target_avg": target_mean_price,
        "target_high": target_high_price,
        "target_low": target_low_price,
        "sentiment_score": sentiment_score,
        "buy_count": buy_count,
        "hold_count": hold_count,
        "sell_count": sell_count,
        "months_considered": months_considered,
        "trend_json": json.dumps(trend_data, ensure_ascii=False),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }

    return result

# ---------------------------
# Main-run
# ---------------------------

if __name__ == "__main__":
    try:
        result = get_yf_sentiment(TICKER)
        print(json.dumps(result, indent=2))
        save_to_db(result)
    except Exception as e:
        print(f"Fout tijdens verwerking: {e}")