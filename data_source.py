import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import pyodbc


def get_data(table_name="Supervisor_Dashboard_History"):
    """
    Unified data loader — tries SQL first, then falls back to demo mode.
    Works with both Streamlit Cloud secrets and local .streamlit/secrets.toml.
    """

    try:
        secrets = st.secrets["mmgpt_db"]
        host = secrets.get("host", "")
        database = secrets.get("database", "")
        driver = secrets.get("driver", "ODBC Driver 17 for SQL Server")
        trusted = secrets.get("trusted_connection", "yes")

        conn_str = f"mssql+pyodbc://@{host}/{database}?driver={driver};trusted_connection={trusted}"
        engine = create_engine(conn_str)

        query = f"SELECT TOP 100 * FROM {table_name}"
        df = pd.read_sql(query, engine)
        st.info(f"✅ Live data loaded from `{table_name}`")
        return df

    except Exception as e:
        st.warning(f"⚠️ Using demo data (reason: {e})")

        # Demo datasets for offline or development mode
        if table_name == "Supervisor_Dashboard_History":
            data = {
                "Supervisor": ["Alice", "Bob", "Charlie", "Diana"],
                "Shift": ["Day", "Night", "Day", "Night"],
                "Output": [1043, 988, 1120, 970],
                "ErrorRate": [0.2, 0.5, 0.1, 0.3],
                "Uptime": [99.5, 98.8, 99.9, 98.5],
                "Timestamp": pd.date_range("2025-12-09", periods=4, freq="H")
            }

        elif table_name == "Signals":
            data = {
                "SignalID": [1, 2, 3],
                "Type": ["Momentum", "Volatility", "Volume Spike"],
                "Confidence": [0.91, 0.85, 0.78],
                "TriggeredAt": pd.date_range("2025-12-09", periods=3, freq="2H")
            }

        elif table_name == "Kaizen_Log":
            data = {
                "Date": pd.date_range("2025-12-01", periods=3, freq="D"),
                "Improvement": ["Reduced downtime", "Improved QC", "Added alerts"],
                "ImpactScore": [8, 7, 9],
                "Owner": ["Tony", "Mia", "Raj"]
            }

        else:
            data = {"Note": ["No demo data available for this table."]}

        df = pd.DataFrame(data)
        st.success(f"✅ Demo data for `{table_name}` loaded successfully.")
        return df
