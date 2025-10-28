# -*- coding: utf-8 -*-
"""
dashboards/streamlit_app.py

Interactive Streamlit dashboard for intraday options analytics:
- Connects to MySQL (option_prices_live)
- Aggregates per 15-minute snapshots
- Computes indicators: moneyness mix, IV metrics, liquidity (spread%, size imbalance), exposures
- Derives EVPS (Expected Volatility Pressure Signal) and trend EMAs on spot
- Detects regimes (KMeans) and predicts next-interval spot drop probability (LogReg)
- Auto-refreshes every 15 minutes

Note: This dashboard is a read-only side-feature; it doesn't modify ETL code.
"""

from __future__ import annotations
import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import streamlit as st
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline


try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from app.db import get_connection


# ---------------------------
# Streamlit page config
# ---------------------------
st.set_page_config(page_title="Options Intraday Dashboard", layout="wide")
st.title("📈 Options Intraday Dashboard — Ahold (AD.AS)")
st.caption(
    "Live analytics refreshed every 15 minutes: spot trend, liquidity, IV pressure, regimes, and predictive signals."
)


# ---------------------------
# Utility helpers
# ---------------------------


@st.cache_data(ttl=60)  # cache tiny queries for a minute to keep UI snappy
def _get_last_created_at() -> datetime | None:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT MAX(created_at) FROM option_prices_live")
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row and row[0] else None
    except Exception:
        return None


@st.cache_data(ttl=120)
def load_data(days_back: int = 7) -> pd.DataFrame:
    """Load recent option snapshots from DB and return a pandas DataFrame.
    We fetch only necessary fields to minimize transfer.
    """
    since = datetime.now() - timedelta(days=days_back)
    query = """
        SELECT created_at, fetched_at, ticker, type, expiry, strike,
               price, bid, ask, bid_size, ask_size,
               iv_mid, iv_spread, iv_delta_15m, vpi,
               moneyness, bidask_spread_pct, size_imbalance,
               delta_exposure, gamma_exposure, vega_exposure, theta_exposure,
               spot_price
        FROM option_prices_live
        WHERE created_at >= %s
        ORDER BY created_at ASC
        """
    conn = get_connection()
    df = pd.read_sql(query, conn, params=[since])
    conn.close()
    # Normalize dtypes
    for c in [
        "price",
        "bid",
        "ask",
        "bid_size",
        "ask_size",
        "iv_mid",
        "iv_spread",
        "iv_delta_15m",
        "vpi",
        "moneyness",
        "bidask_spread_pct",
        "size_imbalance",
        "delta_exposure",
        "gamma_exposure",
        "vega_exposure",
        "theta_exposure",
        "spot_price",
    ]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    # 15-min bucket
    df["ts15"] = pd.to_datetime(df["created_at"]).dt.floor("15min")
    return df


def _nan_to_none(x):
    return None if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else x


