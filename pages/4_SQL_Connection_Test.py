import streamlit as st
import pandas as pd

st.title("🧩 SQL Connection Test")

st.markdown("Reading database connection details from Streamlit Cloud secrets")

# ✅ Access connection dictionary directly from secrets
secrets = st.secrets["mmgpt_db"]

# Display masked details for verification
st.json({
    "dialect": secrets["dialect"],
    "host": secrets["host"],
    "database": secrets["database"],
    "username": secrets["username"]
})

st.info("✅ Connection details successfully read (password hidden).")

st.markdown("---")
st.markdown("**Next step:** We'll connect to the live database and query `Supervisor_Dashboard_History`.")
