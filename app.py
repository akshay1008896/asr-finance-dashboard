# app.py
import json
from datetime import date
import streamlit as st
import pandas as pd

from config import DEFAULT_BILL_CYCLES, DEBTS, REGULARS
from data import load_csv, validate_dataframe, compute_monthly_for_trends
from helpers import normalize_columns, detect_card, get_active_cycles
from ui_sections import (
    diagnostics_section,
    start_balance_override_section,
    debt_summary_section,
    per_card_dates_editor_section,
    bills_tabs_section,
    quick_due_selector_section,
    regulars_section,
    cashflow_section,
    expenses_by_card_section,
    merchants_section,
    trends_section,
    plan_section,
)

st.set_page_config(page_title="ASR Finance Dashboard", layout="wide")
st.title("📊 ASR Finance Dashboard — Bills, SIPs, & Cash Flow")

with st.expander("How to use (read this first)", expanded=False):
    st.markdown("""
1) Upload CSV (we auto-normalize headers: `Date`, `Amount`, `Payment mode`, `type`).
2) Pick a sidebar **Reference month**; the **Bills** section also has its own month selector.
3) In **Per-card custom dates**, override Cycle Start/End/Due for a given month (JSON import/export).
4) Add **Salary** and dated **Extra inflows**; simulator credits inflows before outflows on the same date.
5) **Diagnostics** lets you auto-map new cards and define their cycles.
""")

# ---------------- Sidebar controls ----------------
st.sidebar.header("⚙️ Settings")
today = st.sidebar.date_input("Reference month (any date in the month)", value=date.today())
start_balance_sb = st.sidebar.number_input(
    "Starting balance for month (₹)", min_value=0.0, step=0.01, value=0.00, format="%.2f"
)
extra_buffer_sb  = st.sidebar.number_input(
    "Extra buffer (₹)", min_value=0.0, step=0.01, value=50000.00, format="%.2f"
)

st.sidebar.markdown("---")
st.sidebar.header("💼 Income")
salary_amount = st.sidebar.number_input(
    "Monthly Salary (₹)", min_value=0.0, step=0.01, value=0.00, format="%.2f"
)
salary_payday = st.sidebar.number_input("Salary Payday (1–31)", min_value=1, max_value=31, value=1)

# Persist extra inflows in session
if "extra_inflows" not in st.session_state:
    st.session_state.extra_inflows = [{"Date": date.today(), "Source": "Bonus/Other", "Amount": 0.00}]

with st.sidebar.expander("➕ Extra inflows (dated)", expanded=False):
    df_extra = pd.DataFrame(st.session_state.extra_inflows)
    if "Date" in df_extra:
        df_extra["Date"] = pd.to_datetime(df_extra["Date"], errors="coerce").dt.date
    edited = st.data_editor(
        df_extra,
        num_rows="dynamic",
        use_container_width=True,
    )
    st.session_state.extra_inflows = [
        {
            "Date": (r["Date"] if isinstance(r["Date"], date) else (pd.to_datetime(r["Date"]).date() if pd.notna(r["Date"]) else None)),
            "Source": str(r.get("Source", "") or ""),
            "Amount": round(float(r.get("Amount", 0) or 0), 2),
        }
        for _, r in edited.iterrows()
        if r.get("Date") is not None
    ]

# ---------------- Upload ----------------
uploaded = st.file_uploader("Upload your transactions CSV", type=["csv"])
if not uploaded:
    st.info("Upload your transactions CSV to begin.")
    st.stop()

# ---------------- Load & normalize ----------------
df_raw = load_csv(uploaded)                 # rounds Amount to 2 decimals
df_raw = normalize_columns(df_raw)          # fixes header variants (Payment mode, etc.)

# Validate required columns after normalization
ok, missing_cols = validate_dataframe(df_raw)
if not ok:
    st.error(f"CSV missing required columns (after normalization): {missing_cols}")
    st.stop()

# Derived DF
df = df_raw.copy()
df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
df = df[df["Date"].notna()].copy()
df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0).round(2)
df["type"] = df["type"].fillna("").astype(str)

# Session state holders
for key, default in [
    ("auto_overrides", {}),
    ("new_card_cycles", {}),
    ("cycle_overrides", {}),
    ("card_date_overrides", {}),
    ("paid_flags", {}),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# Manual JSON overrides (sidebar)
st.sidebar.markdown("---")
st.sidebar.header("🔧 Card Detection Overrides (JSON)")
ov_json = st.sidebar.text_area("e.g. {\"3. May Amex\": \"Amex\"}", value="{}")
try:
    user_overrides = json.loads(ov_json or "{}")
    if not isinstance(user_overrides, dict):
        user_overrides = {}
except Exception:
    user_overrides = {}
    st.sidebar.warning("Invalid JSON; overrides ignored.")

# Card detection
df["Card"] = df["Payment mode"].apply(lambda x: detect_card(x, user_overrides))

# Active BILL_CYCLES (merge defaults + newly added cards)
BILL_CYCLES = get_active_cycles(DEFAULT_BILL_CYCLES)

# ---------------- UI sections ----------------
diagnostics_section(df, BILL_CYCLES)

start_balance_effective, extra_buffer_effective = start_balance_override_section(
    start_balance_sb, extra_buffer_sb
)

debt_summary_section(DEBTS)

# Bills — month local to this section
bills_anchor, by_y, by_m = per_card_dates_editor_section(BILL_CYCLES, today)

# Two-tab bills
card_gen_df, card_due_df = bills_tabs_section(df, BILL_CYCLES, bills_anchor, by_y, by_m)

# Quick selector based on bills anchor
quick_due_selector_section(df, BILL_CYCLES, bills_anchor)

# Regular expenses (+ paid toggles) for sidebar month
cash_out_df = regulars_section(today, DEBTS, REGULARS)

# Cash flow simulator (uses income, overrides)
cashflow_section(
    df=df,
    BILL_CYCLES=BILL_CYCLES,
    today=today,
    salary_amount=salary_amount,
    salary_payday=salary_payday,
    cash_out_df=cash_out_df,
    start_balance=start_balance_effective,
    extra_buffer=extra_buffer_effective,
)

# Expenses by card (generating in sidebar month)
expenses_by_card_section(df, BILL_CYCLES, today)

# Top merchants
merchants_section(df, BILL_CYCLES, today)

# Trends
monthly = compute_monthly_for_trends(df)  # already rounded to 2 decimals
trends_section(monthly, BILL_CYCLES, today)

# 1-year plan
plan_section(DEBTS, REGULARS)
