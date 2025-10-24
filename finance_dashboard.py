# app.py
# ASR Finance Dashboard — consolidated, corrected, and fortified
# ICICI updated: bill gen 21st, due 8th next month (offset=1)
# Bills section: inline month selector (Prev / Current / Next / Custom)
# NEW: Per-card, per-month custom dates (Cycle Start, Cycle End, Due Date) with JSON import/export + session persistence
# Priority: Per-month custom dates > Custom day-based cycles > Default cycles

import io
import re
import json
import datetime as dt
from datetime import date
from typing import Dict, Tuple, Optional

import numpy as np
import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta

# ---------------------------
# Page & Title
# ---------------------------
st.set_page_config(page_title="ASR Finance Dashboard", layout="wide")
st.title("📊 ASR Finance Dashboard — Bills, SIPs, & Cash Flow")

with st.expander("How to use (read this first)", expanded=False):
    st.markdown("""
1) **Upload your CSV** — required columns: `Date`, `Amount`, `Payment mode`, `type`. Optional: `Category`, `Note`, `Tags`.
2) Pick a **Reference month** (any date in that month) from the sidebar for page-wide defaults.
3) In **Bills (choose your perspective)** switch the month locally via **Previous / Current / Next / Custom**.
4) **Per-card custom dates**: In the Bills section, open **“🗓 Per-card custom dates for …”** and set **Cycle Start**, **Cycle End (bill gen)**, and **Due Date** for each card for that specific month. Export/Import as JSON.
5) Sections:
   - **Long-Term Debt Summary**
   - **Bills & Cash Flow** (Due-month first, offset-aware, overrides respected)
   - **Regular Expenses** (toggle Paid / persist via JSON)
   - **Expenses by Card** (cycle windows + CSV exports)
   - **Top Merchants per Card** (choose analysis window)
   - **Monthly Trends** (MoM %, anomaly highlight, budget caps)
   - **1-Year Action Plan** (Debt & Investment)
""")

# ---------------------------
# Config / Rules
# ---------------------------
# Default cycles: (cycle_start_day, cycle_end_day, due_day, due_offset_months)
DEFAULT_BILL_CYCLES: Dict[str, Tuple[int, int, int, int]] = {
    "Amex": (22, 21, 10, 1),
    "HSBC": (19, 18, 5, 1),
    "HSBC Cash": (8, 7, 27, 0),
    # ICICI: bill gen 21st, due 8th next month → start 22, end 21, due_offset=1
    "ICICI": (22, 21, 8, 1),
    "One": (19, 18, 8, 1),
    "SBI": (25, 24, 13, 1),
}

# Long-Term Debts & EMIs
DEBTS = [
    {"type": "Cred EMIs", "item": "Movers & Packers", "amount": 23567, "due_day": 25, "tenure_left": 2, "outstanding": 47134},
    {"type": "Cred EMIs", "item": "CC & ITR", "amount": 18273, "due_day": 28, "tenure_left": 13, "outstanding": 237549},
    {"type": "Cred EMIs", "item": "Extra", "amount": 17567, "due_day": 28, "tenure_left": 1, "outstanding": 17567},
    {"type": "Loans", "item": "Wedding Loan", "amount": 33400, "due_day": 18, "tenure_left": 19, "outstanding": 634600},
    {"type": "Loans", "item": "Home Loan EMI", "amount": 19000, "due_day": 20, "tenure_left": "~95", "outstanding": 1805000},
]

# Regular Monthly Expenses (excluding EMIs, but including SIPs and Rent)
REGULARS = [
    {"item": "Papa", "amount": 40000, "date_hint": "1"},
    {"item": "House Rent", "amount": 40000, "date_hint": "1"},
    {"item": "SIP – 3rd", "amount": 2000, "date_hint": "3"},
    {"item": "SIP – 9th", "amount": 10500, "date_hint": "9"},
    {"item": "SIP – 11th", "amount": 500, "date_hint": "11"},
]

# Card detection patterns
CARD_REGEX = [
    (r"\b(amex|american\s*express|plat(?:inum)?)\b", "Amex"),
    (r"\b(icici|ici)\b", "ICICI"),
    (r"\bsbi\b", "SBI"),
    (r"\b(onecard|oncecard)\b", "One"),
    (r"\b(hsbc\s*cash|hsbcl|cashback)\b", "HSBC Cash"),
    (r"\bhsbc\b", "HSBC"),
]

# ---------------------------
# Sidebar: Controls
# ---------------------------
st.sidebar.header("⚙️ Settings")
today = st.sidebar.date_input("Reference month (any date in the month)", value=date.today())
starting_balance = st.sidebar.number_input("Starting balance for month (₹)", min_value=0, value=0, step=1000)
extra_buffer = st.sidebar.number_input("Extra buffer (₹)", min_value=0, value=50000, step=500)

# --- Custom day-based cycles (fallback/general) ---
st.sidebar.markdown("---")
st.sidebar.header("🗂 Custom Card Cycles (days) — optional")
if "cycle_overrides" not in st.session_state:
    st.session_state.cycle_overrides: Dict[str, Tuple[int, int, int, int]] = {}
