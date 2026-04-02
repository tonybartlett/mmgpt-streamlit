"""
Page 3 — Execution Queue Monitor

Displays:
  • Current Supervisor_Execution_Queue for latest RunDate
  • Status column with color coding
  • Null-check summary (data quality)
  • AccountID filter in sidebar
"""

from __future__ import annotations

import os
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from mmgpt_queries import (
    get_account_ids,
    get_exec_queue_null_check,
    get_exec_queue_status_summary,
    get_execution_queue,
    get_latest_exec_run_date,
)

# ──────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="MMGPT · Execution Queue",
    page_icon="📋",
    layout="wide",
)

st.title("Execution Queue Monitor")
st.caption("Live view of dbo.Supervisor_Execution_Queue")
st.divider()

# ──────────────────────────────────────────────
# Determine latest RunDate
# ──────────────────────────────────────────────
df_rd, rd_status = get_latest_exec_run_date()

run_date_str: str | None = None
if df_rd is not None and not df_rd.empty:
    rd_val = df_rd.iloc[0].get("RunDate")
    if pd.notna(rd_val):
        run_date_str = pd.Timestamp(rd_val).strftime("%Y-%m-%d")

if not run_date_str:
    st.error(f"No RunDate found in Execution Queue. ({rd_status})")
    st.stop()

# ──────────────────────────────────────────────
# Sidebar — AccountID filter
# ──────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    st.info(f"RunDate: **{run_date_str}**")

    df_accounts, _ = get_account_ids(run_date_str)
    account_options = ["All"]
    if df_accounts is not None and not df_accounts.empty:
        account_options += df_accounts["AccountID"].dropna().astype(str).tolist()

    selected_account = st.selectbox("Account ID", options=account_options, index=0)

acct_filter = selected_account if selected_account != "All" else None

# ──────────────────────────────────────────────
# 1. Status Summary
# ──────────────────────────────────────────────
st.subheader("Status Summary")

df_status, status_src = get_exec_queue_status_summary(run_date_str, acct_filter)

if df_status is not None and not df_status.empty:
    # Display as metrics
    status_cols = st.columns(len(df_status) + 1)
    total_orders = int(df_status["OrderCount"].sum())
    status_cols[0].metric("Total Orders", f"{total_orders:,}")

    for i, row in df_status.iterrows():
        status_val = row.get("Status", "Unknown") or "NULL"
        count_val = int(row.get("OrderCount", 0))
        status_cols[i + 1].metric(str(status_val), f"{count_val:,}")

    # Pie chart
    fig_pie = px.pie(
        df_status,
        values="OrderCount",
        names="Status",
        title="Order Status Distribution",
        hole=0.4,
    )
    fig_pie.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig_pie, use_container_width=True)
else:
    st.info(f"No status data. ({status_src})")

st.divider()

# ──────────────────────────────────────────────
# 2. Null-Check / Data Quality
# ──────────────────────────────────────────────
st.subheader("Data Quality — Null Check")

df_nulls, null_status = get_exec_queue_null_check(run_date_str, acct_filter)

if df_nulls is not None and not df_nulls.empty:
    n = df_nulls.iloc[0]
    total_rows = int(n.get("ExecQRows", 0))

    null_cols = {
        "TargetQty": int(n.get("NullTargetQty", 0)),
        "StopLoss": int(n.get("NullStopLoss", 0)),
        "TakeProfit": int(n.get("NullTakeProfit", 0)),
        "Confidence": int(n.get("NullConfidence", 0)),
        "Status": int(n.get("NullStatus", 0)),
    }

    nc = st.columns(len(null_cols) + 1)
    nc[0].metric("Total Rows", f"{total_rows:,}")

    for i, (col_name, null_count) in enumerate(null_cols.items()):
        if null_count > 0:
            nc[i + 1].metric(
                f"NULL {col_name}",
                f"{null_count:,}",
                delta=f"-{null_count}",
                delta_color="inverse",
            )
        else:
            nc[i + 1].metric(f"NULL {col_name}", "0", delta="Clean", delta_color="normal")

    # Overall quality indicator
    total_nulls = sum(null_cols.values())
    if total_nulls == 0:
        st.success("All critical fields are populated — no NULLs detected.")
    else:
        st.warning(f"{total_nulls} NULL value(s) detected across {total_rows} rows.")
else:
    st.info(f"Null check not available. ({null_status})")

st.divider()

# ──────────────────────────────────────────────
# 3. Execution Queue Table
# ──────────────────────────────────────────────
st.subheader(f"Execution Queue — {run_date_str}")

df_queue, queue_status = get_execution_queue(run_date_str, acct_filter)

if df_queue is not None and not df_queue.empty:
    # Format numeric columns
    for col in ["StopLoss", "TakeProfit"]:
        if col in df_queue.columns:
            df_queue[col] = pd.to_numeric(df_queue[col], errors="coerce")

    if "ConfidenceScore" in df_queue.columns:
        df_queue["ConfidenceScore"] = pd.to_numeric(df_queue["ConfidenceScore"], errors="coerce")

    # Color-code Status column
    def _status_color(val: str) -> str:
        v = str(val).strip().lower() if pd.notna(val) else ""
        if v in ("filled", "complete", "executed", "done"):
            return "background-color: #2ecc71; color: white"
        elif v in ("pending", "queued", "new"):
            return "background-color: #3498db; color: white"
        elif v in ("partial", "working"):
            return "background-color: #f39c12; color: white"
        elif v in ("cancelled", "rejected", "failed", "error"):
            return "background-color: #e74c3c; color: white"
        return ""

    if "Status" in df_queue.columns:
        styled = df_queue.style.applymap(_status_color, subset=["Status"])
        st.dataframe(styled, use_container_width=True, hide_index=True, height=500)
    else:
        st.dataframe(df_queue, use_container_width=True, hide_index=True, height=500)

    # CSV download
    csv_data = df_queue.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download Queue CSV",
        data=csv_data,
        file_name=f"execution_queue_{run_date_str}.csv",
        mime="text/csv",
    )

    st.caption(f"Source: {queue_status}")
else:
    st.warning(f"No execution queue data for {run_date_str}. ({queue_status})")
