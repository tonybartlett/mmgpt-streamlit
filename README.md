# MMGPT Supervisor — Streamlit Dashboard

Production-grade Streamlit dashboard for the MMGPT Supervisor trading system.

## Pages

| Page | File | Description |
|------|------|-------------|
| Home | `app.py` | Run status, pipeline counts, top 3 signals, system health |
| Supervisor Signals | `pages/1_Supervisor_Signals.py` | Top 50 trade plans by RankGlobal with Risk Band color-coding |
| Performance | `pages/2_Performance.py` | Strategy control panel + WinRate/Return trends over time |
| Execution Queue | `pages/3_Execution_Queue.py` | Queue monitor with status color-coding and null-check QA |
| SQL Connection Test | `pages/4_SQL_Connection_Test.py` | Ad-hoc SQL query runner for connectivity validation |
| Candle Screener | `pages/6_Candle_Screener.py` | Stored procedure runner for candle pattern screening |

## Architecture

- **`data_source.py`** — Unified SQL access layer (bridge + pyodbc fallback)
- **`mmgpt_queries.py`** — All SQL queries as named functions
- **`.streamlit/secrets.toml`** — SQL Server connection config (not committed)

## SQL Server

- Instance: `MMGPTVM\ASXSQLDATA`
- Database: `Stock Master Default`
- Auth: Windows (Trusted Connection)

## Setup

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml  # configure credentials
streamlit run app.py
```

## Key Tables

- `dbo.Supervisor_TradePlans` — Trade plans with entry/exit/risk data
- `dbo.Signals_Converged` — Converged/ranked signals
- `dbo.Signals_Dispatched` — Final dispatched signals
- `dbo.Supervisor_Execution_Queue` — Execution queue with status tracking
- `dbo.Signals_Inbox` — Raw signals from strategies
- `dbo.Supervisor_Dashboard_History` — Daily performance history
- `dbo.vwSupervisor_ControlPanel` — Strategy rollup view (7/30/90d)
- `dbo.vwSupervisor_TopSignals` — Dashboard-ready top signals view
