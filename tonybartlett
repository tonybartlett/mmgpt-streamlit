import streamlit as st
import plotly.express as px
from data_source import get_data
import pandas as pd
from datetime import datetime

# ----------------------------
# App Configuration
# ----------------------------
st.set_page_config(
    page_title="MMGPT Trading Intelligence Dashboard",
    page_icon="📊",
    layout="wide"
)

# ----------------------------
# Header
# ----------------------------
st.title("📊 MMGPT Trading Intelligence Dashboard")
st.caption("Welcome to your unified view of live market signals, analytics, and continuous improvements.")

st.divider()

# ----------------------------
# Section 1: Market Summary
# ----------------------------
st.subheader("📈 Market Summary")

market_data = get_data("Supervisor_Dashboard_History")

if not market_data.empty:
    latest = market_data.iloc[-1]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Symbol", latest.get("Symbol", "ASX:MMG"))
    col2.metric("Latest Close", f"${latest['Close']:.2f}")
    col3.metric("RSI", f"{latest['RSI']:.1f}")
    col4.metric("EMA20", f"${latest['EMA20']:.2f}")

    # Mini performance chart
    price_fig = px.line(market_data, x="Date", y="Close", title="Recent Price Trend")
    price_fig.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(price_fig, use_container_width=True)
else:
    st.warning("⚠️ No market data available.")

st.divider()

# ----------------------------
# Section 2: Active Signals
# ----------------------------
st.subheader("🔍 Active Signals")

signals = get_data("Signals")

if not signals.empty:
    st.write(f"Total signals detected: **{len(signals)}**")

    high_conf = signals[signals["Confidence"] > 0.85]
    if not high_conf.empty:
        st.success(f"{len(high_conf)} high-confidence signals found.")
        st.dataframe(high_conf[["Symbol", "Type", "Confidence", "Direction", "TriggeredAt"]],
                     use_container_width=True)
    else:
        st.info("No high-confidence signals currently.")

    # Visualization
    fig = px.bar(
        signals,
        x="Symbol",
        y="Confidence",
        color="Direction",
        text="Type",
        title="Signal Confidence by Symbol"
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("⚠️ No signal data available.")

st.divider()

# ----------------------------
# Section 3: Kaizen Improvements
# ----------------------------
st.subheader("🧠 Kaizen Log (Continuous Improvements)")

kaizen = get_data("Kaizen_Log")

if not kaizen.empty:
    st.dataframe(kaizen, use_container_width=True)
else:
    st.info("No Kaizen log entries found.")

st.divider()

# ----------------------------
# Section 4: Quick Navigation
# ----------------------------
st.subheader("⚙️ Quick Navigation")

st.markdown("""
- 🏠 **[Dashboard](Dashboard)** — View live stock trends, EMA & RSI performance.
- 🔍 **[Signal Scanner](Signal_Scanner)** — Monitor trading signals and confidence.
- 🧾 **[Kaizen Log](Kaizen_Log)** — Track trading system and model improvements.
- 🧩 **[SQL Connection Test](SQL_Connection_Test)** — Validate database link and connection details.
""")

st.divider()

# ----------------------------
# Footer
# ----------------------------
st.markdown(f"📅 _Last updated: {datetime.now().strftime('%d %b %Y %H:%M:%S')}_  |  © 2025 MMGPT Analytics")
