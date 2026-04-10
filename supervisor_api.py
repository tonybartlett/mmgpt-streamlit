"""
supervisor_api.py — MMGPT Supervisor FastAPI Bridge
====================================================

This file is a **reference copy** stored in the Streamlit repo for version control.
The production instance runs on the VM at:
    E:\\MMGPT_V3\\03_bridge\\supervisor_api.py

Endpoints (v0.8.0):
    GET  /ping                      — public health check (no auth)
    GET  /sql/ping                  — SQL Server connectivity check (auth)
    POST /sql/query                 — execute ad-hoc SQL query (auth)
    POST /sql/stored-proc           — execute stored procedure (auth)
    GET  /supervisor/health         — supervisor system health (auth)
    GET  /portfolio/state           — portfolio state (auth)
    GET  /agent/state               — agent state (auth)
    GET  /agent/status              — agent status (auth)
    GET  /stage/status              — stage status (auth)
    POST /tradingview/webhook       — TradingView Pine Script alert ingestion (token auth)
    GET  /tradingview/recent        — last 20 TradingView signals (auth)

Auth:  X-API-Key header validated against BRIDGE_API_KEY env var.
       TradingView webhook uses ?token= query param instead of header.
SQL:   pyodbc → MMGPTVM\\ASXSQLDATA, "Stock Master Default", Windows Auth.

Usage:
    set BRIDGE_API_KEY=your-secret-key
    uvicorn supervisor_api:app --host 0.0.0.0 --port 8000

Or via NSSM Windows Service (MMGPT-Bridge).
"""

from __future__ import annotations

import os
import logging
import traceback
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import pyodbc
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

# ─── Configuration ───────────────────────────────────────────────────────────

BRIDGE_API_KEY = os.getenv("BRIDGE_API_KEY", os.getenv("SUPERVISOR_API_KEY", ""))
SQL_SERVER = os.getenv("SQL_SERVER", r"MMGPTVM\ASXSQLDATA")
SQL_DATABASE = os.getenv("SQL_DATABASE", "Stock Master Default")
SQL_DRIVER = os.getenv("SQL_DRIVER", "ODBC Driver 17 for SQL Server")
PORT = int(os.getenv("BRIDGE_PORT", "8000"))

# TradingView webhook token — defaults to TV_ prefix + API key
TV_WEBHOOK_TOKEN = os.getenv("TV_WEBHOOK_TOKEN", f"TV_{BRIDGE_API_KEY}")

log = logging.getLogger("supervisor_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")

# ─── FastAPI app ─────────────────────────────────────────────────────────────

app = FastAPI(title="MMGPT Supervisor API", version="0.8.0")

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


# ─── Auth helpers ─────────────────────────────────────────────────────────────

def _check_api_key(x_api_key: Optional[str] = None) -> None:
    """Raise 401 if API key is configured but not provided / wrong."""
    if not BRIDGE_API_KEY:
        return  # no key configured — open access
    if x_api_key != BRIDGE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _check_tv_token(token: Optional[str] = None) -> None:
    """Raise 401 if TradingView webhook token is wrong."""
    if not TV_WEBHOOK_TOKEN:
        return  # no token configured — open access
    if token != TV_WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing webhook token")


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
            if isinstance(val, (datetime, date)):
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

class TradingViewAlert(BaseModel):
    ticker: Optional[str] = None
    strategy: Optional[str] = None
    strategy_name: Optional[str] = None
    action: Optional[str] = None
    price: Optional[float] = None
    score: Optional[float] = None
    note: Optional[str] = None
    run_date: Optional[str] = None


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
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        parts = []
        if params:
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
        if cursor.description is not None:
            columns, rows = _rows_to_dicts(cursor)
            conn.close()
            return {
                "status": "ok",
                "row_count": len(rows),
                "columns": columns,
                "rows": rows,
            }
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


# ─── TradingView Webhook ──────────────────────────────────────────────────────

@app.post("/tradingview/webhook")
async def tradingview_webhook(
    alert: TradingViewAlert,
    token: Optional[str] = Query(None),
):
    """
    Receive a TradingView Pine Script alert and insert it into dbo.Signals_Inbox.

    Authentication: ?token=TV_{BRIDGE_API_KEY} query parameter
    (TradingView sends to the full URL including the token)

    Expected JSON payload from Pine Script alert message:
    {
        "ticker": "{{ticker}}",
        "strategy": "{{strategy.order.comment}}",
        "action": "{{strategy.order.action}}",
        "price": {{close}},
        "score": {{strategy.position_size}},
        "note": "TradingView alert fired at {{timenow}}"
    }
    """
    _check_tv_token(token)

    # Normalise ticker — strip exchange prefix (e.g. "ASX:BHP" → "BHP")
    raw_ticker = (alert.ticker or "UNKNOWN").strip()
    if ":" in raw_ticker:
        raw_ticker = raw_ticker.split(":", 1)[1]

    strategy = (alert.strategy or alert.strategy_name or "TradingView").strip()
    action = (alert.action or "").strip().upper()
    price = alert.price or 0.0
    score = alert.score or 0.0

    # Build note
    note_parts = [f"TradingView | action:{action} | price:{price}"]
    if alert.note:
        note_parts.append(alert.note)
    note = " | ".join(note_parts)[:500]  # cap at 500 chars

    # Determine RunDate
    run_date = date.today().isoformat()
    if alert.run_date:
        try:
            run_date = str(date.fromisoformat(alert.run_date))
        except ValueError:
            pass

    log.info(f"TradingView alert: ticker={raw_ticker} strategy={strategy} action={action} score={score}")

    try:
        conn = _get_connection()
        cursor = conn.cursor()

        # Try inserting into dbo.Signals_Inbox
        # Columns: RunDate, Strategy, Ticker, Score, Note, CreatedAt, StrategyName
        cursor.execute(
            """
            INSERT INTO dbo.Signals_Inbox
                (RunDate, Strategy, Ticker, Score, Note, CreatedAt, StrategyName)
            VALUES
                (?, ?, ?, ?, ?, GETDATE(), ?)
            """,
            run_date,
            strategy,
            raw_ticker,
            score,
            note,
            strategy,
        )
        conn.commit()
        conn.close()

        return {
            "status": "ok",
            "message": "Signal ingested successfully",
            "ticker": raw_ticker,
            "strategy": strategy,
            "action": action,
            "run_date": run_date,
            "rows_inserted": 1,
        }

    except Exception as e:
        log.error(f"TradingView webhook insert failed: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": str(e)}


@app.get("/tradingview/recent")
async def tradingview_recent(
    limit: int = Query(20, ge=1, le=100),
    x_api_key: Optional[str] = Header(None),
):
    """Return the most recent TradingView signals from dbo.Signals_Inbox."""
    _check_api_key(x_api_key)
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT TOP (?) InboxID, RunDate, Strategy, StrategyName, Ticker, Score, Note, CreatedAt
            FROM dbo.Signals_Inbox
            WHERE Note LIKE '%TradingView%'
            ORDER BY CreatedAt DESC
            """,
            limit,
        )
        columns, rows = _rows_to_dicts(cursor)
        conn.close()
        return {
            "status": "ok",
            "row_count": len(rows),
            "columns": columns,
            "rows": rows,
        }
    except Exception as e:
        log.error(f"TradingView recent failed: {e}")
        return {"status": "error", "message": str(e)}


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
