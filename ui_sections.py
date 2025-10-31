# ui_sections.py
# All Streamlit UI components: CSV mapping, diagnostics, CRUD screens, bills, overrides, trends, card-paid toggles

import uuid
import re
from typing import Dict, List, Optional, Tuple
from datetime import date as _date

import streamlit as st
import pandas as pd

from data import save_card_aliases
from helpers import (
    normalize_csv, apply_card_mapping, unique_payment_modes,
    shift_month, get_effective_cycle, card_bill_due_in_month, sum_liability,
    monthly_totals
)

# CSV & Card mapping
def csv_and_mapping_section(card_aliases: Dict[str, str]) -> Optional[pd.DataFrame]:
    file = st.file_uploader("Upload transactions CSV", type=["csv"])
    if not file:
        st.info("CSV must include: Date, Amount, Payment mode, type. Optional: Category, Note, Tags.")
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
        with st.expander("Optional custom fields (key/value)", expanded=False):
            extra_keys = st.text_area("Keys (comma-separated)", value="", help="e.g., limit, bank, last4")
            extra_vals = st.text_area("Values (comma-separated)", value="", help="e.g., 250000, ICICI, 1234")

        row_id    = st.text_input("Existing ID (optional for update)", value="")
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
                "name": name.strip(),
                "start_day": int(start_day),
                "end_day": int(end_day),
                "due_day": int(due_day),
                "due_offset": int(due_off),
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
            return updated

    if items:
        del_id = st.selectbox("Delete card (select ID)", options=[""] + [r["id"] for r in items])
        if del_id and st.button("Delete selected card", type="primary"):
            updated = [r for r in items if r["id"] != del_id]
            return updated
    return None

# Per-card overrides CRUD
def overrides_crud_section(cards: List[dict], overrides: List[dict], ref_date: _date) -> Optional[List[dict]]:
    if not cards:
        st.info("Add a card first.")
        return None

    y, m = ref_date.year, ref_date.month
    this_month = [ov for ov in overrides if ov.get("year")==y and ov.get("month")==m]
    st.markdown(f"### Overrides for {ref_date.strftime('%b %Y')}")
    if this_month:
        show = []
        for ov in this_month:
            card = next((c for c in cards if c["id"]==ov["card_id"]), {"name":"(unknown)"})
            show.append({
                "id": ov["id"], "card_id": ov["card_id"], "card_name": card["name"],
                "year": ov["year"], "month": ov["month"],
                "cycle_start": ov["cycle_start"], "cycle_end": ov["cycle_end"], "due_date": ov["due_date"]
            })
        st.dataframe(pd.DataFrame(show), use_container_width=True, hide_index=True)
    else:
        st.info("No overrides for this month.")

    st.markdown("### Add / Update Override (for selected month)")
    with st.form("override_form", clear_on_submit=True):
        card_choice = st.selectbox("Card", cards, format_func=lambda c: c["name"])
        cs = st.date_input("Cycle Start", value=_date(y, m, 1))
        ce = st.date_input("Cycle End (bill gen)", value=_date(y, m, 1))
        dd = st.date_input("Due Date", value=_date(y, m, 1))
        row_id = st.text_input("Existing Override ID (optional for update)", value="")
        ok = st.form_submit_button("Save")
        if ok:
            new = {
                "id": row_id.strip() or str(uuid.uuid4()),
                "card_id": card_choice["id"],
                "year": y, "month": m,
                "cycle_start": cs.isoformat(),
                "cycle_end": ce.isoformat(),
                "due_date": dd.isoformat(),
            }
            updated, found = [], False
            for r in overrides:
                if r.get("id")==new["id"]:
                    updated.append(new); found=True
                else:
                    updated.append(r)
            if not found:
                updated.append(new)
            return updated

    if overrides:
        del_id = st.selectbox("Delete override (select ID)", options=[""] + [r["id"] for r in overrides])
        if del_id and st.button("Delete selected override", type="primary"):
            updated = [r for r in overrides if r["id"] != del_id]
            return updated
    return None

