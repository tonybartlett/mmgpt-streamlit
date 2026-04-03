"""
pages/0_Bridge_Status.py  —  MMGPT Supervisor API Bridge Status

Shows a live health check of every bridge endpoint:
  • GET /ping              (no auth)
  • GET /sql/ping          (auth)
  • GET /supervisor/health (auth)
  • GET /portfolio/state   (auth)
  • GET /agent/state       (auth)

Also displays bridge configuration and a deployment checklist.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

import streamlit as st

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import bridge_client

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MMGPT · Bridge Status",
    page_icon="🌐",
    layout="wide",
)

st.title("Supervisor API Bridge Status")
st.caption("Live health check for all bridge endpoints  ·  reads from `[bridge]` in Streamlit secrets")
st.divider()


# ═══════════════════════════════════════════════════════════════════════════
#  1.  Configuration
# ═══════════════════════════════════════════════════════════════════════════

st.subheader("Bridge Configuration")

base_url = bridge_client.get_base_url()
api_key  = bridge_client.get_api_key()
key_set  = bool(api_key and api_key != "your-secret-key-here")

cfg1, cfg2, cfg3 = st.columns(3)
cfg1.metric("Base URL",   base_url)
cfg2.metric("API Key",    "Configured ✓" if key_set else "Not set ✗")
cfg3.metric("Checked at", datetime.now().strftime("%H:%M:%S"))

st.divider()


# ═══════════════════════════════════════════════════════════════════════════
#  2.  Live endpoint health check
# ═══════════════════════════════════════════════════════════════════════════

st.subheader("Endpoint Health Check")

_ENDPOINT_META = {
    "/ping":              {"label": "Ping",               "auth": False, "description": "Basic liveness — no auth required"},
    "/sql/ping":          {"label": "SQL Ping",           "auth": True,  "description": "Confirms SQL Server connectivity"},
    "/supervisor/health": {"label": "Supervisor Health",  "auth": True,  "description": "Supervisor agent health summary"},
    "/portfolio/state":   {"label": "Portfolio State",    "auth": True,  "description": "Current portfolio positions"},
    "/agent/state":       {"label": "Agent State",        "auth": True,  "description": "Supervisor agent runtime state"},
}

col_check, col_timeout = st.columns([2, 1])
with col_check:
    run_check = st.button("Run Health Check", type="primary", use_container_width=True)
with col_timeout:
    timeout_s = st.number_input("Timeout (s)", min_value=3, max_value=30, value=10, step=1)

if run_check:
    with st.spinner("Checking all endpoints …"):
        results = bridge_client.check_all_endpoints(timeout=int(timeout_s))

    # ── Summary bar ──────────────────────────────────────────────────────
    total   = len(results)
    ok_cnt  = sum(1 for v in results.values() if v["ok"])
    fail_cnt = total - ok_cnt

    s1, s2, s3 = st.columns(3)
    s1.metric("Total Endpoints", total)
    s2.metric("Online", ok_cnt,   delta=None)
    s3.metric("Offline", fail_cnt, delta=None)

    if ok_cnt == total:
        st.success(f"All {total} endpoints are **ONLINE**")
    elif ok_cnt == 0:
        st.error("All endpoints are **OFFLINE** — check bridge is running and tunnel is active")
    else:
        st.warning(f"{ok_cnt}/{total} endpoints online")

    st.divider()

    # ── Per-endpoint table ────────────────────────────────────────────────
    for path, meta in _ENDPOINT_META.items():
        r = results.get(path, {"ok": False, "latency_ms": None, "response": None, "error": "Not checked"})

        with st.container():
            hdr_col, lat_col, status_col = st.columns([3, 1, 1])

            with hdr_col:
                icon = "✅" if r["ok"] else "❌"
                auth_badge = "🔑 Auth" if meta["auth"] else "🔓 Public"
                st.markdown(f"**{icon}  {meta['label']}**  `GET {path}`  ·  {auth_badge}")
                st.caption(meta["description"])

            with lat_col:
                if r["latency_ms"] is not None:
                    st.metric("Latency", f"{r['latency_ms']} ms")
                else:
                    st.metric("Latency", "—")

            with status_col:
                if r["ok"]:
                    code = r.get("status_code", 200)
                    st.metric("HTTP", str(code))
                else:
                    st.metric("HTTP", r.get("status_code", "ERR"))

            # Show response or error
            if r["ok"] and r["response"]:
                with st.expander("Response", expanded=False):
                    st.json(r["response"])
            elif not r["ok"] and r["error"]:
                st.error(f"Error: {r['error']}")

        st.markdown("---")

    # ── Store last check time in session ─────────────────────────────────
    st.session_state["bridge_last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state["bridge_last_ok"]    = ok_cnt
    st.session_state["bridge_last_total"] = total

else:
    st.info("Click **Run Health Check** to test all endpoints.")


# ═══════════════════════════════════════════════════════════════════════════
#  3.  Session history
# ═══════════════════════════════════════════════════════════════════════════

if "bridge_last_check" in st.session_state:
    st.divider()
    st.subheader("Last Check")
    h1, h2 = st.columns(2)
    h1.metric("Checked at",  st.session_state["bridge_last_check"])
    h2.metric("Result",
              f"{st.session_state['bridge_last_ok']}/{st.session_state['bridge_last_total']} online")


# ═══════════════════════════════════════════════════════════════════════════
#  4.  Deployment checklist
# ═══════════════════════════════════════════════════════════════════════════

st.divider()
st.subheader("Deployment Checklist")

checks = {
    "Base URL is not localhost":              base_url not in ("http://127.0.0.1:8010", "http://localhost:8010"),
    "Base URL uses HTTPS":                   base_url.startswith("https://"),
    "Base URL is not a placeholder":         "your-ngrok" not in base_url and "your-cloudflare" not in base_url,
    "API key is configured":                 key_set,
    "API key is not a placeholder":          api_key not in (None, "your-secret-key-here", ""),
}

for label, passed in checks.items():
    if passed:
        st.markdown(f"  ✅  {label}")
    else:
        st.markdown(f"  ❌  {label}")

if all(checks.values()):
    st.success("All checks passed — bridge is configured for cloud deployment.")
else:
    st.warning(
        "Some checks failed.  Update the `[bridge]` section in Streamlit Cloud Secrets "
        "with your actual ngrok/Cloudflare URL and API key."
    )

st.divider()

# ── Quick reference ───────────────────────────────────────────────────────
with st.expander("Secrets configuration reference", expanded=False):
    st.code(
        """[bridge]
base_url = "https://your-ngrok-url.ngrok-free.app"
api_key  = "your-api-key-here"
""",
        language="toml",
    )
    st.caption(
        "Paste this into **Streamlit Cloud → App Settings → Secrets**, "
        "replacing the placeholder values with your real bridge URL and API key."
    )
