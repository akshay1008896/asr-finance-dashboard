import streamlit as st
import pandas as pd
from datetime import date

from data import (
    load_card_aliases, save_card_aliases,
    load_cards, save_cards,
    load_debts, save_debts,
    load_regulars, save_regulars,
    load_paid_flags, save_paid_flags
)
from ui_sections import (
    csv_and_mapping_section,
    diagnostics_section,
    cards_crud_section,
    debts_crud_section,
    regulars_crud_section,
    bills_section
)

st.set_page_config(page_title="ASR Finance — Credit Cards & CRUD", layout="wide")
st.title("📊 ASR Finance Dashboard — Cards, Bills, & Cash Flow")

# Sidebar controls for reference month and cash inputs
st.sidebar.header("⚙️ Global Controls")
ref_date = st.sidebar.date_input("Reference month (any date in month)", value=date.today())
start_balance = st.sidebar.number_input("Starting Balance (₹)", min_value=0.0, value=0.0, step=1000.0, format="%.2f")
extra_cash = st.sidebar.number_input("Extra Cash (₹)", min_value=0.0, value=0.0, step=1000.0, format="%.2f")
st.sidebar.caption("These inputs are used in cash-flow calculations/notes.")

# Load persisted data from JSON
card_aliases = load_card_aliases()
cards = load_cards()
debts = load_debts()
regulars = load_regulars()
paid_flags = load_paid_flags()

# CSV upload & Card Mapping UI
st.markdown("## 🧾 CSV Upload & Card Mapping")
df = csv_and_mapping_section(card_aliases)
if df is not None and not df.empty:
    st.success(f"Transactions loaded: {len(df):,}")
    with st.expander("Preview normalized transactions (first 200 rows)", expanded=False):
        st.dataframe(df.head(200), use_container_width=True, hide_index=True)

# Card mapping diagnostics
st.markdown("---")
st.markdown("## 🔍 Detector diagnostics (Card mapping)")
diagnostics_section(df, card_aliases)

# Quick cash inputs summary
st.markdown("#### Quick Cash Inputs")
c1, c2 = st.columns(2)
with c1:
    sb = st.number_input("Start balance (₹)", min_value=0.0, value=start_balance,
                         step=1000.0, format="%.2f", key="q_start_balance")
with c2:
    ec = st.number_input("Extra cash (₹)", min_value=0.0, value=extra_cash,
                         step=1000.0, format="%.2f", key="q_extra_cash")
st.caption(f"Net buffer this month: **₹{sb + ec:,.2f}**")

# Cards CRUD section
st.markdown("---")
st.markdown("## 💳 Credit Cards — Manage Cycles")
cards_updated = cards_crud_section(cards)
if cards_updated is not None:
    save_cards(cards_updated)
    cards = cards_updated
    st.success("Cards saved.")

# Bills (Generating vs Due) section
st.markdown("---")
st.markdown("## 🧾 Bills (Generating vs Due) — offset-aware")
bills_section(df, cards, ref_date)

# Debts CRUD section
st.markdown("---")
st.markdown("## 🏦 Long-Term Debt & EMI — Manage")
debts_updated = debts_crud_section(debts)
if debts_updated is not None:
    save_debts(debts_updated)
    st.success("Debts saved.")

# Regular expenses CRUD + Paid toggles section
st.markdown("---")
st.markdown("## 🗓 Regular Expenses (incl. SIPs & Rent) — Manage & Mark Paid")
regs_updated, paid_flags_updated = regulars_crud_section(regulars, paid_flags, ref_date)
if regs_updated is not None:
    save_regulars(regs_updated)
    st.success("Regular expenses saved.")
if paid_flags_updated is not None:
    save_paid_flags(paid_flags_updated)
    st.success("Paid flags saved.")

st.markdown("---")
st.caption("All data persist in `data/*.json`. You can edit JSON directly if needed.")
