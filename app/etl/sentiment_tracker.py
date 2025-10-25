# -*- coding: utf-8 -*-
"""
app/etl/sentiment_tracker.py
Yahoo Finance analistenaanbevelingen + koersdoelen → opslaan in sentiment_data.

Geporteerd uit legacy sentiment_tracker.py en aangepast voor app/ structuur.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, date
import time

import yfinance as yf

from app.db import get_connection


def get_last_record(conn, ticker):
	cur = conn.cursor(dictionary=True)
	cur.execute(
		"SELECT * FROM sentiment_data WHERE ticker = %s ORDER BY timestamp DESC LIMIT 1",
		(ticker,),
	)
	row = cur.fetchone()
	cur.close()
	return row


def records_differ(old, new):
	if not old:
		return True
	keys = [
		"rating_avg",
		"rating_label",
		"target_avg",
		"target_high",
		"target_low",
		"sentiment_score",
		"buy_count",
		"hold_count",
		"sell_count",
	]
	for k in keys:
		if str(old.get(k)) != str(new.get(k)):
			return True
	return False


def should_insert(old, new) -> bool:
	"""Bepaal of we een nieuw record moeten wegschrijven.
	Regels:
	  - Geen vorig record: altijd schrijven
	  - Andere inhoud: schrijven
	  - Zelfde inhoud maar vorige timestamp is van een eerdere kalenderdag: schrijven (dagelijkse snapshot)
	"""
	if not old:
		return True
	if records_differ(old, new):
		return True
	# Vergelijk kalenderdag (UTC)
	try:
		old_dt = old.get("timestamp")
		if isinstance(old_dt, str):
			# MariaDB python connector kan string geven
			old_dt = datetime.fromisoformat(old_dt.replace(" UTC", "").replace("Z", ""))
		if isinstance(old_dt, datetime):
			return old_dt.date() != datetime.now(timezone.utc).date()
	except Exception:
		pass
	return False


def save_to_db(data):
	conn = get_connection()
	cur = conn.cursor()
	cur.execute(
		"""
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
		"""
	)

	last = get_last_record(conn, data["ticker"])
	if not should_insert(last, data):
		# Als dezelfde dag: update het meest recente record zodat latere runs verbeterde waarden kunnen overschrijven
		try:
			cur.execute(
				"""
				UPDATE sentiment_data
				SET rating_avg=%s, rating_label=%s, target_avg=%s, target_high=%s, target_low=%s,
					sentiment_score=%s, buy_count=%s, hold_count=%s, sell_count=%s,
					months_considered=%s, trend_json=%s, timestamp=%s
				WHERE ticker=%s
				ORDER BY timestamp DESC
				LIMIT 1
				""",
				(
					data["rating_avg"], data["rating_label"], data["target_avg"], data["target_high"], data["target_low"],
					data["sentiment_score"], data["buy_count"], data["hold_count"], data["sell_count"],
					data["months_considered"], data["trend_json"], datetime.now(timezone.utc), data["ticker"]
				),
			)
			conn.commit()
			print(f"Record voor {data['ticker']} bijgewerkt (zelfde dag).")
		except Exception:
			print(f"Geen wijzigingen voor {data['ticker']}, overslaan.")
		cur.close(); conn.close()
		return

	cur.execute(
		"""
		INSERT INTO sentiment_data
		(ticker, rating_avg, rating_label, target_avg, target_high, target_low,
		 sentiment_score, timestamp, buy_count, hold_count, sell_count,
		 months_considered, trend_json)
		VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
		""",
		(
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
		),
	)
	conn.commit(); cur.close(); conn.close()
	print(f"Nieuw sentimentrecord opgeslagen voor {data['ticker']}.")


def _with_retries(fn, retries=3, backoff=[2,5,10]):
	last_exc = None
	for i in range(retries):
		try:
			return fn()
		except Exception as e:
			last_exc = e
			if i < retries - 1:
				time.sleep(backoff[min(i, len(backoff)-1)])
	raise last_exc


def get_yf_sentiment(ticker: str = "AD.AS"):
	print(f"Ophalen van sentimentdata voor {ticker} ...")
	t = yf.Ticker(ticker)

	try:
		info = _with_retries(lambda: (t.info or {}))
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

	# yfinance object properties can also raise; guard with retries where possible
	try:
		rec_summary = getattr(t, "recommendations_summary", None)
	except Exception:
		rec_summary = None
	try:
		recs = getattr(t, "recommendations", None)
	except Exception:
		recs = None

	buy_count = hold_count = sell_count = 0
	months_considered = 0
	trend_data = {}

	if rec_summary is not None and not rec_summary.empty:
		df = rec_summary.copy().head(6)
		months_considered = len(df)
		trend_data = df.to_dict(orient="records")
		latest = df.iloc[0] if not df.empty else None
		if latest is not None:
			buy_count = int(latest.get("strongBuy", 0) + latest.get("buy", 0))
			hold_count = int(latest.get("hold", 0))
			sell_count = int(latest.get("sell", 0) + latest.get("strongSell", 0))
	elif recs is not None and not recs.empty:
		recent = recs.tail(10)
		buy_count = len(recent[recent["To Grade"].str.contains("Buy", case=False, na=False)])
		hold_count = len(recent[recent["To Grade"].str.contains("Hold", case=False, na=False)])
		sell_count = len(recent[recent["To Grade"].str.contains("Sell", case=False, na=False)])
		months_considered = 1
		trend_data = recent.to_dict(orient="records")

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


if __name__ == "__main__":
	try:
		res = get_yf_sentiment("AD.AS")
		print(json.dumps(res, indent=2))
		save_to_db(res)
	except Exception as e:
		print(f"Fout tijdens verwerking: {e}")

