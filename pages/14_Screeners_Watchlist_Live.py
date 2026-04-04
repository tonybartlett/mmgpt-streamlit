from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots


st.set_page_config(page_title="Screeners & Watchlist Live", page_icon="📈", layout="wide")


def bridge_config() -> tuple[str, str, int]:
    bridge = st.secrets.get("bridge", {})
    base_url = str(bridge.get("base_url", "")).rstrip("/")
    api_key = str(bridge.get("api_key", ""))
    timeout = int(bridge.get("timeout_seconds", 20))
    return base_url, api_key, timeout


def bridge_request(method: str, path: str, json_body: dict | None = None, allow_error: bool = False):
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
    if allow_error:
        return response
    response.raise_for_status()
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"text": response.text}


def sql_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    payload = {"sql": sql, "query": sql, "params": params or {}, "readonly": True}
    data = bridge_request("POST", "/sql/query", payload)
    rows = data.get("rows") or data.get("data") or data.get("results") or []
    return pd.DataFrame(rows)


def run_screener(run_date: str) -> tuple[bool, str]:
    payload = {
        "procedure": "dbo.sp_Screener_Candles_Strategy_Run",
        "proc_name": "dbo.sp_Screener_Candles_Strategy_Run",
        "name": "dbo.sp_Screener_Candles_Strategy_Run",
        "params": {"RunDate": run_date},
        "expect_result": False,
    }
    first = bridge_request("POST", "/sql/stored-proc", payload, allow_error=True)
    if first.ok:
        return True, f"Triggered candle screener for {run_date}."

    fallback = bridge_request(
        "POST",
        "/sql/query",
        {
            "sql": "EXEC dbo.sp_Screener_Candles_Strategy_Run @RunDate = CAST(:run_date AS date);",
            "query": "EXEC dbo.sp_Screener_Candles_Strategy_Run @RunDate = CAST(:run_date AS date);",
            "params": {"run_date": run_date},
            "readonly": False,
        },
        allow_error=True,
    )
    if fallback.ok:
        return True, f"Triggered candle screener for {run_date} via bridge fallback."

    return False, f"stored-proc={first.status_code}, sql-query={fallback.status_code}"


def tradingview_url(symbol: str) -> str:
    clean = str(symbol or "").strip().upper()
    if clean.endswith(".AU"):
        return f"https://www.tradingview.com/chart/?symbol=ASX%3A{clean[:-3]}"
    if "." in clean:
        base, market = clean.split(".", 1)
        return f"https://www.tradingview.com/chart/?symbol={market}%3A{base}"
    return f"https://www.tradingview.com/chart/?symbol={clean}"


