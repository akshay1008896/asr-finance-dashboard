import streamlit as st
import pandas as pd
from typing import Optional
from helpers import monthly_totals

def trends_section(df: Optional[pd.DataFrame]) -> None:
    g = monthly_totals(df)
    if g is None or g.empty:
        st.info("No expense data to show trends yet.")
        return

    window = st.radio("Window", ["Last 6 months", "Last 12 months", "All Time"], horizontal=True, index=1)
    n_months = 12 if window != "Last 6 months" else 6
    if window != "All Time" and g.shape[0] > n_months:
        g = g.iloc[-n_months:, :]

    available_cards = sorted([c for c in g.columns if pd.notna(c)])
    selected_cards = st.multiselect("Choose cards to analyze", options=available_cards, default=available_cards)
    if not selected_cards:
        st.info("Select at least one card.")
        return

    st.subheader("📊 Trend Chart")
    st.line_chart(g[selected_cards].copy())

    mom = g.pct_change().replace([float("inf"), float("-inf")], pd.NA) * 100.0
    combined = g.copy()
    for c in selected_cards:
        combined[f"{c} MoM %"] = mom[c]

    fmt = {c: "₹{:,.0f}" for c in g.columns}
    fmt.update({c: "{:.1f}%" for c in combined.columns if "MoM %" in c})
    st.subheader("Monthly Totals (₹) and MoM % Change")
    st.dataframe(combined.style.format(fmt), use_container_width=True)
