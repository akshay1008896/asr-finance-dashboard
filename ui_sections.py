# ui_sections.py
import re
import json
import io
import numpy as np
import pandas as pd
import streamlit as st
import datetime as dt
from datetime import date

from helpers import (
    month_shift, months_back, override_key, get_active_cycles, detect_card,
    get_overridden_cycle, get_cycle_for_month, find_cycle_due_in_month, sum_liability,
)

# ---------- Diagnostics ----------
def diagnostics_section(df: pd.DataFrame, BILL_CYCLES):
    with st.expander("🔍 Detector diagnostics (Card mapping)", expanded=False):
        st.markdown("**Mapped Card counts**")
        st.dataframe(
            df["Card"].value_counts(dropna=False).rename_axis("Card").reset_index(name="count"),
            use_container_width=True
        )

        st.markdown("**Unmapped Payment modes**")
        if "Payment mode" not in df.columns:
            st.warning("Column 'Payment mode' not found after normalization.")
            unmapped = pd.DataFrame(columns=["Payment mode", "count"])
        else:
            unmapped = (
                df.loc[df["Card"].isna(), "Payment mode"]
                  .astype(str)
                  .replace({"": "(blank)", "nan": "(blank)", "None": "(blank)"})
                  .rename_axis("Payment mode")
                  .value_counts()
                  .reset_index(name="count")
            )

        if unmapped.empty:
            st.success("All Payment modes are mapped to cards.")
            return

        BANK_HINTS = {
            "axis": "Axis", "hdfc": "HDFC", "kotak": "Kotak", "icici": "ICICI",
            "sbi": "SBI", "hdfc bank": "HDFC", "bob": "BOB", "idfc": "IDFC",
            "yes": "Yes", "rbl": "RBL", "amex": "Amex", "hsbc": "HSBC", "onecard": "One"
        }
        def suggest(name: str) -> str:
            low = str(name).lower()
            for k, v in BANK_HINTS.items():
                if k in low:
                    return v if v in ["Amex","HSBC","One","ICICI","SBI"] else f"{v}"
            token = re.split(r"[^a-z0-9]+", low.strip())[0] or "Card"
            return token.title()

        unmapped["Suggested Card"] = unmapped["Payment mode"].apply(suggest)
        st.dataframe(unmapped.head(20), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### ⚡ Quick add mapping")
        with st.form("add_new_card_form", clear_on_submit=False):
            pm_choice = st.selectbox("Choose a Payment mode string to map", options=list(unmapped["Payment mode"]), index=0)
            sugg = suggest(pm_choice)
            new_card_name = st.text_input("New card name", value=sugg)
            st.caption("Define default cycle days for this new card (can be changed later).")
            c1, c2, c3, c4 = st.columns(4)
            start_day = c1.number_input("Cycle start day", 1, 31, value=22)
            end_day   = c2.number_input("Cycle end day (bill gen)", 1, 31, value=21)
            due_day   = c3.number_input("Due day", 1, 31, value=10)
            offset    = c4.number_input("Due offset (months)", 0, 2, value=1)
            submitted = st.form_submit_button("Add mapping")
            if submitted:
                st.session_state.auto_overrides[pm_choice] = new_card_name
                if new_card_name not in BILL_CYCLES and new_card_name not in st.session_state.new_card_cycles:
                    st.session_state.new_card_cycles[new_card_name] = (int(start_day), int(end_day), int(due_day), int(offset))
                st.success(f"Added mapping: **{pm_choice} → {new_card_name}** with cycle {start_day}/{end_day}, due {due_day}, offset {offset}")

        cexp3, cimp3 = st.columns(2)
        with cexp3:
            st.download_button(
                "Export auto mappings JSON",
                data=json.dumps({"auto_overrides": st.session_state.auto_overrides,
                                 "new_card_cycles": st.session_state.new_card_cycles}, indent=2),
                file_name="auto_mappings.json",
                mime="application/json",
                use_container_width=True
            )
        with cimp3:
            up3 = st.file_uploader("Import auto mappings JSON", type=["json"], key="auto_map_upl")
            if up3 is not None:
                try:
                    data = json.load(up3)
                    a = data.get("auto_overrides", {})
                    c = data.get("new_card_cycles", {})
                    if isinstance(a, dict):
                        st.session_state.auto_overrides.update(a)
                    if isinstance(c, dict):
                        for k, v in c.items():
                            if isinstance(v, (list, tuple)) and len(v) == 4:
                                st.session_state.new_card_cycles[k] = (int(v[0]), int(v[1]), int(v[2]), int(v[3]))
                        st.success("Auto mappings imported.")
                except Exception as e:
                    st.error(f"Failed to import: {e}")

# ---------- Inline starting balance overrides ----------
def start_balance_override_section(start_balance_sb: float, extra_buffer_sb: float):
    with st.expander("💵 Starting balance & Extra cash (overrides for simulator)", expanded=False):
        st.caption("These override the sidebar values **only** in the Cash Flow Simulator.")
        col_a, col_b = st.columns(2)
        st.session_state.override_start_bal = col_a.number_input(
            "Starting balance override (₹)", min_value=0.0, step=0.01,
            value=float(st.session_state.get("override_start_bal", start_balance_sb)),
            format="%.2f"
        )
        st.session_state.override_extra_buf = col_b.number_input(
            "Extra buffer override (₹)", min_value=0.0, step=0.01,
            value=float(st.session_state.get("override_extra_buf", extra_buffer_sb)),
            format="%.2f"
        )
    return st.session_state.override_start_bal, st.session_state.override_extra_buf

# ---------- Debt summary ----------
def debt_summary_section(DEBTS):
    st.subheader("🏦 Long-Term Debt & EMI Summary")
    debt_df = pd.DataFrame(DEBTS)
    total_outstanding_tracked = debt_df[debt_df["tenure_left"].apply(lambda x: isinstance(x, int))]["outstanding"].sum()
    total_emi = float(debt_df["amount"].sum())
    st.markdown(f"**Total Monthly EMI Outflow: ₹{total_emi:,.2f}**")
    st.markdown(f"**Total Tracked Outstanding (Excl. Home Loan): ₹{total_outstanding_tracked:,.2f}**")
    st.dataframe(
        debt_df.style.format({"amount": "₹{:,.2f}", "outstanding": "₹{:,.2f}"}),
        use_container_width=True, hide_index=True,
    )

# ---------- Per-card custom dates + month anchor ----------
def per_card_dates_editor_section(BILL_CYCLES, today: date):
    st.markdown("---")
    st.header("💳 Bills (choose your perspective)")
    sel_col1, sel_col2 = st.columns([1.2, 2])
    with sel_col1:
        bills_view = st.radio(
            "Month View (for this section)",
            options=["Previous", "Current", "Next", "Custom"],
            horizontal=True,
            index=1,
        )
    with sel_col2:
        st.caption("This changes the **month** for both tabs and the quick selector.")

    if bills_view == "Previous":
        bills_anchor = month_shift(today, -1)
    elif bills_view == "Next":
        bills_anchor = month_shift(today, +1)
    elif bills_view == "Custom":
        bills_anchor = st.date_input("Pick any date in the target month (Bills section only)", value=today, key="bills_anchor_custom")
    else:
        bills_anchor = today
    by_y, by_m = bills_anchor.year, bills_anchor.month

    # Per-card custom dates editor
    st.subheader(f"🗓 Per-card custom dates for {bills_anchor.strftime('%b %Y')}")
    with st.expander("Edit custom dates (optional) — overrides apply only to this month", expanded=False):
        edited_records = {}
        for card in sorted(BILL_CYCLES.keys() | st.session_state.new_card_cycles.keys()):
            cstart_d, cend_d, bill_d, due_d = get_overridden_cycle(card, by_y, by_m, BILL_CYCLES)
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
            if start_inp > end_inp:
                st.warning(f"{card}: Start after End; will swap on save.")
            edited_records[key] = {"start": start_inp.isoformat(), "end": end_inp.isoformat(), "due": due_inp.isoformat()}
        e1, e2, e3 = st.columns([1,1,2])
        with e1:
            if st.button("Save month overrides", use_container_width=True):
                fixed = {}
                for k, rec in edited_records.items():
                    s = dt.date.fromisoformat(rec["start"]); e = dt.date.fromisoformat(rec["end"])
                    if s > e: s, e = e, s
                    fixed[k] = {"start": s.isoformat(), "end": e.isoformat(), "due": rec["due"]}
                st.session_state.card_date_overrides.update(fixed)
                st.success("Saved per-card custom dates for this month.")
        with e2:
            if st.button("Clear overrides for this month", use_container_width=True):
                to_del = [k for k in st.session_state.card_date_overrides if k.startswith(f"{by_y:04d}-{by_m:02d}::")]
                for k in to_del: del st.session_state.card_date_overrides[k]
                st.success("Cleared overrides for this month.")
        with e3:
            cexp2, cimp2 = st.columns(2)
            with cexp2:
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
                            valid = {k: v for k, v in data.items() if k.startswith(f"{by_y:04d}-{by_m:02d}::")}
                            for k, rec in list(valid.items()):
                                if not isinstance(rec, dict) or not all(x in rec for x in ("start","end","due")):
                                    del valid[k]
                            st.session_state.card_date_overrides.update(valid)
                            st.success("Imported per-card dates for this month.")
                        else:
                            st.warning("Invalid JSON: expecting { 'YYYY-MM::Card': {start,end,due} }")
                    except Exception as e:
                        st.error(f"Failed to import: {e}")

    return bills_anchor, by_y, by_m

# ---------- Bills tabs ----------
def bills_tabs_section(df, BILL_CYCLES, bills_anchor, by_y, by_m):
    import pandas as pd
    tab_gen, tab_due = st.tabs(["Bills Generating in Selected Month", "Bills Due in Selected Month"])

    with tab_gen:
        rows_gen, per_card_gen = [], {}
        for card in sorted(BILL_CYCLES.keys() | st.session_state.new_card_cycles.keys()):
            cstart, cend, bill_dt, due_dt = get_overridden_cycle(card, by_y, by_m, BILL_CYCLES)
            sub, amount, txn_count = sum_liability(df, card, cstart, cend)
            per_card_gen[card] = {"window": (cstart, cend, bill_dt, due_dt), "df": sub, "amount": amount, "count": txn_count}
            rows_gen.append({
                "Card": card, "Cycle Start": cstart, "Cycle End (Bill Gen)": cend,
                "Due Date": due_dt, "Transactions": txn_count, "Cycle Liability (₹)": round(amount, 2)
            })
        card_gen_df = pd.DataFrame(rows_gen).sort_values(by="Due Date")
        def style_bill_gen(date_col):
            is_today_or_tomorrow = (date_col == bills_anchor) | (date_col == (bills_anchor + dt.timedelta(days=1)))
            return ['background-color: #fff3b0; font-weight: bold' if v else '' for v in is_today_or_tomorrow]
        st.caption(f"Cycles whose **bill is generated** in **{bills_anchor.strftime('%b %Y')}**.")
        st.dataframe(
            card_gen_df.style.apply(style_bill_gen, subset=["Cycle End (Bill Gen)"]).format({
                "Cycle Liability (₹)": "₹{:,.2f}"
            }),
            use_container_width=True, hide_index=True
        )

    with tab_due:
        rows_due, per_card_due, total_due_sel_month = [], {}, 0.0
        for card in sorted(BILL_CYCLES.keys() | st.session_state.new_card_cycles.keys()):
            cstart, cend, bill_dt, due_dt = find_cycle_due_in_month(card, by_y, by_m, BILL_CYCLES)
            sub, amount, txn_count = sum_liability(df, card, cstart, cend)
            per_card_due[card] = {"window": (cstart, cend, bill_dt, due_dt), "df": sub, "amount": amount, "count": txn_count}
            if (due_dt.month == by_m) and (due_dt.year == by_y):
                total_due_sel_month += amount
            rows_due.append({
                "Card": card, "Cycle Start": cstart, "Cycle End (Bill Gen)": cend,
                "Due Date": due_dt, "Transactions": txn_count, "Payable (₹)": round(amount, 2)
            })
        card_due_df = pd.DataFrame(rows_due).sort_values(by="Due Date")
        def style_due(date_col):
            is_today_or_tomorrow = (date_col == bills_anchor) | (date_col == (bills_anchor + dt.timedelta(days=1)))
            return ['background-color: #fff3b0; font-weight: bold' if v else '' for v in is_today_or_tomorrow]
        st.markdown(f"**Total CC Cash-Out in {bills_anchor.strftime('%b %Y')}: ₹{total_due_sel_month:,.2f}**")
        st.caption(f"Cycles whose **due date** falls in **{bills_anchor.strftime('%b %Y')}** (true cash-out).")
        st.dataframe(
            card_due_df.style.apply(style_due, subset=["Due Date"]).format({
                "Payable (₹)": "₹{:,.2f}"
            }),
            use_container_width=True, hide_index=True
        )

    return card_gen_df, card_due_df

# ---------- Quick due selector ----------
def quick_due_selector_section(df, BILL_CYCLES, bills_anchor):
    st.markdown("---")
    st.subheader("📅 Due-Month Quick Selector (Prev / Current / Next)")

    selector_col1, selector_col2 = st.columns([1.3, 2])
    with selector_col1:
        due_view = st.radio(
            "View bills **due** in which month (relative to above month)?",
            options=["Previous", "Current", "Next"], horizontal=True, index=1,
        )
    with selector_col2:
        st.caption(f"Base month: **{bills_anchor.strftime('%b %Y')}**. This selector shifts that base.")

    if due_view == "Previous":
        due_anchor = month_shift(bills_anchor, -1)
    elif due_view == "Next":
        due_anchor = month_shift(bills_anchor, +1)
    else:
        due_anchor = bills_anchor

    rows_quick, total_due_sel_month = [], 0.0
    for card in sorted(BILL_CYCLES.keys() | st.session_state.new_card_cycles.keys()):
        cstart, cend, bill_dt, due_dt = find_cycle_due_in_month(card, due_anchor.year, due_anchor.month, BILL_CYCLES)
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
            "Card": card, "Cycle Start": cstart, "Cycle End (Bill Gen)": cend,
            "Due Date": due_dt, "Payable (₹)": round(payable, 2)
        })
    quick_df = pd.DataFrame(rows_quick).sort_values(by="Due Date")
    def _style_due_sel(dt_col):
        is_sel = (dt_col.apply(lambda d: d.month == due_anchor.month and d.year == due_anchor.year))
        return ['background-color: #fff3b0; font-weight: bold' if v else '' for v in is_sel]
    st.markdown(
        f"**Total CC Cash-Out in {due_anchor.strftime('%b %Y')}: ₹{total_due_sel_month:,.2f}**  "
        f"| **View:** {due_view} (base: {bills_anchor.strftime('%b %Y')})"
    )
    st.dataframe(
        quick_df.style.apply(_style_due_sel, subset=["Due Date"]).format({
            "Payable (₹)": "₹{:,.2f}"
        }),
        use_container_width=True, hide_index=True
    )