use_custom_cycles = st.sidebar.toggle("Use custom day-based cycles", value=bool(st.session_state.cycle_overrides))
with st.sidebar.expander("Edit per-card *days*", expanded=False):
    st.caption("Days clamp to month length automatically. Offset=0 → due same month; Offset=1 → due next month.")
    new_overrides = {}
    all_cards = sorted(set(DEFAULT_BILL_CYCLES.keys()) | set(st.session_state.cycle_overrides.keys()))
    for card in all_cards:
        dft = st.session_state.cycle_overrides.get(card, DEFAULT_BILL_CYCLES.get(card, (22, 21, 10, 1)))
        c1, c2, c3, c4 = st.columns([1,1,1,1])
        start_day = c1.number_input(f"{card} start", min_value=1, max_value=31, value=int(dft[0]), step=1, key=f"days_{card}_start")
        end_day   = c2.number_input(f"{card} end",   min_value=1, max_value=31, value=int(dft[1]), step=1, key=f"days_{card}_end")
        due_day   = c3.number_input(f"{card} due",   min_value=1, max_value=31, value=int(dft[2]), step=1, key=f"days_{card}_due")
        offset    = c4.number_input(f"{card} off",   min_value=0, max_value=2,  value=int(dft[3]), step=1, key=f"days_{card}_off")
        new_overrides[card] = (int(start_day), int(end_day), int(due_day), int(offset))

    if st.button("Save day-based cycles", use_container_width=True):
        st.session_state.cycle_overrides = new_overrides
        st.success("Custom day-based cycles saved to session.")

    cexp, cimp = st.columns(2)
    with cexp:
        st.download_button(
            "Export cycles JSON",
            data=json.dumps(st.session_state.cycle_overrides or {}, indent=2),
            file_name="card_cycles_days.json",
            mime="application/json",
            use_container_width=True
        )
    with cimp:
        up = st.file_uploader("Import cycles JSON", type=["json"], key="cycles_json_upl_days")
        if up is not None:
            try:
                data = json.load(up)
                if isinstance(data, dict):
                    clean = {}
                    for k, v in data.items():
                        if isinstance(v, (list, tuple)) and len(v) == 4:
                            clean[k] = (int(v[0]), int(v[1]), int(v[2]), int(v[3]))
                    st.session_state.cycle_overrides = clean
                    st.success("Day-based cycles imported.")
                else:
                    st.warning("Invalid JSON format. Expect {card: [start,end,due,offset]}.")
            except Exception as e:
                st.error(f"Failed to import: {e}")

# Active cycles (day-based)
if use_custom_cycles and st.session_state.cycle_overrides:
    BILL_CYCLES: Dict[str, Tuple[int, int, int, int]] = {**DEFAULT_BILL_CYCLES, **st.session_state.cycle_overrides}
else:
    BILL_CYCLES = DEFAULT_BILL_CYCLES.copy()

# --- Budget Caps for active cards ---
st.sidebar.markdown("---")
st.sidebar.subheader("💳 Budget Caps (active cards)")
budget_caps: Dict[str, int] = {}
for card in sorted(BILL_CYCLES.keys()):
    budget_caps[card] = st.sidebar.number_input(
        f"{card} cap (₹)",
        min_value=0,
        value=250000 if card == "Amex" else 0,
        step=1000,
        help="0 = no cap check",
        key=f"cap_{card}"
    )

# --- Detection overrides ---
st.sidebar.markdown("---")
st.sidebar.header("🔧 Card Detection Overrides")
overrides_json = st.sidebar.text_area(
    "Optional JSON: map Payment mode to card name (e.g., {\"3. May Amex\": \"Amex\"})",
    value="{}",
    height=120
)
try:
    CARD_OVERRIDES = json.loads(overrides_json or "{}")
    if not isinstance(CARD_OVERRIDES, dict):
        CARD_OVERRIDES = {}
        st.sidebar.warning("Overrides must be a JSON object; ignored.")
except Exception:
    CARD_OVERRIDES = {}
    st.sidebar.warning("Invalid JSON; overrides ignored.")

# --- Paid flags ---
st.sidebar.markdown("---")
st.sidebar.header("☑️ Paid Flags")
if "paid_flags" not in st.session_state:
    st.session_state.paid_flags = {}
c1, c2 = st.sidebar.columns(2)
with c1:
    st.download_button(
        "Export Paid Flags",
        data=json.dumps(st.session_state.paid_flags, indent=2),
        file_name="paid_flags.json",
        mime="application/json",
        help="Download current Paid toggles"
    )
with c2:
    if st.button("Reset Paid Flags"):
        st.session_state.paid_flags.clear()
        st.sidebar.success("Paid flags cleared.")
flags_file = st.sidebar.file_uploader("Import Paid Flags", type=["json"])
if flags_file is not None:
    try:
        st.session_state.paid_flags.update(json.load(flags_file))
        st.sidebar.success("Paid flags imported.")
    except Exception as e:
        st.sidebar.error(f"Failed to import: {e}")

# ---------------------------
# Helpers
# ---------------------------
def month_range(y: int, m: int) -> Tuple[date, date]:
    start = dt.date(y, m, 1)
    end = start + relativedelta(months=1) - dt.timedelta(days=1)
    return start, end

def safe_date(year: int, month: int, day: int) -> date:
    last_day = month_range(year, month)[1].day
    return dt.date(year, month, min(day, last_day))

def detect_card(payment_mode: str, overrides: Optional[Dict[str, str]] = None) -> Optional[str]:
    if not payment_mode:
        return None
    if overrides and payment_mode in overrides:
        return overrides[payment_mode]
    text = str(payment_mode).lower()
    for pat, name in CARD_REGEX:
        if re.search(pat, text):
            if name == "One" and "closed" in text:
                return None
            return name
    return None

# ========= NEW: Per-card, per-month date overrides =========
# st.session_state.card_date_overrides maps: "YYYY-MM::Card" -> {"start": date, "end": date, "due": date}
if "card_date_overrides" not in st.session_state:
    st.session_state.card_date_overrides: Dict[str, Dict[str, str]] = {}  # store ISO strings for serialization

def override_key(year: int, month: int, card: str) -> str:
    return f"{year:04d}-{month:02d}::{card}"

