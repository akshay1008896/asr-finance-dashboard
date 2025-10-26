# ui_sections.py
# All UI blocks: CSV + Card mapping, diagnostics, Debts CRUD, Regulars CRUD (+ Paid)

import uuid
import re
from typing import Dict, List, Optional, Tuple
from datetime import date as _date

import streamlit as st
import pandas as pd

from data import save_card_aliases
from helpers import normalize_csv, apply_card_mapping, auto_detect_card_names

# ---------- CSV & Card Mapping ----------
def csv_and_mapping_section(card_aliases: Dict[str, str]) -> Optional[pd.DataFrame]:
    """Upload CSV, show unmapped Payment modes, let user map to Card, and persist aliases."""
    file = st.file_uploader("Upload transactions CSV", type=["csv"])
    if not file:
        st.info("CSV must include columns: Date, Amount, Payment mode, type. Optional: Category, Note, Tags.")
        return None

    df = normalize_csv(file)
    if df is None or df.empty:
        st.error("CSV invalid or missing required columns.")
        return None

    # Card Mapping UI
    st.markdown("#### Card Mapping")
    st.caption("Map each **Payment mode** value to a Card name. Saved to `data/card_aliases.json`.")
    uniq_modes_df, _ = auto_detect_card_names(df)
    left, right = st.columns([2,2])

    with left:
        st.markdown("**Detected Payment modes**")
        st.dataframe(uniq_modes_df, use_container_width=True, hide_index=True, height=240)

    with right:
        st.markdown("**Mapping editor**")
        edit_df = pd.DataFrame({
            "Payment mode": uniq_modes_df["Payment mode"],
            "Card": [card_aliases.get(pm, "") for pm in uniq_modes_df["Payment mode"]]
        })
        edited = st.data_editor(
            edit_df,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "Payment mode": st.column_config.TextColumn(disabled=True),
                "Card": st.column_config.TextColumn(help="Type the Card name you want for this Payment mode"),
            },
            height=280
        )
        if st.button("💾 Save mapping"):
            new_aliases = {
                r["Payment mode"]: r["Card"].strip()
                for _, r in edited.iterrows() if r["Card"].strip()
            }
            # Keep existing keys not shown in current CSV
            for k, v in card_aliases.items():
                if k not in new_aliases:
                    new_aliases[k] = v
            save_card_aliases(new_aliases)
            st.success("Card mapping saved.")
            # Update passed-in dict in-place
            card_aliases.clear()
            card_aliases.update(new_aliases)

    mapped = apply_card_mapping(df, card_aliases)
    return mapped

# ---------- Diagnostics ----------
def diagnostics_section(df: Optional[pd.DataFrame], aliases: Dict[str, str]) -> None:
    if df is None or df.empty:
        st.info("Upload a CSV first to view diagnostics.")
        return

    st.markdown("**Mapped Card counts**")
    vc = (
        df["Card"].fillna("(unmapped)")
        .value_counts(dropna=False)
        .rename_axis("Card")
        .reset_index(name="count")
    )
    st.dataframe(vc, use_container_width=True, hide_index=True)

    unmapped = df.loc[df["Card"].isna(), ["Payment mode"]].drop_duplicates().sort_values("Payment mode")
    if not unmapped.empty:
        st.warning(f"{len(unmapped)} Payment mode value(s) are not mapped to any Card.")
        st.dataframe(unmapped, use_container_width=True, hide_index=True)

# ---------- Debts CRUD ----------
def debts_crud_section(items: List[dict]) -> Optional[List[dict]]:
    """
    items structure:
    { id, dtype, item, amount, due_day, tenure_left, outstanding }
    """
    st.markdown("### Current Debts")
    if items:
        st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)
    else:
        st.info("No debts yet.")

    st.markdown("### Add / Update")
    with st.form("debt_form", clear_on_submit=True):
        c1, c2, c3 = st.columns([2,1,1])
        dtype = c1.text_input("Type (e.g., Loan, Cred EMI)")
        item = c1.text_input("Item / Name")
        amount = c2.number_input("Monthly amount (₹)", min_value=0.0, value=0.0, step=0.01, format="%.2f")
        due_day = c3.number_input("Due day", min_value=1, max_value=31, value=10)
        tenure_left = c2.text_input("Tenure left (e.g., '12', '~95')", value="")
        outstanding = c3.number_input("Outstanding (₹)", min_value=0.0, value=0.0, step=0.01, format="%.2f")
        row_id = st.text_input("Existing ID (optional for update)", value="")
        ok = st.form_submit_button("Save")
        if ok:
            new = {
                "id": row_id.strip() or str(uuid.uuid4()),
                "dtype": dtype.strip(),
                "item": item.strip(),
                "amount": round(float(amount), 2),
                "due_day": int(due_day),
                "tenure_left": tenure_left.strip(),
                "outstanding": round(float(outstanding), 2),
            }
            updated = []
            found = False
            for r in items:
                if r.get("id") == new["id"]:
                    updated.append(new)
                    found = True
                else:
                    updated.append(r)
            if not found:
                updated.append(new)
            return updated

    if items:
        del_id = st.selectbox("Delete debt (select ID)", options=[""] + [r["id"] for r in items])
        if del_id and st.button("Delete selected debt", type="primary"):
            updated = [r for r in items if r["id"] != del_id]
            return updated

    return None