# ---------- Regulars & Paid toggles ----------
def regulars_section(today: date, DEBTS, REGULARS):
    st.markdown("---")
    st.subheader("🗓️ Regular Expenses (incl. SIPs & Rent) — Toggle Paid")

    def month_range(y, m):
        import datetime as dt2
        from dateutil.relativedelta import relativedelta
        start = dt2.date(y, m, 1)
        end = start + relativedelta(months=1) - dt2.timedelta(days=1)
        return start, end

    def due_in_month(d_hint: str, y: int, m: int) -> date:
        import re, datetime as dt2
        d = int(re.sub(r"[^0-9]", "", d_hint) or "1")
        return dt2.date(y, m, min(d, month_range(y, m)[1].day))

    y, m = today.year, today.month
    all_cash_outs = []
    for r in REGULARS:
        all_cash_outs.append({
            "Item": r["item"], "Amount (₹)": round(float(r["amount"]), 2),
            "Due Date": due_in_month(r["date_hint"], y, m), "Type": "Regular"
        })
    for d in DEBTS:
        dday = int(re.sub(r"[^0-9]", "", str(d["due_day"])) or "1")
        all_cash_outs.append({
            "Item": d["item"], "Amount (₹)": round(float(d["amount"]), 2),
            "Due Date": date(y, m, min(dday, month_range(y, m)[1].day)), "Type": d["type"]
        })
    cash_out_df = pd.DataFrame(all_cash_outs).sort_values(by="Due Date")
    cash_out_df["Key"] = cash_out_df.apply(lambda r: f"CASH::{r['Item']}::{r['Due Date'].isoformat()}", axis=1)
    if "paid_flags" not in st.session_state:
        st.session_state.paid_flags = {}
    cash_out_df["Paid"] = cash_out_df["Key"].map(lambda k: st.session_state.paid_flags.get(k, False))

    cols = st.columns([3, 2, 2, 1])
    cols[0].markdown("**Item (Type)**")
    cols[1].markdown("**Amount (₹)**")
    cols[2].markdown("**Due Date**")
    cols[3].markdown("**Paid?**")
    for _, row in cash_out_df.iterrows():
        c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
        with c1: st.markdown(f"**{row['Item']}** ({row['Type']})")
        with c2: st.markdown(f"₹{float(row['Amount (₹)']):,.2f}")
        with c3: st.markdown(f"{row['Due Date'].strftime('%b %d, %Y')}")
        with c4:
            st.session_state.paid_flags[row["Key"]] = st.checkbox("", value=row["Paid"], key=row["Key"], label_visibility="collapsed")

    cash_out_df["Paid"] = cash_out_df["Key"].map(lambda k: st.session_state.paid_flags.get(k, False))
    return cash_out_df

