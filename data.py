# data.py
import pandas as pd
import streamlit as st

REQUIRED_COLS = {"Date", "Amount", "Payment mode", "type"}

@st.cache_data(show_spinner=False)
def load_csv(uploaded) -> pd.DataFrame:
    df = pd.read_csv(uploaded)
    if "Amount" in df.columns:
        df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0).round(2)
    return df

def validate_dataframe(df: pd.DataFrame):
    missing = REQUIRED_COLS.difference(df.columns)
    return (len(missing) == 0, missing)

@st.cache_data(show_spinner=False)
def compute_monthly_for_trends(df: pd.DataFrame) -> pd.DataFrame:
    tmp = df.copy()
    tmp = tmp.loc[tmp["type"].str.lower().eq("expense")].copy()
    tmp["YYYY-MM"] = tmp["Date"].dt.to_period("M").astype(str)
    tmp = tmp.loc[tmp["Card"].notna()].copy()
    g = (
        tmp.groupby(["YYYY-MM", "Card"])["Amount"]
        .sum()
        .unstack(fill_value=0.0)
        .sort_index()
    )
    return g.round(2)
