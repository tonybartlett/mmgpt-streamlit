"""
app.py — MMGPT Supervisor Dashboard · Home Page

Displays today's run status:
  • Latest RunDate across pipeline stages
  • Pipeline counts (Inbox → Converged → Queue → Dispatched)
  • Top 3 signals by RankGlobal
  • System health indicator
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

import pandas as pd
import streamlit as st

# Ensure project root is on sys.path
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from mmgpt_queries import (
    get_latest_run_date,
    get_pipeline_counts,
    get_top_signals_home,
)

# ──────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="MMGPT Supervisor · Home",
    page_icon="🏠",
    layout="wide",
)

# ──────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────
st.title("MMGPT Supervisor Dashboard")
st.caption("Production staging — wired to SQL Server · Stock Master Default")
st.divider()

# ──────────────────────────────────────────────
# 1. Latest RunDate
# ──────────────────────────────────────────────
df_dates, date_status = get_latest_run_date()

run_date_str: str | None = None
health_ok = True

if df_dates is not None and not df_dates.empty:
    row = df_dates.iloc[0]
    # Determine the most recent RunDate across all tables
    date_cols = ["LatestInbox", "LatestConverged", "LatestQueue", "LatestDispatched", "LatestTradePlan"]
    dates = []
    for c in date_cols:
        val = row.get(c)
        if pd.notna(val):
            dates.append(pd.Timestamp(val))

    if dates:
        latest_ts = max(dates)
        run_date_str = latest_ts.strftime("%Y-%m-%d")
    else:
        health_ok = False
else:
    health_ok = False

# ──────────────────────────────────────────────
# 2. System Health Indicator
# ──────────────────────────────────────────────
col_health, col_date, col_conn = st.columns([1, 1, 1])

with col_health:
    if health_ok:
        st.success("System Health: ONLINE")
    else:
        st.error("System Health: OFFLINE — no RunDate found")

with col_date:
    if run_date_str:
        st.info(f"Latest RunDate: **{run_date_str}**")
    else:
        st.warning("No RunDate available")

with col_conn:
    st.caption(f"Connection: {date_status}")

st.divider()

# ──────────────────────────────────────────────
# 3. Pipeline Counts
# ──────────────────────────────────────────────
if run_date_str:
    st.subheader("Pipeline Overview")

    df_counts, counts_status = get_pipeline_counts(run_date_str)

    if df_counts is not None and not df_counts.empty:
        r = df_counts.iloc[0]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Signals Inbox", f"{int(r.get('InboxCount', 0)):,}")
        c2.metric("Converged", f"{int(r.get('ConvergedCount', 0)):,}")
        c3.metric("Trade Plans", f"{int(r.get('TradePlanCount', 0)):,}")
        c4.metric("Exec Queue", f"{int(r.get('QueueCount', 0)):,}")
        c5.metric("Dispatched", f"{int(r.get('DispatchedCount', 0)):,}")
    else:
        st.warning(f"Could not load pipeline counts. ({counts_status})")

    st.divider()

    # ──────────────────────────────────────────
    # 4. Top 3 Signals
    # ──────────────────────────────────────────
    st.subheader("Top 3 Signals by Rank")

    df_top, top_status = get_top_signals_home(run_date_str, top_n=3)

    if df_top is not None and not df_top.empty:
        for idx, sig in df_top.iterrows():
            rank = sig.get("RankGlobal", "—")
            ticker = sig.get("Ticker", "—")
            side = sig.get("Side", "—")
            score = sig.get("CompositeScore", 0)
            risk = sig.get("RiskBand", "—")
            mix = sig.get("StrategyMixCategory", "—")
            n_strat = sig.get("NumStrategies", 0)

            # Color-code risk band
            if str(risk).lower() == "high":
                risk_color = "🟢"
            elif str(risk).lower() == "medium":
                risk_color = "🟡"
            else:
                risk_color = "🔴"

            cols = st.columns([0.5, 1.5, 1, 1, 1, 1, 1])
            cols[0].markdown(f"**#{rank}**")
            cols[1].markdown(f"**{ticker}**")
            cols[2].markdown(f"{side}")
            cols[3].markdown(f"Score: {score:.2f}" if isinstance(score, (int, float)) else f"Score: {score}")
            cols[4].markdown(f"{risk_color} {risk}")
            cols[5].markdown(f"{mix}")
            cols[6].markdown(f"{n_strat} strategies")
    else:
        st.info(f"No top signals available. ({top_status})")

    st.divider()

# ──────────────────────────────────────────────
# 5. Quick Navigation
# ──────────────────────────────────────────────
st.subheader("Navigation")

nav_cols = st.columns(4)
nav_cols[0].page_link("pages/1_Supervisor_Signals.py", label="Supervisor Signals", icon="📡")
nav_cols[1].page_link("pages/2_Performance.py", label="Strategy Performance", icon="📈")
nav_cols[2].page_link("pages/3_Execution_Queue.py", label="Execution Queue", icon="📋")
nav_cols[3].page_link("pages/6_Candle_Screener.py", label="Candle Screener", icon="🕯️")

st.divider()

# ──────────────────────────────────────────────
# Footer
# ──────────────────────────────────────────────
st.caption(
    f"Last refreshed: {datetime.now().strftime('%d %b %Y %H:%M:%S')}  ·  "
    "MMGPT Supervisor v3  ·  Stock Master Default"
)
