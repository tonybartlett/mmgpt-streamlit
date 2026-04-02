"""
Page 4 — SQL Connection Test

Validates SQL connectivity via mmgpt-sql-bridge and/or direct pyodbc.
"""

from __future__ import annotations

import os
import sys

import streamlit as st

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from data_source import run_query

st.set_page_config(page_title="MMGPT · SQL Connection Test", page_icon="🧩", layout="wide")

st.title("SQL Connection Test")
st.caption("Validates SQL connectivity via mmgpt-sql-bridge and/or direct pyodbc.")
st.divider()

default_sql = "SELECT TOP (5) GETDATE() AS server_time"
sql = st.text_area("Test Query", value=default_sql, height=100)

if st.button("Run Test"):
    with st.spinner("Executing query..."):
        df, status = run_query(sql)
    if df is not None:
        st.success(f"Connection OK — {status}")
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.error(f"Connection failed — {status}")