# ---------- Cash flow ----------
def cashflow_section(df, BILL_CYCLES, today, salary_amount, salary_payday, cash_out_df, start_balance, extra_buffer):
    st.subheader("💰 Cash Flow Simulator (by date) — Due-month view (sidebar month)")

    balance = round(float(start_balance) + float(extra_buffer), 2)
    events = []

    # INCOME: salary
    if salary_amount and salary_amount > 0:
        from helpers import month_range
        s_day = min(int(salary_payday), month_range(today.year, today.month)[1].day)
        s_date = dt.date(today.year, today.month, s_day)
        events.append({"Date": s_date, "Event": "Salary", "Amount (₹)": round(float(salary_amount), 2), "Type": "Income", "flow": "in"})

    # INCOME: extra inflows in this month
    for rec in (st.session_state.extra_inflows or []):
        d = rec.get("Date")
        amt = round(float(rec.get("Amount", 0) or 0), 2)
        src = str(rec.get("Source", "") or "Extra")
        if isinstance(d, date) and (d.year == today.year) and (d.month == today.month) and amt > 0:
            events.append({"Date": d, "Event": f"Extra: {src}", "Amount (₹)": amt, "Type": "Income", "flow": "in"})

    # OUT: CC bills due
    rows_due_sidebar = []
    for card in sorted(BILL_CYCLES.keys() | st.session_state.new_card_cycles.keys()):
        cstart_s, cend_s, bill_dt_s, due_dt_s = find_cycle_due_in_month(card, today.year, today.month, BILL_CYCLES)
        mask_s = (
            (df["Card"] == card)
            & (df["type"].str.lower().eq("expense"))
            & (df["Amount"] > 0)
            & (df["Date"].dt.date >= cstart_s)
            & (df["Date"].dt.date <= cend_s)
        )
        payable_s = round(float(df.loc[mask_s, "Amount"].sum()), 2)
        if payable_s > 0:
            rows_due_sidebar.append((card, due_dt_s, payable_s))
    for card, dd, amt in rows_due_sidebar:
        if dd.month == today.month and dd.year == today.year:
            events.append({"Date": dd, "Event": f"{card} Bill Payment (CC)", "Amount (₹)": round(amt, 2), "Type": "CC Bill", "flow": "out"})

    # OUT: regulars/EMIs (unpaid)
    for _, r in cash_out_df.iterrows():
        if (not r["Paid"]) and (r["Due Date"].month == today.month) and (r["Due Date"].year == today.year):
            events.append({"Date": r["Due Date"], "Event": r["Item"], "Amount (₹)": round(float(r["Amount (₹)"]), 2), "Type": "Regular/EMI", "flow": "out"})

    # sort (incomes before outflows on same date)
    def _priority(e):
        return (e["Date"], 0 if e["flow"] == "in" else 1, e["Event"])
    events = sorted(events, key=_priority)

    rows2, total_in, total_out = [], 0.0, 0.0
    for ev in events:
        amt = round(float(ev["Amount (₹)"]), 2)
        if ev["flow"] == "in":
            balance = round(balance + amt, 2); total_in = round(total_in + amt, 2); disp = "+ " + f"₹{amt:,.2f}"
        else:
            balance = round(balance - amt, 2); total_out = round(total_out + amt, 2); disp = "- " + f"₹{amt:,.2f}"
        rows2.append([ev["Date"], ev["Event"], disp, round(balance, 2)])

    sim_df = pd.DataFrame(rows2, columns=["Date", "Event", "Amount (₹)", "Balance After (₹)"])

    def style_low_balance(df_in: pd.DataFrame):
        styles = pd.DataFrame('', index=df_in.index, columns=df_in.columns)
        styles.loc[df_in['Balance After (₹)'] < 0, 'Balance After (₹)'] = 'background-color: #ffcccc; color: red; font-weight: bold'
        styles.loc[(df_in['Balance After (₹)'] >= 0) & (df_in['Balance After (₹)'] < float(st.session_state.get('override_extra_buf', 0))) , 'Balance After (₹)'] = 'background-color: #ffefcc'
        return styles

    st.markdown(
        f"**Starting Cash Balance:** ₹{float(start_balance):,.2f}  "
        f"| **Buffer:** ₹{float(extra_buffer):,.2f}  "
        f"| **Inflows:** ₹{total_in:,.2f}  "
        f"| **Outflows:** ₹{total_out:,.2f}  "
        f"| **Net Change:** ₹{(total_in - total_out):,.2f}"
    )
    st.dataframe(
        sim_df.style.apply(style_low_balance, axis=None).format({
            "Balance After (₹)": "₹{:,.2f}"
        }),
        use_container_width=True, hide_index=True
    )

