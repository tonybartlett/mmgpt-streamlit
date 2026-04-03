"""
data_source.py — Unified SQL access layer for MMGPT Streamlit dashboard.

Connection strategy (in order):
  1. Supervisor API bridge at st.secrets["bridge"]["base_url"]
     with X-API-Key header from st.secrets["bridge"]["api_key"]
     Endpoints:  POST /sql/query          {"query": "..."}
                 POST /sql/stored-proc    {"proc": "...", "params": {...}}
  2. Fall back to direct pyodbc (Windows Auth — only works on the VM)

All public functions return (DataFrame | None, status_string).
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

import pandas as pd

# ── optional Streamlit import ─────────────────────────────────────────────────
try:
    import streamlit as st
    _HAS_ST = True
except ImportError:
    _HAS_ST = False

# ── optional deps — graceful degradation ──────────────────────────────────────
try:
    import pyodbc  # type: ignore
except ImportError:
    pyodbc = None

try:
    import requests  # type: ignore
except ImportError:
    requests = None


# ══════════════════════════════════════════════════════════════════════════════
#  Config helpers
# ══════════════════════════════════════════════════════════════════════════════

def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    return v if v not in (None, "") else default


def _bridge_base_url() -> Optional[str]:
    """
    Resolve the bridge base URL.  Priority:
      1. st.secrets["bridge"]["base_url"]
      2. MMGPT_SQL_BRIDGE_URL env var
      3. None  (bridge not configured)
    """
    if _HAS_ST:
        try:
            url = st.secrets["bridge"]["base_url"]
            if url:
                return str(url).rstrip("/")
        except Exception:
            pass
    val = _env("MMGPT_SQL_BRIDGE_URL")
    if val:
        return val.rstrip("/")
    return None


def _bridge_api_key() -> Optional[str]:
    """
    Resolve the bridge API key.  Priority:
      1. st.secrets["bridge"]["api_key"]
      2. BRIDGE_API_KEY env var
    """
    if _HAS_ST:
        try:
            key = st.secrets["bridge"]["api_key"]
            if key:
                return str(key)
        except Exception:
            pass
    return _env("BRIDGE_API_KEY")


def _bridge_headers() -> Dict[str, str]:
    """Build request headers for bridge calls, including X-API-Key."""
    h: Dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    key = _bridge_api_key()
    if key:
        h["X-API-Key"] = key
    return h


def _build_conn_str() -> Optional[str]:
    """Build a pyodbc connection string from Streamlit secrets or env."""
    # 1) Env override
    env_cs = _env("SQL_CONN_STR")
    if env_cs:
        return env_cs

    # 2) Streamlit secrets — [sql] section (preferred)
    if _HAS_ST:
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
                uid = sec.get("username", "")
                pwd = sec.get("password", "")
                if uid:
                    parts.append(f"UID={uid}")
                    parts.append(f"PWD={pwd}")
                else:
                    parts.append("Trusted_Connection=yes")
            if sec.get("trust_server_certificate", False):
                parts.append("TrustServerCertificate=yes")
            if sec.get("mars_connection", False):
                parts.append("MARS_Connection=yes")
            return ";".join(parts)
        except Exception:
            pass

    # 3) Flat keys fallback
    if _HAS_ST:
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
            if str(trusted).lower() in ("true", "yes", "1"):
                parts.append("Trusted_Connection=yes")
            return ";".join(parts)
        except Exception:
            pass

    return None


# ══════════════════════════════════════════════════════════════════════════════
#  SQL Bridge (HTTP)
# ══════════════════════════════════════════════════════════════════════════════

def _bridge_post(path: str, payload: Dict[str, Any], timeout: int = 30) -> Optional[pd.DataFrame]:
    """
    POST to the bridge and return a DataFrame from the response.
    The bridge returns: {"status": "ok", "rows": [...], "columns": [...], ...}
    """
    if requests is None:
        return None
    base = _bridge_base_url()
    if not base:
        return None

    url = f"{base}{path}"
    try:
        r = requests.post(url, json=payload, headers=_bridge_headers(), timeout=timeout)
        r.raise_for_status()
        data = r.json()

        # Handle error responses from the bridge
        if isinstance(data, dict) and data.get("status") == "error":
            return None

        # Extract rows
        rows = data.get("rows") if isinstance(data, dict) else data
        if isinstance(rows, list):
            if len(rows) == 0:
                # Return empty DataFrame with column names if available
                cols = data.get("columns", []) if isinstance(data, dict) else []
                return pd.DataFrame(columns=cols) if cols else pd.DataFrame()
            return pd.DataFrame(rows)
    except Exception:
        return None
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  Direct pyodbc
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
#  Public API
# ══════════════════════════════════════════════════════════════════════════════

def run_query(sql: str) -> Tuple[Optional[pd.DataFrame], str]:
    """
    Execute a SQL query.  Tries bridge first, then direct pyodbc.
    Returns (DataFrame | None, status_string).
    """
    # 1. Try bridge  POST /sql/query
    df = _bridge_post("/sql/query", {"query": sql})
    if df is not None:
        return df, "SQL via bridge"

    # 2. Fall back to direct pyodbc
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

    # 1. Try bridge  POST /sql/stored-proc
    df = _bridge_post("/sql/stored-proc", {"proc": proc_name, "params": params})
    if df is not None:
        return df, "Stored proc via bridge"

    # 2. Direct pyodbc fallback
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