def add_tradingview_column(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "Ticker" not in frame.columns:
        return frame
    result = frame.copy()
    result["TradingView"] = result["Ticker"].astype(str).map(tradingview_url)
    return result


def get_run_dates() -> pd.DataFrame:
    return sql_df(
        """
        SELECT TOP (30) CAST(RunDate AS date) AS RunDate
        FROM dbo.Supervisor_TradePlans
        GROUP BY CAST(RunDate AS date)
        ORDER BY RunDate DESC;
        """
    )


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
        ORDER BY RunDate DESC, Ticker ASC;
        """,
        {"run_date": run_date},
    )


def eodhd_config() -> tuple[str, str]:
    cfg = st.secrets.get("eodhd", {})
    token = str(cfg.get("api_token", ""))
    base_url = str(cfg.get("base_url", "https://eodhd.com/api")).rstrip("/")
    return base_url, token


def get_daily_history(symbol: str, days: int) -> pd.DataFrame:
    base_url, token = eodhd_config()
    if not token:
        return pd.DataFrame()
    response = requests.get(
        f"{base_url}/eod/{symbol}",
        params={"api_token": token, "fmt": "json", "period": "d", "order": "a"},
        timeout=20,
    )
    response.raise_for_status()
    frame = pd.DataFrame(response.json())
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.sort_values("date").tail(days)


def build_ohlcv_chart(frame: pd.DataFrame, symbol: str) -> go.Figure:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.04)
    fig.add_trace(
        go.Candlestick(
            x=frame["date"],
            open=frame["open"],
            high=frame["high"],
            low=frame["low"],
            close=frame["close"],
            name=symbol,
        ),
        row=1,
        col=1,
    )
    if "volume" in frame.columns:
        fig.add_trace(go.Bar(x=frame["date"], y=frame["volume"], marker_color="#2563eb", opacity=0.45), row=2, col=1)
    fig.update_layout(height=620, margin=dict(l=12, r=12, t=36, b=12), xaxis_rangeslider_visible=False, showlegend=False)
    return fig


st.title("Screeners & Watchlist Live")
st.caption("Self-contained bridge page with screener trigger fallback and TradingView links.")

try:
    run_dates = get_run_dates()
    run_date_options = pd.to_datetime(run_dates["RunDate"]).dt.date.tolist() if not run_dates.empty else []
except Exception as error:
    st.error(str(error))
    st.stop()

with st.sidebar:
    selected_run_date = st.selectbox("Run date", run_date_options, index=0) if run_date_options else st.date_input("Run date", value=date.today())
    top_n = st.slider("Rows to load", min_value=25, max_value=500, value=100, step=25)
    history_days = st.selectbox("Chart lookback", [90, 180, 365], index=2)
    manual_watchlist = st.text_input("Extra watchlist", value="SVL.AU,WDS.AU")
    trigger = st.button("Run candle screener", use_container_width=True)
    refresh = st.button("Refresh", use_container_width=True)

if refresh:
    st.cache_data.clear()

if trigger:
    ok, message = run_screener(str(selected_run_date))
    if ok:
        st.success(message)
        st.cache_data.clear()
    else:
        st.warning("Screener trigger did not succeed from this page.")
        st.caption(message)

try:
    results = get_candle_results(str(selected_run_date), top_n)
except Exception as error:
    st.error(str(error))
    st.stop()

if results.empty:
    st.warning("No screener rows returned for the selected run date.")
    st.stop()

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
filtered_display = add_tradingview_column(filtered)

metric_cols = st.columns(4)
metric_cols[0].metric("Rows", len(filtered_display))
metric_cols[1].metric("Long", int((filtered.get("Direction") == "L").sum()) if "Direction" in filtered.columns else 0)
metric_cols[2].metric("Short", int((filtered.get("Direction") == "S").sum()) if "Direction" in filtered.columns else 0)
metric_cols[3].metric("Unique tickers", filtered["Ticker"].nunique() if "Ticker" in filtered.columns else 0)

board_tab, watchlist_tab = st.tabs(["Screener Board", "Watchlist"])

with board_tab:
    st.subheader("Latest Passes")
    st.data_editor(
        filtered_display,
        use_container_width=True,
        hide_index=True,
        height=420,
        disabled=True,
        column_config={"TradingView": st.column_config.LinkColumn("TradingView", display_text="Open")},
    )
    top_cols = st.columns(3)
    for idx, (_, row) in enumerate(filtered.head(6).iterrows()):
        with top_cols[idx % 3]:
            st.markdown(f"**{row.get('Ticker', 'Unknown')}**  \\n{row.get('SetupType', 'Unknown')} · {row.get('Direction', 'n/a')}")
            st.write(f"Momentum: {row.get('MomentumScore', 'n/a')}")
            st.write(f"Vol Ratio: {row.get('VolumeRatio', 'n/a')}")
            st.link_button("Open in TradingView", tradingview_url(str(row.get("Ticker", ""))), use_container_width=True)

with watchlist_tab:
    queue = get_execution_watchlist(str(selected_run_date))
    queue_tickers = queue["Ticker"].dropna().astype(str).tolist() if not queue.empty and "Ticker" in queue.columns else []
    screener_tickers = filtered["Ticker"].dropna().astype(str).tolist() if not filtered.empty and "Ticker" in filtered.columns else []
    manual_tickers = [item.strip().upper() for item in manual_watchlist.split(",") if item.strip()]
    watchlist = list(dict.fromkeys(queue_tickers + screener_tickers[:10] + manual_tickers))
    if not watchlist:
        st.info("No watchlist tickers available yet.")
    else:
        chosen_symbol = st.selectbox("Ticker drilldown", watchlist, index=0)
        st.link_button("Open Selected Ticker in TradingView", tradingview_url(chosen_symbol), use_container_width=False)
        if not queue.empty:
            st.data_editor(
                add_tradingview_column(queue),
                use_container_width=True,
                hide_index=True,
                height=280,
                disabled=True,
                column_config={"TradingView": st.column_config.LinkColumn("TradingView", display_text="Open")},
            )
        history = get_daily_history(chosen_symbol, history_days)
        if not history.empty and {"date", "open", "high", "low", "close"}.issubset(history.columns):
            st.plotly_chart(build_ohlcv_chart(history, chosen_symbol), use_container_width=True)
            st.dataframe(history, use_container_width=True, hide_index=True, height=260)
