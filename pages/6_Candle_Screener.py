import streamlit as st
import pandas as pd
from datetime import date
from data_source import run_stored_proc

# ============================================================
# Candle Screener Dashboard
# ============================================================

st.set_page_config(page_title="Candle Screener", layout="wide")

st.title("🕯️ Candle Screener – SQL Strategy Dashboard")
st.caption("Runs dbo.sp_Screener_Candles_Strategy_Run from the MMGPT SQL database and displays strategy results.")

# ------------------------------------------------------------
# User Input: Select Run Date
# ------------------------------------------------------------
st.sidebar.header("📅 Run Parameters")
selected_date = st.sidebar.date_input("Select Run Date", date.today())

st.sidebar.info("The screener will execute your SQL stored procedure using the chosen date.")

# ------------------------------------------------------------
# Run Stored Procedure
# ------------------------------------------------------------
if st.sidebar.button("▶️ Run Screener"):
    st.info(f"Running Candle Screener for {selected_date} ... please wait ⏳")

    try:
        df = run_stored_proc("dbo.sp_Screener_Candles_Strategy_Run", {"RunDate": selected_date})
        if df is not None and not df.empty:
            st.success(f"✅ Screener completed successfully for {selected_date}.")
            
            # Basic Summary
            st.subheader("📊 Summary Statistics")
            st.write(f"Rows Returned: {len(df):,}")
            st.write("Columns:", list(df.columns))
            
            # Display Results
            st.subheader("📈 Screener Results")
            st.dataframe(df)

            # Optional: Chart if columns exist
            candle_cols = ["BullishEngulfing", "BearishEngulfing", "Hammer", "Doji"]
            available = [c for c in candle_cols if c in df.columns]
            if available:
                st.bar_chart(df[available].sum())
        else:
            st.warning("⚠️ Stored procedure returned no data.")
    except Exception as e:
        st.error(f"❌ Error executing stored procedure: {e}")
else:
    st.info("Select a date and click **Run Screener** to begin.")

# ------------------------------------------------------------
# Notes
# ------------------------------------------------------------
st.markdown("""
---
### ℹ️ Notes
- This dashboard directly connects to your SQL database.
- Procedure: `dbo.sp_Screener_Candles_Strategy_Run`
- Parameter: `@RunDate (date)`
- Results are displayed in a live interactive table.
""")