# ---------- Expenses by card ----------
def expenses_by_card_section(df, BILL_CYCLES, today):
    st.markdown("---")
    st.header("🧾 Expenses by Card (cycle that **generates** in selected month)")
    summary_rows = []
    per_card_transactions = {}
    for card in sorted(BILL_CYCLES.keys() | st.session_state.new_card_cycles.keys()):
        cstart, cend, bill_dt, due_dt = get_overridden_cycle(card, today.year, today.month, BILL_CYCLES)
        mask = (
            (df["Card"] == card)
            & (df["type"].str.lower().eq("expense"))
            & (df["Amount"] > 0)
            & (df["Date"].dt.date >= cstart)
            & (df["Date"].dt.date <= cend)
        )
        sub = df.loc[mask, ["Date", "Category", "Amount", "Note", "Payment mode", "Tags"]].copy().sort_values("Date")
        if not sub.empty:
            sub["Amount"] = sub["Amount"].round(2)
        amount = round(float(sub["Amount"].sum() if not sub.empty else 0.0), 2)
        txn_count = int(sub.shape[0])
        per_card_transactions[card] = {"window": (cstart, cend, bill_dt, due_dt), "df": sub, "amount": amount, "count": txn_count}
        summary_rows.append({
            "Card": card, "Transactions": txn_count, "Cycle Liability (₹)": round(amount, 2),
            "Cycle Start": cstart, "Cycle End (Bill Gen)": cend, "Due Date": due_dt
        })
    summary_df = pd.DataFrame(summary_rows)
    st.dataframe(
        summary_df.style.format({"Cycle Liability (₹)": "₹{:,.2f}"}),
        use_container_width=True, hide_index=True
    )
    for card in sorted(BILL_CYCLES.keys() | st.session_state.new_card_cycles.keys()):
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
                    category_breakdown.assign(Amount=lambda d: d["Amount"].round(2)).style.format({
                        "Amount": "₹{:,.2f}",
                        "% of Total": "{:.1f}%"
                    }),
                    use_container_width=True, hide_index=True
                )
                st.markdown("**Transactions (Cycle Window)**")
                st.dataframe(sub.assign(Amount=sub["Amount"].round(2)).style.format({"Amount": "₹{:,.2f}"}),
                             use_container_width=True, hide_index=True)
                buf = io.StringIO()
                sub_export = sub.copy()
                sub_export["Amount"] = sub_export["Amount"].round(2)
                sub_export.to_csv(buf, index=False)
                st.download_button(
                    f"Download {card} Cycle Transactions CSV",
                    data=buf.getvalue(),
                    file_name=f"{card}_cycle_{cstart}_to_{cend}.csv",
                    mime="text/csv"
                )

