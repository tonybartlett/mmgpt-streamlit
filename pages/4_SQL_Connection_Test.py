import streamlit as st
from data_source import get_data

st.title("🧩 SQL Connection Test")

st.markdown("Reading database connection details from Streamlit Cloud secrets...")

# Try pulling test data
df = get_data("Supervisor_Dashboard_History")

if not df.empty:
    st.success("✅ Connection details read successfully (live or demo).")
    st.dataframe(df.head(), use_container_width=True)
else:
    st.error("⚠️ No data loaded — check connection or secrets configuration.")