def get_overridden_cycle(card: str, year: int, month: int,
                         fallback_from_days: bool = True) -> Tuple[date, date, date, date]:
    """
    Return (cycle_start, cycle_end, bill_dt, due_dt) for the cycle that ENDS in (year,month),
    applying per-month date overrides first; if absent, compute from day-based cycles.
    """
    key = override_key(year, month, card)
    if key in st.session_state.card_date_overrides:
        rec = st.session_state.card_date_overrides[key]
        try:
            cstart = dt.date.fromisoformat(rec["start"])
            cend   = dt.date.fromisoformat(rec["end"])
            ddue   = dt.date.fromisoformat(rec["due"])
            return cstart, cend, cend, ddue
        except Exception:
            pass  # fall back below

    # fallback: compute from day-based cycles
    if fallback_from_days:
        start_day, end_day, due_day, due_offset = BILL_CYCLES[card]
        cycle_end = safe_date(year, month, end_day)
        start_date = safe_date(year, month, start_day)
        cycle_start = start_date - relativedelta(months=1) if start_day > end_day else start_date
        # due month = bill month + offset
        due_month = month + due_offset
        due_year = year + (due_month - 1) // 12
        due_month = (due_month - 1) % 12 + 1
        due_dt = safe_date(due_year, due_month, due_day)
        return cycle_start, cycle_end, cycle_end, due_dt

    # ultimate fallback to a safe window of the selected month
    start, end = month_range(year, month)
    return start, end, end, end

def find_cycle_whose_due_falls_in_month(card: str, target_year: int, target_month: int) -> Tuple[date, date, date, date]:
    """
    Find the cycle (considering overrides) whose DUE DATE falls in target (year, month).
    We search around the target month by trying cycles whose bill-generation month is nearby.
    """
    # search bill-generation anchors in a small window
    candidates = []
    for k in range(-2, 3):  # previous 2 months .. next 2 months
        anchor = dt.date(target_year, target_month, 15) + relativedelta(months=k)
        cy, cm = anchor.year, anchor.month
        cstart, cend, bill_dt, due_dt = get_overridden_cycle(card, cy, cm, fallback_from_days=True)
        candidates.append((cstart, cend, bill_dt, due_dt))

    # choose the one whose due falls in target month
    for cstart, cend, bill_dt, due_dt in candidates:
        if due_dt.year == target_year and due_dt.month == target_month:
            return cstart, cend, bill_dt, due_dt

    # if none match exactly, fallback to closest by abs days diff
    closest = min(candidates, key=lambda x: abs((x[3] - dt.date(target_year, target_month, 15)).days))
    return closest

# ---------------------------
# Inputs
# ---------------------------
uploaded = st.file_uploader("Upload your transactions CSV", type=["csv"])

# ---------------------------
# Main
# ---------------------------
if uploaded is None:
    st.info("Upload your transactions CSV to begin.")
    st.stop()

df_raw = pd.read_csv(uploaded)

# Validate required columns
required_cols = {"Date", "Amount", "Payment mode", "type"}
missing = required_cols.difference(df_raw.columns)
if missing:
    st.error(f"CSV missing required columns: {missing}")
    st.stop()

# Ensure optional columns exist
df = df_raw.copy()
for opt_col in ["Category", "Note", "Tags"]:
    if opt_col not in df.columns:
        df[opt_col] = ""

# Basic normalization
df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0)
df["type"] = df["type"].fillna("").astype(str)

# Derived
df = df[df["Date"].notna()].copy()
df["Card"] = df["Payment mode"].apply(lambda x: detect_card(x, overrides=CARD_OVERRIDES))

# --- Validation report
with st.expander("🧪 Data validation report", expanded=False):
    issues = []
    if (df["Date"] < "2000-01-01").any():
        issues.append(("Dates < 2000", int((df["Date"] < "2000-01-01").sum())))
    if df["Card"].isna().sum() > 0:
        issues.append(("Unmapped Payment mode → Card", int(df["Card"].isna().sum())))
    invalid_types = ~df["type"].str.lower().isin({"expense", "income", "payment", "credit", "refund", "transfer"})
    if invalid_types.any():
        issues.append(("Unknown `type` values", int(invalid_types.sum())))

    if len(issues) == 0:
        st.success("No major issues found.")
    else:
        rep = pd.DataFrame(issues, columns=["Issue", "Count"])
        st.dataframe(rep, use_container_width=True, hide_index=True)

# Detector diagnostics
with st.expander("🔍 Detector diagnostics (Card mapping)", expanded=False):
    st.dataframe(
        df["Card"].value_counts(dropna=False).rename_axis("Card").reset_index(name="count"),
        use_container_width=True
    )

# ---------------------------
# Debt summary
# ---------------------------
st.subheader("🏦 Long-Term Debt & EMI Summary")

debt_df = pd.DataFrame(DEBTS)
total_outstanding_tracked = debt_df[debt_df["tenure_left"].apply(lambda x: isinstance(x, int))]["outstanding"].sum()
total_emi = float(debt_df["amount"].sum())

st.markdown(f"**Total Monthly EMI Outflow: ₹{total_emi:,.2f}**")
st.markdown(f"**Total Tracked Outstanding (Excl. Home Loan): ₹{total_outstanding_tracked:,.2f}**")

st.dataframe(
    debt_df.style.format({"amount": "₹{:,.0f}", "outstanding": "₹{:,.0f}"}),
    use_container_width=True,
    hide_index=True,
    column_config={
        "type": st.column_config.TextColumn("Type"),
        "item": st.column_config.TextColumn("Item"),
        "amount": st.column_config.NumberColumn("Monthly (₹)"),
        "due_day": st.column_config.TextColumn("Due Day"),
        "tenure_left": st.column_config.TextColumn("Tenure Left"),
        "outstanding": st.column_config.NumberColumn("Outstanding (₹)"),
    }
)

# ---------------------------
# Bills — Month View + Per-card custom dates UI
# ---------------------------
st.markdown("---")
st.header("💳 Bills (choose your perspective)")

# --- Month selector for Bills section (independent of sidebar 'today')
sel_col1, sel_col2 = st.columns([1.2, 2])
with sel_col1:
    bills_view = st.radio(
        "Month View (for this section)",
        options=["Previous", "Current", "Next", "Custom"],
        horizontal=True,
        index=1,
        help="Controls the month used for the tables below."
    )
with sel_col2:
    st.caption("This changes the **month** for both tabs and the quick selector below.")

