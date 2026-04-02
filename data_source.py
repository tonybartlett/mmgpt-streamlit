"""
data_source.py — Unified SQL access layer for MMGPT Streamlit dashboard.

Connection strategy:
  1. Try mmgpt-sql-bridge (HTTP POST to local FastAPI bridge)
  2. Fall back to direct pyodbc with Streamlit secrets or env var

All public functions return (DataFrame | None, status_string).
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import streamlit as st

# Optional deps — graceful degradation
try:
    import pyodbc  # type: ignore
except ImportError:
    pyodbc = None

try:
    import requests  # type: ignore
except ImportError:
    requests = None


# ──────────────────────────────────────────────
# Config helpers
# ──────────────────────────────────────────────

def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    return v if v not in (None, "") else default


def _build_conn_str() -> Optional[str]:
    """Build a pyodbc connection string from Streamlit secrets or env."""
    # 1) Env override
    env_cs = _env("SQL_CONN_STR")
    if env_cs:
        return env_cs

    # 2) Streamlit secrets — [sql] section (preferred)
    try:
        sec = st.secrets["sql"]
        server = sec["server"]
        database = sec["database"]
        driver = sec.get("driver", "ODBC Driver 17 for SQL Server")
        parts = [
            f"DRIVER={{{driver}}}",
            f"SERVER={server}",
            f"DATABASE={database}",
        ]
        if sec.get("use_windows_auth", False):
            parts.append("Trusted_Connection=yes")
        else:
            parts.append(f"UID={sec.get('username', '')}")
            parts.append(f"PWD={sec.get('password', '')}")
        if sec.get("trust_server_certificate", False):
            parts.append("TrustServerCertificate=yes")
        if sec.get("mars_connection", False):
            parts.append("MARS_Connection=yes")
        return ";".join(parts)
    except Exception:
        pass

    # 3) Flat keys fallback
    try:
        server = st.secrets["SQL_SERVER"]
        database = st.secrets["SQL_DATABASE"]
        driver = st.secrets.get("SQL_DRIVER", "ODBC Driver 17 for SQL Server")
        trusted = st.secrets.get("SQL_TRUSTED_CONNECTION", "true")
        parts = [
            f"DRIVER={{{driver}}}",
            f"SERVER={server}",
            f"DATABASE={database}",
        ]
        if trusted.lower() in ("true", "yes", "1"):
            parts.append("Trusted_Connection=yes")
        return ";".join(parts)
    except Exception:
        pass

    return None


# ──────────────────────────────────────────────
# SQL Bridge (HTTP)
# ──────────────────────────────────────────────

def _sql_bridge_base() -> str:
    return _env("MMGPT_SQL_BRIDGE_URL", "http://127.0.0.1:8010").rstrip("/")


def _sql_bridge_post(path: str, payload: Dict[str, Any], timeout: int = 20) -> Optional[pd.DataFrame]:
    if requests is None:
        return None
    url = f"{_sql_bridge_base()}{path}"
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        rows = data["rows"] if isinstance(data, dict) and "rows" in data else data
        if isinstance(rows, list):
            return pd.DataFrame(rows)
    except Exception:
        return None
    return None


# ──────────────────────────────────────────────
# Direct pyodbc
# ──────────────────────────────────────────────

def _direct_pyodbc_query(sql: str) -> Optional[pd.DataFrame]:
    if pyodbc is None:
        return None
    conn_str = _build_conn_str()
    if not conn_str:
        return None
    try:
        conn = pyodbc.connect(conn_str)
        df = pd.read_sql(sql, conn)
        conn.close()
        return df
    except Exception:
        return None


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def run_query(sql: str) -> Tuple[Optional[pd.DataFrame], str]:
    """
    Execute a SQL query.  Tries bridge first, then direct pyodbc.
    Returns (DataFrame | None, status_string).
    """
    df = _sql_bridge_post("/query", {"query": sql})
    if df is None:
        df = _sql_bridge_post("/sql/query", {"query": sql})
    if df is not None:
        return df, "SQL via mmgpt-sql-bridge"

    df2 = _direct_pyodbc_query(sql)
    if df2 is not None:
        return df2, "SQL via direct pyodbc"

    return None, "SQL not available (bridge + direct failed)"


def run_stored_proc(
    proc_name: str,
    params: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[pd.DataFrame], str]:
    """
    Execute a stored procedure.
    Returns (DataFrame | None, status_string).
    """
    params = params or {}

    # Try bridge
    df = _sql_bridge_post("/stored-proc", {"proc": proc_name, "params": params})
    if df is None:
        df = _sql_bridge_post("/sql/stored-proc", {"proc": proc_name, "params": params})
    if df is not None:
        return df, "Stored proc via mmgpt-sql-bridge"

    # Direct pyodbc fallback
    if pyodbc is None:
        return None, "pyodbc not installed"
    conn_str = _build_conn_str()
    if not conn_str:
        return None, "SQL connection string not configured"

    parts = []
    for k, v in params.items():
        if v is None:
            parts.append(f"@{k}=NULL")
        elif isinstance(v, (int, float)):
            parts.append(f"@{k}={v}")
        else:
            vv = str(v).replace("'", "''")
            parts.append(f"@{k}='{vv}'")
    exec_sql = f"EXEC {proc_name} {', '.join(parts)}" if parts else f"EXEC {proc_name}"

    try:
        conn = pyodbc.connect(conn_str)
        df = pd.read_sql(exec_sql, conn)
        conn.close()
        return df, "Stored proc via direct pyodbc"
    except Exception as e:
        return None, f"Stored proc failed: {e}"
