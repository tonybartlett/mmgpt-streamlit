import streamlit as st
from data_source import get_data
import plotly.express as px

st.title("📝 Kaizen Log")

# Load data
df = get_data("Kaizen_Log")

st.subheader("Recent Improvements")
st.dataframe(df, use_container_width=True)

# Top improvement
top_improvement = df.loc[df["ImpactScore"].idxmax()]
st.success(f"🏆 Top improvement: **{top_improvement['Improvement']}** (Impact Score: {top_improvement['ImpactScore']})")

# Visualization
fig = px.bar(df, x="Date", y="ImpactScore", color="Owner", title="Improvement Impact Over Time")
st.plotly_chart(fig, use_container_width=True)
