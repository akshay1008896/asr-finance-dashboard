# helpers.py
# Normalization & mapping helpers (decimal-safe)

from typing import Dict, Optional, Tuple
import pandas as pd
import numpy as np

REQUIRED_COLS = {"Date", "Amount", "Payment mode", "type"}
OPTIONAL_COLS = ["Category", "Note", "Tags"]

def normalize_csv(file) -> Optional[pd.DataFrame]:
    """Read CSV and normalize columns & types. Returns DataFrame or None."""
    try:
        df = pd.read_csv(file)
    except Exception:
        return None

    missing = REQUIRED_COLS.difference(df.columns)
    if missing:
        return None

    # Ensure optional columns exist
    for c in OPTIONAL_COLS:
        if c not in df.columns:
            df[c] = ""

    # Normalize
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df[df["Date"].notna()].copy()
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0).round(2)
    df["type"] = df["type"].fillna("").astype(str)
    df["Payment mode"] = df["Payment mode"].fillna("").astype(str)
    return df

def apply_card_mapping(df: pd.DataFrame, aliases: Dict[str, str]) -> pd.DataFrame:
    """Adds a 'Card' column by exact-match aliases on 'Payment mode'. Unmapped → None."""
    if df is None or df.empty:
        return df
    out = df.copy()
    out["Card"] = out["Payment mode"].map(aliases).replace({np.nan: None})
    return out

def auto_detect_card_names(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns (unique_modes_df, same_as_first) for convenience.
    Caller uses unique_modes_df to build the mapping editor.
    """
    modes = (
        df["Payment mode"]
        .fillna("")
        .astype(str)
        .str.strip()
    )
    uniq_modes = pd.DataFrame({"Payment mode": sorted(modes.unique())})
    return uniq_modes, uniq_modes