# Bills + Cashflow
def bills_section(df: Optional[pd.DataFrame], cards: List[dict], overrides: List[dict],
                  ref_date: _date, start_balance: float, extra_cash: float) -> None:
    if df is None or df.empty:
        st.info("Upload & map your CSV first to see bills.")
        return
    if not cards:
        st.info("Add at least one card to compute bills.")
        return

    s1, s2 = st.columns([1.2, 2])
    with s1:
        view = st.radio("Bills month view", options=["Previous", "Current", "Next", "Custom"],
                        index=1, horizontal=True)
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

    # Tab: generating
    with tab_gen:
        rows_gen = []
        for c in cards:
            cstart, cend, bill_dt, due_dt = get_effective_cycle(c, y, m, overrides)
            sub, amount, txn_count = sum_liability(df, c["name"], cstart, cend)
            rows_gen.append({
                "Card": c["name"],
                "Cycle Start": cstart, "Cycle End (Bill Gen)": cend,
                "Due Date": due_dt, "Transactions": txn_count,
                "Cycle Liability (₹)": round(amount, 2),
                "Due Offset (m)": c["due_offset"]
            })
        gen_df = pd.DataFrame(rows_gen).sort_values("Due Date")
        st.caption(f"Cycles whose **bill is generated** in **{anchor.strftime('%b %Y')}**.")
        st.dataframe(
            gen_df, use_container_width=True, hide_index=True,
            column_config={"Cycle Liability (₹)": st.column_config.NumberColumn(format="₹%,.2f")}
        )

    # Tab: due
    with tab_due:
        rows_due, total_due = [], 0.0
        for c in cards:
            cstart, cend, bill_dt, due_dt = card_bill_due_in_month(c, anchor, overrides)
            sub, amount, txn_count = sum_liability(df, c["name"], cstart, cend)
            if (due_dt.year == y) and (due_dt.month == m):
                total_due += amount
            rows_due.append({
                "Card": c["name"],
                "Cycle Start": cstart, "Cycle End (Bill Gen)": cend,
                "Due Date": due_dt, "Transactions": txn_count,
                "Payable (₹)": round(amount, 2),
                "Due Offset (m)": c["due_offset"]
            })
        due_df = pd.DataFrame(rows_due).sort_values("Due Date")
        st.markdown(f"**Total CC Cash-Out in {anchor.strftime('%b %Y')}: ₹{total_due:,.2f}**")
        st.caption("Cycles whose **due date** falls in the selected month (true cash-out).")
        st.dataframe(
            due_df, use_container_width=True, hide_index=True,
            column_config={"Payable (₹)": st.column_config.NumberColumn(format="₹%,.2f")}
        )

    st.markdown("### 💰 Cash Flow Simulator (due-month view)")
    balance = float(start_balance) + float(extra_cash)
    events = []
    for _, r in due_df.iterrows():
        events.append({"Date": r["Due Date"], "Event": f"{r['Card']} Bill", "Amount (₹)": float(r["Payable (₹)"])})

    if events:
        ev_df = pd.DataFrame(events).sort_values(by="Date")
        out_rows = []
        for _, ev in ev_df.iterrows():
            balance -= ev["Amount (₹)"]
            out_rows.append([ev["Date"], ev["Event"], round(ev["Amount (₹)"], 2), round(balance, 2)])
        sim_df = pd.DataFrame(out_rows, columns=["Date", "Event", "Amount (₹)", "Balance After (₹)"])
        def _style(df_in: pd.DataFrame):
            styles = pd.DataFrame('', index=df_in.index, columns=df_in.columns)
            styles.loc[df_in['Balance After (₹)'] < 0, 'Balance After (₹)'] = 'background-color: #ffcccc; color: red; font-weight: bold'
            return styles
        st.dataframe(sim_df.style.apply(_style, axis=None).format({
            "Amount (₹)": "₹{:,.2f}", "Balance After (₹)": "₹{:,.2f}",
            "Date": lambda x: x.strftime('%b %d')
        }), use_container_width=True, hide_index=True)
    else:
        st.info("No bill events for the selected month.")

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
                "dtype": dtype.strip(),
                "item": item.strip(),
                "amount": round(float(amount), 2),
                "due_day": int(due_day),
                "tenure_left": tenure_left.strip(),
                "outstanding": round(float(outstanding), 2),
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
            return updated

    if items:
        del_id = st.selectbox("Delete debt (select ID)", options=[""] + [r["id"] for r in items])
        if del_id and st.button("Delete selected debt", type="primary"):
            updated = [r for r in items if r["id"] != del_id]
            return updated
    return None

# Regulars CRUD + Credit Card Paid toggles
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

# Trends
def trends_section(df: Optional[pd.DataFrame]) -> None:
    g = monthly_totals(df)
    if g is None or g.empty:
        st.info("No expense data to show trends yet.")
        return

    window = st.radio("Window", ["Last 6 months", "Last 12 months", "All Time"], horizontal=True, index=1)
    n_months = 12 if window != "Last 6 months" else 6
    if window != "All Time" and g.shape[0] > n_months:
        g = g.iloc[-n_months:, :]

    available_cards = sorted([c for c in g.columns if pd.notna(c)])
    selected_cards = st.multiselect("Choose cards to analyze", options=available_cards, default=available_cards)
    if not selected_cards:
        st.info("Select at least one card.")
        return

    st.subheader("📊 Trend Chart")
    st.line_chart(g[selected_cards].copy())

    mom = g.pct_change().replace([float("inf"), float("-inf")], pd.NA) * 100.0
    combined = g.copy()
    for c in selected_cards:
        combined[f"{c} MoM %"] = mom[c]

    fmt = {c: "₹{:,.0f}" for c in g.columns}
    fmt.update({c: "{:.1f}%" for c in combined.columns if "MoM %" in c})
    st.subheader("Monthly Totals (₹) and MoM % Change")
    st.dataframe(combined.style.format(fmt), use_container_width=True)
