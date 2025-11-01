# app/etl/greeks_snapshot.py
from app.db import get_connection
import datetime as dt


def ensure_greeks_history_table():
    """Create the fd_greeks_history table if it doesn't exist."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fd_greeks_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL,
            timestamp DATETIME NOT NULL,
            total_delta DECIMAL(12,4),
            total_gamma DECIMAL(12,6),
            total_vega DECIMAL(12,4),
            total_theta DECIMAL(12,4),
            source VARCHAR(20) DEFAULT 'live',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uniq_snapshot (ticker, DATE(timestamp), HOUR(timestamp), MINUTE(timestamp) DIV 15)
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
        AND DATE(timestamp)=%s
        AND HOUR(timestamp)=%s
        AND MINUTE(timestamp) DIV %s = %s
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
        )
        SELECT
            p.ticker,
            ROUND(SUM(p.quantity * o.delta * 100), 4) AS total_delta,
            ROUND(SUM(p.quantity * o.gamma * 100), 6) AS total_gamma,
            ROUND(SUM(p.quantity * o.vega), 4) AS total_vega,
            ROUND(SUM(p.quantity * o.theta), 4) AS total_theta,
            COUNT(*) AS position_count
        FROM fd_positions p
        JOIN latest_options o
          ON p.ticker = o.ticker
         AND p.expiry = o.expiry  -- Exact date match
         AND ABS(p.strike - o.strike) < 0.01  -- Handle floating point precision
         AND UPPER(p.type) = UPPER(o.type)
        WHERE o.rn = 1  -- Latest data only
        GROUP BY p.ticker
    """,
        (ticker,),
    )

    row = cur.fetchone()
    if not row or row["position_count"] == 0:
        print(f"⚠️ Geen matching posities gevonden voor {ticker} — snapshot overgeslagen.")
        cur.close()
        conn.close()
        return

    # Insert snapshot
    cur.execute(
        """
        INSERT INTO fd_greeks_history
        (ticker, timestamp, total_delta, total_gamma, total_vega, total_theta, source)
        VALUES (%s, %s, %s, %s, %s, %s, 'live')
    """,
        (
            ticker,
            snapshot_time,
            row["total_delta"],
            row["total_gamma"],
            row["total_vega"],
            row["total_theta"],
        ),
    )
    conn.commit()

    print(
        f"✅ Snapshot opgeslagen voor {ticker} ({snapshot_time}) → "
        f"Δ={row['total_delta']}, Γ={row['total_gamma']}, "
        f"Θ={row['total_theta']}, ν={row['total_vega']} "
        f"({row['position_count']} posities)"
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
            timestamp,
            total_delta,
            total_gamma,
            total_vega,
            total_theta
        FROM fd_greeks_history
        WHERE ticker = %s
        AND timestamp >= DATE_SUB(NOW(), INTERVAL %s HOUR)
        ORDER BY timestamp DESC
    """,
        (ticker, hours_back),
    )

    results = cur.fetchall()
    cur.close()
    conn.close()

    return results


if __name__ == "__main__":
    record_greek_snapshot()
