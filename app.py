import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(page_title="MMGPT Dashboard", layout="wide")

st.title("📈 MMGPT Trading Intelligence Dashboard")
st.markdown("Welcome to your first live MMGPT Streamlit app!")

st.sidebar.header("Controls")
strategy = st.sidebar.selectbox("Strategy", ["Momentum", "Mean Reversion", "Breakout"])
st.sidebar.write(f"📊 Selected Strategy: **{strategy}**")

# Generate some example data
df = pd.DataFrame({
    "Date": pd.date_range("2025-01-01", periods=100),
    "Equity": np.cumprod(1 + np.random.randn(100) / 100)
})

fig = px.line(df, x="Date", y="Equity", title="Simulated Equity Curve")
st.plotly_chart(fig, use_container_width=True)
