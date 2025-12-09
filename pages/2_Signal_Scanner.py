import streamlit as st
from data_source import get_data
import plotly.express as px

st.title("🔍 Signal Scanner")

# Load signal data
df = get_data("Signals")

st.subheader("All Signals")
st.dataframe(df, use_container_width=True)

# High-Confidence Signals
st.markdown("### ⚡ High-Confidence Signals")
high_conf = df[df["Confidence"] > 0.85]

if not high_conf.empty:
    st.success(f"{len(high_conf)} high-confidence signals found")
    st.table(high_conf)
else:
    st.info("No signals above confidence threshold.")

# Visualization
fig = px.bar(df, x="Type", y="Confidence", color="Type", title="Signal Confidence Levels")
st.plotly_chart(fig, use_container_width=True)
