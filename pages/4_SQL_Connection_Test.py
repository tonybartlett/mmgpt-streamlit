import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import pyodbc

st.title("🧩 SQL Connection Test")

# Attempt to read secrets (live mode)
try:
    secrets = st.secrets["mmgpt_db"]
    host = secrets.get("host", "")
    database = secrets.get("database", "")
    dialect = secrets.get("dialect", "mssql")
    username = secrets.get("username", "")
    password = secrets.get("password", "")
    driver = secrets.get("driver", "ODBC Driver 17 for SQL Server")

    st.markdown(f"Connecting to **{host}** (Windows-auth) and querying `Supervisor_Dashboard_History`...")

    # Build the connection string
    connection_string = f"mssql+pyodbc://{host}/{database}?driver={driver};trusted_connection=yes"
    engine = create_engine(connection_string)

    # Test query
    df = pd.read_sql("SELECT TOP 10 * FROM Supervisor_Dashboard_History", engine)
    st.success("✅ Connection successful!")
    st.dataframe(df)

except Exception as e:
    st.error(f"⚠️ Connection failed: {e}")
    st.info("🔄 Switching to demo mode (simulated database)...")

    # DEMO DATA: placeholder for testing UI
    demo_data = {
        "Supervisor": ["Alice", "Bob", "Charlie"],
        "Metric": ["Uptime", "Error Rate", "Output"],
        "Value": [99.5, 0.2, 1043]
    }
    df = pd.DataFrame(demo_data)
    st.dataframe(df)
    st.success("✅ Demo data loaded successfully.")