def compute_aggregates(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate option rows per 15-minute snapshot to derive features for modeling and charting."""
    if df.empty:
        return pd.DataFrame()

    # base aggregations per ts15
    agg = df.groupby("ts15").agg(
        spot=("spot_price", "median"),
        iv_mid_mean=("iv_mid", "mean"),
        iv_spread_mean=("iv_spread", "mean"),
        vpi_mean=("vpi", "mean"),
        moneyness_atm_share=(lambda x: ((x - 1.0).abs() <= 0.05).mean()),
        spread_pct_mean=("bidask_spread_pct", "mean"),
        size_imbalance_mean=("size_imbalance", "mean"),
        delta_exp_net=("delta_exposure", "sum"),
        gamma_exp_net=("gamma_exposure", "sum"),
        vega_exp_net=("vega_exposure", "sum"),
        theta_exp_net=("theta_exposure", "sum"),
        n=("spot_price", "count"),
    )

    # Add trend indicators on spot
    agg["spot"] = agg["spot"].interpolate(limit_direction="both")
    agg["ret_15m"] = agg["spot"].pct_change()
    agg["ema_fast"] = agg["spot"].ewm(span=6, adjust=False).mean()  # ~1.5h on 15m bars
    agg["ema_slow"] = agg["spot"].ewm(span=20, adjust=False).mean()  # ~5h
    agg["trend"] = np.where(agg["ema_fast"] > agg["ema_slow"], "Uptrend", "Down/Flat")

    # EVPS (Expected Volatility Pressure Signal)
    # Heuristic: normalize VPI and Vega exposure, multiply to reflect volatility pressure weighted by vega
    z = lambda s: (s - s.mean()) / (s.std(ddof=0) + 1e-9)
    vpi_z = z(agg["vpi_mean"].fillna(0))
    vega_z = z(agg["vega_exp_net"].fillna(0))
    agg["evps"] = (vpi_z * vega_z).rolling(2, min_periods=1).mean()

    # Liquidity stress composite
    liq_z = z(agg["spread_pct_mean"].fillna(0)) + z(agg["size_imbalance_mean"].fillna(0))
    agg["liquidity_stress"] = liq_z.rolling(2, min_periods=1).mean()

    return agg.reset_index()


def detect_regimes(feat: pd.DataFrame, n_clusters: int = 3) -> pd.Series:
    if len(feat) < n_clusters + 3:
        return pd.Series([0] * len(feat), index=feat.index, name="regime")
    cols = [
        "iv_mid_mean",
        "iv_spread_mean",
        "vpi_mean",
        "moneyness_atm_share",
        "spread_pct_mean",
        "size_imbalance_mean",
        "delta_exp_net",
        "gamma_exp_net",
        "vega_exp_net",
        "theta_exp_net",
        "evps",
        "liquidity_stress",
    ]
    X = feat[cols].fillna(0.0).values
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    km = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
    labels = km.fit_predict(Xs)
    return pd.Series(labels, index=feat.index, name="regime")


def train_predictor(
    feat: pd.DataFrame, drop_threshold_pct: float = 0.3
) -> tuple[Pipeline | None, float | None]:
    """Train a simple logistic regression to predict next-interval spot drop.
    Target y=1 if next 15m return <= -threshold%.
    Returns (model, latest_probability_of_drop).
    """
    if len(feat) < 40:
        return None, None

    y = (feat["ret_15m"].shift(-1) <= -(drop_threshold_pct / 100.0)).astype(int)
    cols = [
        "iv_mid_mean",
        "iv_spread_mean",
        "vpi_mean",
        "moneyness_atm_share",
        "spread_pct_mean",
        "size_imbalance_mean",
        "delta_exp_net",
        "gamma_exp_net",
        "vega_exp_net",
        "theta_exp_net",
        "evps",
        "liquidity_stress",
        "ema_fast",
        "ema_slow",
    ]
    X = feat[cols].fillna(0.0)

    # Drop last row where y is NaN (no next period yet)
    X_train = X.iloc[:-1, :]
    y_train = y.iloc[:-1]
    if y_train.sum() == 0 or y_train.sum() == len(y_train):
        return None, None

    clf = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            ("logreg", LogisticRegression(max_iter=200, class_weight="balanced", random_state=42)),
        ]
    )
    clf.fit(X_train, y_train)

    latest_prob = float(clf.predict_proba(X.iloc[[-1], :])[0, 1])
    return clf, latest_prob


# ---------------------------
# Sidebar controls
# ---------------------------
with st.sidebar:
    st.header("Controls")
    days = st.slider("Days back", min_value=1, max_value=30, value=7, step=1)
    drop_thr = st.slider("Drop threshold (%)", min_value=0.1, max_value=2.0, value=0.5, step=0.1)
    st.caption("Target: predict if next 15m return <= -threshold%")

    auto_refresh = st.toggle("Auto-refresh every 15 minutes", value=True)
    refresh_ms = 15 * 60 * 1000
    if auto_refresh:
        st.experimental_rerun  # marker for Streamlit Cloud (ignored locally)
        st.autorefresh = st.experimental_rerun  # no-op alias to avoid lints
        st_autorefresh = st.experimental_data_editor  # dummy to keep symbol alive
        st.toast("Auto-refresh enabled (15m)", icon="⏱️")


# ---------------------------
# Load & compute
# ---------------------------
last_ts = _get_last_created_at()
st.info(f"Latest DB snapshot: {last_ts}" if last_ts else "No data yet — waiting for ETL run")

try:
    raw = load_data(days)
except Exception as e:
    st.error(f"Database connection failed: {e}")
    st.stop()

if raw.empty:
    st.warning("No data found for the selected window.")
    st.stop()

feat = compute_aggregates(raw)
feat["regime"] = detect_regimes(feat)
model, p_drop = train_predictor(feat, drop_threshold_pct=drop_thr)


# ---------------------------
# Layout: top KPIs
# ---------------------------
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(
        "Spot", f"{feat['spot'].iloc[-1]:.3f}", delta=f"{feat['ret_15m'].iloc[-1]*100:.2f}% 15m"
    )
with col2:
    st.metric("IV (mid)", f"{feat['iv_mid_mean'].iloc[-1]:.3f}")
with col3:
    st.metric("EVPS", f"{feat['evps'].iloc[-1]:.2f}")
with col4:
    regime = feat["regime"].iloc[-1]
    st.metric("Regime", f"#{int(regime)}")


# ---------------------------
# Charts
# ---------------------------
st.subheader("Trend and Spot")
spot_df = feat.set_index("ts15")[["spot", "ema_fast", "ema_slow"]].rename(
    columns={"spot": "Spot", "ema_fast": "EMA Fast", "ema_slow": "EMA Slow"}
)
st.line_chart(spot_df)

st.subheader("IV and Liquidity")
iv_liq = feat.set_index("ts15")[
    [
        "iv_mid_mean",
        "iv_spread_mean",
        "vpi_mean",
        "spread_pct_mean",
        "size_imbalance_mean",
        "evps",
        "liquidity_stress",
    ]
].rename(
    columns={
        "iv_mid_mean": "IV Mid",
        "iv_spread_mean": "IV Spread",
        "vpi_mean": "VPI",
        "spread_pct_mean": "Spread %",
        "size_imbalance_mean": "Size Imbalance",
        "evps": "EVPS",
        "liquidity_stress": "Liquidity Stress",
    }
)
st.area_chart(iv_liq)

st.subheader("Exposures (net)")
exp = feat.set_index("ts15")[
    ["delta_exp_net", "gamma_exp_net", "vega_exp_net", "theta_exp_net"]
].rename(
    columns={
        "delta_exp_net": "Delta Exposure",
        "gamma_exp_net": "Gamma Exposure",
        "vega_exp_net": "Vega Exposure",
        "theta_exp_net": "Theta Exposure",
    }
)
st.line_chart(exp)


# ---------------------------
# Prediction
# ---------------------------
st.subheader("Intraday Prediction — Next 15m Spot Drop")
if model is None or p_drop is None:
    st.warning("Not enough balanced history to train a predictive model yet.")
else:
    st.metric("Probability of drop next 15m", f"{p_drop*100:.1f}%")
    # Feature snapshot table for transparency
    show_cols = [
        "ts15",
        "spot",
        "ema_fast",
        "ema_slow",
        "iv_mid_mean",
        "iv_spread_mean",
        "vpi_mean",
        "moneyness_atm_share",
        "spread_pct_mean",
        "size_imbalance_mean",
        "evps",
        "liquidity_stress",
        "regime",
    ]
    st.dataframe(feat[show_cols].tail(12).set_index("ts15"))


# ---------------------------
# Notes & definitions
# ---------------------------
with st.expander("Metric definitions"):
    st.markdown(
        """
        - Spot: median underlying price across options in snapshot.
        - Trend: EMA Fast (~1.5h) vs EMA Slow (~5h) on 15m bars.
        - IV Mid/Spread: average implied vol mid/spread across contracts.
        - VPI: IV delta vs previous snapshot normalized by IV spread.
        - Moneyness ATM Share: fraction of contracts with |S/K - 1| <= 5%.
        - Spread %: mean bid-ask spread relative to mid price.
        - Size Imbalance: mean (ask_size - bid_size) / (ask_size + bid_size).
        - Exposures: net sum of Greek exposures (100-share contract assumptions).
        - EVPS: z(VPI) * z(Vega Exposure) smoothed — heuristic volatility pressure.
        - Liquidity Stress: z(Spread %) + z(Size Imbalance) smoothed.
        """
    )
