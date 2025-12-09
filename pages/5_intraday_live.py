import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
from datetime import datetime, timedelta
from data_source import get_data

# ------------------------------
# Page Config
# ------------------------------
st.set_page_config(page_title="Intraday Live Monitor", page_icon="⏱️", layout="wide")
st.title("⏱️ Intraday Live Monitor (ASX – 15-Minute Updates)")
st.caption("Real-time view powered by simulated intraday data. Will sync with EODHD when API credentials are active.")

# ------------------------------
# Refresh Control
# ------------------------------
refresh_rate = 15  # seconds (for demo, real 15m API refresh later)
st.sidebar.subheader("⚙️ Refresh Settings")
auto_refresh = st.sidebar.checkbox("Auto-refresh", value=True)
refresh_interval = st.sidebar.slider("Refresh every (sec)", 10, 300, refresh_rate, 5)

placeholder = st.empty()

# ------------------------------
# Simulated Intraday Data Generator
# ------------------------------
def generate_intraday_data(symbol="ASX:MMG", intervals=26):
    now = datetime.now().replace(second=0, microsecond=0)
    times = [now - timedelta(minutes=15 * i) for i in range(intervals)][::-1]

    base_price = 150 + np.random.randn() * 2
    close = base_price + np.cumsum(np.random.randn(intervals)) * 0.3
    open_ = close - np.random.uniform(-0.3, 0.3, size=intervals)
    high = np.maximum(open_, close) + np.random.rand(intervals)
    low = np.minimum(open_, close) - np.random.rand(intervals)
    volume = np.random.randint(1000, 5000, size=intervals)

    df = pd.DataFrame({
        "Datetime": times,
        "Open": open_,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
        "Symbol": symbol
    })
    df["EMA5"] = df["Close"].ewm(span=5).mean()
    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["RSI"] = np.random.uniform(30, 70, len(df))

    # Generate a basic signal system (simulated)
    df["Signal"] = np.where(df["EMA5"] > df["EMA20"], "Buy", "Sell")
    df["Confidence"] = np.where(df["Signal"] == "Buy",
                                np.random.uniform(0.75, 0.95, len(df)),
                                np.random.uniform(0.6, 0.85, len(df)))
    return df


# ------------------------------
# Render Dashboard
# ------------------------------
def render_dashboard():
    df = generate_intraday_data()

    latest = df.iloc[-1]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Symbol", latest["Symbol"])
    col2.metric("Last Close", f"${latest['Close']:.2f}")
    col3.metric("RSI", f"{latest['RSI']:.1f}")
    col4.metric("Signal", latest["Signal"])

    # Candlestick + EMA overlay
    st.markdown("### 📊 Intraday Price Chart (Candles + EMA5 + EMA20)")
    fig = go.Figure(data=[go.Candlestick(
        x=df["Datetime"],
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name="Price"
    )])
    fig.add_trace(go.Scatter(
        x=df["Datetime"], y=df["EMA5"],
        mode="lines", name="EMA5", line=dict(color="blue", width=1.5)
    ))
    fig.add_trace(go.Scatter(
        x=df["Datetime"], y=df["EMA20"],
        mode="lines", name="EMA20", line=dict(color="orange", width=1.5)
    ))
    fig.update_layout(
        xaxis_rangeslider_visible=False,
        template="plotly_white",
        height=500
    )
    st.plotly_chart(fig, use_container_width=True)

    # Volume chart
    st.markdown("### 📦 Volume Over Time")
    vol_fig = go.Figure(data=[go.Bar(x=df["Datetime"], y=df["Volume"], name="Volume")])
    vol_fig.update_layout(template="plotly_white", height=300)
    st.plotly_chart(vol_fig, use_container_width=True)

    # Signal summary
    st.markdown("### ⚡ Latest Signals")
    st.dataframe(df[["Datetime", "Signal", "Confidence", "EMA5", "EMA20", "RSI"]].tail(10),
                 use_container_width=True)

    # Countdown to next refresh
    st.caption(f"🕒 Last updated: {datetime.now().strftime('%H:%M:%S')} | Next refresh in {refresh_interval}s")

# ------------------------------
# Auto-Refresh Logic
# ------------------------------
if auto_refresh:
    while True:
        with placeholder.container():
            render_dashboard()
        time.sleep(refresh_interval)
else:
    render_dashboard()
