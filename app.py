# app.py
# ASR Finance Dashboard — Local JSON persistence, CSV-first, Per-card custom dates
# + Credit Card Paid toggles

from datetime import date
import streamlit as st
import pandas as pd

from data import (
    load_cards, save_cards,
    load_debts, save_debts,
    load_regulars, save_regulars,
    load_paid_flags, save_paid_flags,
    load_card_aliases, save_card_aliases,
    load_overrides, save_overrides,
)
from ui_sections import (
    csv_and_mapping_section,
    diagnostics_section,
    cards_crud_section,
    overrides_crud_section,
    bills_section,
    debts_crud_section,
    regulars_crud_section,
    trends_section,
)

st.set_page_config(page_title="ASR Finance — Local", layout="wide")
st.title("📊 ASR Finance Dashboard — Local JSON + CSV (Per-Card Custom Dates)")

# Sidebar: global reference month & balances
st.sidebar.header("⚙️ Global Controls")
ref_date = st.sidebar.date_input("Reference month (any date in month)", value=date.today())
start_balance = st.sidebar.number_input("Starting Balance (₹)", min_value=0.0, value=0.0, step=1000.0, format="%.2f")
extra_cash = st.sidebar.number_input("Extra Cash (₹)", min_value=0.0, value=0.0, step=1000.0, format="%.2f")

# Load all local state
cards = load_cards()
debts = load_debts()
regulars = load_regulars()
paid_flags = load_paid_flags()
card_aliases = load_card_aliases()
overrides = load_overrides()

# CSV & mapping
st.markdown("## 🧾 CSV Upload & Card Mapping")
df = csv_and_mapping_section(card_aliases)
if df is not None and not df.empty:
    st.success(f"Transactions loaded: {len(df):,}")
    with st.expander("Preview normalized transactions (first 200 rows)", expanded=False):
        st.dataframe(df.head(200), use_container_width=True, hide_index=True)

st.markdown("---")
st.markdown("## 🔍 Detector diagnostics (Card mapping)")
diagnostics_section(df, card_aliases)

st.caption(f"Net buffer (this month only): **₹{(start_balance + extra_cash):,.2f}**")

# CRUD: Cards
st.markdown("---")
st.markdown("## 💳 Credit Cards — Manage Cycles")
cards_updated = cards_crud_section(cards)
if cards_updated is not None:
    save_cards(cards_updated)
    cards = cards_updated
    st.success("Cards saved.")

# CRUD: Per-card custom dates
st.markdown("---")
st.markdown("## 📅 Per-Card Custom Dates (month overrides)")
ovr_updated = overrides_crud_section(cards, overrides, ref_date)
if ovr_updated is not None:
    save_overrides(ovr_updated)
    overrides = ovr_updated
    st.success("Card overrides saved.")

# Bills (Generating vs Due) + Cashflow
st.markdown("---")
st.markdown("## 🧾 Bills (Generating vs Due) — offset-aware + Cashflow")
bills_section(df, cards, overrides, ref_date, start_balance, extra_cash)

# CRUD: Debts / EMIs
st.markdown("---")
st.markdown("## 🏦 Long-Term Debt & EMI — Manage")
debts_updated = debts_crud_section(debts)
if debts_updated is not None:
    save_debts(debts_updated)
    debts = debts_updated
    st.success("Debts saved.")

# CRUD: Regular expenses + Paid toggles + Credit Card toggles
st.markdown("---")
st.markdown("## 🗓 Regular Expenses — Manage & Mark Paid (incl. Credit Cards)")
regs_updated, paid_flags_updated = regulars_crud_section(
    regulars, paid_flags, ref_date, cards=cards, overrides=overrides, df=df
)
if regs_updated is not None:
    save_regulars(regs_updated)
    regulars = regs_updated
    st.success("Regular expenses saved.")
if paid_flags_updated is not None:
    save_paid_flags(paid_flags_updated)
    paid_flags = paid_flags_updated
    st.success("Paid flags saved.")

# Monthly Trends (from CSV)
st.markdown("---")
st.markdown("## 📈 Monthly Trends & Anomalies")
trends_section(df)

st.markdown("---")
st.caption("Data is stored locally under ./data/*.json. CSV is your primary transaction source.")
