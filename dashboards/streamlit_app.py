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


@st.cache_data(ttl=60)
def get_latest_regime_signal() -> pd.DataFrame:
    """Get latest regime analysis with EVPS signals per expiry - based on your SQL query."""
    try:
        query = """
        WITH latest AS (
          SELECT
              expiry,
              ROUND(AVG(spot_price), 3) AS avg_spot,
              ROUND(AVG(iv_mid), 4) AS avg_iv,
              ROUND(AVG(iv_delta_15m), 5) AS avg_iv_delta,
              ROUND(AVG(vpi), 5) AS avg_vpi,
              ROUND(AVG(iv_spread), 4) AS avg_spread,
              ROUND(AVG(size_imbalance), 4) AS avg_imbalance,
              ROUND(AVG(bidask_spread_pct), 4) AS avg_bidask,
              COALESCE(SUM(volume), 0) AS total_volume,
              ROUND(SUM(delta_exposure), 2) AS total_delta,
              ROUND(SUM(gamma_exposure), 2) AS total_gamma,
              ROUND(SUM(vega_exposure), 2) AS total_vega,
              ROUND(AVG(vega_exposure / NULLIF(ABS(gamma_exposure), 0)), 4) AS vega_gamma_ratio,
              MAX(created_at) AS last_update
          FROM option_prices_live
          WHERE expiry IN ('November 2025', 'December 2025', 'Januari 2026', 'Maart 2026')
            AND created_at = (SELECT MAX(created_at) FROM option_prices_live)
          GROUP BY expiry
        ),
        scored AS (
          SELECT *,
              ROUND((COALESCE(avg_vpi, 0) * 1.5) + (COALESCE(avg_iv_delta, 0) * 10) + (COALESCE(avg_spread, 0) * 5), 5) AS evps_signal,
              CASE
                WHEN (COALESCE(avg_vpi, 0) > 0.1 AND COALESCE(avg_iv_delta, 0) > 0.001) THEN '🔴 Strong Risk-Off (Vol Demand ↑)'
                WHEN (COALESCE(avg_vpi, 0) > 0.03 AND COALESCE(avg_iv_delta, 0) > 0) THEN '🟠 Mild Risk-Off (Hedge Buying)'
                WHEN (COALESCE(avg_vpi, 0) < -0.05 AND COALESCE(avg_iv_delta, 0) < 0) THEN '🟢 Risk-On (Vol Unwind ↓)'
                WHEN ABS(COALESCE(avg_vpi, 0)) < 0.02 AND ABS(COALESCE(avg_iv_delta, 0)) < 0.0005 THEN '⚖️ Neutral / Rangebound'
                ELSE '🟠 Mixed / Transition'
              END AS regime_state,
              CASE
                WHEN (COALESCE(avg_vpi, 0) > 0.05 AND COALESCE(avg_iv_delta, 0) > 0) THEN '↓ Predicted Down Pressure'
                WHEN (COALESCE(avg_vpi, 0) < -0.05 AND COALESCE(avg_iv_delta, 0) < 0) THEN '↑ Predicted Up Pressure'
                ELSE '→ Flat / Neutral'
              END AS predicted_direction
          FROM latest
        )
        SELECT
          expiry,
          avg_spot,
          avg_iv,
          avg_vpi,
          avg_iv_delta,
          avg_spread,
          avg_bidask,
          avg_imbalance,
          evps_signal,
          regime_state,
          predicted_direction,
          total_volume,
          total_delta,
          total_gamma,
          total_vega,
          vega_gamma_ratio,
          last_update
        FROM scored
        ORDER BY expiry;
        """
        conn = get_connection()
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Failed to load regime signals: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120)
def load_data(days_back: int = 7) -> pd.DataFrame:
    """Load recent option snapshots from DB and return a pandas DataFrame.
    We fetch only necessary fields to minimize transfer.
    """
    since = datetime.now() - timedelta(days=days_back)
    query = """
        SELECT created_at, fetched_at, ticker, type, expiry, strike,
               price, bid, ask, bid_size, ask_size, volume,
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
        "volume",
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
        spread_pct_mean=("bidask_spread_pct", "mean"),
        size_imbalance_mean=("size_imbalance", "mean"),
        delta_exp_net=("delta_exposure", "sum"),
        gamma_exp_net=("gamma_exposure", "sum"),
        vega_exp_net=("vega_exposure", "sum"),
        theta_exp_net=("theta_exposure", "sum"),
        n=("spot_price", "count"),
    )

    # Calculate moneyness ATM share separately
    agg["moneyness_atm_share"] = df.groupby("ts15")["moneyness"].apply(
        lambda x: ((x - 1.0).abs() <= 0.05).mean()
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
    if auto_refresh:
        st.toast("Auto-refresh enabled (15m)", icon="⏱️")
        # Note: Auto-refresh requires manual browser refresh or st.rerun() in newer versions


# ---------------------------
# Load & compute
# ---------------------------
last_ts = _get_last_created_at()
st.info(f"Latest DB snapshot: {last_ts}" if last_ts else "No data yet — waiting for ETL run")

# Load regime signals
regime_signals = get_latest_regime_signal()

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
# Regime Signals & EVPS Analysis per Expiry
# ---------------------------
if not regime_signals.empty:
    st.subheader("🎯 Live Volatility Stress & Regime Analysis by Expiry")

    # Display regime signals in expandable cards
    for _, row in regime_signals.iterrows():
        regime_color = (
            "🔴"
            if "Strong Risk-Off" in row["regime_state"]
            else (
                "🟠"
                if "Mild Risk-Off" in row["regime_state"] or "Mixed" in row["regime_state"]
                else "🟢" if "Risk-On" in row["regime_state"] else "⚖️"
            )
        )

        with st.expander(
            f"{regime_color} {row['expiry']} | EVPS: {row['evps_signal']:.3f} | {row['regime_state']}",
            expanded=True,
        ):
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("VPI (Volatility Pressure)", f"{row['avg_vpi']:.4f}")
                st.metric("IV Delta 15m", f"{row['avg_iv_delta']:.5f}")
                st.metric("IV Spread", f"{row['avg_spread']:.4f}")

            with col2:
                st.metric("Bid-Ask Spread %", f"{row['avg_bidask']:.2f}%")
                st.metric("Size Imbalance", f"{row['avg_imbalance']:.4f}")
                st.metric("Total Volume", f"{int(row['total_volume'])}")

            with col3:
                st.metric("Net Delta Exposure", f"{row['total_delta']:,.0f}")
                st.metric("Net Gamma Exposure", f"{row['total_gamma']:,.0f}")
                st.metric("Net Vega Exposure", f"{row['total_vega']:,.0f}")

            # Prediction signal
            pred_color = (
                "🔴"
                if "Down" in row["predicted_direction"]
                else "🟢" if "Up" in row["predicted_direction"] else "🟡"
            )
            st.info(f"{pred_color} **Prediction**: {row['predicted_direction']}")

            # EVPS breakdown
            vpi_contrib = row["avg_vpi"] * 1.5 if row["avg_vpi"] else 0
            iv_delta_contrib = row["avg_iv_delta"] * 10 if row["avg_iv_delta"] else 0
            spread_contrib = row["avg_spread"] * 5 if row["avg_spread"] else 0

            st.caption(
                f"EVPS Components: VPI({vpi_contrib:.3f}) + IV_Δ({iv_delta_contrib:.3f}) + Spread({spread_contrib:.3f}) = {row['evps_signal']:.3f}"
            )
else:
    st.warning("No regime signals available for latest snapshot")


# ---------------------------
# Enhanced Charts with Volatility Stress Visualization
# ---------------------------
st.subheader("📈 Spot Price Trend with Volatility Stress Signals")

# Create a combined chart with spot price and EVPS overlay
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

if PLOTLY_AVAILABLE:
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        subplot_titles=("Spot Price with EMAs", "EVPS & Volatility Stress"),
        vertical_spacing=0.1,
        row_heights=[0.7, 0.3],
    )

    # Spot price with EMAs
    fig.add_trace(
        go.Scatter(
            x=feat["ts15"], y=feat["spot"], name="Spot Price", line=dict(color="blue", width=2)
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=feat["ts15"], y=feat["ema_fast"], name="EMA Fast", line=dict(color="orange", width=1)
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=feat["ts15"], y=feat["ema_slow"], name="EMA Slow", line=dict(color="red", width=1)
        ),
        row=1,
        col=1,
    )

    # EVPS with stress levels
    fig.add_trace(
        go.Scatter(x=feat["ts15"], y=feat["evps"], name="EVPS", line=dict(color="purple", width=2)),
        row=2,
        col=1,
    )
    fig.add_hline(
        y=0.1, line_dash="dash", line_color="red", annotation_text="High Stress", row=2, col=1
    )
    fig.add_hline(
        y=-0.1, line_dash="dash", line_color="green", annotation_text="Low Stress", row=2, col=1
    )

    # Add background colors for stress zones
    fig.add_hrect(y0=0.1, y1=1, fillcolor="red", opacity=0.1, row=2, col=1)
    fig.add_hrect(y0=-1, y1=-0.1, fillcolor="green", opacity=0.1, row=2, col=1)

    fig.update_layout(height=600, title="Volatility Stress & Price Action Analysis")
    st.plotly_chart(fig, use_container_width=True)

    # VPI and IV Delta correlation chart
    st.subheader("🔥 VPI vs IV Delta - Leading Indicator Matrix")
    fig2 = go.Figure()
    # Handle NaN values in marker sizing
    marker_sizes = feat["ret_15m"].abs() * 1000
    marker_sizes = marker_sizes.fillna(10)  # Default size for NaN values
    marker_colors = feat["ret_15m"].fillna(0)  # Default color for NaN values

    fig2.add_trace(
        go.Scatter(
            x=feat["vpi_mean"],
            y=feat["iv_mid_mean"],
            mode="markers+lines",
            marker=dict(
                size=marker_sizes,  # Size by return magnitude
                color=marker_colors,
                colorscale="RdYlGn_r",
                showscale=True,
                colorbar=dict(title="15m Return"),
            ),
            line=dict(width=1, color="gray"),
            name="VPI-IV Path",
        )
    )

    # Add quadrant lines
    fig2.add_hline(y=feat["iv_mid_mean"].median(), line_dash="dot", line_color="gray")
    fig2.add_vline(x=0, line_dash="dot", line_color="gray")

    # Add annotations for quadrants
    fig2.add_annotation(
        x=0.05,
        y=feat["iv_mid_mean"].max() * 0.9,
        text="Risk-Off<br/>Vol Demand",
        showarrow=False,
        bgcolor="rgba(255,0,0,0.1)",
    )
    fig2.add_annotation(
        x=-0.05,
        y=feat["iv_mid_mean"].max() * 0.9,
        text="Risk-On<br/>Vol Unwind",
        showarrow=False,
        bgcolor="rgba(0,255,0,0.1)",
    )

    fig2.update_layout(
        title="VPI-IV Regime Map (bubble size = return magnitude)",
        xaxis_title="VPI (Volatility Pressure Index)",
        yaxis_title="IV Mid",
        height=500,
    )
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.warning("Install plotly for enhanced volatility stress visualizations: pip install plotly")

st.subheader("📊 Traditional Charts")
spot_df = feat.set_index("ts15")[["spot", "ema_fast", "ema_slow"]].rename(
    columns={"spot": "Spot", "ema_fast": "EMA Fast", "ema_slow": "EMA Slow"}
)
st.line_chart(spot_df)

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
# EVPS Alert System
# ---------------------------
st.subheader("⚠️ EVPS Alert System - Volatility Stress Buildup Detection")

if not regime_signals.empty:
    high_stress_expiries = regime_signals[regime_signals["evps_signal"] > 0.05]
    risk_off_expiries = regime_signals[regime_signals["regime_state"].str.contains("Risk-Off")]

    if not high_stress_expiries.empty or not risk_off_expiries.empty:
        st.error("🚨 **VOLATILITY STRESS ALERT** - Potential price drop conditions detected!")

        for _, row in high_stress_expiries.iterrows():
            st.markdown(f"- **{row['expiry']}**: EVPS = {row['evps_signal']:.3f} (High Stress)")

        for _, row in risk_off_expiries.iterrows():
            st.markdown(
                f"- **{row['expiry']}**: {row['regime_state']} → {row['predicted_direction']}"
            )
    else:
        st.success("✅ No high volatility stress detected across expiries")

    # Show stress buildup trend
    recent_evps = feat["evps"].tail(6)  # Last 6 periods (1.5h)
    evps_trend = "Rising" if recent_evps.iloc[-1] > recent_evps.iloc[0] else "Falling"
    evps_change = recent_evps.iloc[-1] - recent_evps.iloc[0]

    if abs(evps_change) > 0.05:
        trend_color = "🔴" if evps_trend == "Rising" else "🟢"
        st.info(f"{trend_color} **EVPS Trend (1.5h)**: {evps_trend} by {evps_change:+.3f}")

    # Key thresholds
    st.markdown("**Alert Thresholds:**")
    st.markdown("- EVPS > 0.05: High volatility stress")
    st.markdown("- VPI > 0.1 + IV_Δ > 0.001: Strong risk-off signal")
    st.markdown("- Rising EVPS trend over 1.5h: Building pressure")

# ---------------------------
# Notes & definitions
# ---------------------------
with st.expander("Metric definitions & EVPS Formula"):
    st.markdown(
        """
        ## Core Metrics
        - **Spot**: median underlying price across options in snapshot.
        - **Trend**: EMA Fast (~1.5h) vs EMA Slow (~5h) on 15m bars.
        - **IV Mid/Spread**: average implied vol mid/spread across contracts.
        - **VPI**: IV delta vs previous snapshot normalized by IV spread.
        - **Moneyness ATM Share**: fraction of contracts with |S/K - 1| <= 5%.
        - **Spread %**: mean bid-ask spread relative to mid price.
        - **Size Imbalance**: mean (ask_size - bid_size) / (ask_size + bid_size).
        - **Exposures**: net sum of Greek exposures (100-share contract assumptions).

        ## EVPS (Expected Volatility Pressure Signal)
        **Formula**: `EVPS = (VPI × 1.5) + (IV_Delta_15m × 10) + (IV_Spread × 5)`

        **Components:**
        - **VPI × 1.5**: Volatility pressure index weighted 1.5x
        - **IV_Delta_15m × 10**: 15-minute IV change amplified 10x
        - **IV_Spread × 5**: IV spread contribution weighted 5x

        **Interpretation:**
        - EVPS > 0.05: High stress, potential downside pressure
        - EVPS < -0.05: Low stress, potential upside
        - Rising EVPS trend: Volatility stress building up

        ## Regime States
        - 🔴 **Strong Risk-Off**: VPI > 0.1 AND IV_Δ > 0.001 (Vol demand surge)
        - 🟠 **Mild Risk-Off**: VPI > 0.03 AND IV_Δ > 0 (Hedge buying)
        - 🟢 **Risk-On**: VPI < -0.05 AND IV_Δ < 0 (Vol unwind)
        - ⚖️ **Neutral**: Low VPI and IV_Δ activity
        """
    )