def shift_month(d: date, k: int) -> date:
    mid = dt.date(d.year, d.month, 15) + relativedelta(months=k)
    end_day = month_range(mid.year, mid.month)[1].day
    return dt.date(mid.year, mid.month, min(d.day, end_day))

if bills_view == "Previous":
    bills_anchor = shift_month(today, -1)
elif bills_view == "Next":
    bills_anchor = shift_month(today, +1)
elif bills_view == "Custom":
    bills_anchor = st.date_input(
        "Pick any date in the target month (Bills section only)",
        value=today,
        key="bills_anchor_custom"
    )
else:
    bills_anchor = today

by_y, by_m = bills_anchor.year, bills_anchor.month

# --- NEW: Per-card, per-month custom dates editor ---
st.subheader(f"🗓 Per-card custom dates for {bills_anchor.strftime('%b %Y')}")
with st.expander("Edit custom dates (optional) — overrides apply only to this month", expanded=False):
    st.caption("These overrides replace day-based cycles for this specific month. They persist in session and can be exported/imported.")
    # Build a temp table with defaults for this month
    cards_sorted = sorted(BILL_CYCLES.keys())
    # capture edited values
    edited_records = {}
    for card in cards_sorted:
        # default values (from overrides if already set, else from day-based)
        cstart_d, cend_d, bill_d, due_d = get_overridden_cycle(card, by_y, by_m, fallback_from_days=True)
        # If already stored, use stored explicitly
        key = override_key(by_y, by_m, card)
        if key in st.session_state.card_date_overrides:
            rec = st.session_state.card_date_overrides[key]
            try:
                cstart_d = dt.date.fromisoformat(rec["start"])
                cend_d   = dt.date.fromisoformat(rec["end"])
                due_d    = dt.date.fromisoformat(rec["due"])
            except Exception:
                pass

        c1, c2, c3 = st.columns(3)
        st.markdown(f"**{card}**")
        start_inp = c1.date_input(f"{card} — Cycle Start", value=cstart_d, key=f"ov_{key}_start")
        end_inp   = c2.date_input(f"{card} — Cycle End (bill gen)", value=cend_d, key=f"ov_{key}_end")
        due_inp   = c3.date_input(f"{card} — Due Date", value=due_d, key=f"ov_{key}_due")

        # sanity: ensure start <= end (if not, swap)
        if start_inp > end_inp:
            st.warning(f"{card}: Start was after End; adjusted on save.")
        edited_records[key] = {
            "start": start_inp.isoformat(),
            "end":   end_inp.isoformat(),
            "due":   due_inp.isoformat()
        }

    e1, e2, e3 = st.columns([1,1,2])
    with e1:
        if st.button("Save month overrides", use_container_width=True):
            # normalize any start>end by swapping
            fixed = {}
            for k, rec in edited_records.items():
                s = dt.date.fromisoformat(rec["start"])
                e = dt.date.fromisoformat(rec["end"])
                if s > e:
                    s, e = e, s
                fixed[k] = {"start": s.isoformat(), "end": e.isoformat(), "due": rec["due"]}
            st.session_state.card_date_overrides.update(fixed)
            st.success("Saved per-card custom dates for this month.")
    with e2:
        if st.button("Clear overrides for this month", use_container_width=True):
            to_del = [k for k in st.session_state.card_date_overrides.keys() if k.startswith(f"{by_y:04d}-{by_m:02d}::")]
            for k in to_del:
                del st.session_state.card_date_overrides[k]
            st.success("Cleared overrides for this month.")
    with e3:
        cexp2, cimp2 = st.columns(2)
        with cexp2:
            # export only this month's overrides
            this_month = {k: v for k, v in st.session_state.card_date_overrides.items() if k.startswith(f"{by_y:04d}-{by_m:02d}::")}
            st.download_button(
                "Export this month JSON",
                data=json.dumps(this_month, indent=2),
                file_name=f"card_date_overrides_{by_y}-{by_m:02d}.json",
                mime="application/json",
                use_container_width=True
            )
        with cimp2:
            up2 = st.file_uploader("Import this month JSON", type=["json"], key=f"card_date_json_{by_y}_{by_m}")
            if up2 is not None:
                try:
                    data = json.load(up2)
                    if isinstance(data, dict):
                        # validate keys belong to this month
                        valid = {k: v for k, v in data.items() if k.startswith(f"{by_y:04d}-{by_m:02d}::")}
                        # minimal schema check
                        for k, rec in list(valid.items()):
                            if not isinstance(rec, dict) or not all(x in rec for x in ("start","end","due")):
                                del valid[k]
                        st.session_state.card_date_overrides.update(valid)
                        st.success("Imported per-card dates for this month.")
                    else:
                        st.warning("Invalid JSON: expecting an object of { 'YYYY-MM::Card': {start,end,due} }")
                except Exception as e:
                    st.error(f"Failed to import: {e}")

# ---------------------------
# Utilities
# ---------------------------
def sum_liability(df_in: pd.DataFrame, card: str, start_dt: date, end_dt: date):
    mask = (
        (df_in["Card"] == card)
        & (df_in["type"].str.lower().eq("expense"))
        & (df_in["Amount"] > 0)
        & (df_in["Date"].dt.date >= start_dt)
        & (df_in["Date"].dt.date <= end_dt)
    )
    sub = df_in.loc[mask, ["Date", "Category", "Amount", "Note", "Payment mode", "Tags"]].copy().sort_values("Date")
    amount = float(sub["Amount"].sum()) if not sub.empty else 0.0
    txn_count = int(sub.shape[0])
    return sub, amount, txn_count

# ---------------------------
# Bills — Tabs
# ---------------------------
tab_gen, tab_due = st.tabs(["Bills Generating in Selected Month", "Bills Due in Selected Month"])

