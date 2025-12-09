import streamlit as st
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
import pyodbc


def get_data(table_name="Supervisor_Dashboard_History"):
    """
    Unified data loader — tries SQL first, then falls back to realistic stock/indicator demo data.
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
        st.warning(f"⚠️ Using simulated stock data (reason: {e})")

        if table_name == "Supervisor_Dashboard_History":
            # Simulated stock data for dashboard
            dates = pd.date_range("2025-11-01", periods=30)
            np.random.seed(42)
            close = np.cumsum(np.random.randn(30)) + 150
            open_ = close - np.random.randn(30)
            high = np.maximum(open_, close) + np.random.rand(30)
            low = np.minimum(open_, close) - np.random.rand(30)
            volume = np.random.randint(1000, 5000, size=30)

            data = pd.DataFrame({
                "Date": dates,
                "Open": open_,
                "High": high,
                "Low": low,
                "Close": close,
                "Volume": volume
            })
            data["Symbol"] = "ASX:MMG"
            data["EMA20"] = data["Close"].ewm(span=20).mean()
            data["RSI"] = np.random.uniform(30, 70, size=len(data))

            return data

        elif table_name == "Signals":
            data = pd.DataFrame({
                "SignalID": [1, 2, 3, 4],
                "Symbol": ["ASX:MMG", "ASX:BHP", "ASX:RIO", "ASX:FMG"],
                "Type": ["RSI Overbought", "MACD Bullish", "Volume Spike", "EMA Cross"],
                "Confidence": [0.92, 0.88, 0.83, 0.80],
                "Direction": ["Sell", "Buy", "Buy", "Buy"],
                "TriggeredAt": pd.date_range("2025-12-09", periods=4, freq="4H")
            })
            return data

        elif table_name == "Kaizen_Log":
            data = pd.DataFrame({
                "Date": pd.date_range("2025-12-01", periods=4, freq="D"),
                "Improvement": [
                    "Improved RSI filter for false signals",
                    "Optimized MACD backtest window",
                    "Refined EMA crossover logic",
                    "Integrated volume confirmation checks"
                ],
                "ImpactScore": [8, 7, 9, 6],
                "Owner": ["Tony", "Mia", "Raj", "Sam"]
            })
            return data

        else:
            return pd.DataFrame({"Note": ["No demo data available for this table."]})
