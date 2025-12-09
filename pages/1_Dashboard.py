import streamlit as st
import plotly.express as px
from data_source import get_data

st.title("📊 MMGPT Dashboard")

# Load data
df = get_data("Supervisor_Dashboard_History")

# Filters
st.sidebar.header("Filters")
supervisors = st.sidebar.multiselect("Select Supervisors:", df["Supervisor"].unique(), default=df["Supervisor"].unique())
filtered = df[df["Supervisor"].isin(supervisors)]

# KPI Metrics
col1, col2, col3 = st.columns(3)
col1.metric("Avg Uptime (%)", f"{filtered['Uptime'].mean():.2f}")
col2.metric("Avg Error Rate (%)", f"{filtered['ErrorRate'].mean():.2f}")
col3.metric("Total Output", f"{filtered['Output'].sum():,.0f}")

# Line Chart
st.markdown("### 📈 Output Over Time")
fig = px.line(filtered, x="Timestamp", y="Output", color="Supervisor", markers=True)
st.plotly_chart(fig, use_container_width=True)

# Table view toggle
if st.checkbox("Show raw data"):
    st.dataframe(filtered)
