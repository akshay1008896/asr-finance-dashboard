import uuid
import re
from typing import Dict, List, Optional, Tuple
from datetime import date as _date

import streamlit as st
import pandas as pd

from data import save_card_aliases
from helpers import (
    normalize_csv, apply_card_mapping, unique_payment_modes,
    shift_month, cycle_window_for_month, card_bill_due_in_month, sum_liability
)

# CSV & Card mapping
def csv_and_mapping_section(card_aliases: Dict[str, str]) -> Optional[pd.DataFrame]:
    file = st.file_uploader("Upload transactions CSV", type=["csv"])
    if not file:
        st.info("CSV must include columns: Date, Amount, Payment mode, type. Optional: Category, Note, Tags.")
        return None
    df = normalize_csv(file)
    if df is None or df.empty:
        st.error("CSV invalid or missing required columns.")
        return None
    st.markdown("#### Card Mapping (Payment mode → Card)")
    modes_df = unique_payment_modes(df)
    c1, c2 = st.columns([2, 2])
    with c1:
        st.markdown("**Detected Payment modes**")
        st.dataframe(modes_df, use_container_width=True, hide_index=True, height=240)
    with c2:
        st.markdown("**Mapping editor**")
        edit_df = pd.DataFrame({
            "Payment mode": modes_df["Payment mode"],
            "Card": [card_aliases.get(pm, "") for pm in modes_df["Payment mode"]],
        })
        edited = st.data_editor(
            edit_df, use_container_width=True, hide_index=True, num_rows="dynamic",
            column_config={
                "Payment mode": st.column_config.TextColumn(disabled=True),
                "Card": st.column_config.TextColumn(help="Type the Card name you want for this Payment mode"),
            },
            height=280
        )
        if st.button("💾 Save mapping"):
            new_aliases = {r["Payment mode"]: r["Card"].strip()
                           for _, r in edited.iterrows() if r["Card"].strip()}
            for k, v in card_aliases.items():
                if k not in new_aliases:
                    new_aliases[k] = v
            save_card_aliases(new_aliases)
            st.success("Card mapping saved.")
            card_aliases.clear()
            card_aliases.update(new_aliases)
    return apply_card_mapping(df, card_aliases)

# Diagnostics
def diagnostics_section(df: Optional[pd.DataFrame], aliases: Dict[str, str]) -> None:
    if df is None or df.empty:
        st.info("Upload a CSV first to view diagnostics.")
        return
    st.markdown("**Mapped Card counts**")
    vc = df["Card"].fillna("(unmapped)").value_counts(dropna=False).rename_axis("Card").reset_index(name="count")
    st.dataframe(vc, use_container_width=True, hide_index=True)
    unmapped = df.loc[df["Card"].isna(), ["Payment mode"]].drop_duplicates().sort_values("Payment mode")
    if not unmapped.empty:
        st.warning(f"{len(unmapped)} Payment mode value(s) are not mapped to any Card.")
        st.dataframe(unmapped, use_container_width=True, hide_index=True)

# Cards CRUD
def cards_crud_section(items: List[dict]) -> Optional[List[dict]]:
    st.markdown("### Current Cards & Cycles")
    if items:
        st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)
    else:
        st.info("No cards yet. Add one below.")
    st.markdown("### Add / Update")
    with st.form("card_form", clear_on_submit=True):
        c1, c2, c3 = st.columns([2, 1, 1])
        name = c1.text_input("Card Name (e.g., Amex, ICICI)")
        start_day = c2.number_input("Cycle Start Day", min_value=1, max_value=31, value=22)
        end_day   = c3.number_input("Cycle End Day (Bill Gen)", min_value=1, max_value=31, value=21)
        due_day   = c2.number_input("Due Day", min_value=1, max_value=31, value=8)
        due_off   = c3.number_input("Due Offset (months)", min_value=0, max_value=3, value=1)
        row_id    = st.text_input("Existing ID (optional for update)", value="")
        ok = st.form_submit_button("Save")
        if ok:
            new = {
                "id": row_id.strip() or str(uuid.uuid4()),
                "name": name.strip(),
                "start_day": int(start_day),
                "end_day": int(end_day),
                "due_day": int(due_day),
                "due_offset": int(due_off),
            }
            updated, found = [], False
            for r in items:
                if r.get("id") == new["id"]:
                    updated.append(new); found = True
                else:
                    updated.append(r)
            if not found:
                updated.append(new)
            return updated
    if items:
        del_id = st.selectbox("Delete card (select ID)", options=[""] + [r["id"] for r in items])
        if del_id and st.button("Delete selected card", type="primary"):
            updated = [r for r in items if r["id"] != del_id]
            return updated
    return None