# --- Tab 1: Bills Generating in the selected month (by_y, by_m)
with tab_gen:
    rows_gen = []
    per_card_gen = {}
    for card in BILL_CYCLES.keys():
        cstart, cend, bill_dt, due_dt = get_overridden_cycle(card, by_y, by_m, fallback_from_days=True)
        sub, amount, txn_count = sum_liability(df, card, cstart, cend)
        per_card_gen[card] = {"window": (cstart, cend, bill_dt, due_dt), "df": sub, "amount": amount, "count": txn_count}
        rows_gen.append({
            "Card": card,
            "Cycle Start": cstart,
            "Cycle End (Bill Gen)": cend,
            "Due Date": due_dt,
            "Transactions": txn_count,
            "Cycle Liability (₹)": round(amount, 2)
        })
    card_gen_df = pd.DataFrame(rows_gen).sort_values(by="Due Date")

    st.caption(f"Cycles whose **bill is generated** in **{bills_anchor.strftime('%b %Y')}**.")
    def style_bill_gen(date_col):
        is_today_or_tomorrow = (date_col == bills_anchor) | (date_col == (bills_anchor + dt.timedelta(days=1)))
        return ['background-color: #fff3b0; font-weight: bold' if v else '' for v in is_today_or_tomorrow]
    st.dataframe(
        card_gen_df.style.apply(style_bill_gen, subset=["Cycle End (Bill Gen)"]),
        use_container_width=True,
        hide_index=True,
        column_config={"Cycle Liability (₹)": st.column_config.NumberColumn(format="₹%,.2f")}
    )

# --- Tab 2: Bills DUE in the selected month (offset-aware but override-respecting)
with tab_due:
    rows_due = []
    per_card_due = {}
    total_due_sel_month = 0.0
    for card in BILL_CYCLES.keys():
        cstart, cend, bill_dt, due_dt = find_cycle_whose_due_falls_in_month(card, by_y, by_m)
        sub, amount, txn_count = sum_liability(df, card, cstart, cend)
        per_card_due[card] = {"window": (cstart, cend, bill_dt, due_dt), "df": sub, "amount": amount, "count": txn_count}
        if (due_dt.month == by_m) and (due_dt.year == by_y):
            total_due_sel_month += amount
        rows_due.append({
            "Card": card,
            "Cycle Start": cstart,
            "Cycle End (Bill Gen)": cend,
            "Due Date": due_dt,
            "Transactions": txn_count,
            "Payable (₹)": round(amount, 2)
        })
    card_due_df = pd.DataFrame(rows_due).sort_values(by="Due Date")

    st.markdown(f"**Total CC Cash-Out in {bills_anchor.strftime('%b %Y')}: ₹{total_due_sel_month:,.2f}**")
    st.caption(f"Cycles whose **due date** falls in **{bills_anchor.strftime('%b %Y')}** (true cash-out).")

    def style_due(date_col):
        is_today_or_tomorrow = (date_col == bills_anchor) | (date_col == (bills_anchor + dt.timedelta(days=1)))
        return ['background-color: #fff3b0; font-weight: bold' if v else '' for v in is_today_or_tomorrow]
    st.dataframe(
        card_due_df.style.apply(style_due, subset=["Due Date"]),
        use_container_width=True,
        hide_index=True,
        column_config={"Payable (₹)": st.column_config.NumberColumn(format="₹%,.2f")}
    )

# ---------------------------
# Due-Month Quick Selector (Prev / Current / Next) — relative to chosen month
# ---------------------------
st.markdown("---")
st.subheader("📅 Due-Month Quick Selector (Prev / Current / Next)")

selector_col1, selector_col2 = st.columns([1.3, 2])
with selector_col1:
    due_view = st.radio(
        "View bills **due** in which month (relative to the month above)?",
        options=["Previous", "Current", "Next"],
        horizontal=True,
        index=1,
        help="Previous/Next relative to the **Bills section month**, not the sidebar."
    )
with selector_col2:
    st.caption(f"Base month: **{bills_anchor.strftime('%b %Y')}**. This selector shifts that base.")

if due_view == "Previous":
    due_anchor = shift_month(bills_anchor, -1)
elif due_view == "Next":
    due_anchor = shift_month(bills_anchor, +1)
else:
    due_anchor = bills_anchor

rows_quick, total_due_sel_month = [], 0.0
for card in BILL_CYCLES.keys():
    cstart, cend, bill_dt, due_dt = find_cycle_whose_due_falls_in_month(card, due_anchor.year, due_anchor.month)
    mask = (
        (df["Card"] == card)
        & (df["type"].str.lower().eq("expense"))
        & (df["Amount"] > 0)
        & (df["Date"].dt.date >= cstart)
        & (df["Date"].dt.date <= cend)
    )
    payable = float(df.loc[mask, "Amount"].sum())
    if (due_dt.month == due_anchor.month) and (due_dt.year == due_anchor.year):
        total_due_sel_month += payable
    rows_quick.append({
        "Card": card,
        "Cycle Start": cstart,
        "Cycle End (Bill Gen)": cend,
        "Due Date": due_dt,
        "Payable (₹)": round(payable, 2)
    })
quick_df = pd.DataFrame(rows_quick).sort_values(by="Due Date")

st.markdown(
    f"**Total CC Cash-Out in {due_anchor.strftime('%b %Y')}: ₹{total_due_sel_month:,.2f}**  "
    f"| **View:** {due_view} (base: {bills_anchor.strftime('%b %Y')})"
)
def _style_due_sel(dt_col):
    is_sel = (dt_col.apply(lambda d: d.month == due_anchor.month and d.year == due_anchor.year))
    return ['background-color: #fff3b0; font-weight: bold' if v else '' for v in is_sel]
st.dataframe(
    quick_df.style.apply(_style_due_sel, subset=["Due Date"]),
    use_container_width=True,
    hide_index=True,
    column_config={"Payable (₹)": st.column_config.NumberColumn(format="₹%,.2f")}
)

# ---------------------------
# Regular Expenses with Paid toggles (selected month = sidebar 'today')
# ---------------------------
st.markdown("---")
st.subheader("🗓️ Regular Expenses (incl. SIPs & Rent) — Toggle Paid")

