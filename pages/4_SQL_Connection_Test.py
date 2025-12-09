import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

st.title("🧩 SQL Connection Test")

st.markdown("Connecting to **MMGPTVM\\\\ASXSQLDATA** (Windows-auth) and querying `Supervisor_Dashboard_History`")

# Load connection secrets
secrets = st.secrets["mmgpt_db"]

# Build connection string (Windows Authentication)
connection_string = (
    f"mssql+pyodbc://@{secrets['host']}/{secrets['database'].replace(' ', '%20')}"
    "?driver=ODBC+Driver+17+for+SQL+Server"
    "&trusted_connection=yes"
)

try:
    engine = create_engine(connection_string)
    with engine.connect() as conn:
        st.success("✅ Connected to MMGPT SQL Server (Windows Authentication)")
        df = pd.read_sql("SELECT TOP 10 * FROM Supervisor_Dashboard_History", conn)
        st.dataframe(df)
except Exception as e:
    st.error(f"❌ Connection failed: {e}")
