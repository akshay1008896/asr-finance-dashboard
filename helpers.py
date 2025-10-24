# helpers.py
import re
import datetime as dt
from datetime import date
from typing import Dict, Tuple, Optional

import pandas as pd
from dateutil.relativedelta import relativedelta

from config import CANON_COLS  # constants only — OK

# -------- Rounding helpers (2 decimals everywhere) --------
def r2(x) -> float:
    try:
        return round(float(x), 2)
    except Exception:
        return 0.00

def round_series_2(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").round(2)

# -------- Column normalization --------
def normalize_columns(pdf: pd.DataFrame) -> pd.DataFrame:
    new_cols = {}
    for c in pdf.columns:
        key = c.strip().lower().replace("_", " ")
        key_compact = key.replace(" ", "")
        if key in CANON_COLS:
            new_cols[c] = CANON_COLS[key]
        elif key_compact in CANON_COLS:
            new_cols[c] = CANON_COLS[key_compact]
        else:
            new_cols[c] = c
    return pdf.rename(columns=new_cols)

# -------- Card detection --------
CARD_REGEX = [
    (r"\b(amex|american\s*express|plat(?:inum)?)\b", "Amex"),
    (r"\b(icici|ici)\b", "ICICI"),
    (r"\bsbi\b", "SBI"),
    (r"\b(onecard|oncecard)\b", "One"),
    (r"\b(hsbc\s*cash|hsbcl|cashback)\b", "HSBC Cash"),
    (r"\bhsbc\b", "HSBC"),
]

def detect_card(payment_mode: str, user_overrides: Optional[Dict[str, str]] = None) -> Optional[str]:
    if not payment_mode:
        return None
    import streamlit as st
    # auto mapping created via diagnostics UI
    if payment_mode in (getattr(st.session_state, 'auto_overrides', {}) or {}):
        return st.session_state.auto_overrides[payment_mode]
    # user JSON overrides
    if user_overrides and payment_mode in user_overrides:
        return user_overrides[payment_mode]
    text = str(payment_mode).lower()
    for pat, name in CARD_REGEX:
        if re.search(pat, text):
            if name == "One" and "closed" in text:
                return None
            return name
    return None

# -------- Dates & cycles --------
def month_range(y: int, m: int):
    start = dt.date(y, m, 1)
    end = start + relativedelta(months=1) - dt.timedelta(days=1)
    return start, end

def safe_date(year: int, month: int, day: int) -> date:
    last_day = month_range(year, month)[1].day
    return dt.date(year, month, min(day, last_day))

def month_shift(d: date, k: int) -> date:
    mid = dt.date(d.year, d.month, 15) + relativedelta(months=k)
    end_day = month_range(mid.year, mid.month)[1].day
    return dt.date(mid.year, mid.month, min(d.day, end_day))

def months_back(n: int, ref_date: date):
    end = dt.date(ref_date.year, ref_date.month, month_range(ref_date.year, ref_date.month)[1].day)
    start = end - relativedelta(months=n) + relativedelta(days=1)
    return start, end

def override_key(year: int, month: int, card: str) -> str:
    return f"{year:04d}-{month:02d}::{card}"

def get_active_cycles(default_cycles: Dict[str, Tuple[int,int,int,int]]) -> Dict[str, Tuple[int,int,int,int]]:
    import streamlit as st
    cycles = default_cycles.copy()
    if getattr(st.session_state, "cycle_overrides", None):
        cycles.update(st.session_state.cycle_overrides)
    if getattr(st.session_state, "new_card_cycles", None):
        cycles.update(st.session_state.new_card_cycles)
    return cycles

def get_cycle_for_month(card: str, year: int, month: int, cycles: Dict[str, Tuple[int,int,int,int]]):
    start_day, end_day, due_day, due_offset = cycles[card]
    cycle_end = safe_date(year, month, end_day)
    start_date = safe_date(year, month, start_day)
    cycle_start = start_date - relativedelta(months=1) if start_day > end_day else start_date
    due_month = month + due_offset
    due_year = year + (due_month - 1) // 12
    due_month = (due_month - 1) % 12 + 1
    due_dt = safe_date(due_year, due_month, due_day)
    return cycle_start, cycle_end, cycle_end, due_dt

def get_overridden_cycle(card: str, year: int, month: int, cycles: Dict[str, Tuple[int,int,int,int]]):
    import streamlit as st
    key = override_key(year, month, card)
    if key in st.session_state.card_date_overrides:
        r = st.session_state.card_date_overrides[key]
        try:
            cstart = dt.date.fromisoformat(r["start"])
            cend   = dt.date.fromisoformat(r["end"])
            ddue   = dt.date.fromisoformat(r["due"])
            return cstart, cend, cend, ddue
        except Exception:
            pass
    return get_cycle_for_month(card, year, month, cycles)

def find_cycle_due_in_month(card: str, target_year: int, target_month: int, cycles: Dict[str, Tuple[int,int,int,int]]):
    candidates = []
    for k in range(-2, 3):
        anchor = dt.date(target_year, target_month, 15) + relativedelta(months=k)
        cstart, cend, bill_dt, due_dt = get_overridden_cycle(card, anchor.year, anchor.month, cycles)
        candidates.append((cstart, cend, bill_dt, due_dt))
    for cstart, cend, bill_dt, due_dt in candidates:
        if due_dt.year == target_year and due_dt.month == target_month:
            return cstart, cend, bill_dt, due_dt
    center = dt.date(target_year, target_month, 15)
    return min(candidates, key=lambda x: abs((x[3] - center).days))

def sum_liability(df: pd.DataFrame, card: str, start_dt: date, end_dt: date):
    mask = (
        (df["Card"] == card)
        & (df["type"].str.lower().eq("expense"))
        & (df["Amount"] > 0)
        & (df["Date"].dt.date >= start_dt)
        & (df["Date"].dt.date <= end_dt)
    )
    sub = df.loc[mask, ["Date", "Category", "Amount", "Note", "Payment mode", "Tags"]].copy().sort_values("Date")
    if not sub.empty:
        sub["Amount"] = round_series_2(sub["Amount"])
    amount = r2(sub["Amount"].sum() if not sub.empty else 0.0)
    txn_count = int(sub.shape[0])
    return sub, amount, txn_count
