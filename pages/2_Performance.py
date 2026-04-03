"""
Page 2 — Strategy Performance

Displays:
  • Key metrics: overall win rate, total trades, avg return
  • Per-strategy table from vwSupervisor_ControlPanel (latest + 7/30/90d rollups)
  • WinRate over time line chart from Supervisor_Dashboard_History
"""

from __future__ import annotations

import os
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from mmgpt_queries import (
    get_control_panel,
    get_dashboard_history,
    get_performance_summary,
)

# ──────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="MMGPT · Strategy Performance",
    page_icon="📈",
    layout="wide",
)

st.title("Strategy Performance")
st.caption("Per-strategy metrics from vwSupervisor_ControlPanel + historical trends")
st.divider()

# ──────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")
    history_days = st.slider("History lookback (days)", min_value=7, max_value=365, value=90, step=7)

# ──────────────────────────────────────────────
# 1. Key Metrics
# ──────────────────────────────────────────────
st.subheader("Overall Performance")

df_perf, perf_status = get_performance_summary()

if df_perf is not None and not df_perf.empty:
    p = df_perf.iloc[0]
    k1, k2, k3, k4 = st.columns(4)
    def _safe_int(val, default=0):
        if val is None:
            return default
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return default

    k1.metric("Total Strategies", f"{_safe_int(p.get('TotalStrategies')):,}")
    k2.metric("Total Trades", f"{_safe_int(p.get('TotalTrades')):,}")

    # Safe float conversion — values may arrive as str, None, or NaN from bridge
    def _safe_float(val, default=None):
        if val is None:
            return default
        try:
            f = float(val)
            return f if pd.notna(f) else default
        except (ValueError, TypeError):
            return default

    avg_wr = _safe_float(p.get("AvgWinRate"))
    k3.metric("Avg Win Rate", f"{avg_wr:.1f}%" if avg_wr is not None else "—")

    avg_ret = _safe_float(p.get("AvgReturnPct"))
    k4.metric("Avg Return %", f"{avg_ret:.2f}%" if avg_ret is not None else "—")
else:
    st.info(f"Performance summary not available. ({perf_status})")

st.divider()

# ──────────────────────────────────────────────
# 2. Control Panel — per-strategy table
# ──────────────────────────────────────────────
st.subheader("Strategy Control Panel")

df_cp, cp_status = get_control_panel()

if df_cp is not None and not df_cp.empty:
    # Format percentage columns if they exist
    pct_cols = [c for c in df_cp.columns if "Rate" in c or "Pct" in c or "Return" in c]
    for col in pct_cols:
        df_cp[col] = pd.to_numeric(df_cp[col], errors="coerce")

    st.dataframe(
        df_cp,
        use_container_width=True,
        hide_index=True,
        height=450,
    )
    st.caption(f"Source: {cp_status}")
else:
    st.warning(f"Control panel data not available. ({cp_status})")

st.divider()

# ──────────────────────────────────────────────
# 3. WinRate over time — line chart
# ──────────────────────────────────────────────
st.subheader(f"Win Rate Trend (Last {history_days} Days)")

df_hist, hist_status = get_dashboard_history(days=history_days)

if df_hist is not None and not df_hist.empty:
    # Ensure proper types
    if "AsOfDate" in df_hist.columns:
        df_hist["AsOfDate"] = pd.to_datetime(df_hist["AsOfDate"], errors="coerce")
    if "WinRate" in df_hist.columns:
        df_hist["WinRate"] = pd.to_numeric(df_hist["WinRate"], errors="coerce")

    if "Strategy" in df_hist.columns and "WinRate" in df_hist.columns:
        fig_wr = px.line(
            df_hist,
            x="AsOfDate",
            y="WinRate",
            color="Strategy",
            title="Win Rate by Strategy Over Time",
            labels={"AsOfDate": "Date", "WinRate": "Win Rate (%)"},
        )
        fig_wr.update_layout(
            height=420,
            margin=dict(l=20, r=20, t=40, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_wr, use_container_width=True)
    else:
        st.info("WinRate or Strategy column not found in history data.")

    # ── Avg Return trend ──
    if "AvgReturnPct" in df_hist.columns:
        df_hist["AvgReturnPct"] = pd.to_numeric(df_hist["AvgReturnPct"], errors="coerce")

        st.subheader(f"Avg Return % Trend (Last {history_days} Days)")
        fig_ret = px.line(
            df_hist,
            x="AsOfDate",
            y="AvgReturnPct",
            color="Strategy",
            title="Average Return % by Strategy Over Time",
            labels={"AsOfDate": "Date", "AvgReturnPct": "Avg Return (%)"},
        )
        fig_ret.update_layout(
            height=380,
            margin=dict(l=20, r=20, t=40, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_ret, use_container_width=True)

    # ── Trades trend ──
    if "Trades" in df_hist.columns:
        df_hist["Trades"] = pd.to_numeric(df_hist["Trades"], errors="coerce")

        st.subheader(f"Trade Count Trend (Last {history_days} Days)")
        fig_trades = px.bar(
            df_hist,
            x="AsOfDate",
            y="Trades",
            color="Strategy",
            title="Daily Trade Count by Strategy",
            labels={"AsOfDate": "Date", "Trades": "Trades"},
        )
        fig_trades.update_layout(
            height=350,
            margin=dict(l=20, r=20, t=40, b=20),
            barmode="stack",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_trades, use_container_width=True)

    st.caption(f"History source: {hist_status}")
else:
    st.warning(f"No dashboard history available. ({hist_status})")
