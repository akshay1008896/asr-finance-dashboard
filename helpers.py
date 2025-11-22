# helpers.py
# CSV normalization, card mapping, cycle math (incl. per-card overrides), utilities

from typing import Dict, Optional, Tuple, List
from datetime import date
import calendar
import logging

import pandas as pd
import numpy as np
from dateutil.relativedelta import relativedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REQUIRED_COLS = {"Date", "Amount", "Payment mode", "type"}
OPTIONAL_COLS = ["Category", "Note", "Tags"]

def normalize_csv(file) -> Optional[pd.DataFrame]:
    """
    Read CSV, validate, and normalize schema.
    Expected columns: Date, Amount, Payment mode, type.
    """
    try:
        df = pd.read_csv(file)
    except Exception as e:
        logger.error(f"Failed to read CSV: {e}")
        return None
    
    missing = REQUIRED_COLS.difference(df.columns)
    if missing:
        logger.error(f"Missing required columns: {missing}")
        return None
        
    for c in OPTIONAL_COLS:
        if c not in df.columns:
            df[c] = ""
            
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    # Drop rows with invalid dates
    if df["Date"].isna().any():
        logger.warning(f"Dropping {df['Date'].isna().sum()} rows with invalid dates")
        df = df[df["Date"].notna()].copy()
        
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0).round(2)
    df["type"] = df["type"].fillna("").astype(str)
    df["Payment mode"] = df["Payment mode"].fillna("").astype(str)
    return df

def apply_card_mapping(df: pd.DataFrame, aliases: Dict[str, str]) -> pd.DataFrame:
    """Map 'Payment mode' to 'Card' using the provided aliases."""
    if df is None or df.empty:
        return df
    out = df.copy()
    out["Card"] = out["Payment mode"].map(aliases).replace({np.nan: None})
    return out

def unique_payment_modes(df: pd.DataFrame) -> pd.DataFrame:
    """Extract unique payment modes from the dataframe."""
    modes = df["Payment mode"].fillna("").astype(str).str.strip()
    return pd.DataFrame({"Payment mode": sorted(modes.unique())})

# ---------- Date helpers ----------
def month_range(y: int, m: int) -> Tuple[date, date]:
    """Return the first and last date of a given month."""
    start = date(y, m, 1)
    last = calendar.monthrange(y, m)[1]
    return start, date(y, m, last)

def safe_date(y: int, m: int, d: int) -> date:
    """Return a valid date, clamping the day to the last day of the month if necessary."""
    last = calendar.monthrange(y, m)[1]
    return date(y, m, max(1, min(d, last)))

def shift_month(d: date, k: int) -> date:
    """Shift the date by k months, keeping the day if possible."""
    anchor = date(d.year, d.month, 15) + relativedelta(months=k)
    _, end = month_range(anchor.year, anchor.month)
    return date(anchor.year, anchor.month, min(d.day, end.day))

# ---------- Cycles (cards) ----------
def cycle_window_for_month(card_row: Dict, year: int, month: int) -> Tuple[date, date, date, date]:
    """
    Compute cycle start, end, bill generation date, and due date for a given month.
    Returns: (cycle_start, cycle_end, bill_gen_date, due_date)
    """
    start_day = int(card_row["start_day"])
    end_day   = int(card_row["end_day"])
    due_day   = int(card_row["due_day"])
    due_off   = int(card_row["due_offset"])

    cycle_end = safe_date(year, month, end_day)
    cycle_start = safe_date(year, month, start_day)
    
    # If start day > end day, the cycle started in the previous month
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
    """Find a specific override for a card and month."""
    for ov in overrides:
        if ov.get("card_id") == card_id and ov.get("year") == year and ov.get("month") == month:
            return ov
    return None

def get_effective_cycle(card_row: Dict, year: int, month: int, overrides: List[Dict]) -> Tuple[date, date, date, date]:
    """
    Compute the effective cycle, considering any overrides.
    Returns: (cycle_start, cycle_end, bill_gen_date, due_date)
    """
    ov = get_override_for(card_row["id"], year, month, overrides)
    if ov:
        cs = date.fromisoformat(ov["cycle_start"])
        ce = date.fromisoformat(ov["cycle_end"])
        dd = date.fromisoformat(ov["due_date"])
        return cs, ce, ce, dd
    return cycle_window_for_month(card_row, year, month)

def card_bill_due_in_month(card_row: Dict, ref_date: date, overrides: List[Dict]) -> Tuple[date, date, date, date]:
    """
    Find the cycle whose due date falls in the reference month.
    This accounts for the due offset.
    """
    due_off = int(card_row["due_offset"])
    # To find the cycle that is due in ref_date, we look back due_off months
    target = shift_month(date(ref_date.year, ref_date.month, 15), -due_off)
    return get_effective_cycle(card_row, target.year, target.month, overrides)

def sum_liability(df: pd.DataFrame, card_name: str, start_dt: date, end_dt: date) -> Tuple[pd.DataFrame, float, int]:
    """
    Calculate total liability for a card within a date range.
    Returns: (subset_df, total_amount, transaction_count)
    """
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
    """
    Calculate monthly totals per card.
    Returns a DataFrame with months as index and cards as columns.
    """
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
