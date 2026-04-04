from __future__ import annotations

from datetime import date

import pandas as pd
import requests
import streamlit as st


def bridge_config() -> tuple[str, str, int]:
    bridge = st.secrets.get("bridge", {})
    base_url = str(bridge.get("base_url", "")).rstrip("/")
    api_key = str(bridge.get("api_key", ""))
    timeout = int(bridge.get("timeout_seconds", 20))
    return base_url, api_key, timeout


def bridge_request(method: str, path: str, json_body: dict | None = None) -> dict:
    base_url, api_key, timeout = bridge_config()
    if not base_url:
        raise RuntimeError("Bridge base_url is missing from Streamlit secrets.")

    headers = {"Accept": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    response = requests.request(
        method=method.upper(),
        url=f"{base_url}/{path.lstrip('/')}",
        json=json_body,
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json() if response.content else {}


def sql_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    payload = {"sql": sql, "query": sql, "params": params or {}, "readonly": True}
    data = bridge_request("POST", "/sql/query", payload)
    rows = data.get("rows") or data.get("data") or []
    return pd.DataFrame(rows)


def run_proc(name: str, params: dict | None = None) -> dict:
    payload = {"procedure": name, "proc_name": name, "name": name, "params": params or {}, "expect_result": False}
    return bridge_request("POST", "/sql/stored-proc", payload)


@st.cache_data(ttl=60)
def get_run_dates() -> pd.DataFrame:
    return sql_df(
        """
        SELECT TOP (30) CAST(RunDate AS date) AS RunDate
        FROM dbo.Supervisor_TradePlans
        GROUP BY CAST(RunDate AS date)
        ORDER BY RunDate DESC;
        """
    )


@st.cache_data(ttl=60)
def get_candle_source() -> pd.DataFrame:
    return sql_df(
        """
        SELECT TOP (1) *
        FROM (
            SELECT 1 AS SortOrder, 'dbo.vwCandlesScreener_Latest_Compat' AS ObjectName, 'VIEW' AS ObjectType,
                CASE
                    WHEN COL_LENGTH('dbo.vwCandlesScreener_Latest_Compat', 'RunDate') IS NOT NULL THEN 'RunDate'
                    WHEN COL_LENGTH('dbo.vwCandlesScreener_Latest_Compat', 'TradeDate') IS NOT NULL THEN 'TradeDate'
                    WHEN COL_LENGTH('dbo.vwCandlesScreener_Latest_Compat', 'Date') IS NOT NULL THEN 'Date'
                    ELSE NULL
                END AS DateColumn
            WHERE OBJECT_ID('dbo.vwCandlesScreener_Latest_Compat', 'V') IS NOT NULL
            UNION ALL
            SELECT 2 AS SortOrder, 'dbo.vwCandlesScreener_Latest' AS ObjectName, 'VIEW' AS ObjectType,
                CASE
                    WHEN COL_LENGTH('dbo.vwCandlesScreener_Latest', 'RunDate') IS NOT NULL THEN 'RunDate'
                    WHEN COL_LENGTH('dbo.vwCandlesScreener_Latest', 'TradeDate') IS NOT NULL THEN 'TradeDate'
                    WHEN COL_LENGTH('dbo.vwCandlesScreener_Latest', 'Date') IS NOT NULL THEN 'Date'
                    ELSE NULL
                END AS DateColumn
            WHERE OBJECT_ID('dbo.vwCandlesScreener_Latest', 'V') IS NOT NULL
            UNION ALL
            SELECT 3 AS SortOrder, 'dbo.Candles_Calculations' AS ObjectName, 'TABLE' AS ObjectType,
                CASE
                    WHEN COL_LENGTH('dbo.Candles_Calculations', 'RunDate') IS NOT NULL THEN 'RunDate'
                    WHEN COL_LENGTH('dbo.Candles_Calculations', 'TradeDate') IS NOT NULL THEN 'TradeDate'
                    WHEN COL_LENGTH('dbo.Candles_Calculations', 'Date') IS NOT NULL THEN 'Date'
                    ELSE NULL
                END AS DateColumn
            WHERE OBJECT_ID('dbo.Candles_Calculations', 'U') IS NOT NULL
        ) sources
        ORDER BY SortOrder;
        """
    )


@st.cache_data(ttl=60)
def get_candle_results(run_date: str, top_n: int) -> pd.DataFrame:
    return sql_df(
        """
        DECLARE @RunDate date = CAST(:run_date AS date);
        DECLARE @TopN int = :top_n;
        DECLARE @DateColumn sysname;
        DECLARE @Sql nvarchar(max);

        IF OBJECT_ID('dbo.vwCandlesScreener_Latest_Compat', 'V') IS NOT NULL
        BEGIN
            SET @DateColumn =
                CASE
                    WHEN COL_LENGTH('dbo.vwCandlesScreener_Latest_Compat', 'RunDate') IS NOT NULL THEN 'RunDate'
                    WHEN COL_LENGTH('dbo.vwCandlesScreener_Latest_Compat', 'TradeDate') IS NOT NULL THEN 'TradeDate'
                    WHEN COL_LENGTH('dbo.vwCandlesScreener_Latest_Compat', 'Date') IS NOT NULL THEN 'Date'
                    ELSE NULL
                END;
            SET @Sql = N'SELECT TOP (@TopN) * FROM dbo.vwCandlesScreener_Latest_Compat'
                + CASE WHEN @DateColumn IS NULL THEN N'' ELSE N' WHERE CAST(' + QUOTENAME(@DateColumn) + N' AS date) = @RunDate' END
                + N' ORDER BY Ticker ASC;';
            EXEC sp_executesql @Sql, N'@RunDate date, @TopN int', @RunDate = @RunDate, @TopN = @TopN;
            RETURN;
        END

        IF OBJECT_ID('dbo.vwCandlesScreener_Latest', 'V') IS NOT NULL
        BEGIN
            SET @DateColumn =
                CASE
                    WHEN COL_LENGTH('dbo.vwCandlesScreener_Latest', 'RunDate') IS NOT NULL THEN 'RunDate'
                    WHEN COL_LENGTH('dbo.vwCandlesScreener_Latest', 'TradeDate') IS NOT NULL THEN 'TradeDate'
                    WHEN COL_LENGTH('dbo.vwCandlesScreener_Latest', 'Date') IS NOT NULL THEN 'Date'
                    ELSE NULL
                END;
            SET @Sql = N'SELECT TOP (@TopN) * FROM dbo.vwCandlesScreener_Latest'
                + CASE WHEN @DateColumn IS NULL THEN N'' ELSE N' WHERE CAST(' + QUOTENAME(@DateColumn) + N' AS date) = @RunDate' END
                + N' ORDER BY Ticker ASC;';
            EXEC sp_executesql @Sql, N'@RunDate date, @TopN int', @RunDate = @RunDate, @TopN = @TopN;
            RETURN;
        END

        IF OBJECT_ID('dbo.Candles_Calculations', 'U') IS NOT NULL
        BEGIN
            SET @DateColumn =
                CASE
                    WHEN COL_LENGTH('dbo.Candles_Calculations', 'RunDate') IS NOT NULL THEN 'RunDate'
                    WHEN COL_LENGTH('dbo.Candles_Calculations', 'TradeDate') IS NOT NULL THEN 'TradeDate'
                    WHEN COL_LENGTH('dbo.Candles_Calculations', 'Date') IS NOT NULL THEN 'Date'
                    ELSE NULL
                END;
            SET @Sql = N'SELECT TOP (@TopN) * FROM dbo.Candles_Calculations'
                + CASE WHEN @DateColumn IS NULL THEN N'' ELSE N' WHERE CAST(' + QUOTENAME(@DateColumn) + N' AS date) = @RunDate' END
                + N' ORDER BY Ticker ASC;';
            EXEC sp_executesql @Sql, N'@RunDate date, @TopN int', @RunDate = @RunDate, @TopN = @TopN;
        END
        ELSE
        BEGIN
            SELECT CAST(NULL AS nvarchar(20)) AS Ticker WHERE 1 = 0;
        END
        """,
        {"run_date": run_date, "top_n": top_n},
    )


@st.cache_data(ttl=60)
def get_execution_watchlist(run_date: str) -> pd.DataFrame:
    return sql_df(
        """
        WITH latest_run AS (
            SELECT CAST(MAX(RunDate) AS date) AS RunDate
            FROM dbo.Supervisor_Execution_Queue
        )
        SELECT TOP (50)
            CAST(RunDate AS date) AS RunDate,
            Ticker,
            Strategy,
            Side,
            Status,
            TargetQty,
            StopLoss,
            TakeProfit
        FROM dbo.Supervisor_Execution_Queue
        WHERE CAST(RunDate AS date) = COALESCE(CAST(:run_date AS date), (SELECT RunDate FROM latest_run))
        ORDER BY CreatedAtUTC DESC, ExecutionID DESC;
        """,
        {"run_date": run_date},
    )


st.set_page_config(page_title="Screeners & Watchlist", page_icon="📚", layout="wide")
st.title("Screeners & Watchlist")
st.caption("Live screeners and a bridge-backed watchlist page running straight from SQL.")

run_dates = get_run_dates()
run_date_options = pd.to_datetime(run_dates["RunDate"]).dt.date.tolist() if not run_dates.empty else []

with st.sidebar:
    selected_run_date = st.selectbox("Run date", run_date_options, index=0) if run_date_options else st.date_input("Run date", value=date.today())
    top_n = st.slider("Rows to load", min_value=25, max_value=500, value=100, step=25)
    manual_watchlist = st.text_input("Extra watchlist", value="SVL.AU,WDS.AU")
    trigger = st.button("Run candle screener", use_container_width=True)
    refresh = st.button("Refresh", use_container_width=True)

if refresh:
    st.cache_data.clear()

if trigger:
    result = run_proc("dbo.sp_Screener_Candles_Strategy_Run", {"RunDate": str(selected_run_date)})
    st.success(result.get("message", f"Triggered candle screener for {selected_run_date}."))
    st.cache_data.clear()

source = get_candle_source()
if not source.empty:
    row = source.iloc[0]
    source_cols = st.columns(3)
    source_cols[0].metric("Source", row.get("ObjectName", "Unknown"))
    source_cols[1].metric("Type", row.get("ObjectType", "Unknown"))
    source_cols[2].metric("Date column", row.get("DateColumn", "Unknown"))

results = get_candle_results(str(selected_run_date), top_n)
watchlist = get_execution_watchlist(str(selected_run_date))

summary_cols = st.columns(4)
summary_cols[0].metric("Screener rows", len(results))
summary_cols[1].metric("Watchlist rows", len(watchlist))
summary_cols[2].metric("Long setups", int((results.get("Direction") == "L").sum()) if "Direction" in results.columns else 0)
summary_cols[3].metric("Short setups", int((results.get("Direction") == "S").sum()) if "Direction" in results.columns else 0)

board_tab, watchlist_tab, sql_tab = st.tabs(["Screener Board", "Watchlist", "SQL Access"])

with board_tab:
    st.subheader("Latest Screener Passes")
    if results.empty:
        st.warning("No screener rows returned for the selected run date.")
    else:
        setup_options = sorted(str(v) for v in results["SetupType"].dropna().unique()) if "SetupType" in results.columns else []
        direction_options = sorted(str(v) for v in results["Direction"].dropna().unique()) if "Direction" in results.columns else []
        filter_cols = st.columns(3)
        selected_setups = filter_cols[0].multiselect("Setup type", setup_options, default=setup_options)
        selected_directions = filter_cols[1].multiselect("Direction", direction_options, default=direction_options)
        ticker_contains = filter_cols[2].text_input("Ticker contains", value="").strip().upper()

        filtered = results.copy()
        if selected_setups:
            filtered = filtered[filtered["SetupType"].astype(str).isin(selected_setups)]
        if selected_directions:
            filtered = filtered[filtered["Direction"].astype(str).isin(selected_directions)]
        if ticker_contains:
            filtered = filtered[filtered["Ticker"].astype(str).str.upper().str.contains(ticker_contains, na=False)]

        st.dataframe(filtered, use_container_width=True, hide_index=True, height=420)

with watchlist_tab:
    st.subheader("Execution Watchlist")
    manual_names = [item.strip().upper() for item in manual_watchlist.split(",") if item.strip()]
    screener_names = results["Ticker"].dropna().astype(str).tolist()[:15] if "Ticker" in results.columns else []
    queue_names = watchlist["Ticker"].dropna().astype(str).tolist() if "Ticker" in watchlist.columns else []
    combined = list(dict.fromkeys(queue_names + screener_names + manual_names))

    tag_frame = pd.DataFrame({"Ticker": combined}) if combined else pd.DataFrame(columns=["Ticker"])
    left, right = st.columns([0.58, 0.42])
    with left:
        st.dataframe(watchlist, use_container_width=True, hide_index=True, height=420)
    with right:
        st.subheader("Combined watchlist")
        st.dataframe(tag_frame, use_container_width=True, hide_index=True, height=420)

with sql_tab:
    st.subheader("Bridge SQL access")
    st.caption("This page is reading directly from the bridge SQL endpoint, so it can query any allowed SQL table or view in the database.")
    sql = st.text_area(
        "Readonly SQL query",
        value="SELECT TOP (25) * FROM dbo.Candles_Calculations ORDER BY [Date] DESC, Ticker ASC;",
        height=120,
    )
    if st.button("Run SQL preview", use_container_width=False):
        preview = sql_df(sql)
        if preview.empty:
            st.info("Query returned no rows.")
        else:
            st.dataframe(preview, use_container_width=True, hide_index=True, height=360)
