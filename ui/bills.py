import streamlit as st
import pandas as pd
from datetime import date as _date
from typing import List, Optional
from helpers import shift_month, get_effective_cycle, sum_liability, card_bill_due_in_month

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
