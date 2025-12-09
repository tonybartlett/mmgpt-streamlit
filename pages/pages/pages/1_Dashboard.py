import streamlit as st
import pandas as pd

st.title("🔎 MMGPT Signal Scanner")
st.markdown("Displays current trade setups based on daily indicators.")

data = {
    "Ticker": ["BHP.AX", "CBA.AX", "FMG.AX", "WES.AX"],
    "Momentum Score": [92, 88, 75, 81],
    "Signal": ["BUY", "BUY", "HOLD", "BUY"]
}

df = pd.DataFrame(data)
st.dataframe(df, use_container_width=True)
