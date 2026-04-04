from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

from core.config import get_app_config
from core.query_runner import get_query_runner
from core.ui import coerce_dates, render_empty_state, render_error, render_mode_banner
from queries.candles import get_candle_results
from queries.execution import get_execution_queue
from queries.intraday import get_daily_history, get_realtime_quotes
from queries.supervisor import get_available_run_dates

st.set_page_config(page_title="Screeners & Watchlist TV", page_icon="📺", layout="wide")


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


def trigger_candle_screener_with_fallback(run_date: date) -> tuple[bool, str]:
    runner = get_query_runner()
    try:
        runner.execute_procedure(
            "dbo.sp_Screener_Candles_Strategy_Run",
            params={"RunDate": str(run_date)},
            expect_result=False,
        )
        return True, f"Triggered dbo.sp_Screener_Candles_Strategy_Run for {run_date}."
    except Exception as first_error:
        config = get_app_config()
        if not config.uses_bridge or not config.bridge.base_url:
            return False, str(first_error)

        try:
            response = requests.post(
                f"{config.bridge.base_url.rstrip('/')}/sql/query",
                headers={"X-API-Key": config.bridge.api_key, "Accept": "application/json"},
                json={
                    "sql": "EXEC dbo.sp_Screener_Candles_Strategy_Run @RunDate = CAST(:run_date AS date);",
                    "query": "EXEC dbo.sp_Screener_Candles_Strategy_Run @RunDate = CAST(:run_date AS date);",
                    "params": {"run_date": str(run_date)},
                    "readonly": False,
                },
                timeout=config.bridge.timeout_seconds,
            )
            response.raise_for_status()
            return True, f"Triggered dbo.sp_Screener_Candles_Strategy_Run for {run_date}."
        except Exception as fallback_error:
            return False, f"{first_error} | fallback failed: {fallback_error}"


def build_ohlcv_chart(frame: pd.DataFrame, symbol: str) -> go.Figure:
    chart = frame.copy()
    chart["date"] = pd.to_datetime(chart["date"])
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.04)
    fig.add_trace(
        go.Candlestick(
            x=chart["date"],
            open=chart["open"],
            high=chart["high"],
            low=chart["low"],
            close=chart["close"],
            name=symbol,
        ),
        row=1,
        col=1,
    )
    if "volume" in chart.columns:
        fig.add_trace(
            go.Bar(x=chart["date"], y=chart["volume"], marker_color="#1b8a5a", opacity=0.55, name="Volume"),
            row=2,
            col=1,
        )
    fig.update_layout(height=640, margin=dict(l=12, r=12, t=36, b=12), showlegend=False, xaxis_rangeslider_visible=False)
    return fig


st.title("Screeners & Watchlist TV")
st.caption("Fixed screener trigger flow plus TradingView launch links on screener and watchlist rows.")
render_mode_banner(get_query_runner().mode_label)

with st.sidebar:
    st.header("Screening Controls")
    try:
        run_dates = get_available_run_dates()
        run_date_options = pd.to_datetime(run_dates["RunDate"]).dt.date.tolist() if not run_dates.empty else []
    except Exception:
        run_date_options = []

    if run_date_options:
        selected_run_date = st.selectbox("Run date", run_date_options, index=0)
    else:
        selected_run_date = st.date_input("Run date", value=date.today())

    top_n = st.slider("Rows to load", min_value=25, max_value=500, value=100, step=25)
    history_days = st.selectbox("Chart lookback", [90, 180, 365], index=2)
    manual_watchlist = st.text_input("Extra watchlist", value="SVL.AU,WDS.AU")
    trigger = st.button("Run candle screener", use_container_width=True)
    refresh = st.button("Refresh", use_container_width=True)

if refresh:
    st.cache_data.clear()

if trigger:
    ok, message = trigger_candle_screener_with_fallback(selected_run_date)
    if ok:
        st.success(message)
        st.cache_data.clear()
    else:
        st.error("Could not trigger the candle screener from this page.")
        st.caption(message)

try:
    screener = get_candle_results(selected_run_date, top_n=top_n)
except Exception as error:
    render_error(error)
    st.stop()

if screener.empty:
    render_empty_state(
        "No candle screener rows were returned.",
        "vwCandlesScreener_Latest_Compat",
        "Run the candle screener first, then reload this page.",
        resolved_context=str(selected_run_date),
    )
    st.stop()

screener = coerce_dates(screener)
setup_options = sorted(str(value) for value in screener["SetupType"].dropna().unique()) if "SetupType" in screener.columns else []
direction_options = sorted(str(value) for value in screener["Direction"].dropna().unique()) if "Direction" in screener.columns else []

filter_cols = st.columns([1.1, 0.9, 1.1, 0.9])
with filter_cols[0]:
    selected_setups = st.multiselect("Setup type", setup_options, default=setup_options)
with filter_cols[1]:
    selected_directions = st.multiselect("Direction", direction_options, default=direction_options)
with filter_cols[2]:
    ticker_contains = st.text_input("Ticker contains", value="").strip().upper()