y, m = today.year, today.month  # use sidebar month for this section by design
def due_in_month(d_hint: str, y: int, m: int) -> date:
    d = int(re.sub(r"[^0-9]", "", d_hint) or "1")
    return dt.date(y, m, min(d, month_range(y, m)[1].day))
all_cash_outs = []
for r in REGULARS:
    all_cash_outs.append({"Item": r["item"], "Amount (₹)": r["amount"], "Due Date": due_in_month(r["date_hint"], y, m), "Type": "Regular"})
for d in DEBTS:
    dday = int(re.sub(r"[^0-9]", "", str(d["due_day"])) or "1")
    all_cash_outs.append({"Item": d["item"], "Amount (₹)": d["amount"], "Due Date": dt.date(y, m, min(dday, month_range(y, m)[1].day)), "Type": d["type"]})
cash_out_df = pd.DataFrame(all_cash_outs).sort_values(by="Due Date")
cash_out_df["Key"] = cash_out_df.apply(lambda r: f"CASH::{r['Item']}::{r['Due Date'].isoformat()}", axis=1)
cash_out_df["Paid"] = cash_out_df["Key"].map(lambda k: st.session_state.paid_flags.get(k, False))

cols = st.columns([3, 2, 2, 1])
cols[0].markdown("**Item (Type)**")
cols[1].markdown("**Amount (₹)**")
cols[2].markdown("**Due Date**")
cols[3].markdown("**Paid?**")
for _, row in cash_out_df.iterrows():
    c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
    with c1: st.markdown(f"**{row['Item']}** ({row['Type']})")
    with c2: st.markdown(f"₹{row['Amount (₹)']:,}")
    with c3: st.markdown(f"{row['Due Date'].strftime('%b %d, %Y')}")
    with c4:
        paid = st.checkbox("", value=row["Paid"], key=row["Key"], label_visibility="collapsed")
        st.session_state.paid_flags[row["Key"]] = paid
cash_out_df["Paid"] = cash_out_df["Key"].map(lambda k: st.session_state.paid_flags.get(k, False))

# ---------------------------
# Cash Flow Simulator (Due-month view = sidebar 'today')
# ---------------------------
st.subheader("💰 Cash Flow Simulator (by date) — Due-month view")

balance = starting_balance + extra_buffer
events = []
# a) CC bills due this month (using override-aware due finder)
rows_due_sidebar = []
for card in BILL_CYCLES.keys():
    cstart_s, cend_s, bill_dt_s, due_dt_s = find_cycle_whose_due_falls_in_month(card, today.year, today.month)
    mask_s = (
        (df["Card"] == card)
        & (df["type"].str.lower().eq("expense"))
        & (df["Amount"] > 0)
        & (df["Date"].dt.date >= cstart_s)
        & (df["Date"].dt.date <= cend_s)
    )
    payable_s = float(df.loc[mask_s, "Amount"].sum())
    rows_due_sidebar.append((card, due_dt_s, payable_s))
for card, dd, amt in rows_due_sidebar:
    if dd.month == today.month and dd.year == today.year and amt > 0:
        events.append({"Date": dd, "Event": f"{card} Bill Payment (CC)", "Amount (₹)": amt, "Type": "CC Bill"})
# b) Regulars/EMIs
for _, r in cash_out_df.iterrows():
    if not r["Paid"] and r["Due Date"].month == today.month and r["Due Date"].year == today.year:
        events.append({"Date": r["Due Date"], "Event": r["Item"], "Amount (₹)": r["Amount (₹)"], "Type": "Regular/EMI"})
ev_df = pd.DataFrame(events).sort_values(by="Date").drop_duplicates(subset=["Date", "Event"])
rows2 = []
for _, ev in ev_df.iterrows():
    balance -= ev["Amount (₹)"]
    rows2.append([ev["Date"], ev["Event"], ev["Amount (₹)"], round(balance, 2)])
sim_df = pd.DataFrame(rows2, columns=["Date", "Event", "Amount (₹)", "Balance After (₹)"])

def style_low_balance(df_in: pd.DataFrame):
    styles = pd.DataFrame('', index=df_in.index, columns=df_in.columns)
    styles.loc[df_in['Balance After (₹)'] < 0, 'Balance After (₹)'] = 'background-color: #ffcccc; color: red; font-weight: bold'
    styles.loc[(df_in['Balance After (₹)'] >= 0) & (df_in['Balance After (₹)'] < extra_buffer), 'Balance After (₹)'] = 'background-color: #ffefcc'
    return styles
st.markdown(f"**Starting Cash Balance: ₹{starting_balance:,.2f}** (with Buffer: ₹{extra_buffer:,.2f})")
st.dataframe(
    sim_df.style.apply(style_low_balance, axis=None).format({
        "Amount (₹)": "₹{:,.2f}",
        "Balance After (₹)": "₹{:,.2f}",
        "Date": lambda x: x.strftime('%b %d'),
    }),
    use_container_width=True,
    hide_index=True
)

# ---------------------------
# Expenses by Card (cycle windows — generating month view = sidebar 'today')
# ---------------------------
st.markdown("---")
st.header("🧾 Expenses by Card (cycle that **generates** in selected month)")
st.caption("Transactions included in each card's cycle window (full cycle for the month where bill is generated).")

summary_rows = []
per_card_transactions = {}
for card in BILL_CYCLES.keys():
    cstart, cend, bill_dt, due_dt = get_overridden_cycle(card, today.year, today.month, fallback_from_days=True)
    mask = (
        (df["Card"] == card)
        & (df["type"].str.lower().eq("expense"))
        & (df["Amount"] > 0)
        & (df["Date"].dt.date >= cstart)
        & (df["Date"].dt.date <= cend)
    )
    sub = df.loc[mask, ["Date", "Category", "Amount", "Note", "Payment mode", "Tags"]].copy().sort_values("Date")
    amount = float(sub["Amount"].sum()) if not sub.empty else 0.0
    txn_count = int(sub.shape[0])
    per_card_transactions[card] = {"window": (cstart, cend, bill_dt, due_dt), "df": sub, "amount": amount, "count": txn_count}
    summary_rows.append({
        "Card": card,
        "Transactions": txn_count,
        "Cycle Liability (₹)": round(amount, 2),
        "Cycle Start": cstart,
        "Cycle End (Bill Gen)": cend,
        "Due Date": due_dt
    })
