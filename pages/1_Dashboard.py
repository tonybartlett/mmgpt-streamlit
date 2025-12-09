import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from data_source import get_data

st.title("📊 MMGPT Market Dashboard")

# Load data
df = get_data("Supervisor_Dashboard_History")

# Validate data
if df.empty:
    st.error("No data available to display.")
    st.stop()

# Sidebar filters
st.sidebar.header("Filters")
symbols = df["Symbol"].unique() if "Symbol" in df.columns else ["ASX:MMG"]
selected_symbol = st.sidebar.selectbox("Select Symbol", symbols)
filtered = df[df["Symbol"] == selected_symbol]

# KPIs
col1, col2, col3 = st.columns(3)
col1.metric("Latest Close", f"${filtered['Close'].iloc[-1]:.2f}")
col2.metric("RSI", f"{filtered['RSI'].iloc[-1]:.2f}")
col3.metric("EMA20", f"${filtered['EMA20'].iloc[-1]:.2f}")

# Candlestick Chart
st.markdown("### 📈 Stock Price (Candlestick + EMA20)")
fig = go.Figure(data=[go.Candlestick(
    x=filtered["Date"],
    open=filtered["Open"],
    high=filtered["High"],
    low=filtered["Low"],
    close=filtered["Close"],
    name="Price",
)])
fig.add_trace(go.Scatter(
    x=filtered["Date"], y=filtered["EMA20"], 
    mode="lines", name="EMA20", line=dict(color="orange", width=2)
))
fig.update_layout(
    xaxis_title="Date", 
    yaxis_title="Price", 
    template="plotly_white",
    height=500
)
st.plotly_chart(fig, use_container_width=True)

# RSI Chart
st.markdown("### 🔍 RSI Trend")
rsi_fig = px.line(filtered, x="Date", y="RSI", title="Relative Strength Index (RSI)")
rsi_fig.add_hline(y=70, line_dash="dot", line_color="red")
rsi_fig.add_hline(y=30, line_dash="dot", line_color="green")
st.plotly_chart(rsi_fig, use_container_width=True)

# Raw data toggle
if st.checkbox("Show raw data"):
    st.dataframe(filtered)
