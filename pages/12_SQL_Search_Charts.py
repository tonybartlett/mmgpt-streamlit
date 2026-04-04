from __future__ import annotations

import re

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots


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


def eodhd_config() -> tuple[str, str]:
    cfg = st.secrets.get("eodhd", {})
    token = str(cfg.get("api_token", ""))
    base_url = str(cfg.get("base_url", "https://eodhd.com/api")).rstrip("/")
    return base_url, token


def get_daily_history(symbol: str, days: int) -> pd.DataFrame:
    base_url, token = eodhd_config()
    if not token:
        raise RuntimeError("EODHD api_token is missing from Streamlit secrets.")

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


def parse_prompt(prompt: str) -> tuple[str, int]:
    symbol_match = re.search(r"\b([A-Z0-9]{1,8}\.[A-Z]{2,4})\b", prompt.upper())
    if not symbol_match:
        raise ValueError("Could not find a symbol like SVL.AU in the prompt.")
    days_match = re.search(r"(\d+)\s*days?", prompt.lower())
    days = int(days_match.group(1)) if days_match else 365
    return symbol_match.group(1).upper(), max(30, min(days, 2000))


def build_chart(frame: pd.DataFrame, symbol: str) -> go.Figure:
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


@st.cache_data(ttl=60)
def search_sql_objects(search_text: str) -> pd.DataFrame:
    return sql_df(
        """
        SELECT TOP (100)
            s.name + '.' + o.name AS ObjectName,
            o.type_desc AS ObjectType,
            create_date,
            modify_date
        FROM sys.objects o
        JOIN sys.schemas s ON s.schema_id = o.schema_id
        WHERE o.type IN ('U', 'V')
          AND (:search_text = '' OR o.name LIKE :pattern)
        ORDER BY o.modify_date DESC, ObjectName ASC;
        """,
        {"search_text": search_text, "pattern": f"%{search_text}%"},
    )


st.set_page_config(page_title="SQL Search & Charts", page_icon="🧪", layout="wide")
st.title("SQL Search & Charts")
st.caption("Text-first chart requests plus bridge-backed SQL access to tables and views.")

prompt = st.text_area(
    "Ask for a chart",
    value="Show me the chart for SVL.AU for the past 365 days (candle chart) with OHLCV",
    height=100,
)

if st.button("Run chart prompt", use_container_width=False):
    try:
        symbol, days = parse_prompt(prompt)
        history = get_daily_history(symbol, days)
        if history.empty:
            st.warning("No daily history returned for that prompt.")
        else:
            info_cols = st.columns(3)
            info_cols[0].metric("Symbol", symbol)
            info_cols[1].metric("Lookback", f"{days} days")
            info_cols[2].metric("Rows", len(history))
            st.plotly_chart(build_chart(history, symbol), use_container_width=True)
            st.dataframe(history, use_container_width=True, hide_index=True, height=260)
    except Exception as error:
        st.error(str(error))

st.divider()
left, right = st.columns([0.42, 0.58])

with left:
    st.subheader("Table search")
    search_text = st.text_input("Search tables or views", value="Candles")
    objects = search_sql_objects(search_text.strip())
    st.dataframe(objects, use_container_width=True, hide_index=True, height=380)

with right:
    st.subheader("Raw SQL query")
    query = st.text_area(
        "Readonly SQL",
        value="SELECT TOP (25) * FROM dbo.Candles_Calculations ORDER BY [Date] DESC, Ticker ASC;",
        height=120,
    )
    if st.button("Run SQL", use_container_width=False):
        try:
            result = sql_df(query)
            if result.empty:
                st.info("Query returned no rows.")
            else:
                st.dataframe(result, use_container_width=True, hide_index=True, height=380)
        except Exception as error:
            st.error(str(error))