summary_df = pd.DataFrame(summary_rows)
st.dataframe(
    summary_df,
    use_container_width=True,
    hide_index=True,
    column_config={"Cycle Liability (₹)": st.column_config.NumberColumn(format="₹%,.2f")}
)

for card in BILL_CYCLES.keys():
    detail = per_card_transactions[card]
    cstart, cend, bill_dt, due_dt = detail["window"]
    sub = detail["df"]
    total_amt = max(detail["amount"], 1e-9)
    expander_title = f"{card} | Due: {due_dt.strftime('%b %d')} | Liability: ₹{detail['amount']:,.2f} | Txns: {detail['count']}"
    with st.expander(expander_title):
        if sub.empty:
            st.info("No transactions for this cycle.")
        else:
            category_breakdown = sub.groupby("Category", dropna=False)["Amount"].sum().reset_index().sort_values("Amount", ascending=False)
            category_breakdown["% of Total"] = (category_breakdown["Amount"] / total_amt) * 100
            st.markdown("**Category Breakdown**")
            st.dataframe(
                category_breakdown.style.format({"Amount": "₹{:,.0f}", "% of Total": "{:.1f}%"}),
                use_container_width=True,
                hide_index=True
            )
            st.markdown("**Transactions (Cycle Window)**")
            st.dataframe(sub.style.format({"Amount": "₹{:,.0f}"}), use_container_width=True, hide_index=True)
            csv_buf = io.StringIO()
            sub.to_csv(csv_buf, index=False)
            st.download_button(
                f"Download {card} Cycle Transactions CSV",
                data=csv_buf.getvalue(),
                file_name=f"{card}_cycle_{cstart}_to_{cend}.csv",
                mime="text/csv"
            )

# ---------------------------
# Top Merchants per Card — window selection
# ---------------------------
st.markdown("---")
st.header("🏷️ Top Merchants per Card — choose analysis window")
def months_back(n: int, ref_date: date) -> Tuple[date, date]:
    end = dt.date(ref_date.year, ref_date.month, month_range(ref_date.year, ref_date.month)[1].day)
    start = end - relativedelta(months=n) + relativedelta(days=1)
    return start, end

window_choice = st.radio("Window", ["Current Cycle (Generating Month)", "Last 3 months", "Last 6 months", "Last 12 months"], horizontal=True, index=1)
if window_choice == "Current Cycle (Generating Month)":
    use_current_cycle = True
else:
    use_current_cycle = False
    nmap = {"Last 3 months": 3, "Last 6 months": 6, "Last 12 months": 12}
    global_start, global_end = months_back(nmap[window_choice], today)

for card in BILL_CYCLES.keys():
    if use_current_cycle:
        cstart, cend, _, _ = get_overridden_cycle(card, today.year, today.month, fallback_from_days=True)
        mask = (df["Card"] == card) & (df["Date"].dt.date >= cstart) & (df["Date"].dt.date <= cend)
        window_label = f"{cstart} → {cend}"
    else:
        mask = (df["Card"] == card) & (df["Date"].dt.date >= global_start) & (df["Date"].dt.date <= global_end)
        window_label = f"{global_start} → {global_end}"
    sub = df.loc[mask & (df["type"].str.lower().eq("expense")) & (df["Amount"] > 0), ["Date", "Category", "Note", "Amount"]].copy()
    with st.expander(f"**{card}** — Top Merchants | Window: {window_label}"):
        if sub.empty:
            st.info("No expense transactions in this window.")
        else:
            top = sub.groupby(["Category", "Note"], dropna=False)["Amount"].sum().reset_index().sort_values("Amount", ascending=False)
            st.dataframe(top.head(10).style.format({"Amount": "₹{:,.0f}"}), use_container_width=True, hide_index=True)
            buf = io.StringIO()
            top.to_csv(buf, index=False)
            st.download_button(
                f"Download Top Merchants — {card}",
                data=buf.getvalue(),
                file_name=f"top_merchants_{card}_{window_choice.replace(' ', '_')}.csv",
                mime="text/csv"
            )

# ---------------------------
# Monthly Trends (MoM %, anomalies, caps)
# ---------------------------
st.markdown("---")
st.header("📈 Monthly Trends, MoM % Change, & Anomalies")
st.caption("Rolling monthly totals for expense transactions; anomalies (>1.5× median) and over-cap highlighted. Use sidebar to set caps.")

@st.cache_data(show_spinner=False)
def compute_monthly_for_trends(trends_df: pd.DataFrame) -> pd.DataFrame:
    tmp = trends_df.copy()
    tmp = tmp.loc[tmp["type"].str.lower().eq("expense")].copy()
    tmp["YYYY-MM"] = tmp["Date"].dt.to_period("M").astype(str)
    tmp = tmp.loc[tmp["Card"].notna()].copy()
    g = (
        tmp.groupby(["YYYY-MM", "Card"])["Amount"]
        .sum()
        .unstack(fill_value=0.0)
        .sort_index()
    )
    return g

monthly = compute_monthly_for_trends(df)
window = st.radio("Window", ["Last 6 months", "Last 12 months", "All Time"], horizontal=True, index=1)
exclude_current_month_from_anomaly = st.checkbox("Exclude selected month from anomaly calculations", value=True)
n_months = 12 if window != "Last 6 months" else 6
if window != "All Time" and monthly.shape[0] > n_months:
    monthly = monthly.iloc[-n_months:, :]

available_cards = sorted([c for c in monthly.columns if pd.notna(c) and c in BILL_CYCLES.keys()])
selected_cards = st.multiselect("Choose cards to analyze", options=available_cards, default=available_cards)