# ---------- Merchants ----------
def merchants_section(df, BILL_CYCLES, today):
    st.markdown("---")
    st.header("🏷️ Top Merchants per Card — choose analysis window")
    window_choice = st.radio("Window", ["Current Cycle (Generating Month)", "Last 3 months", "Last 6 months", "Last 12 months"], horizontal=True, index=1)
    use_current_cycle = (window_choice == "Current Cycle (Generating Month)")
    if not use_current_cycle:
        nmap = {"Last 3 months": 3, "Last 6 months": 6, "Last 12 months": 12}
        global_start, global_end = months_back(nmap[window_choice], today)
    for card in sorted(BILL_CYCLES.keys() | st.session_state.new_card_cycles.keys()):
        if use_current_cycle:
            cstart, cend, _, _ = get_overridden_cycle(card, today.year, today.month, BILL_CYCLES)
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
                st.dataframe(top.head(10).assign(Amount=lambda d: d["Amount"].round(2))
                            .style.format({"Amount": "₹{:,.2f}"}),
                            use_container_width=True, hide_index=True)
                buf = io.StringIO()
                top_export = top.copy()
                top_export["Amount"] = top_export["Amount"].round(2)
                top_export.to_csv(buf, index=False)
                st.download_button(
                    f"Download Top Merchants — {card}",
                    data=buf.getvalue(),
                    file_name=f"top_merchants_{card}_{window_choice.replace(' ', '_')}.csv",
                    mime="text/csv"
                )

