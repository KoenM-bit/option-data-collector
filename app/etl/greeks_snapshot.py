# app/etl/greeks_snapshot.py
from app.db import get_connection
import datetime as dt


def ensure_greeks_history_table():
    """Create the fd_greeks_history table if it doesn't exist."""
    conn = get_connection()
    cur = conn.cursor()

    # Use existing schema - table likely already exists with different structure
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fd_greeks_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL,
            as_of_date DATE NOT NULL,
            ts DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            total_delta DECIMAL(18,8),
            total_gamma DECIMAL(18,8),
            total_vega DECIMAL(18,8),
            total_theta DECIMAL(18,8),
            spot_price DECIMAL(18,8),
            source ENUM('live','daily') DEFAULT 'live',
            INDEX idx_ticker_date (ticker, as_of_date, ts)
        )
    """
    )
    conn.commit()
    cur.close()
    conn.close()


def record_greek_snapshot(ticker="AD.AS", interval_minutes=15):
    """
    Record a Greeks snapshot for portfolio positions.

    Args:
        ticker: The ticker symbol (default: AD.AS)
        interval_minutes: Snapshot interval in minutes (default: 15)
    """
    ensure_greeks_history_table()
    conn = get_connection()
    cur = conn.cursor(dictionary=True)

    now = dt.datetime.now()
    today = now.date()
    weekday = today.weekday()  # 0=Monday, 6=Sunday

    # Skip weekends
    if weekday >= 5:
        print(f"⏸ {today} is weekend — geen snapshot nodig.")
        cur.close()
        conn.close()
        return

    # Check if snapshot already exists for this interval
    interval_slot = (now.minute // interval_minutes) * interval_minutes
    snapshot_time = now.replace(minute=interval_slot, second=0, microsecond=0)

    cur.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM fd_greeks_history
        WHERE ticker=%s
        AND as_of_date=%s
        AND HOUR(ts)=%s
        AND MINUTE(ts) DIV %s = %s
    """,
        (ticker, today, now.hour, interval_minutes, interval_slot // interval_minutes),
    )

    if cur.fetchone()["cnt"] > 0:
        print(f"✅ Snapshot voor {ticker} bestaat al voor {snapshot_time}, overslaan.")
        cur.close()
        conn.close()
        return

    # Get total Greeks from current positions with latest option data
    cur.execute(
        """
        WITH latest_options AS (
            SELECT
                ticker, expiry, strike, type,
                delta, gamma, vega, theta,
                ROW_NUMBER() OVER (
                    PARTITION BY ticker, expiry, strike, type
                    ORDER BY created_at DESC
                ) AS rn
            FROM option_prices_live
            WHERE ticker = %s
        ),
        month_mapping AS (
            SELECT
                p.ticker, p.expiry as position_expiry, p.strike, p.type, p.quantity,
                CASE
                    WHEN MONTH(p.expiry) = 1 THEN 'Januari'
                    WHEN MONTH(p.expiry) = 2 THEN 'Februari'
                    WHEN MONTH(p.expiry) = 3 THEN 'Maart'
                    WHEN MONTH(p.expiry) = 4 THEN 'April'
                    WHEN MONTH(p.expiry) = 5 THEN 'Mei'
                    WHEN MONTH(p.expiry) = 6 THEN 'Juni'
                    WHEN MONTH(p.expiry) = 7 THEN 'Juli'
                    WHEN MONTH(p.expiry) = 8 THEN 'Augustus'
                    WHEN MONTH(p.expiry) = 9 THEN 'September'
                    WHEN MONTH(p.expiry) = 10 THEN 'Oktober'
                    WHEN MONTH(p.expiry) = 11 THEN 'November'
                    WHEN MONTH(p.expiry) = 12 THEN 'December'
                END as dutch_month,
                YEAR(p.expiry) as expiry_year
            FROM fd_positions p
            WHERE p.ticker = %s
        )
        SELECT
            m.ticker,
            ROUND(SUM(m.quantity * o.delta * 100), 4) AS total_delta,
            ROUND(SUM(m.quantity * o.gamma * 100), 6) AS total_gamma,
            ROUND(SUM(m.quantity * o.vega), 4) AS total_vega,
            ROUND(SUM(m.quantity * o.theta), 4) AS total_theta,
            COUNT(*) AS position_count
        FROM month_mapping m
        JOIN latest_options o
          ON m.ticker = o.ticker
         AND o.expiry = CONCAT(m.dutch_month, ' ', m.expiry_year)  -- Match month format
         AND ABS(m.strike - o.strike) < 0.01  -- Handle floating point precision
         AND UPPER(m.type) = UPPER(o.type)
        WHERE o.rn = 1  -- Latest data only
        GROUP BY m.ticker
    """,
        (ticker, ticker),
    )

    row = cur.fetchone()
    if not row or row["position_count"] == 0:
        print(f"⚠️ Geen matching posities gevonden voor {ticker} — snapshot overgeslagen.")
        cur.close()
        conn.close()
        return

    # Get current spot price (simple fallback)
    try:
        import yfinance as yf

        spot_price = float(yf.Ticker(ticker).history(period="1d")["Close"].iloc[-1])
    except:
        spot_price = 36.84  # Fallback

    # Insert snapshot
    cur.execute(
        """
        INSERT INTO fd_greeks_history
        (ticker, as_of_date, ts, total_delta, total_gamma, total_vega, total_theta, spot_price, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'live')
    """,
        (
            ticker,
            today,
            snapshot_time,
            row["total_delta"],
            row["total_gamma"],
            row["total_vega"],
            row["total_theta"],
            spot_price,
        ),
    )
    conn.commit()

    print(
        f"✅ Snapshot opgeslagen voor {ticker} ({snapshot_time}) → "
        f"Δ={row['total_delta']}, Γ={row['total_gamma']}, "
        f"Θ={row['total_theta']}, ν={row['total_vega']} "
        f"({row['position_count']} posities) @ €{spot_price}"
    )

    cur.close()
    conn.close()


def get_latest_greeks_summary(ticker="AD.AS", hours_back=24):
    """Get recent Greeks snapshots for analysis."""
    conn = get_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute(
        """
        SELECT
            as_of_date,
            ts,
            total_delta,
            total_gamma,
            total_vega,
            total_theta,
            spot_price
        FROM fd_greeks_history
        WHERE ticker = %s
        AND ts >= DATE_SUB(NOW(), INTERVAL %s HOUR)
        ORDER BY ts DESC
    """,
        (ticker, hours_back),
    )

    results = cur.fetchall()
    cur.close()
    conn.close()

    return results


if __name__ == "__main__":
    record_greek_snapshot()
