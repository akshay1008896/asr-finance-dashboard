from typing import Dict, Optional, Tuple, List
from datetime import date
import pandas as pd
import numpy as np
from dateutil.relativedelta import relativedelta
import calendar

REQUIRED_COLS = {"Date", "Amount", "Payment mode", "type"}
OPTIONAL_COLS = ["Category", "Note", "Tags"]

def normalize_csv(file) -> Optional[pd.DataFrame]:
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

def month_range(y: int, m: int):
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

def cycle_window_for_month(card_row: Dict, year: int, month: int) -> Tuple[date, date, date, date]:
    start_day = int(card_row["start_day"])
    end_day   = int(card_row["end_day"])
    due_day   = int(card_row["due_day"])
    due_off   = int(card_row["due_offset"])
    cycle_end = safe_date(year, month, end_day)
    start_date = safe_date(year, month, start_day)
    if start_day > end_day:
        cycle_start = shift_month(start_date, -1)
    else:
        cycle_start = start_date
    due_month = month + due_off
    due_year  = year
    while due_month > 12:
        due_month -= 12
        due_year += 1
    due_dt = safe_date(due_year, due_month, due_day)
    return cycle_start, cycle_end, cycle_end, due_dt

def card_bill_due_in_month(card_row: Dict, ref_date: date) -> Tuple[date, date, date, date]:
    due_off = int(card_row["due_offset"])
    target = shift_month(date(ref_date.year, ref_date.month, 15), -due_off)
    return cycle_window_for_month(card_row, target.year, target.month)

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
