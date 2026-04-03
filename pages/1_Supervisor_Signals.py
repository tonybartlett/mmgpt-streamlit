"""
Page 1 — Supervisor Signals Dashboard

Displays top trade plans from dbo.Supervisor_TradePlans:
  • Date selector (defaults to MAX RunDate)
  • Summary metrics: total signals, High/Medium/Low counts, avg composite score
  • Top 50 signals table with color-coded Risk Band
  • CSV download
"""

from __future__ import annotations

import os
import sys

import pandas as pd
import streamlit as st

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from mmgpt_queries import (
    get_available_run_dates_converged,
    get_signal_summary,
    get_trade_plans,
)

# ──────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="MMGPT · Supervisor Signals",
    page_icon="📡",
    layout="wide",
)

st.title("Supervisor Signals")
st.caption("Trade plans from dbo.Supervisor_TradePlans — ordered by RankGlobal")
st.divider()

# ──────────────────────────────────────────────
# Sidebar — Date selector
# ──────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")

    df_dates, _ = get_available_run_dates_converged()

    if df_dates is not None and not df_dates.empty:
        date_options = pd.to_datetime(df_dates["RunDate"]).dt.date.tolist()
        selected_date = st.selectbox(
            "Run Date",
            options=date_options,
            index=0,
            format_func=lambda d: d.strftime("%Y-%m-%d"),
        )
    else:
        st.warning("No RunDates found in Signals_Converged.")
        st.stop()

    top_n = st.slider("Max rows", min_value=10, max_value=200, value=50, step=10)

run_date_str = str(selected_date)

# ──────────────────────────────────────────────
# Summary metrics
# ──────────────────────────────────────────────
st.subheader("Summary Metrics")

df_summary, summary_status = get_signal_summary(run_date_str)

if df_summary is not None and not df_summary.empty:
    s = df_summary.iloc[0]
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    def _si(v):
        try: return int(float(v))
        except (ValueError, TypeError): return 0
    def _sf(v):
        try:
            f = float(v)
            return f if pd.notna(f) else None
        except (ValueError, TypeError): return None

    m1.metric("Total Signals", f"{_si(s.get('TotalSignals')):,}")
    m2.metric("High Risk", f"{_si(s.get('HighCount')):,}")
    m3.metric("Medium Risk", f"{_si(s.get('MediumCount')):,}")
    m4.metric("Low Risk", f"{_si(s.get('LowCount')):,}")
    avg_comp = _sf(s.get("AvgComposite"))
    m5.metric("Avg Composite", f"{avg_comp:.2f}" if avg_comp is not None else "—")
    avg_wt = _sf(s.get("AvgWeightPct"))
    m6.metric("Avg Weight %", f"{avg_wt:.2f}%" if avg_wt is not None else "—")
else:
    st.info(f"Summary not available. ({summary_status})")

st.divider()

# ──────────────────────────────────────────────
# Trade Plans table
# ──────────────────────────────────────────────
st.subheader(f"Top {top_n} Trade Plans — {run_date_str}")

df_plans, plans_status = get_trade_plans(run_date_str, top_n=top_n)

if df_plans is not None and not df_plans.empty:
    # Rename columns for display
    display_cols = {
        "RankGlobal": "Rank",
        "Ticker": "Ticker",
        "SignalSide": "Side",
        "EntryPrice": "Entry Price",
        "StopLossPrice": "Stop Loss",
        "TakeProfitPrice": "Take Profit",
        "TakeProfitPct": "TP %",
        "StopLossPct": "SL %",
        "WeightPct": "Weight %",
        "CompositeScore": "Composite Score",
        "RiskBand": "Risk Band",
        "StrategyMixCategory": "Strategy Mix",
        "StrategiesHit": "Strategies Hit",
        "NumStrategies": "# Strategies",
    }

    # Select only columns that exist
    available = [c for c in display_cols if c in df_plans.columns]
    df_display = df_plans[available].rename(columns=display_cols)

    # Format numeric columns
    for col in ["Entry Price", "Stop Loss", "Take Profit"]:
        if col in df_display.columns:
            df_display[col] = pd.to_numeric(df_display[col], errors="coerce").map(
                lambda x: f"${x:,.4f}" if pd.notna(x) else "—"
            )

    for col in ["TP %", "SL %", "Weight %"]:
        if col in df_display.columns:
            df_display[col] = pd.to_numeric(df_display[col], errors="coerce").map(
                lambda x: f"{x:.2f}%" if pd.notna(x) else "—"
            )

    if "Composite Score" in df_display.columns:
        df_display["Composite Score"] = pd.to_numeric(
            df_display["Composite Score"], errors="coerce"
        ).map(lambda x: f"{x:.3f}" if pd.notna(x) else "—")

    # Color-code Risk Band using Streamlit column_config
    def _risk_color(val: str) -> str:
        v = str(val).strip().lower()
        if v == "high":
            return "background-color: #2ecc71; color: white"
        elif v == "medium":
            return "background-color: #f39c12; color: white"
        elif v == "low":
            return "background-color: #e74c3c; color: white"
        return ""

    # Apply styling
    if "Risk Band" in df_display.columns:
        styler = df_display.style
        _map_fn = getattr(styler, "map", None) or getattr(styler, "applymap")
        styled = _map_fn(_risk_color, subset=["Risk Band"])
        st.dataframe(styled, use_container_width=True, hide_index=True, height=600)
    else:
        st.dataframe(df_display, use_container_width=True, hide_index=True, height=600)

    # CSV download
    csv_data = df_plans[available].to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download CSV",
        data=csv_data,
        file_name=f"supervisor_signals_{run_date_str}.csv",
        mime="text/csv",
    )

    st.caption(f"Data source: {plans_status}")
else:
    st.warning(f"No trade plans found for {run_date_str}. ({plans_status})")