with filter_cols[3]:
    sort_by = st.selectbox("Rank by", ["MomentumScore", "VolumeRatio", "DollarVolume", "ClosePrice"], index=0)

filtered = screener.copy()
if selected_setups:
    filtered = filtered[filtered["SetupType"].astype(str).isin(selected_setups)]
if selected_directions:
    filtered = filtered[filtered["Direction"].astype(str).isin(selected_directions)]
if ticker_contains:
    filtered = filtered[filtered["Ticker"].astype(str).str.upper().str.contains(ticker_contains, na=False)]
if sort_by in filtered.columns:
    filtered = filtered.sort_values(by=sort_by, ascending=False, na_position="last")
filtered_display = add_tradingview_column(filtered)

metric_cols = st.columns(4)
metric_cols[0].metric("Filtered rows", len(filtered))
metric_cols[1].metric("Long setups", int((filtered.get("Direction") == "L").sum()) if "Direction" in filtered.columns else 0)
metric_cols[2].metric("Avg momentum", f"{filtered['MomentumScore'].mean():.1f}" if "MomentumScore" in filtered.columns and not filtered.empty else "n/a")
metric_cols[3].metric("Avg vol ratio", f"{filtered['VolumeRatio'].mean():.2f}" if "VolumeRatio" in filtered.columns and not filtered.empty else "n/a")

board_tab, watchlist_tab = st.tabs(["Screener Board", "Watchlist Drilldown"])

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

    st.subheader("Top Names")
    highlight_cols = st.columns(3)
    for idx, (_, row) in enumerate(filtered.head(6).iterrows()):
        with highlight_cols[idx % 3]:
            st.markdown(
                f"""
                <div style='border:1px solid rgba(120,120,120,0.2); border-radius:16px; padding:1rem; background:rgba(128,128,128,0.05); min-height:150px;'>
                    <h4 style='margin:0 0 0.35rem 0;'>{row.get('Ticker', 'Unknown')}</h4>
                    <div style='color: rgba(127, 127, 127, 0.9); font-size: 0.92rem;'>{row.get('SetupType', 'Unknown')} · {row.get('Direction', 'n/a')}</div>
                    <p style='margin-top:0.7rem;'>
                        Momentum <strong>{row.get('MomentumScore', 'n/a')}</strong><br/>
                        Vol Ratio <strong>{row.get('VolumeRatio', 'n/a')}</strong><br/>
                        Close <strong>{row.get('ClosePrice', 'n/a')}</strong>
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.link_button("Open in TradingView", tradingview_url(str(row.get("Ticker", ""))), use_container_width=True)

with watchlist_tab:
    st.subheader("Watchlist Builder")
    try:
        queue = get_execution_queue(selected_run_date)
    except Exception:
        queue = pd.DataFrame()

    queue_tickers = queue["Ticker"].dropna().astype(str).str.strip().tolist() if not queue.empty and "Ticker" in queue.columns else []
    screener_tickers = filtered["Ticker"].dropna().astype(str).str.strip().tolist() if not filtered.empty and "Ticker" in filtered.columns else []
    manual_tickers = [value.strip().upper() for value in manual_watchlist.split(",") if value.strip()]
    watchlist = list(dict.fromkeys(queue_tickers + screener_tickers[:10] + manual_tickers))

    if not watchlist:
        st.info("No watchlist tickers are available yet.")
    else:
        chosen_symbol = st.selectbox("Ticker drilldown", watchlist, index=0)
        st.link_button("Open Selected Ticker in TradingView", tradingview_url(chosen_symbol), use_container_width=False)

        try:
            quotes = get_realtime_quotes([chosen_symbol])
            if not quotes.empty:
                quote_row = quotes.iloc[0].to_dict()
                st.metric("Live price", quote_row.get("close") or quote_row.get("price") or quote_row.get("last") or "n/a")
        except Exception as error:
            render_error(error)

        try:
            daily = get_daily_history(chosen_symbol, days=history_days)
            normalized = {column.lower(): column for column in daily.columns}
            rename_map = {
                normalized.get("date", "date"): "date",
                normalized.get("open", "open"): "open",
                normalized.get("high", "high"): "high",
                normalized.get("low", "low"): "low",
                normalized.get("close", "close"): "close",
                normalized.get("volume", "volume"): "volume",
            }
            daily = daily.rename(columns=rename_map)
            required = {"date", "open", "high", "low", "close"}
            if not daily.empty and required.issubset(daily.columns):
                st.subheader(f"{chosen_symbol} Daily OHLCV")
                st.plotly_chart(build_ohlcv_chart(daily, chosen_symbol), use_container_width=True)
        except Exception as error:
            render_error(error)

        if not queue.empty and "Ticker" in queue.columns:
            st.subheader("Queue Watchlist")
            st.data_editor(
                add_tradingview_column(queue),
                use_container_width=True,
                hide_index=True,
                height=280,
                disabled=True,
                column_config={"TradingView": st.column_config.LinkColumn("TradingView", display_text="Open")},
            )
