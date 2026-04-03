"""
bridge_client.py  —  MMGPT Supervisor API bridge client.

Reads connection config from Streamlit secrets:

    [bridge]
    base_url = "https://your-ngrok-or-cloudflare-url.com"
    api_key  = "your-secret-key-here"

Falls back to environment variables:
    MMGPT_BRIDGE_URL, MMGPT_BRIDGE_API_KEY

All public functions return the parsed JSON response dict on success,
or None on any failure (network error, auth error, timeout, etc.).
Exceptions are never raised to callers.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

# ── optional deps ────────────────────────────────────────────────────────────
try:
    import requests as _requests          # type: ignore
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

try:
    import streamlit as st
    _HAS_ST = True
except ImportError:
    _HAS_ST = False


# ═══════════════════════════════════════════════════════════════════════════
#  Config resolution
# ═══════════════════════════════════════════════════════════════════════════

def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    return v if v not in (None, "") else default


def get_base_url() -> str:
    """
    Resolve the bridge base URL.  Priority:
      1. st.secrets["bridge"]["base_url"]
      2. MMGPT_BRIDGE_URL  env var
      3. http://127.0.0.1:8010  (local fallback)
    """
    if _HAS_ST:
        try:
            url = st.secrets["bridge"]["base_url"]
            if url:
                return str(url).rstrip("/")
        except Exception:
            pass
    return _env("MMGPT_BRIDGE_URL", "http://127.0.0.1:8010").rstrip("/")


def get_api_key() -> Optional[str]:
    """
    Resolve the bridge API key.  Priority:
      1. st.secrets["bridge"]["api_key"]
      2. MMGPT_BRIDGE_API_KEY  env var
    """
    if _HAS_ST:
        try:
            key = st.secrets["bridge"]["api_key"]
            if key:
                return str(key)
        except Exception:
            pass
    return _env("MMGPT_BRIDGE_API_KEY")


def _headers(include_auth: bool = True) -> Dict[str, str]:
    """Build request headers, optionally including the API key."""
    h: Dict[str, str] = {"Accept": "application/json"}
    if include_auth:
        key = get_api_key()
        if key:
            h["X-API-Key"] = key
    return h


# ═══════════════════════════════════════════════════════════════════════════
#  Internal HTTP helpers
# ═══════════════════════════════════════════════════════════════════════════

def _get(
    path: str,
    *,
    auth: bool = True,
    timeout: int = 15,
) -> Optional[Dict[str, Any]]:
    """
    Perform a GET request to the bridge.
    Returns parsed JSON dict on success, None on any failure.
    """
    if not _HAS_REQUESTS:
        return None
    url = f"{get_base_url()}{path}"
    try:
        r = _requests.get(url, headers=_headers(include_auth=auth), timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _post(
    path: str,
    payload: Dict[str, Any],
    *,
    auth: bool = True,
    timeout: int = 30,
) -> Optional[Dict[str, Any]]:
    """
    Perform a POST request to the bridge.
    Returns parsed JSON dict on success, None on any failure.
    """
    if not _HAS_REQUESTS:
        return None
    url = f"{get_base_url()}{path}"
    try:
        r = _requests.post(url, json=payload, headers=_headers(include_auth=auth), timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════
#  Public endpoint helpers
# ═══════════════════════════════════════════════════════════════════════════

def ping(timeout: int = 10) -> Optional[Dict[str, Any]]:
    """
    GET /ping  —  no authentication required.
    Returns {"status": "ok", ...} or None on failure.
    """
    return _get("/ping", auth=False, timeout=timeout)


def sql_ping(timeout: int = 10) -> Optional[Dict[str, Any]]:
    """
    GET /sql/ping  —  requires X-API-Key.
    Returns {"status": "ok", "db": "...", ...} or None on failure.
    """
    return _get("/sql/ping", auth=True, timeout=timeout)


def supervisor_health(timeout: int = 15) -> Optional[Dict[str, Any]]:
    """
    GET /supervisor/health  —  requires X-API-Key.
    Returns supervisor system health dict or None on failure.
    """
    return _get("/supervisor/health", auth=True, timeout=timeout)


def portfolio_state(timeout: int = 15) -> Optional[Dict[str, Any]]:
    """
    GET /portfolio/state  —  requires X-API-Key.
    Returns current portfolio state dict or None on failure.
    """
    return _get("/portfolio/state", auth=True, timeout=timeout)


def agent_state(timeout: int = 15) -> Optional[Dict[str, Any]]:
    """
    GET /agent/state  —  requires X-API-Key.
    Returns current agent state dict or None on failure.
    """
    return _get("/agent/state", auth=True, timeout=timeout)


def run_sql_query(sql: str, timeout: int = 30) -> Optional[Dict[str, Any]]:
    """
    POST /sql/query  —  requires X-API-Key.
    Accepts {"query": "SELECT ..."} and returns {"rows": [...], ...} or None.
    """
    return _post("/sql/query", {"query": sql}, auth=True, timeout=timeout)


def run_stored_proc(proc: str, params: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Optional[Dict[str, Any]]:
    """
    POST /sql/stored-proc  —  requires X-API-Key.
    Returns {"rows": [...], ...} or None.
    """
    return _post("/sql/stored-proc", {"proc": proc, "params": params or {}}, auth=True, timeout=timeout)


# ═══════════════════════════════════════════════════════════════════════════
#  Timed health check helper (used by Bridge Status page)
# ═══════════════════════════════════════════════════════════════════════════

def check_all_endpoints(timeout: int = 10) -> Dict[str, Dict[str, Any]]:
    """
    Run a health check against every known endpoint.
    Returns a dict keyed by endpoint path, each value containing:
      {
        "ok":        bool,
        "latency_ms": float | None,
        "response":  dict | None,
        "error":     str | None,
      }
    """
    endpoints = [
        ("/ping",              False),   # (path, requires_auth)
        ("/sql/ping",          True),
        ("/supervisor/health", True),
        ("/portfolio/state",   True),
        ("/agent/state",       True),
    ]

    results: Dict[str, Dict[str, Any]] = {}

    for path, requires_auth in endpoints:
        if not _HAS_REQUESTS:
            results[path] = {"ok": False, "latency_ms": None, "response": None, "error": "requests not installed"}
            continue

        url = f"{get_base_url()}{path}"
        headers = _headers(include_auth=requires_auth)
        t0 = time.perf_counter()
        try:
            r = _requests.get(url, headers=headers, timeout=timeout)
            latency_ms = (time.perf_counter() - t0) * 1000
            ok = r.status_code < 400
            try:
                resp = r.json()
            except Exception:
                resp = {"raw": r.text[:200]}
            results[path] = {
                "ok":         ok,
                "latency_ms": round(latency_ms, 1),
                "response":   resp,
                "error":      None if ok else f"HTTP {r.status_code}",
                "status_code": r.status_code,
            }
        except _requests.exceptions.ConnectionError:
            results[path] = {
                "ok": False,
                "latency_ms": None,
                "response": None,
                "error": "Connection refused — bridge not reachable",
            }
        except _requests.exceptions.Timeout:
            results[path] = {
                "ok": False,
                "latency_ms": None,
                "response": None,
                "error": f"Timed out after {timeout}s",
            }
        except Exception as exc:
            results[path] = {
                "ok": False,
                "latency_ms": None,
                "response": None,
                "error": str(exc),
            }

    return results