# ---------- Regulars CRUD + Paid toggles ----------
def _due_date_for_hint(y: int, m: int, hint: str) -> int:
    # Extract first number; clamp to month end
    try:
        d = int(re.sub(r"[^0-9]", "", hint) or "1")
    except Exception:
        d = 1
    import calendar
    last = calendar.monthrange(y, m)[1]
    return max(1, min(d, last))

def regulars_crud_section(items: List[dict], paid_flags: Dict[str, bool], ref_date: _date) -> Tuple[Optional[List[dict]], Optional[Dict[str, bool]]]:
    """
    items structure:
    { id, item, amount, date_hint }
    paid_flags: key = f"CASH::{item}::{YYYY-MM}" -> bool
    """
    y, m = ref_date.year, ref_date.month

    st.markdown("### Current Regular Expenses")
    if items:
        preview = []
        for r in items:
            due_day = _due_date_for_hint(y, m, r.get("date_hint","1"))
            preview.append({
                "id": r.get("id"),
                "item": r.get("item"),
                "amount": round(float(r.get("amount", 0.0)), 2),
                "date_hint": r.get("date_hint",""),
                "due_day (this month)": due_day
            })
        st.dataframe(pd.DataFrame(preview), use_container_width=True, hide_index=True)
    else:
        st.info("No regular expenses yet.")

    st.markdown("### Add / Update")
    with st.form("regular_form", clear_on_submit=True):
        c1, c2 = st.columns([2,1])
        item = c1.text_input("Item / Description")
        amount = c2.number_input("Amount (₹)", min_value=0.0, value=0.0, step=0.01, format="%.2f")
        date_hint = c2.text_input("Due day hint (e.g., '1', '9', '15')", value="1")
        row_id = st.text_input("Existing ID (optional for update)", value="")
        ok = st.form_submit_button("Save")
        if ok:
            new = {
                "id": row_id.strip() or str(uuid.uuid4()),
                "item": item.strip(),
                "amount": round(float(amount), 2),
                "date_hint": date_hint.strip(),
            }
            updated = []
            found = False
            for r in items:
                if r.get("id") == new["id"]:
                    updated.append(new)
                    found = True
                else:
                    updated.append(r)
            if not found:
                updated.append(new)
            return updated, None

    if items:
        del_id = st.selectbox("Delete regular (select ID)", options=[""] + [r["id"] for r in items])
        if del_id and st.button("Delete selected regular", type="primary"):
            updated = [r for r in items if r["id"] != del_id]
            return updated, None

    # Paid toggles (per month)
    st.markdown("### Toggle Paid (for selected month)")
    if items:
        table = []
        for r in items:
            due_day = _due_date_for_hint(y, m, r.get("date_hint","1"))
            key = f"CASH::{r.get('item','')}::{y}-{str(m).zfill(2)}"
            table.append((r, due_day, key))

        cols = st.columns([3, 2, 2, 1])
        cols[0].markdown("**Item**")
        cols[1].markdown("**Amount (₹)**")
        cols[2].markdown("**Due Day**")
        cols[3].markdown("**Paid?**")

        for r, due_day, key in table:
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            with c1: st.markdown(f"**{r.get('item','')}**")
            with c2: st.markdown(f"₹{float(r.get('amount',0.0)):.2f}")
            with c3: st.markdown(str(due_day))
            with c4:
                current = paid_flags.get(key, False)
                val = st.checkbox("", value=current, key=key, label_visibility="collapsed")
                paid_flags[key] = bool(val)

        if st.button("💾 Save Paid Flags"):
            return None, paid_flags

    return None, None
