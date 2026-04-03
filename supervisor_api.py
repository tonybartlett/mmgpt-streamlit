"""
supervisor_api.py — MMGPT Supervisor FastAPI Bridge
====================================================

This file is a **reference copy** stored in the Streamlit repo for version control.
The production instance runs on the VM at:
    E:\\MMGPT_V3\\03_bridge\\supervisor_api.py

Endpoints (v0.7.0):
    GET  /ping               — public health check (no auth)
    GET  /sql/ping           — SQL Server connectivity check (auth)
    POST /sql/query          — execute ad-hoc SQL query (auth)
    POST /sql/stored-proc    — execute stored procedure (auth)
    GET  /supervisor/health  — supervisor system health (auth)
    GET  /portfolio/state    — portfolio state (auth)
    GET  /agent/state        — agent state (auth)
    GET  /agent/status       — agent status (auth)
    GET  /stage/status       — stage status (auth)

Auth:  X-API-Key header validated against BRIDGE_API_KEY env var.
SQL:   pyodbc → MMGPTVM\\ASXSQLDATA, "Stock Master Default", Windows Auth.

Usage:
    set BRIDGE_API_KEY=your-secret-key
    uvicorn supervisor_api:app --host 0.0.0.0 --port 8010

Or via run.bat on the VM.
"""

from __future__ import annotations

import os
import logging
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

import pyodbc
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

# ─── Configuration ───────────────────────────────────────────────────────────

BRIDGE_API_KEY = os.getenv("BRIDGE_API_KEY", "")
SQL_SERVER = os.getenv("SQL_SERVER", r"MMGPTVM\ASXSQLDATA")
SQL_DATABASE = os.getenv("SQL_DATABASE", "Stock Master Default")
SQL_DRIVER = os.getenv("SQL_DRIVER", "ODBC Driver 17 for SQL Server")
PORT = int(os.getenv("BRIDGE_PORT", "8010"))

log = logging.getLogger("supervisor_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")

# ─── FastAPI app ─────────────────────────────────────────────────────────────

