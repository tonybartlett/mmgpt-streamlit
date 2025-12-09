import plotly.graph_objects as go

st.markdown("### 📈 Stock Price (Candlestick + EMA20)")
fig = go.Figure(data=[go.Candlestick(
    x=df["Date"],
    open=df["Open"],
    high=df["High"],
    low=df["Low"],
    close=df["Close"],
    name="Price"
)])
fig.add_trace(go.Scatter(x=df["Date"], y=df["EMA20"], mode="lines", name="EMA20", line=dict(color="orange", width=2)))
st.plotly_chart(fig, use_container_width=True)
