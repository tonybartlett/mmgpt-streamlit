"""
mmgpt_queries.py — All SQL queries for the MMGPT Supervisor Streamlit dashboard.

Each function calls run_query / run_stored_proc from data_source and returns
(DataFrame | None, status_string).  Keeps SQL out of page files.

Column names verified against live database 2026-04-03:
  Supervisor_TradePlans:  TradePlanID, RunDate, Ticker, StrategyCode, SignalSide,
      EntryRule, EntryPrice, WeightPct, TakeProfitPrice, TakeProfitPct,
      StopLossPrice, StopLossPct, TimeStopDate, CompositeScore, RankGlobal,
      RiskBand, StrategyMixCategory, StrategiesHit, NumStrategies, Notes, CreatedAt
  Supervisor_Execution_Queue:  ExecutionID, RunDate, AccountID, Strategy, Ticker,
      Side, ReasonCode, CurrentQty, TargetQty, DeltaQty, PriceType, LimitPrice,
      TimeInForce, StopLoss, TakeProfit, ConfidenceScore, Status, CreatedAtUTC, SentAtUTC
  Signals_Converged:  ConvergedID, RunDate, Ticker, StrategiesHit, NumStrategies,
      CompositeScore, RiskBand, StrategyMixCategory, RankGlobal, RankByStrategyMix,
      MaxStrategyScore, HasTrend, CreatedAt
  Supervisor_Dashboard_History:  AsOfDate, Strategy, ActiveRunID, Lookback, NearPct,
      MinDollarVol, TP_Pct, SL_Pct, TimeoutDays, Trades, Wins, Losses, Timeouts,
      WinRate, AvgReturnPct, PerfAsOf, LastPromotedAt, Trades30d, Wins30d, Losses30d,
      Timeouts30d, AvgWinRate30d, AvgRetPct30d, RecordedAtUTC, ...
  vwSupervisor_ControlPanel:  Strategy, AsOfDate, Trades, WinRate, AvgReturnPct,
      WeightedWinRate7d, WeightedRetPct7d, WeightedWinRate30d, WeightedRetPct30d,
      WeightedWinRate90d, WeightedRetPct90d
  vwSupervisor_TopSignals:  RunDate, Ticker, StrategiesHit, NumStrategies,
      CompositeScore, RiskBand, StrategyMixCategory, RankGlobal, RankByStrategyMix,
      MaxStrategyScore, HasTrend
"""

from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd

from data_source import run_query, run_stored_proc


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Home / Run-status queries
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_latest_run_date() -> Tuple[Optional[pd.DataFrame], str]:
    """Return the MAX RunDate across key tables."""
    sql = """
    SELECT
        LatestInbox     = (SELECT MAX(RunDate) FROM dbo.Signals_Inbox),
        LatestConverged = (SELECT MAX(RunDate) FROM dbo.Signals_Converged),
        LatestQueue     = (SELECT MAX(RunDate) FROM dbo.Supervisor_Execution_Queue),
        LatestDispatched= (SELECT MAX(RunDate) FROM dbo.Signals_Dispatched),
        LatestTradePlan = (SELECT MAX(RunDate) FROM dbo.Supervisor_TradePlans);
    """
    return run_query(sql)


def get_pipeline_counts(run_date: str) -> Tuple[Optional[pd.DataFrame], str]:
    """Counts of rows in Inbox / Converged / Queue / Dispatched for a given RunDate."""
    sql = f"""
    SELECT
        InboxCount      = (SELECT COUNT(*) FROM dbo.Signals_Inbox              WHERE RunDate = '{run_date}'),
        ConvergedCount  = (SELECT COUNT(*) FROM dbo.Signals_Converged          WHERE RunDate = '{run_date}'),
        QueueCount      = (SELECT COUNT(*) FROM dbo.Supervisor_Execution_Queue WHERE RunDate = '{run_date}'),
        DispatchedCount = (SELECT COUNT(*) FROM dbo.Signals_Dispatched         WHERE RunDate = '{run_date}'),
        TradePlanCount  = (SELECT COUNT(*) FROM dbo.Supervisor_TradePlans      WHERE RunDate = '{run_date}');
    """
    return run_query(sql)