# ---------- Trends ----------
def trends_section(monthly: pd.DataFrame, BILL_CYCLES, today: date):
    st.markdown("---")
    st.header("📈 Monthly Trends, MoM % Change, & Anomalies")

    window = st.radio("Window", ["Last 6 months", "Last 12 months", "All Time"], horizontal=True, index=1)
    exclude_current_month_from_anomaly = st.checkbox("Exclude selected month from anomaly calculations", value=True)
    n_months = 12 if window != "Last 6 months" else 6
    m = monthly.copy()
    if window != "All Time" and m.shape[0] > n_months:
        m = m.iloc[-n_months:, :]

    available_cards = sorted([c for c in m.columns if pd.notna(c) and (c in BILL_CYCLES or c in st.session_state.new_card_cycles)])
    selected_cards = st.multiselect("Choose cards to analyze", options=available_cards, default=available_cards)
    if not selected_cards:
        st.info("Select at least one card to analyze monthly trends.")
        return

    mom = m.pct_change().replace([np.inf, -np.inf], np.nan) * 100.0
    combined_df = m.copy()
    for card in selected_cards:
        combined_df[f"{card} MoM %"] = mom[card]
    combined_df = combined_df[sorted(combined_df.columns)].copy().round(2)

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
        return df_out

    st.subheader("📊 Trend Chart")
    st.line_chart(m[selected_cards].copy())

    st.subheader("Monthly Totals (₹) and MoM % Change")
    format_dict = {c: "₹{:,.2f}" for c in m.columns}
    format_dict.update({c: "{:.1f}%" for c in combined_df.columns if "MoM %" in c})
    st.dataframe(
        combined_df.style.apply(style_anomalies_and_caps, axis=None).format(format_dict),
        use_container_width=True
    )
    st.download_button(
        "Download Monthly Trends Data (CSV)",
        data=m[selected_cards].round(2).to_csv().encode('utf-8'),
        file_name=f"monthly_trends_{'all' if window=='All Time' else str(n_months)+'m'}.csv",
        mime="text/csv"
    )

# ---------- 1-Year Plan (added) ----------
def plan_section(DEBTS, REGULARS):
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
        p1_emi = float(debt_p1["amount"])
        p1_tenure = debt_p1["tenure_left"]
        cash_flow_increase = p1_emi
        total_sip = sum(r['amount'] for r in REGULARS if 'SIP' in r['item'])

        st.subheader("1. Debt Clearance Strategy (Snowball for Cash Flow)")
        st.markdown(f"""
- **Phase 1:** Focus on **{debt_p1['item']}** (Outstanding: ₹{float(debt_p1['outstanding']):,.2f}; Tenure left: {p1_tenure}).
- **Action:** Continue ₹{p1_emi:,.2f}/mo for {p1_tenure} months; then roll that EMI to the next debt.
- **Cash-Flow Unlock:** **₹{cash_flow_increase:,.2f}/mo** freed post-clearance.

**Current Monthly SIPs:** ₹{float(total_sip):,.2f}
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