mom = monthly.pct_change().replace([np.inf, -np.inf], np.nan) * 100.0
combined_df = monthly.copy()
for card in selected_cards:
    combined_df[f"{card} MoM %"] = mom[card]
combined_df = combined_df[sorted(combined_df.columns)].copy()

def style_anomalies_and_caps(df_in: pd.DataFrame) -> pd.DataFrame:
    df_out = pd.DataFrame('', index=df_in.index, columns=df_in.columns)
    this_ym = f"{today.year}-{str(today.month).zfill(2)}"
    for col in [c for c in df_in.columns if "MoM %" not in c]:
        series_for_med = df_in[col]
        if exclude_current_month_from_anomaly and (len(df_in.index) > 0) and (df_in.index[-1] == this_ym):
            series_for_med = series_for_med.iloc[:-1]
        med = series_for_med[series_for_med > 0].median()
        if med and med > 0:
            is_anom = df_in[col] > 1.5 * med
            df_out.loc[is_anom, col] = "background-color: #f7a5a5; font-weight: bold"
        cap = budget_caps.get(col, 0) or 0
        if cap > 0:
            is_over_cap = df_in[col] > cap
            df_out.loc[is_over_cap, col] = "background-color: #ffcccc; font-weight: bold"
        mom_col = f"{col} MoM %"
        if mom_col in df_in.columns and med and med > 0:
            is_high_mom = (df_in[mom_col] > 50) & (df_in[col] > med * 1.1)
            df_out.loc[is_high_mom, mom_col] = "background-color: #d1f7c4; font-weight: bold"
    return df_out

if selected_cards:
    st.subheader("📊 Trend Chart")
    plot_df = monthly[selected_cards].copy()
    st.line_chart(plot_df)
    st.subheader("Monthly Totals (₹) and MoM % Change")
    format_dict = {c: "₹{:,.0f}" for c in monthly.columns}
    format_dict.update({c: "{:.1f}%" for c in combined_df.columns if "MoM %" in c})
    st.dataframe(
        combined_df.style.apply(style_anomalies_and_caps, axis=None).format(format_dict),
        use_container_width=True
    )
    st.download_button(
        "Download Monthly Trends Data (CSV)",
        data=monthly[selected_cards].to_csv().encode('utf-8'),
        file_name=f"monthly_trends_{'all' if window=='All Time' else str(n_months)+'m'}.csv",
        mime="text/csv"
    )
else:
    st.info("Select at least one card to analyze monthly trends.")

# ---------------------------
# 1-Year Financial Action Plan (Debt & Investment)
# ---------------------------
st.markdown("---")
st.header("🎯 1-Year Financial Action Plan: Debt & Investment")

unsecured_debt = pd.DataFrame(DEBTS)
unsecured_debt = unsecured_debt[unsecured_debt["item"] != "Home Loan EMI"].copy()
def _to_num(x):
    try:
        return int(x)
    except Exception:
        return np.nan
unsecured_debt["tenure_num"] = unsecured_debt["tenure_left"].apply(_to_num)
unsecured_debt_sorted = unsecured_debt.sort_values("tenure_num", na_position="last")

if not unsecured_debt_sorted.empty and not unsecured_debt_sorted["tenure_num"].isna().all():
    debt_p1 = unsecured_debt_sorted.iloc[0]
    p1_emi = debt_p1["amount"]
    p1_tenure = debt_p1["tenure_left"]
    cash_flow_increase = p1_emi
    total_sip = sum(r['amount'] for r in REGULARS if 'SIP' in r['item'])
    st.subheader("1. Debt Clearance Strategy (Snowball for Cash Flow)")
    st.markdown(f"""
- **Phase 1:** Focus on **{debt_p1['item']}** (Outstanding: ₹{debt_p1['outstanding']:,.0f}; Tenure left: {p1_tenure}).
- **Action:** Continue ₹{p1_emi:,.0f}/mo for {p1_tenure} months; then roll that EMI to the next debt.
- **Cash-Flow Unlock:** **₹{cash_flow_increase:,.0f}/mo** freed post-clearance.

**Current Monthly SIPs:** ₹{total_sip:,.0f}
""")
    st.subheader("2. Investment Strategy for 1-Year Goal (Capital Preservation)")
    st.markdown("""
| Fund Purpose | Risk Profile | Recommended Instrument | Why? |
|---|---|---|---|
| **Down Payment (~₹40L)** | **LOW** | **Liquid / Ultra Short Duration Funds** | Higher post-tax than savings a/c, high liquidity, low volatility. |
| **New Monthly Savings** | **LOW** | **Corporate Bond Funds / FDs** | Slightly higher returns; suitable for closing-cost buffer. |
| **Existing Long-Horizon SIPs** | **HIGH/MOD** | **Continue as-is** | Don’t divert long-term equity SIPs to 1-year goals. |
""")
else:
    st.info("No short-term unsecured debt data available for a dynamic reduction plan.")
    st.markdown("""
**General Guidance**
1. **Snowball** (free cash flow fastest) vs **Avalanche** (minimize interest) — pick Snowball to boost DTI pre home-loan.
2. **< 3 years goal** → **Debt/Liquid instruments**, not equities.
""")

# ---------------------------
# Assumptions
# ---------------------------
with st.expander("📋 Assumptions & Exclusions", expanded=False):
    st.markdown("""
- **Priority:** Per-month custom dates (this month per card) override everything; if absent, use **day-based cycles**; else defaults.
- **Liabilities** sum only rows with `type` ≈ `Expense` and `Amount` > 0.
- Refunds/credits/transfers are excluded from liabilities and merchant rankings.
- Cycle windows are **inclusive** of both start and end dates.
- **Bills Generating**: cycles whose **bill-generation (cycle end)** falls in the chosen month.
- **Bills Due**: cycles whose **due date** falls in the chosen month (true cash-out). We search nearby anchors to accommodate overrides.
- Anomaly detection uses 1.5× median of positive months; option to exclude selected month from the statistic.
""")