def get_top_signals_home(run_date: str, top_n: int = 3) -> Tuple[Optional[pd.DataFrame], str]:
    """Top N signals by RankGlobal for the home page summary.
    Note: Column is SignalSide (not Side) in Supervisor_TradePlans.
    """
    sql = f"""
    SELECT TOP ({top_n})
        RankGlobal,
        Ticker,
        SignalSide,
        CompositeScore,
        RiskBand,
        StrategyMixCategory,
        NumStrategies
    FROM dbo.Supervisor_TradePlans
    WHERE RunDate = '{run_date}'
    ORDER BY RankGlobal ASC;
    """
    return run_query(sql)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Page 1 — Supervisor Signals (Trade Plans)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_available_run_dates_converged() -> Tuple[Optional[pd.DataFrame], str]:
    """Distinct RunDates from Signals_Converged, most recent first."""
    sql = """
    SELECT DISTINCT RunDate
    FROM dbo.Signals_Converged
    ORDER BY RunDate DESC;
    """
    return run_query(sql)


def get_trade_plans(run_date: str, top_n: int = 50) -> Tuple[Optional[pd.DataFrame], str]:
    """Top N trade plans for a given RunDate, ordered by RankGlobal.
    Uses actual column names from Supervisor_TradePlans.
    """
    sql = f"""
    SELECT TOP ({top_n})
        RankGlobal,
        Ticker,
        SignalSide,
        EntryPrice,
        StopLossPrice,
        TakeProfitPrice,
        TakeProfitPct,
        StopLossPct,
        WeightPct,
        CompositeScore,
        RiskBand,
        StrategyMixCategory,
        StrategiesHit,
        NumStrategies,
        TimeStopDate,
        Notes
    FROM dbo.Supervisor_TradePlans
    WHERE RunDate = '{run_date}'
    ORDER BY RankGlobal ASC;
    """
    return run_query(sql)


def get_signal_summary(run_date: str) -> Tuple[Optional[pd.DataFrame], str]:
    """Summary metrics for the signals page header."""
    sql = f"""
    SELECT
        TotalSignals   = COUNT(*),
        HighCount      = SUM(CASE WHEN RiskBand = 'High'   THEN 1 ELSE 0 END),
        MediumCount    = SUM(CASE WHEN RiskBand = 'Medium' THEN 1 ELSE 0 END),
        LowCount       = SUM(CASE WHEN RiskBand = 'Low'    THEN 1 ELSE 0 END),
        AvgComposite   = AVG(CAST(CompositeScore AS FLOAT)),
        AvgWeightPct   = AVG(CAST(WeightPct AS FLOAT))
    FROM dbo.Supervisor_TradePlans
    WHERE RunDate = '{run_date}';
    """
    return run_query(sql)


def get_top_signals_view(run_date: str) -> Tuple[Optional[pd.DataFrame], str]:
    """Pull from the dashboard-ready top signals view."""
    sql = f"""
    SELECT *
    FROM dbo.vwSupervisor_TopSignals
    WHERE RunDate = '{run_date}'
    ORDER BY RankGlobal ASC;
    """
    return run_query(sql)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Page 2 — Performance
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_control_panel() -> Tuple[Optional[pd.DataFrame], str]:
    """Full control panel view — latest + 7/30/90d rollups per strategy."""
    sql = """
    SELECT *
    FROM dbo.vwSupervisor_ControlPanel
    ORDER BY Strategy;
    """
    return run_query(sql)


def get_dashboard_history(days: int = 90) -> Tuple[Optional[pd.DataFrame], str]:
    """Daily history rows for the last N days."""
    sql = f"""
    SELECT
        AsOfDate,
        Strategy,
        Trades,
        WinRate,
        AvgReturnPct
    FROM dbo.Supervisor_Dashboard_History
    WHERE AsOfDate >= DATEADD(DAY, -{days}, GETDATE())
    ORDER BY AsOfDate ASC, Strategy ASC;
    """
    return run_query(sql)


