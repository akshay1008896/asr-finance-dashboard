# helpers.py
# CSV normalization, card mapping, cycle math (incl. per-card overrides), utilities

from typing import Dict, Optional, Tuple, List
from datetime import date
import calendar

import pandas as pd
import numpy as np
from dateutil.relativedelta import relativedelta

REQUIRED_COLS = {"Date", "Amount", "Payment mode", "type"}
OPTIONAL_COLS = ["Category", "Note", "Tags"]

def normalize_csv(file) -> Optional[pd.DataFrame]:
    """Read CSV, validate, normalize schema."""
    try:
        df = pd.read_csv(file)
    except Exception:
        return None
    missing = REQUIRED_COLS.difference(df.columns)
    if missing:
        return None
    for c in OPTIONAL_COLS:
        if c not in df.columns:
            df[c] = ""
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df[df["Date"].notna()].copy()
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0).round(2)
    df["type"] = df["type"].fillna("").astype(str)
    df["Payment mode"] = df["Payment mode"].fillna("").astype(str)
    return df

def apply_card_mapping(df: pd.DataFrame, aliases: Dict[str, str]) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    out["Card"] = out["Payment mode"].map(aliases).replace({np.nan: None})
    return out

def unique_payment_modes(df: pd.DataFrame) -> pd.DataFrame:
    modes = df["Payment mode"].fillna("").astype(str).str.strip()
    return pd.DataFrame({"Payment mode": sorted(modes.unique())})

# ---------- Date helpers ----------
def month_range(y: int, m: int) -> Tuple[date, date]:
    start = date(y, m, 1)
    last = calendar.monthrange(y, m)[1]
    return start, date(y, m, last)

def safe_date(y: int, m: int, d: int) -> date:
    last = calendar.monthrange(y, m)[1]
    return date(y, m, max(1, min(d, last)))

def shift_month(d: date, k: int) -> date:
    anchor = date(d.year, d.month, 15) + relativedelta(months=k)
    _, end = month_range(anchor.year, anchor.month)
    return date(anchor.year, anchor.month, min(d.day, end.day))

# ---------- Cycles (cards) ----------
def cycle_window_for_month(card_row: Dict, year: int, month: int) -> Tuple[date, date, date, date]:
    """Compute cycle from card fields (no override)."""
    start_day = int(card_row["start_day"])
    end_day   = int(card_row["end_day"])
    due_day   = int(card_row["due_day"])
    due_off   = int(card_row["due_offset"])

    cycle_end = safe_date(year, month, end_day)
    cycle_start = safe_date(year, month, start_day)
    if start_day > end_day:
        cycle_start = shift_month(cycle_start, -1)

    due_month = month + due_off
    due_year  = year
    while due_month > 12:
        due_month -= 12
        due_year += 1
    due_dt = safe_date(due_year, due_month, due_day)
    return cycle_start, cycle_end, cycle_end, due_dt

def get_override_for(card_id: str, year: int, month: int, overrides: List[Dict]) -> Optional[Dict]:
    for ov in overrides:
        if ov.get("card_id") == card_id and ov.get("year") == year and ov.get("month") == month:
            return ov
    return None

def get_effective_cycle(card_row: Dict, year: int, month: int, overrides: List[Dict]) -> Tuple[date, date, date, date]:
    """Use override if present; else fallback to standard cycle."""
    ov = get_override_for(card_row["id"], year, month, overrides)
    if ov:
        cs = date.fromisoformat(ov["cycle_start"])
        ce = date.fromisoformat(ov["cycle_end"])
        dd = date.fromisoformat(ov["due_date"])
        return cs, ce, ce, dd
    return cycle_window_for_month(card_row, year, month)

def card_bill_due_in_month(card_row: Dict, ref_date: date, overrides: List[Dict]) -> Tuple[date, date, date, date]:
    """Cycle whose due date falls in the ref month (offset-aware), with overrides."""
    due_off = int(card_row["due_offset"])
    target = shift_month(date(ref_date.year, ref_date.month, 15), -due_off)
    return get_effective_cycle(card_row, target.year, target.month, overrides)

def sum_liability(df: pd.DataFrame, card_name: str, start_dt: date, end_dt: date) -> Tuple[pd.DataFrame, float, int]:
    mask = (
        (df["Card"] == card_name) &
        (df["type"].str.lower().eq("expense")) &
        (df["Amount"] > 0) &
        (df["Date"].dt.date >= start_dt) &
        (df["Date"].dt.date <= end_dt)
    )
    sub = df.loc[mask, ["Date", "Category", "Amount", "Note", "Payment mode", "Tags"]].copy().sort_values("Date")
    amount = round(float(sub["Amount"].sum()), 2) if not sub.empty else 0.0
    return sub, amount, len(sub)

# ---------- Trends ----------
def monthly_totals(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    if df is None or df.empty:
        return None
    tmp = df.loc[df["type"].str.lower().eq("expense")].copy()
    if tmp.empty:
        return None
    tmp["YYYY-MM"] = tmp["Date"].dt.to_period("M").astype(str)
    tmp = tmp.loc[tmp["Card"].notna()].copy()
    g = (
        tmp.groupby(["YYYY-MM", "Card"])["Amount"]
        .sum()
        .unstack(fill_value=0.0)
        .sort_index()
    )
    return g