app = FastAPI(title="MMGPT Supervisor API", version="0.7.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://*.streamlit.app",
        "http://localhost:*",
        "http://127.0.0.1:*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Auth helper ─────────────────────────────────────────────────────────────

def _check_api_key(x_api_key: Optional[str] = None) -> None:
    """Raise 401 if API key is configured but not provided / wrong."""
    if not BRIDGE_API_KEY:
        return  # no key configured — open access
    if x_api_key != BRIDGE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ─── SQL helper ──────────────────────────────────────────────────────────────

def _get_connection() -> pyodbc.Connection:
    conn_str = (
        f"DRIVER={{{SQL_DRIVER}}};"
        f"SERVER={SQL_SERVER};"
        f"DATABASE={SQL_DATABASE};"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
        "MARS_Connection=yes;"
    )
    return pyodbc.connect(conn_str)


def _rows_to_dicts(cursor: pyodbc.Cursor) -> tuple[list[str], list[dict]]:
    """Convert cursor results to (column_names, list_of_dicts)."""
    columns = [desc[0] for desc in cursor.description]
    rows = []
    for row in cursor.fetchall():
        d = {}
        for i, col in enumerate(columns):
            val = row[i]
            # Convert non-JSON-serializable types to string
            if isinstance(val, (datetime,)):
                d[col] = str(val)
            elif isinstance(val, bytes):
                d[col] = val.hex()
            elif val is None:
                d[col] = None
            else:
                d[col] = str(val)
        rows.append(d)
    return columns, rows


# ─── Request models ──────────────────────────────────────────────────────────

class SqlQueryRequest(BaseModel):
    query: str

class StoredProcRequest(BaseModel):
    proc: str
    params: Optional[Dict[str, Any]] = None


# ═══════════════════════════════════════════════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/ping")
async def ping():
    """Public health check — no auth required."""
    return {
        "status": "ok",
        "service": "MMGPT Supervisor API",
        "message": "API is running",
    }


@app.get("/sql/ping")
async def sql_ping(x_api_key: Optional[str] = Header(None)):
    """Check SQL Server connectivity."""
    _check_api_key(x_api_key)
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT @@SERVERNAME AS server_name, DB_NAME() AS database_name, GETDATE() AS local_server_time")
        row = cursor.fetchone()
        conn.close()
        return {
            "status": "ok",
            "server_name": row[0],
            "database_name": row[1],
            "local_server_time": str(row[2]),
        }
    except Exception as e:
        log.error(f"SQL ping failed: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/sql/query")
async def sql_query(req: SqlQueryRequest, x_api_key: Optional[str] = Header(None)):
    """Execute a read-only SQL query and return rows as a list of dicts."""
    _check_api_key(x_api_key)
    log.info(f"SQL query: {req.query[:200]}")
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(req.query)

        if cursor.description is None:
            conn.close()
            return {"status": "ok", "row_count": 0, "columns": [], "rows": []}

        columns, rows = _rows_to_dicts(cursor)
        conn.close()
        return {
            "status": "ok",
            "row_count": len(rows),
            "columns": columns,
            "rows": rows,
        }
    except Exception as e:
        log.error(f"SQL query failed: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": str(e)}


@app.post("/sql/stored-proc")
async def sql_stored_proc(req: StoredProcRequest, x_api_key: Optional[str] = Header(None)):
    """Execute a stored procedure with optional parameters.

    Handles both:
    - Procedures that return result sets (SELECT)
    - Action procedures that do INSERT/UPDATE/DELETE (no result set)
    """
    _check_api_key(x_api_key)
    params = req.params or {}
    log.info(f"Stored proc: {req.proc} params={params}")

    try:
        conn = _get_connection()
        cursor = conn.cursor()

        # Build EXEC statement
        parts = []
        for k, v in params.items():
            if v is None:
                parts.append(f"@{k}=NULL")
            elif isinstance(v, (int, float)):
                parts.append(f"@{k}={v}")
            else:
                vv = str(v).replace("'", "''")
                parts.append(f"@{k}=N'{vv}'")

        exec_sql = f"SET NOCOUNT ON; EXEC {req.proc}"
        if parts:
            exec_sql += " " + ", ".join(parts)

        cursor.execute(exec_sql)

        # Check if there's a result set
        if cursor.description is not None:
            columns, rows = _rows_to_dicts(cursor)
            conn.close()
            return {
                "status": "ok",
                "row_count": len(rows),
                "columns": columns,
                "rows": rows,
            }

        # No result set — action proc.  Commit and report success.
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return {
            "status": "ok",
            "row_count": 0,
            "columns": [],
            "rows": [],
            "message": f"Procedure executed successfully. Rows affected: {affected}",
        }

    except Exception as e:
        log.error(f"Stored proc failed: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": str(e)}


@app.get("/supervisor/health")
async def supervisor_health(x_api_key: Optional[str] = Header(None)):
    """Supervisor system health — latest RunDates and pipeline counts."""
    _check_api_key(x_api_key)
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                LatestInbox     = (SELECT MAX(RunDate) FROM dbo.Signals_Inbox),
                LatestConverged = (SELECT MAX(RunDate) FROM dbo.Signals_Converged),
                LatestTradePlan = (SELECT MAX(RunDate) FROM dbo.Supervisor_TradePlans),
                LatestQueue     = (SELECT MAX(RunDate) FROM dbo.Supervisor_Execution_Queue),
                LatestDispatched= (SELECT MAX(RunDate) FROM dbo.Signals_Dispatched)
        """)
        row = cursor.fetchone()
        conn.close()
        return {
            "status": "ok",
            "latest_inbox": str(row[0]) if row[0] else None,
            "latest_converged": str(row[1]) if row[1] else None,
            "latest_trade_plan": str(row[2]) if row[2] else None,
            "latest_queue": str(row[3]) if row[3] else None,
            "latest_dispatched": str(row[4]) if row[4] else None,
        }
    except Exception as e:
        log.error(f"Supervisor health failed: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/portfolio/state")
async def portfolio_state(x_api_key: Optional[str] = Header(None)):
    """Portfolio state — placeholder for future implementation."""
    _check_api_key(x_api_key)
    return {"status": "ok", "message": "Portfolio state endpoint — not yet implemented"}


@app.get("/agent/state")
async def agent_state(x_api_key: Optional[str] = Header(None)):
    """Agent state — placeholder for future implementation."""
    _check_api_key(x_api_key)
    return {"status": "ok", "message": "Agent state endpoint — not yet implemented"}


@app.get("/agent/status")
async def agent_status(x_api_key: Optional[str] = Header(None)):
    """Agent status — placeholder for future implementation."""
    _check_api_key(x_api_key)
    return {"status": "ok", "message": "Agent status endpoint — not yet implemented"}


@app.get("/stage/status")
async def stage_status(x_api_key: Optional[str] = Header(None)):
    """Stage status — placeholder for future implementation."""
    _check_api_key(x_api_key)
    return {"status": "ok", "message": "Stage status endpoint — not yet implemented"}


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
