import streamlit as st

st.title("📊 MMGPT Dashboard – Equity Overview")
st.markdown("This is where your live portfolio stats will appear (linked to SQL later).")

st.metric(label="Total Portfolio Value", value="$100,000", delta="+2.3% this week")
st.metric(label="Sharpe Ratio", value="1.82")
st.metric(label="Weekly Win Rate", value="72%")
