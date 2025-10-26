# app.py
# ASR Finance Dashboard — Customizable (local JSON persistence)
# - CSV reader with Card Mapping UI
# - CRUD for Debts & Regular Expenses (+ Paid toggles)
# - Decimal-safe formatting (2 dp everywhere)

import streamlit as st
import pandas as pd
from datetime import date

from config import DEC_FMT_MONEY
from data import (
    load_card_aliases, save_card_aliases,
    load_debts, save_debts,
    load_regulars, save_regulars,
    load_paid_flags, save_paid_flags,
)
from ui_sections import (
    csv_and_mapping_section,
    diagnostics_section,
    debts_crud_section,
    regulars_crud_section,
)

st.set_page_config(page_title="ASR Finance — Customizable", layout="wide")
st.title("📊 ASR Finance Dashboard — Customizable")

# ---------------- Sidebar controls ----------------
st.sidebar.header("⚙️ Controls")
ref_date = st.sidebar.date_input("Reference month (any date in month)", value=date.today())
start_balance = st.sidebar.number_input(
    "Starting Balance (₹)", min_value=0.0, value=0.0, step=1000.0, format="%.2f"
)
extra_cash = st.sidebar.number_input(
    "Extra Cash (₹)", min_value=0.0, value=0.0, step=1000.0, format="%.2f"
)
st.sidebar.caption("These are general inputs for your own planning; they don't affect stored data.")

# ---------------- Load persisted data ----------------
card_aliases = load_card_aliases()
debts = load_debts()
regulars = load_regulars()
paid_flags = load_paid_flags()

# ---------------- CSV + Card Mapping ----------------
st.markdown("## 🧾 CSV Upload & Card Mapping")
df = csv_and_mapping_section(card_aliases)
if df is not None and not df.empty:
    st.success(f"Transactions loaded: {len(df):,}")
    with st.expander("Preview normalized transactions (first 200 rows)", expanded=False):
        st.dataframe(df.head(200), use_container_width=True, hide_index=True)

# ---------------- Detector diagnostics ----------------
st.markdown("---")
st.markdown("## 🔍 Detector diagnostics (Card mapping)")
diagnostics_section(df, card_aliases)

# Quick inputs directly under diagnostics
st.markdown("#### Quick Inputs")
c1, c2 = st.columns(2)
with c1:
    sb = st.number_input(
        "Start balance (₹)", min_value=0.0, value=start_balance, step=1000.0, format="%.2f",
        key="q_start_balance"
    )
with c2:
    ec = st.number_input(
        "Extra cash (₹)", min_value=0.0, value=extra_cash, step=1000.0, format="%.2f",
        key="q_extra_cash"
    )
st.caption(f"Net buffer this month: **₹{sb + ec:,.2f}**")

# ---------------- Debts CRUD ----------------
st.markdown("---")
st.markdown("## 🏦 Long-Term Debt & EMI — Manage")
debts_updated = debts_crud_section(debts)
if debts_updated is not None:
    save_debts(debts_updated)
    st.success("Debts saved.")

# ---------------- Regulars CRUD (+ Paid toggles) ----------------
st.markdown("---")
st.markdown("## 🗓 Regular Expenses (incl. SIPs & Rent) — Manage")
regs_updated, paid_flags_updated = regulars_crud_section(regulars, paid_flags, ref_date)
if regs_updated is not None:
    save_regulars(regs_updated)
    st.success("Regular expenses saved.")
if paid_flags_updated is not None:
    save_paid_flags(paid_flags_updated)
    st.success("Paid flags saved.")

st.markdown("---")
st.caption("All data are stored locally in `data/*.json`. You can edit JSON directly if needed.")
