"""
app.py  —  MMGPT Supervisor Dashboard  ·  Home Page

Connection strategy (in order):
  1. Supervisor API bridge  (reads [bridge] section from st.secrets)
  2. Direct pyodbc          (local VM only — Windows Auth)

A clear banner at the top shows which mode is active.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Optional

import pandas as pd
import streamlit as st

# ── path setup ────────────────────────────────────────────────────────────────
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import bridge_client
from mmgpt_queries import (
    get_latest_run_date,
    get_pipeline_counts,
    get_top_signals_home,
)

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MMGPT Supervisor · Home",
    page_icon="🏠",
    layout="wide",
)


# ═══════════════════════════════════════════════════════════════════════════
#  1.  Detect active connection mode
# ═══════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=30, show_spinner=False)
def _probe_bridge() -> bool:
    """Return True if the bridge /ping endpoint is reachable."""
    result = bridge_client.ping(timeout=8)
    return result is not None


bridge_online = _probe_bridge()

# Determine the connection label shown in the UI
if bridge_online:
    _conn_mode   = "bridge"
    _conn_label  = "Supervisor API Bridge"
    _conn_icon   = "🌐"
    _conn_colour = "success"
else:
    _conn_mode   = "pyodbc"
    _conn_label  = "Direct pyodbc (local VM)"
    _conn_icon   = "🖥️"
    _conn_colour = "info"


# ── inject bridge URL into data_source so mmgpt_queries uses the right path ──
# data_source.py reads MMGPT_SQL_BRIDGE_URL from env; we set it here so the
# existing query functions pick up the secrets-configured URL automatically.
if bridge_online:
    _bridge_url = bridge_client.get_base_url()
    os.environ["MMGPT_SQL_BRIDGE_URL"] = _bridge_url
    _api_key = bridge_client.get_api_key()
    if _api_key:
        os.environ["BRIDGE_API_KEY"] = _api_key


# ═══════════════════════════════════════════════════════════════════════════
#  2.  Header
# ═══════════════════════════════════════════════════════════════════════════

st.title("MMGPT Supervisor Dashboard")
st.caption("Production — Stock Master Default  ·  MMGPTVM\\ASXSQLDATA")

# ── Connection mode banner ────────────────────────────────────────────────
if _conn_colour == "success":
    st.success(
        f"{_conn_icon}  **Connection mode: {_conn_label}**  ·  "
        f"Bridge URL: `{bridge_client.get_base_url()}`"
    )
else:
    st.info(
        f"{_conn_icon}  **Connection mode: {_conn_label}**  ·  "
        "Bridge not reachable — using direct Windows Auth connection"
    )

st.divider()


# ═══════════════════════════════════════════════════════════════════════════
#  3.  Latest RunDate
# ═══════════════════════════════════════════════════════════════════════════

df_dates, date_status = get_latest_run_date()
run_date_str: Optional[str] = None
health_ok = True

if df_dates is not None and not df_dates.empty:
    row = df_dates.iloc[0]
    date_cols = ["LatestInbox", "LatestConverged", "LatestQueue", "LatestDispatched", "LatestTradePlan"]
    dates = []
    for c in date_cols:
        val = row.get(c)
        if pd.notna(val):
            dates.append(pd.Timestamp(val))
    if dates:
        run_date_str = max(dates).strftime("%Y-%m-%d")
    else:
        health_ok = False
else:
    health_ok = False


# ═══════════════════════════════════════════════════════════════════════════
#  4.  System health row
# ═══════════════════════════════════════════════════════════════════════════

col_health, col_date, col_conn = st.columns(3)

with col_health:
    if health_ok:
        st.success("System Health: **ONLINE**")
    else:
        st.error("System Health: **OFFLINE** — no RunDate found")

with col_date:
    if run_date_str:
        st.info(f"Latest RunDate: **{run_date_str}**")
    else:
        st.warning("No RunDate available")

with col_conn:
    st.caption(f"Data source: {date_status}")
    if _conn_mode == "bridge":
        st.caption(f"Bridge: `{bridge_client.get_base_url()}`")

st.divider()


# ═══════════════════════════════════════════════════════════════════════════
#  5.  Pipeline counts
# ═══════════════════════════════════════════════════════════════════════════

if run_date_str:
    st.subheader("Pipeline Overview")
    df_counts, counts_status = get_pipeline_counts(run_date_str)
    if df_counts is not None and not df_counts.empty:
        r = df_counts.iloc[0]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Signals Inbox",  f"{int(r.get('InboxCount',      0)):,}")
        c2.metric("Converged",      f"{int(r.get('ConvergedCount',  0)):,}")
        c3.metric("Trade Plans",    f"{int(r.get('TradePlanCount',  0)):,}")
        c4.metric("Exec Queue",     f"{int(r.get('QueueCount',      0)):,}")
        c5.metric("Dispatched",     f"{int(r.get('DispatchedCount', 0)):,}")
    else:
        st.warning(f"Could not load pipeline counts. ({counts_status})")

    st.divider()

    # ── Top 3 signals ────────────────────────────────────────────────────
    st.subheader("Top 3 Signals by Rank")
    df_top, top_status = get_top_signals_home(run_date_str, top_n=3)
    if df_top is not None and not df_top.empty:
        for _, sig in df_top.iterrows():
            rank    = sig.get("RankGlobal", "—")
            ticker  = sig.get("Ticker", "—")
            side    = sig.get("Side", "—")
            score   = sig.get("CompositeScore", 0)
            risk    = sig.get("RiskBand", "—")
            mix     = sig.get("StrategyMixCategory", "—")
            n_strat = sig.get("NumStrategies", 0)

            risk_icon = {"high": "🟢", "medium": "🟡"}.get(str(risk).lower(), "🔴")

            cols = st.columns([0.5, 1.5, 1, 1, 1, 1, 1])
            cols[0].markdown(f"**#{rank}**")
            cols[1].markdown(f"**{ticker}**")
            cols[2].markdown(str(side))
            cols[3].markdown(f"Score: {score:.2f}" if isinstance(score, float) else f"Score: {score}")
            cols[4].markdown(f"{risk_icon} {risk}")
            cols[5].markdown(str(mix))
            cols[6].markdown(f"{n_strat} strategies")
    else:
        st.info(f"No top signals available. ({top_status})")

    st.divider()


# ═══════════════════════════════════════════════════════════════════════════
#  6.  Quick navigation
# ═══════════════════════════════════════════════════════════════════════════

st.subheader("Navigation")
nav_cols = st.columns(5)
nav_cols[0].page_link("pages/0_Bridge_Status.py",      label="Bridge Status",        icon="🌐")
nav_cols[1].page_link("pages/1_Supervisor_Signals.py", label="Supervisor Signals",   icon="📡")
nav_cols[2].page_link("pages/2_Performance.py",        label="Strategy Performance", icon="📈")
nav_cols[3].page_link("pages/3_Execution_Queue.py",    label="Execution Queue",      icon="📋")
nav_cols[4].page_link("pages/6_Candle_Screener.py",    label="Candle Screener",      icon="🕯️")

st.divider()


# ═══════════════════════════════════════════════════════════════════════════
#  7.  Footer
# ═══════════════════════════════════════════════════════════════════════════

st.caption(
    f"Last refreshed: {datetime.now().strftime('%d %b %Y %H:%M:%S')}  ·  "
    f"MMGPT Supervisor v3  ·  Mode: {_conn_label}"
)
