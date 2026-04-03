"""
Page 6 — Candle Screener

Runs dbo.sp_Screener_Candles_Strategy_Run via data_source.run_stored_proc()
and displays candle pattern results.
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pandas as pd
import streamlit as st

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from data_source import run_stored_proc

# ──────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="MMGPT · Candle Screener",
    page_icon="🕯️",
    layout="wide",
)

st.title("Candle Screener")
st.caption("Runs dbo.sp_Screener_Candles_Strategy_Run from SQL Server")
st.divider()

# ──────────────────────────────────────────────
# Sidebar — Parameters
# ──────────────────────────────────────────────
with st.sidebar:
    st.header("Run Parameters")
    selected_date = st.date_input("Run Date", value=date.today())
    st.info("The screener executes the stored procedure with the chosen date.")

# ──────────────────────────────────────────────
# Run Stored Procedure
# ──────────────────────────────────────────────
if st.sidebar.button("Run Screener"):
    with st.spinner(f"Running Candle Screener for {selected_date}..."):
        # The stored proc does INSERT/UPDATE and may not return a result set.
        # First, execute the proc:
        df, status = run_stored_proc(
            "dbo.sp_Screener_Candles_Strategy_Run",
            {"RunDate": str(selected_date)},
        )

        # If the proc returned data, use it directly.
        # If not ("No results" / empty), the proc ran successfully but is
        # an action proc — show a success message instead of an error.
        has_data = df is not None and not df.empty

    if has_data:
        st.success(f"Screener completed — {status}")

        # Summary
        st.subheader("Summary")
        s1, s2 = st.columns(2)
        s1.metric("Rows Returned", f"{len(df):,}")
        s2.metric("Columns", f"{len(df.columns)}")

        # Results table
        st.subheader("Screener Results")
        st.dataframe(df, use_container_width=True, hide_index=True, height=500)

        # Pattern distribution chart
        candle_cols = ["BullishEngulfing", "BearishEngulfing", "Hammer", "Doji"]
        available = [c for c in candle_cols if c in df.columns]
        if available:
            st.subheader("Pattern Distribution")
            pattern_counts = df[available].sum().reset_index()
            pattern_counts.columns = ["Pattern", "Count"]
            st.bar_chart(pattern_counts.set_index("Pattern"))

        # CSV download
        csv_data = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download Results CSV",
            data=csv_data,
            file_name=f"candle_screener_{selected_date}.csv",
            mime="text/csv",
        )
    elif "error" in str(status).lower():
        st.error(f"Stored procedure failed: {status}")
    else:
        # Proc ran but returned no result set (action proc)
        st.success(
            f"Candle Screener executed successfully for {selected_date}. "
            "This procedure performs data processing and does not return a result set."
        )
        st.info(f"Bridge response: {status}")
else:
    st.info("Select a date and click **Run Screener** to begin.")

# ──────────────────────────────────────────────
# Notes
# ──────────────────────────────────────────────
st.divider()
st.caption(
    "Procedure: `dbo.sp_Screener_Candles_Strategy_Run`  ·  "
    "Parameter: `@RunDate (date)`  ·  "
    "Connection: SQL Bridge / direct pyodbc"
)
