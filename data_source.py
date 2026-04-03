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

import logging
import os
import traceback
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# ── logging ───────────────────────────────────────────────────────────────────
log = logging.getLogger("mmgpt.data_source")

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
    import requests as _requests  # type: ignore
    _HAS_REQUESTS = True
except ImportError:
    _requests = None  # type: ignore
    _HAS_REQUESTS = False


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
    """Build request headers for bridge calls, including X-API-Key and ngrok bypass."""
    h: Dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "ngrok-skip-browser-warning": "true",   # bypass ngrok interstitial
    }
    key = _bridge_api_key()
    if key:
        h["X-API-Key"] = key
    return h


def _build_conn_str() -> Optional[str]:
    """Build a pyodbc connection string from Streamlit secrets or env."""
    env_cs = _env("SQL_CONN_STR")
    if env_cs:
        return env_cs

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

    return None


# ══════════════════════════════════════════════════════════════════════════════
#  Diagnostic info (exposed for debug sidebar)
# ══════════════════════════════════════════════════════════════════════════════

_last_bridge_error: Optional[str] = None


def get_diag() -> Dict[str, Any]:
    """Return diagnostic info about the current data_source configuration."""
    return {
        "bridge_url": _bridge_base_url(),
        "api_key_set": _bridge_api_key() is not None,
        "api_key_preview": (_bridge_api_key() or "")[:4] + "..." if _bridge_api_key() else None,
        "requests_available": _HAS_REQUESTS,
        "pyodbc_available": pyodbc is not None,
        "last_bridge_error": _last_bridge_error,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  SQL Bridge (HTTP)
# ══════════════════════════════════════════════════════════════════════════════

def _bridge_post(
    path: str,
    payload: Dict[str, Any],
    timeout: int = 30,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    POST to the bridge and return (DataFrame, None) on success
    or (None, error_detail) on failure.
    """
    global _last_bridge_error

    if not _HAS_REQUESTS:
        err = "requests library not installed"
        _last_bridge_error = err
        return None, err

    base = _bridge_base_url()
    if not base:
        err = "bridge URL not configured (no st.secrets[bridge][base_url] or MMGPT_SQL_BRIDGE_URL)"
        _last_bridge_error = err
        return None, err

    url = f"{base}{path}"
    headers = _bridge_headers()

    try:
        r = _requests.post(url, json=payload, headers=headers, timeout=timeout)

        # Check for non-JSON response (ngrok interstitial, etc.)
        ct = r.headers.get("content-type", "")
        if "application/json" not in ct:
            err = f"Bridge returned non-JSON content-type: {ct} (body: {r.text[:200]})"
            _last_bridge_error = err
            log.warning(err)
            return None, err

        r.raise_for_status()
        data = r.json()

        # Handle error responses from the bridge
        if isinstance(data, dict) and data.get("status") == "error":
            err = f"Bridge error: {data.get('message', 'unknown')}"
            _last_bridge_error = err
            return None, err

        # Extract rows
        rows: List = data.get("rows") if isinstance(data, dict) else data
        if isinstance(rows, list):
            _last_bridge_error = None  # success — clear error
            if len(rows) == 0:
                cols = data.get("columns", []) if isinstance(data, dict) else []
                return pd.DataFrame(columns=cols) if cols else pd.DataFrame(), None
            return pd.DataFrame(rows), None

        err = f"Unexpected bridge response shape: {str(data)[:200]}"
        _last_bridge_error = err
        return None, err

    except _requests.exceptions.ConnectionError as e:
        err = f"Bridge connection refused: {e}"
        _last_bridge_error = err
        return None, err
    except _requests.exceptions.Timeout:
        err = f"Bridge timeout after {timeout}s"
        _last_bridge_error = err
        return None, err
    except _requests.exceptions.HTTPError as e:
        err = f"Bridge HTTP error: {e} (body: {e.response.text[:200] if e.response else 'N/A'})"
        _last_bridge_error = err
        return None, err
    except Exception as e:
        err = f"Bridge unexpected error: {type(e).__name__}: {e}"
        _last_bridge_error = err
        log.exception("Bridge POST failed")
        return None, err


# ══════════════════════════════════════════════════════════════════════════════
#  Direct pyodbc
# ══════════════════════════════════════════════════════════════════════════════

def _direct_pyodbc_query(sql: str) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    if pyodbc is None:
        return None, "pyodbc not installed"
    conn_str = _build_conn_str()
    if not conn_str:
        return None, "SQL connection string not configured"
    try:
        conn = pyodbc.connect(conn_str)
        df = pd.read_sql(sql, conn)
        conn.close()
        return df, None
    except Exception as e:
        return None, f"pyodbc error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
#  Public API
# ══════════════════════════════════════════════════════════════════════════════

def run_query(sql: str) -> Tuple[Optional[pd.DataFrame], str]:
    """
    Execute a SQL query.  Tries bridge first, then direct pyodbc.
    Returns (DataFrame | None, status_string).
    """
    errors: List[str] = []

    # 1. Try bridge  POST /sql/query
    df, err = _bridge_post("/sql/query", {"query": sql})
    if df is not None:
        return df, "SQL via bridge"
    if err:
        errors.append(f"bridge: {err}")

    # 2. Fall back to direct pyodbc
    df2, err2 = _direct_pyodbc_query(sql)
    if df2 is not None:
        return df2, "SQL via direct pyodbc"
    if err2:
        errors.append(f"pyodbc: {err2}")

    detail = " | ".join(errors) if errors else "no connection method available"
    return None, f"SQL not available ({detail})"


def run_stored_proc(
    proc_name: str,
    params: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[pd.DataFrame], str]:
    """
    Execute a stored procedure.
    Returns (DataFrame | None, status_string).
    """
    params = params or {}
    errors: List[str] = []

    # 1. Try bridge  POST /sql/stored-proc
    df, err = _bridge_post("/sql/stored-proc", {"proc": proc_name, "params": params})
    if df is not None:
        return df, "Stored proc via bridge"
    if err:
        errors.append(f"bridge: {err}")

    # 2. Direct pyodbc fallback
    if pyodbc is None:
        errors.append("pyodbc: not installed")
    else:
        conn_str = _build_conn_str()
        if not conn_str:
            errors.append("pyodbc: connection string not configured")
        else:
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
                errors.append(f"pyodbc: {e}")

    detail = " | ".join(errors) if errors else "no connection method available"
    return None, f"Stored proc not available ({detail})"