# Bills (Generating vs Due)
def bills_section(df: Optional[pd.DataFrame], cards: List[dict], ref_date: _date) -> None:
    if df is None or df.empty:
        st.info("Upload & map your CSV first to see bills.")
        return
    if not cards:
        st.info("Add at least one card (with cycle details) to compute bills.")
        return
    s1, s2 = st.columns([1.2, 2])
    with s1:
        view = st.radio(
            "Bills month view",
            options=["Previous", "Current", "Next", "Custom"],
            index=1, horizontal=True,
            help="Controls the month used for both tabs and the quick selector."
        )
    if view == "Previous":
        anchor = shift_month(ref_date, -1)
    elif view == "Next":
        anchor = shift_month(ref_date, +1)
    elif view == "Custom":
        anchor = st.date_input("Pick any date in the target month", value=ref_date, key="bills_anchor_custom")
    else:
        anchor = ref_date
    y, m = anchor.year, anchor.month
    tab_gen, tab_due = st.tabs(["Bills Generating in Selected Month", "Bills Due in Selected Month"])
    with tab_gen:
        rows_gen = []
        for c in cards:
            cstart, cend, bill_dt, due_dt = cycle_window_for_month(c, y, m)
            sub, amount, txn_count = sum_liability(df, c["name"], cstart, cend)
            rows_gen.append({
                "Card": c["name"], "Cycle Start": cstart, "Cycle End (Bill Gen)": cend,
                "Due Date": due_dt, "Transactions": txn_count, "Cycle Liability (₹)": round(amount, 2),
                "Due Offset (m)": c["due_offset"]
            })
        gen_df = pd.DataFrame(rows_gen).sort_values("Due Date")
        st.caption(f"Cycles whose **bill is generated** in **{anchor.strftime('%b %Y')}**.")
        st.dataframe(
            gen_df, use_container_width=True, hide_index=True,
            column_config={"Cycle Liability (₹)": st.column_config.NumberColumn(format="₹%,.2f")}
        )
    with tab_due:
        rows_due, total_due = [], 0.0
        for c in cards:
            cstart, cend, bill_dt, due_dt = card_bill_due_in_month(c, anchor)
            sub, amount, txn_count = sum_liability(df, c["name"], cstart, cend)
            if (due_dt.year == y) and (due_dt.month == m):
                total_due += amount
            rows_due.append({
                "Card": c["name"], "Cycle Start": cstart, "Cycle End (Bill Gen)": cend,
                "Due Date": due_dt, "Transactions": txn_count, "Payable (₹)": round(amount, 2),
                "Due Offset (m)": c["due_offset"]
            })
        due_df = pd.DataFrame(rows_due).sort_values("Due Date")
        st.markdown(f"**Total CC Cash-Out in {anchor.strftime('%b %Y')}: ₹{total_due:,.2f}**")
        st.caption("Cycles whose **due date** falls in the selected month (true cash-out).")
        st.dataframe(
            due_df, use_container_width=True, hide_index=True,
            column_config={"Payable (₹)": st.column_config.NumberColumn(format="₹%,.2f")}
        )
    st.markdown("---")
    st.subheader("📅 Due-Month Quick Selector (relative to above)")
    q1, q2 = st.columns([1.3, 2])
    with q1:
        qview = st.radio(
            "View bills due in which month?",
            options=["Previous", "Current", "Next"], index=1, horizontal=True
        )
    if qview == "Previous":
        due_anchor = shift_month(anchor, -1)
    elif qview == "Next":
        due_anchor = shift_month(anchor, +1)
    else:
        due_anchor = anchor
    rows_quick, total_q = [], 0.0
    for c in cards:
        cstart, cend, bill_dt, due_dt = card_bill_due_in_month(c, due_anchor)
        _, amount, _ = sum_liability(df, c["name"], cstart, cend)
        if (due_dt.year == due_anchor.year) and (due_dt.month == due_anchor.month):
            total_q += amount
        rows_quick.append({
            "Card": c["name"], "Cycle Start": cstart, "Cycle End (Bill Gen)": cend,
            "Due Date": due_dt, "Payable (₹)": round(amount, 2), "Due Offset (m)": c["due_offset"]
        })
    quick_df = pd.DataFrame(rows_quick).sort_values("Due Date")
    st.markdown(f"**Total CC Cash-Out in {due_anchor.strftime('%b %Y')}: ₹{total_q:,.2f}** | Base: {anchor.strftime('%b %Y')}")
    st.dataframe(
        quick_df, use_container_width=True, hide_index=True,
        column_config={"Payable (₹)": st.column_config.NumberColumn(format="₹%,.2f")}
    )

# Debts CRUD
def debts_crud_section(items: List[dict]) -> Optional[List[dict]]:
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
            updated, found = [], False
            for r in items:
                if r.get("id") == new["id"]:
                    updated.append(new); found = True
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

# Regulars CRUD + Paid toggles
def _due_day_from_hint(y: int, m: int, hint: str) -> int:
    try:
        d = int(re.sub(r"[^0-9]", "", hint) or "1")
    except Exception:
        d = 1
    import calendar
    last = calendar.monthrange(y, m)[1]
    return max(1, min(d, last))

def regulars_crud_section(items: List[dict], paid_flags: Dict[str, bool], ref_date: _date) -> Tuple[Optional[List[dict]], Optional[Dict[str, bool]]]:
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
        row_id = st.text_input("Existing ID (optional for update)", value="")
        ok = st.form_submit_button("Save")
        if ok:
            new = {
                "id": row_id.strip() or str(uuid.uuid4()),
                "item": item.strip(),
                "amount": round(float(amount), 2),
                "date_hint": date_hint.strip(),
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
        if st.button("💾 Save Paid Flags"):
            return None, paid_flags
    return None, None