def get_performance_summary() -> Tuple[Optional[pd.DataFrame], str]:
    """Aggregate performance summary across all strategies."""
    sql = """
    SELECT
        TotalStrategies = COUNT(DISTINCT Strategy),
        TotalTrades     = SUM(CAST(Trades AS BIGINT)),
        AvgWinRate      = AVG(CAST(WinRate AS FLOAT)),
        AvgReturnPct    = AVG(CAST(AvgReturnPct AS FLOAT))
    FROM dbo.Supervisor_Dashboard_History
    WHERE AsOfDate = (SELECT MAX(AsOfDate) FROM dbo.Supervisor_Dashboard_History);
    """
    return run_query(sql)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Page 3 — Execution Queue
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_latest_exec_run_date() -> Tuple[Optional[pd.DataFrame], str]:
    """Latest RunDate in the execution queue."""
    sql = """
    SELECT MAX(RunDate) AS RunDate
    FROM dbo.Supervisor_Execution_Queue;
    """
    return run_query(sql)


def get_execution_queue(
    run_date: str,
    account_id: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], str]:
    """Execution queue for a given RunDate, optionally filtered by AccountID.
    Uses actual column names from Supervisor_Execution_Queue.
    """
    where = f"WHERE e.RunDate = '{run_date}'"
    if account_id and account_id != "All":
        safe_id = account_id.replace("'", "''")
        where += f" AND e.AccountID = '{safe_id}'"

    sql = f"""
    SELECT
        e.ExecutionID,
        e.RunDate,
        e.AccountID,
        e.Strategy,
        e.Ticker,
        e.Side,
        e.ReasonCode,
        e.TargetQty,
        e.DeltaQty,
        e.PriceType,
        e.StopLoss,
        e.TakeProfit,
        e.ConfidenceScore,
        e.[Status]
    FROM dbo.Supervisor_Execution_Queue e
    {where}
    ORDER BY e.ConfidenceScore DESC, e.Ticker ASC;
    """
    return run_query(sql)


def get_account_ids(run_date: str) -> Tuple[Optional[pd.DataFrame], str]:
    """Distinct AccountIDs for a given RunDate."""
    sql = f"""
    SELECT DISTINCT AccountID
    FROM dbo.Supervisor_Execution_Queue
    WHERE RunDate = '{run_date}'
    ORDER BY AccountID;
    """
    return run_query(sql)


def get_exec_queue_null_check(
    run_date: str,
    account_id: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], str]:
    """Null-check summary for execution queue data quality."""
    where_clause = f"WHERE RunDate = '{run_date}'"
    if account_id and account_id != "All":
        safe_id = account_id.replace("'", "''")
        where_clause += f" AND AccountID = '{safe_id}'"

    sql = f"""
    SELECT
        ExecQRows      = COUNT(*),
        NullTargetQty  = SUM(CASE WHEN TargetQty       IS NULL THEN 1 ELSE 0 END),
        NullStopLoss   = SUM(CASE WHEN StopLoss        IS NULL THEN 1 ELSE 0 END),
        NullTakeProfit = SUM(CASE WHEN TakeProfit       IS NULL THEN 1 ELSE 0 END),
        NullConfidence = SUM(CASE WHEN ConfidenceScore  IS NULL THEN 1 ELSE 0 END),
        NullStatus     = SUM(CASE WHEN [Status]         IS NULL THEN 1 ELSE 0 END)
    FROM dbo.Supervisor_Execution_Queue
    {where_clause};
    """
    return run_query(sql)


def get_exec_queue_status_summary(
    run_date: str,
    account_id: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], str]:
    """Status breakdown for execution queue."""
    where_clause = f"WHERE RunDate = '{run_date}'"
    if account_id and account_id != "All":
        safe_id = account_id.replace("'", "''")
        where_clause += f" AND AccountID = '{safe_id}'"

    sql = f"""
    SELECT
        [Status],
        OrderCount = COUNT(*)
    FROM dbo.Supervisor_Execution_Queue
    {where_clause}
    GROUP BY [Status]
    ORDER BY COUNT(*) DESC;
    """
    return run_query(sql)
