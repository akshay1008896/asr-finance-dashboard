import uuid
import re
import streamlit as st
import pandas as pd
from typing import List, Dict, Optional, Tuple
from datetime import date as _date
from helpers import card_bill_due_in_month, sum_liability

def _due_day_from_hint(y: int, m: int, hint: str) -> int:
    try:
        d = int(re.sub(r"[^0-9]", "", hint) or "1")
    except Exception:
        d = 1
    import calendar
    last = calendar.monthrange(y, m)[1]
    return max(1, min(d, last))

def regulars_crud_section(items: List[dict], paid_flags: Dict[str, bool],
                          ref_date: _date, cards: List[dict], overrides: List[dict],
                          df: Optional[pd.DataFrame]):
    y, m = ref_date.year, ref_date.month
    st.markdown("### Current Regular Expenses")
    if items:
        preview = []
        for r in items:
            due_day = _due_day_from_hint(y, m, r.get("date_hint","1"))
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
        date_hint = c2.text_input("Due day hint (e.g., '1','9','15')", value="1")
        with st.expander("Optional custom fields (key/value)", expanded=False):
            extra_keys = st.text_area("Keys (comma-separated)", value="")
            extra_vals = st.text_area("Values (comma-separated)", value="")
        row_id = st.text_input("Existing ID (optional for update)", value="")
        ok = st.form_submit_button("Save")
        if ok:
            extra = {}
            if extra_keys.strip():
                k_list = [k.strip() for k in extra_keys.split(",")]
                v_list = [v.strip() for v in extra_vals.split(",")] if extra_vals.strip() else []
                for i, k in enumerate(k_list):
                    extra[k] = v_list[i] if i < len(v_list) else ""
            new = {
                "id": row_id.strip() or str(uuid.uuid4()),
                "item": item.strip(),
                "amount": round(float(amount), 2),
                "date_hint": date_hint.strip(),
                "extra": extra,
            }
            updated, found = [], False
            for r in items:
                if r.get("id") == new["id"]:
                    updated.append(new); found = True
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

    st.markdown("### Toggle Paid (for selected month)")

    # 1. Render regular expense toggles
    if items:
        cols = st.columns([3, 2, 2, 1])
        cols[0].markdown("**Item**")
        cols[1].markdown("**Amount (₹)**")
        cols[2].markdown("**Due Day**")
        cols[3].markdown("**Paid?**")
        for r in items:
            due_day = _due_day_from_hint(y, m, r.get("date_hint","1"))
            key = f"CASH::{r.get('item','')}::{y}-{str(m).zfill(2)}"
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            with c1: st.markdown(f"**{r.get('item','')}**")
            with c2: st.markdown(f"₹{float(r.get('amount',0.0)):.2f}")
            with c3: st.markdown(str(due_day))
            with c4:
                current = paid_flags.get(key, False)
                val = st.checkbox("", value=current, key=key, label_visibility="collapsed")
                paid_flags[key] = bool(val)

    # 2. Compute and render credit card dues toggles
    card_dues = []
    if df is not None and not df.empty:
        for card in cards:
            cstart, cend, _, due_dt = card_bill_due_in_month(card, ref_date, overrides)
            _, amount, _ = sum_liability(df, card["name"], cstart, cend)
            if amount > 0 and due_dt.year == y and due_dt.month == m:
                card_dues.append({"card_name": card["name"], "amount": round(amount, 2), "due_day": due_dt.day})

    if card_dues:
        st.markdown("**Credit Card Bills**")
        for cd in card_dues:
            key = f"CC::{cd['card_name']}::{y}-{str(m).zfill(2)}"
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            with c1:
                st.markdown(f"**{cd['card_name']} (CC)**")
            with c2:
                st.markdown(f"₹{cd['amount']:.2f}")
            with c3:
                st.markdown(str(cd['due_day']))
            with c4:
                current = paid_flags.get(key, False)
                val = st.checkbox("", value=current, key=key, label_visibility="collapsed")
                paid_flags[key] = bool(val)

    # Save flags
    if st.button("💾 Save Paid Flags"):
        return None, paid_flags

    return None, None
