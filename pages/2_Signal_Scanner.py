import streamlit as st
import plotly.express as px
from data_source import get_data

st.title("🔍 Signal Scanner")

df = get_data("Signals")

if df.empty:
    st.error("No signal data found.")
    st.stop()

# Summary
st.markdown(f"### Showing {len(df)} signals across {df['Symbol'].nunique()} symbols")

# Filters
col1, col2 = st.columns(2)
symbol = col1.selectbox("Select Symbol", df["Symbol"].unique())
min_conf = col2.slider("Minimum Confidence", 0.0, 1.0, 0.8, 0.01)
filtered = df[(df["Symbol"] == symbol) & (df["Confidence"] >= min_conf)]

# Display filtered signals
st.subheader("Filtered Signals")
st.dataframe(filtered, use_container_width=True)

# Summary visualization
st.markdown("### Signal Confidence Overview")
fig = px.bar(
    df,
    x="Symbol",
    y="Confidence",
    color="Direction",
    barmode="group",
    text="Type",
    title="Signal Confidence by Symbol"
)
fig.update_traces(textposition="outside")
st.plotly_chart(fig, use_container_width=True)

# Highlight high-confidence signals
high_conf = df[df["Confidence"] > 0.85]
if not high_conf.empty:
    st.success(f"{len(high_conf)} high-confidence signals detected.")
    st.table(high_conf[["Symbol", "Type", "Confidence", "Direction"]])
else:
    st.info("No high-confidence signals at this time.")
