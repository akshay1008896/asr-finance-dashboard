import io
import re
import json
import datetime as dt
from datetime import date
import numpy as np
import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta

st.set_page_config(page_title="ASR Finance Dashboard", layout="wide")
st.title("📊 ASR Finance Dashboard — Bills, SIPs, & Cash Flow")

with st.expander("How to use (read this first)", expanded=False):
    st.markdown("""
1) **Upload your CSV** — columns: Date, Category, Amount, Note, type, Payment mode, To payment mode, Tags.
2) Pick a **Reference month** (any date in that month). We compute each card's **billing cycle that ends in that month**.
3) Use these sections:
    - **Long-Term Debt Summary** (NEW)
    - **Credit Card Dues** (cycle totals → due next month)
    - **Regular Expenses** (toggle Paid)
    - **Cash Flow Simulator** (date-wise)
    - **Expenses by Card** (cycle transactions + category breakdown + CSV)
    - **Top Merchants per Card** (choose analysis window)
    - **Monthly Trends (by Card)** (MoM %, anomaly highlight, budget caps)
""")

# ---------------------------
# Config / Rules
# ---------------------------
# (cycle_start_day, cycle_end_day, due_day, due_offset_months)
BILL_CYCLES = {
    "Amex": (22, 21, 10, 1), 
    "HSBC": (19, 18, 5, 1),
    "HSBC Cash": (8, 7, 27, 0),
    # UPDATED: ICICI cycle from 10th to 9th, due 29th of the same month (offset 0)
    "ICICI": (10, 9, 29, 0), 
    "One": (19, 18, 8, 1),
    "SBI": (25, 24, 13, 1),
}

# Long-Term Debts & EMIs
DEBTS = [
    {"type": "Cred EMIs", "item": "Movers & Packers", "amount": 23567, "due_day": 25, "tenure_left": 2, "outstanding": 47134},
    {"type": "Cred EMIs", "item": "CC & ITR", "amount": 18273, "due_day": 28, "tenure_left": 13, "outstanding": 237549},
    {"type": "Loans", "item": "Wedding Loan", "amount": 33400, "due_day": 18, "tenure_left": 19, "outstanding": 634600},
    {"type": "Loans", "item": "Home Loan EMI", "amount": 19000, "due_day": 20, "tenure_left": "~95", "outstanding": 1805000},
]

# Regular Monthly Expenses (excluding EMIs, but including SIPs and Rent)
REGULARS = [
    {"item": "Papa", "amount": 40000, "date_hint": "1"},
    {"item": "House Rent", "amount": 40000, "date_hint": "1"},
    {"item": "SIP – 3rd", "amount": 2000, "date_hint": "3"},
    {"item": "SIP – 9th", "amount": 10500, "date_hint": "9"},
    {"item": "SIP – 11th", "amount": 500, "date_hint": "11"},
]

# ---------------------------
# Helpers
# ---------------------------
def detect_card(payment_mode: str):
    """
    Map free-text `Payment mode` into canonical card names.
    Prioritize explicit card names over general keywords.
    """
    text = str(payment_mode or "").lower()

    # 1. Explicit matches for known card names/prefixes
    if any(k in text for k in ["amex", "plat", "3. may amex"]):
        return "Amex"
    
    # 2. ICICI / ICI
    if any(k in text for k in ["ici", "icici", "2.feb ici"]):
        return "ICICI"
    
    # 3. SBI
    if any(k in text for k in ["sbi", "1. jan sbi"]):
        return "SBI"

    # 4. OneCard (OnceCard)
    if any(k in text for k in ["oncecard", "one", "5. oncecard"]):
        if "closed" in text:
            return None 
        return "One"

    # 5. HSBC/HSBCL - Distinguish between generic HSBC and the Cash/Cashback/HSBCL one
    if any(k in text for k in ["hsbcl", "4. jun hsbcl", "hsbc cash", "cashback"]):
        return "HSBC Cash"
    if "hsbc" in text:
        return "HSBC"
    
    return None

def month_range(y, m):
    """Returns (start_date, end_date) for a given year/month."""
    start = dt.date(y, m, 1)
    end = start + relativedelta(months=1) - dt.timedelta(days=1)
    return start, end

def safe_date(year: int, month: int, day: int):
    """Return a valid date by clamping day to the last day of the month when needed."""
    last_day = month_range(year, month)[1].day
    return dt.date(year, month, min(day, last_day))

def cycle_window_for_month(card: str, year: int, month: int):
    """Return (cycle_start_date, cycle_end_date, bill_generation_date, due_date) for the cycle that ENDS in `year-month`."""
    start_day, end_day, due_day, due_offset = BILL_CYCLES[card]
    # Cycle End Date (Bill Generation Date) - clamp to valid day for month
    cycle_end = safe_date(year, month, end_day)
    bill_month, bill_year = month, year

    # Cycle Start Date
    start_date = safe_date(year, month, start_day)
    if start_day > end_day:
        cycle_start = start_date - relativedelta(months=1)
    else:
        cycle_start = start_date

    # Due Date (apply offset, handle year rollover) and clamp day
    due_month = bill_month + due_offset
    due_year = bill_year
    if due_month > 12:
        due_month -= 12
        due_year += 1

    due_dt = safe_date(due_year, due_month, due_day)
    bill_dt = cycle_end

    return cycle_start, cycle_end, bill_dt, due_dt

def months_back(n, ref_date):
    """Return (start_date, end_date) for the last n months window including the month of ref_date."""
    end = dt.date(ref_date.year, ref_date.month, month_range(ref_date.year, ref_date.month)[1].day)
    start = end - relativedelta(months=n) + relativedelta(days=1)
    return start, end


def _find_cycle_containing_date(card: str, target_date: dt.date):
    """Return the cycle (start,end,bill_dt,due_dt) that contains target_date.

    The function checks the cycle for the month of target_date and its immediate neighbors
    (previous and next month) and returns the cycle where cycle_start <= target_date <= cycle_end.
    If none match, return the cycle for the month of target_date.
    """
    year = target_date.year
    month = target_date.month

    # try current, previous, next
    for offset in (0, -1, 1):
        y = (dt.date(year, month, 1) + relativedelta(months=offset)).year
        m = (dt.date(year, month, 1) + relativedelta(months=offset)).month
        try:
            cstart, cend, bill_dt, due_dt = cycle_window_for_month(card, y, m)
        except Exception:
            # fallback to naive cycle for current month if something unexpected occurs
            cstart, cend, bill_dt, due_dt = cycle_window_for_month(card, year, month)

        if cstart <= target_date <= cend:
            return cstart, cend, bill_dt, due_dt

    # default to cycle for the target month
    return cycle_window_for_month(card, year, month)


def choose_card_cycle(df: pd.DataFrame, card: str, ref_date: date):
    """Choose the most relevant cycle for `card` based on transactions in `df`.

    Behavior:
    - If the card has no transactions, fall back to the cycle that ends in ref_date's month.
    - Otherwise, find the cycle that contains the card's last transaction date. If the last
      transaction appears to be a payment (negative amount or type contains 'payment'/'credit'/'refund'),
      consider the next cycle (advance by one month) since the bill was likely paid and the next cycle is active.
    """
    # default
    y, m = ref_date.year, ref_date.month

    card_txns = df[df["Card"] == card]
    if card_txns.empty:
        return cycle_window_for_month(card, y, m)

    last_row = card_txns.sort_values("Date").iloc[-1]
    last_date = last_row["Date"].date()

    # detect if last txn is likely a payment
    last_type = str(last_row.get("type", "")).lower()
    last_amount = float(last_row.get("Amount", 0.0))
    is_payment_like = (last_amount < 0) or any(k in last_type for k in ("payment", "credit", "refund"))

    if is_payment_like:
        # advance to next calendar month and return that cycle
        next_dt = last_date + relativedelta(months=1)
        try:
            return cycle_window_for_month(card, next_dt.year, next_dt.month)
        except Exception:
            return cycle_window_for_month(card, y, m)

    # otherwise return the cycle that contains the last transaction
    return _find_cycle_containing_date(card, last_date)

# ---------------------------
# Sidebar: Budget Caps
# ---------------------------
st.sidebar.header("⚙️ Budget Caps (per card)")
budget_caps = {}
for card in BILL_CYCLES.keys():
    budget_caps[card] = st.sidebar.number_input(
        f"{card} cap (₹)", min_value=0, value=250000 if card == "Amex" else 0, step=1000, help="0 = no cap check"
    )

# ---------------------------
# Inputs
# ---------------------------
uploaded = st.file_uploader("Upload your transactions CSV", type=["csv"])
colA, colB, colC = st.columns([1,1,1])
with colA:
    today = st.date_input("Reference month (choose any date in month)", value=date.today())
with colB:
    starting_balance = st.number_input("Starting balance for month (₹)", min_value=0, value=0, step=1000)
with colC:
    extra_buffer = st.number_input("Extra buffer (₹)", min_value=0, value=50000, step=500)

if "paid_flags" not in st.session_state:
    st.session_state.paid_flags = {}

# ---------------------------
# Main Logic
# ---------------------------
if uploaded is not None:
    df = pd.read_csv(uploaded)

    # Validate required columns (include 'type' since many parts of the app filter by it)
    required_cols = {"Date", "Amount", "Payment mode", "type"}
    missing = required_cols.difference(df.columns)
    if missing:
        st.error(f"CSV missing required columns: {missing}")
        st.stop()

    # Ensure optional columns exist so later lookups won't KeyError
    for opt_col in ["Category", "Note", "Tags"]:
        if opt_col not in df.columns:
            df[opt_col] = ""

    # Clean + map cards
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    # Ensure Amount is numeric to allow sums and comparisons
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0)
    # Normalize type column to string and fill NAs
    df["type"] = df["type"].fillna("").astype(str)
    df["Card"] = df["Payment mode"].apply(detect_card)
    df = df[df["Date"].notna()].copy() # Filter out rows with invalid dates

    # Detector diagnostics
    with st.expander("🧪 Detector diagnostics (Card mapping)", expanded=False):
        st.write("Mapped Card counts:")
        st.dataframe(
            df["Card"].value_counts(dropna=False).rename_axis("Card").reset_index(name="count"),
            use_container_width=True
        )

    # -------- Long-Term Debt Summary --------
    st.subheader("🏦 Long-Term Debt & EMI Summary")
    debt_df = pd.DataFrame(DEBTS)
    total_outstanding = debt_df[debt_df["tenure_left"].apply(lambda x: isinstance(x, int))]["outstanding"].sum()
    total_emi = debt_df["amount"].sum()
    
    st.markdown(f"**Total Monthly EMI Outflow: ₹{total_emi:,.2f}**")
    st.markdown(f"**Total Tracked Outstanding (Excl. Home Loan): ₹{total_outstanding:,.2f}**")
    
    st.dataframe(
        debt_df.style.format({
            "Monthly (₹)": "₹{:,.0f}",
            "Outstanding (₹)": "₹{:,.0f}"
        }).set_caption("Note: Home Loan Tenure/Outstanding are approximations."),
        use_container_width=True,
        hide_index=True,
        column_config={
            "amount": st.column_config.NumberColumn("Monthly (₹)"),
            "due_day": st.column_config.TextColumn("Due Day"),
            "outstanding": st.column_config.NumberColumn("Outstanding (₹)"),
            "tenure_left": st.column_config.TextColumn("Tenure Left")
        }
    )

    # -------- Per-card cycle totals for chosen month --------
    y, m = today.year, today.month
    rows = []
    per_card_transactions = {}
    total_next_due = 0

    for card in BILL_CYCLES.keys():
        # choose cycle dynamically for each card based on its last transaction
        cstart, cend, bill_dt, due_dt = choose_card_cycle(df, card, today)

        # We look at expenses from the start of the cycle up to 'today' for the current liability.
        # Use inclusive start so transactions on cycle start date are included.
        mask = (df["Card"] == card) & (df["Date"].dt.date >= cstart) & (df["Date"].dt.date <= today)

        sub = df.loc[mask & (df["type"] == "Expense"), ["Date", "Category", "Amount", "Note", "Payment mode", "Tags"]].copy().sort_values("Date")

        amount = float(sub["Amount"].sum()) if not sub.empty else 0.0
        txn_count = int(sub.shape[0])

        per_card_transactions[card] = {"window": (cstart, cend, bill_dt, due_dt), "df": sub, "amount": amount, "count": txn_count}

        # The bill is generated this month (due next month) if the Cycle End is this card's cycle end month.
        if cend.month == m and cend.year == y:
            total_next_due += amount

        rows.append({
            "Card": card,
            "Cycle Start": cstart,
            "Cycle End (Bill Gen)": cend,
            "Due Date": due_dt,
            "Transactions": txn_count,
            "Current Liability (₹)": round(amount, 2)
        })
        
    card_due_df = pd.DataFrame(rows).sort_values(by="Due Date")

    st.subheader("💳 Credit Card Dues (cycle that ends this month → due next month)")
    st.markdown(f"**Total Estimated Cash-Out for Next Month (Bills Generated {today.strftime('%b')}): ₹{total_next_due:,.2f}**")
    
    def style_bill_gen(date_col):
        is_today_or_tomorrow = (date_col == date.today()) | (date_col == date.today() + dt.timedelta(days=1))
        return ['background-color: yellow; font-weight: bold' if v else '' for v in is_today_or_tomorrow]

    st.dataframe(
        card_due_df.style.apply(style_bill_gen, subset=["Cycle End (Bill Gen)"]), 
        use_container_width=True,
        hide_index=True,
        column_config={
            "Current Liability (₹)": st.column_config.NumberColumn(format="₹%,.2f")
        }
    )

    # -------- Regular Expenses with Paid toggles --------
    st.subheader("🗓️ Regular Expenses (incl. SIPs & Rent) - Toggle Paid to exclude from cash-out")
    
    # Combine REGULARS and DEBTS for display/toggling
    all_cash_outs = []
    for r in REGULARS:
        due = dt.date(y, m, min(int(r["date_hint"]), month_range(y, m)[1].day))
        all_cash_outs.append({"Item": r["item"], "Amount (₹)": r["amount"], "Due Date": due, "Type": "Regular"})
    
    for d in DEBTS:
        due = dt.date(y, m, min(int(d["due_day"]), month_range(y, m)[1].day))
        all_cash_outs.append({"Item": d["item"], "Amount (₹)": d["amount"], "Due Date": due, "Type": d["type"]})
        
    cash_out_df = pd.DataFrame(all_cash_outs).sort_values(by="Due Date")
    
    # Apply session state logic for paid status
    cash_out_df["Key"] = cash_out_df.apply(lambda r: f"CASH::{r['Item']}::{r['Due Date'].isoformat()}", axis=1)
    cash_out_df["Paid"] = cash_out_df["Key"].map(lambda k: st.session_state.paid_flags.get(k, False))
    
    cols = st.columns([3, 2, 2, 1])
    cols[0].markdown("**Item (Type)**")
    cols[1].markdown("**Amount (₹)**")
    cols[2].markdown("**Due Date**")
    cols[3].markdown("**Paid?**")

    for i, row in cash_out_df.iterrows():
        c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
        with c1: st.markdown(f"**{row['Item']}** ({row['Type']})")
        with c2: st.markdown(f"₹{row['Amount (₹)']:,}")
        with c3: st.markdown(f"{row['Due Date'].strftime('%b %d, %Y')}")
        with c4:
            paid = st.checkbox("", value=row["Paid"], key=row["Key"], label_visibility="collapsed")
            st.session_state.paid_flags[row["Key"]] = paid
    
    cash_out_df["Paid"] = cash_out_df["Key"].map(lambda k: st.session_state.paid_flags.get(k, False))

    # -------- Cash Flow Simulator --------
    st.subheader("💰 Cash Flow Simulator (by date)")
    
    balance = starting_balance + extra_buffer
    events = []
    
    # a) Credit Card Bills 
    for _, r in card_due_df.iterrows():
        # Only show the bill payment due date, not bill generation
        if r["Due Date"].month == today.month: 
             events.append({"Date": r["Due Date"], "Event": f"{r['Card']} Bill Payment (CC)", "Amount (₹)": r["Current Liability (₹)"], "Type": "CC Bill"})
    
    # b) Other Cash Outs (Regulars and EMIs)
    for _, r in cash_out_df.iterrows():
        if not r["Paid"] and r["Due Date"].month == today.month:
            events.append({"Date": r["Due Date"], "Event": r["Item"], "Amount (₹)": r["Amount (₹)"], "Type": r["Type"]})

    ev_df = pd.DataFrame(events).sort_values(by="Date").drop_duplicates(subset=["Date", "Event"]) # Drop potential duplicates
    rows2 = []
    for _, ev in ev_df.iterrows():
        balance -= ev["Amount (₹)"]
        rows2.append([ev["Date"], ev["Event"], ev["Amount (₹)"], round(balance, 2)])
        
    sim_df = pd.DataFrame(rows2, columns=["Date", "Event", "Amount (₹)", "Balance After (₹)"])
    
    def style_low_balance(df_in):
        styles = pd.DataFrame('', index=df_in.index, columns=df_in.columns)
        # Low balance highlight
        styles.loc[df_in['Balance After (₹)'] < 0, 'Balance After (₹)'] = 'background-color: #ffcccc; color: red; font-weight: bold'
        styles.loc[(df_in['Balance After (₹)'] >= 0) & (df_in['Balance After (₹)'] < extra_buffer), 'Balance After (₹)'] = 'background-color: #ffefcc'
        return styles

    st.markdown(f"**Starting Cash Balance: ₹{starting_balance:,.2f}** (with Buffer: ₹{extra_buffer:,.2f})")
    st.dataframe(
        sim_df.style.apply(style_low_balance, axis=None).format({
            "Amount (₹)": "₹{:,.2f}",
            "Balance After (₹)": "₹{:,.2f}",
            "Date": lambda x: x.strftime('%b %d')
        }), 
        use_container_width=True,
        hide_index=True
    )
    
    # -------- Expenses by Card (detailed) --------
    st.markdown("---")
    st.header("🧾 Expenses by Card (for this cycle)")
    st.caption("Transactions included in each card's cycle window up to today.")
    
    summary_df = card_due_df[["Card","Transactions","Current Liability (₹)","Cycle Start","Cycle End (Bill Gen)","Due Date"]].copy()
    st.dataframe(
        summary_df, 
        use_container_width=True,
        hide_index=True,
        column_config={"Current Liability (₹)": st.column_config.NumberColumn(format="₹%,.2f")}
    )

    for card in BILL_CYCLES.keys():
        detail = per_card_transactions[card]
        cstart, cend, bill_dt, due_dt = detail["window"]
        sub = detail["df"]
        
        category_breakdown = sub.groupby("Category")["Amount"].sum().reset_index().sort_values("Amount", ascending=False)
        category_breakdown["% of Total"] = (category_breakdown["Amount"] / detail['amount']) * 100
        
        expander_title = f"{card} | Due: {due_dt.strftime('%b %d')} | Liability: ₹{detail['amount']:,.2f} | Txns: {detail['count']}"
        with st.expander(expander_title):
            if sub.empty:
                st.info("No transactions for this cycle yet.")
            else:
                st.markdown("**Category Breakdown**")
                st.dataframe(
                    category_breakdown.style.format({
                        "Amount": "₹{:,.0f}",
                        "% of Total": "{:.1f}%"
                    }), 
                    use_container_width=True,
                    hide_index=True
                )
                
                st.markdown("**Transactions (Cycle Window)**")
                st.dataframe(sub.style.format({"Amount": "₹{:,.0f}"}), use_container_width=True, hide_index=True)
                
                csv_buf = io.StringIO()
                sub.to_csv(csv_buf, index=False)
                st.download_button(
                    f"Download {card} Cycle Transactions CSV",
                    data=csv_buf.getvalue(),
                    file_name=f"{card}_cycle_{cstart}_to_{cend}.csv",
                    mime="text/csv"
                )

    # -------- Top Merchants per Card (selectable window) --------
    st.markdown("---")
    st.header("🏷️ Top Merchants per Card — choose analysis window")
    window_choice = st.radio("Window", ["Current Cycle", "Last 3 months", "Last 6 months", "Last 12 months"], horizontal=True, index=1)

    if window_choice == "Current Cycle":
        pass 
    else:
        nmap = {"Last 3 months": 3, "Last 6 months": 6, "Last 12 months": 12}
        global_start, global_end = months_back(nmap[window_choice], today)

    for card in BILL_CYCLES.keys():
        if window_choice == "Current Cycle":
            cstart, _, _, _ = per_card_transactions[card]["window"]
            mask = (df["Card"] == card) & (df["Date"].dt.date > cstart) & (df["Date"].dt.date <= today)
            window_label = f"{cstart} → {today}"
        else:
            mask = (df["Card"] == card) & (df["Date"].dt.date >= global_start) & (df["Date"].dt.date <= global_end)
            window_label = f"{global_start} → {global_end}"

        sub = df.loc[mask & (df["type"] == "Expense"), ["Date","Category","Note","Amount"]].copy()
        
        with st.expander(f"**{card}** — Top Merchants | Window: {window_label}"):
            if sub.empty:
                st.info("No expense transactions in this window.")
            else:
                top = sub.groupby(["Category","Note"], dropna=False)["Amount"].sum().reset_index().sort_values("Amount", ascending=False)
                st.dataframe(top.head(10).style.format({"Amount": "₹{:,.0f}"}), use_container_width=True, hide_index=True)
                
                buf = io.StringIO()
                top.to_csv(buf, index=False)
                st.download_button(
                    f"Download Top Merchants — {card}",
                    data=buf.getvalue(),
                    file_name=f"top_merchants_{card}_{window_choice.replace(' ', '_')}.csv",
                    mime="text/csv"
                )

    # -------- Monthly Trends (by Card) with MoM %, Anomaly, Budget Caps --------
    st.markdown("---")
    st.header("📈 Monthly Trends, MoM % Change, & Anomalies")
    st.caption("Rolling monthly totals for expense transactions; anomalies (>1.5× median) and over-cap highlighted. Use sidebar to set caps.")

    trends_df = df.copy()
    trends_df = trends_df[trends_df["type"] == "Expense"]
    trends_df["YYYY-MM"] = trends_df["Date"].dt.to_period("M").astype(str)
    
    trends_df = trends_df[trends_df["Card"].notna()]
    monthly = (
        trends_df.groupby(["YYYY-MM", "Card"])["Amount"]
        .sum()
        .reset_index()
        .pivot(index="YYYY-MM", columns="Card", values="Amount")
        .fillna(0.0)
        .sort_index()
    )

    window = st.radio("Window", ["Last 6 months", "Last 12 months", "All Time"], horizontal=True, index=1)
    n_months = 12
    if window == "Last 6 months":
        n_months = 6
    if window != "All Time" and monthly.shape[0] > n_months:
        monthly = monthly.iloc[-n_months:, :]

    available_cards = sorted([c for c in monthly.columns if pd.notna(c) and c in BILL_CYCLES.keys()])
    selected_cards = st.multiselect("Choose cards to analyze", options=available_cards, default=available_cards)

    mom = monthly.pct_change().replace([np.inf, -np.inf], np.nan) * 100.0
    
    combined_df = monthly.copy()
    for card in selected_cards:
        combined_df[f"{card} MoM %"] = mom[card]
        
    combined_df = combined_df[sorted(combined_df.columns)].copy()

    def style_anomalies_and_caps(df_in: pd.DataFrame):
        df_out = pd.DataFrame('', index=df_in.index, columns=df_in.columns)
        
        for col in [c for c in df_in.columns if "MoM %" not in c]:
            data_series = df_in[col].iloc[:-1] if df_in.index[-1].startswith(str(date.today().year) + '-' + str(date.today().month).zfill(2)) else df_in[col]
            med = data_series[data_series > 0].median()
            
            if med > 0:
                is_anom = df_in[col] > 1.5 * med
                df_out.loc[is_anom, col] = "background-color: #f7a5a5; font-weight: bold"

            cap = budget_caps.get(col, 0) or 0
            if cap > 0:
                is_over_cap = df_in[col] > cap
                df_out.loc[is_over_cap, col] = "background-color: #ffcccc; font-weight: bold"
            
            mom_col = f"{col} MoM %"
            if mom_col in df_in.columns:
                is_high_mom = (df_in[mom_col] > 50) & (df_in[col] > med * 1.1)
                df_out.loc[is_high_mom, mom_col] = "background-color: #d1f7c4; font-weight: bold"

        return df_out

    if selected_cards:
        st.subheader("📊 Trend Chart")
        plot_df = monthly[selected_cards].copy()
        st.line_chart(plot_df)

        st.subheader("Monthly Totals (₹) and MoM % Change")
        
        format_dict = {c: "₹{:,.0f}" for c in monthly.columns}
        format_dict.update({c: "{:.1f}%" for c in combined_df.columns if "MoM %" in c})
        
        st.dataframe(
            combined_df.style.apply(style_anomalies_and_caps, axis=None).format(format_dict), 
            use_container_width=True
        )
        
        st.download_button(
            "Download Monthly Trends Data (CSV)", 
            data=monthly[selected_cards].to_csv().encode('utf-8'),
            file_name=f"monthly_trends_{n_months}m.csv", 
            mime="text/csv"
        )
    else:
        st.info("Select at least one card to analyze monthly trends.")

    # -------- Debt Reduction Suggestions & Investment Strategy (Dynamic) --------
    st.markdown("---")
    st.header("🎯 1-Year Financial Action Plan: Debt & Investment")
    
    # Dynamic Debt Calculation
    unsecured_debt = debt_df[debt_df["item"] != "Home Loan EMI"].sort_values("tenure_left")
    
    debt_p1 = unsecured_debt.iloc[0] if not unsecured_debt.empty else None
    
    if debt_p1 is not None and isinstance(debt_p1["tenure_left"], (int, float)):
        # Calculate the potential cash flow increase using the Snowball method (clearing shortest tenure first)
        p1_emi = debt_p1["amount"]
        p1_tenure = debt_p1["tenure_left"]
        
        cash_flow_increase = p1_emi
        
        st.subheader("1. Debt Clearance Strategy (Snowball for Cash Flow)")
        st.markdown(f"""
        Your primary goal for the next 12 months should be to **maximize free monthly cash flow** to improve your Debt-to-Income (DTI) ratio for the new ₹1.6 Cr home loan.

        * **Phase 1: Attack the Shortest Debt.** Your smallest or shortest-tenure loan is **{debt_p1['item']}** (₹{debt_p1['outstanding']:,.0f} outstanding).
        * **Action:** Continue paying the EMI of **₹{p1_emi:,.0f}** for **{p1_tenure} more months**.
        * **Result:** Once cleared, you must immediately roll the entire **₹{cash_flow_increase:,.0f}** into the next debt (**{unsecured_debt.iloc[1]['item']}**). This "snowball" effect will accelerate all subsequent payments, drastically reducing your unsecured debt before the home loan application.
        
        **Total Current Monthly SIPs:** ₹{sum(r['amount'] for r in REGULARS if 'SIP' in r['item'])}
        """)
        
        st.subheader("2. Investment Strategy for 1-Year Goal (Safety First)")
        st.markdown(f"""
        With a short **1-year horizon** for your ₹40 Lakh down payment and additional closing costs, **capital preservation** is paramount. Traditional equity SIPs (stocks, high-risk mutual funds) are too volatile and should **not** be used for your down payment fund.

        | Fund Purpose | Risk Profile | Recommended Indian Instrument | Why This Choice? |
        | :--- | :--- | :--- | :--- |
        | **Down Payment Fund (₹40 Lakh)** | **LOW** | **Liquid Funds / Ultra Short Duration Debt Funds** | Offers better post-tax returns than a bank account while maintaining high liquidity and very low volatility. Your capital is safe. |
        | **New Monthly Savings** (from cleared debt/budget cuts) | **LOW** | **Corporate Bond Funds** or **Fixed Deposits (FDs)** | Slightly higher returns than liquid funds, suitable for the **new monthly cash** you generate for closing costs (₹3-5 Lakh buffer). |
        | **Existing SIPs** (₹{sum(r['amount'] for r in REGULARS if 'SIP' in r['item']):,.0f}/month) | **HIGH/MODERATE** | **Continue your existing SIPs**. | These funds are for long-term goals (5+ years). Do **not** stop these or redirect them to your short-term home goal. |

        **Key Action:** Move your ₹40 Lakh down payment from any high-risk investment (like a volatile stock or balanced fund) immediately into the recommended **Liquid/Ultra Short Duration Funds**.
        """)

    else:
        st.info("No short-term unsecured debt data available for generating a dynamic reduction plan.")
        st.markdown(
        """
        **General Guidance:**
        1. **Prioritize High-Interest Debt:** If you have any debt, attack the one with the highest interest rate (Avalanche method) to save the most money overall, or the one with the lowest outstanding balance (Snowball method) to free up cash flow quickly. For a 1-year home loan application, **freeing up cash flow (Snowball)** is usually more impactful.
        2. **Investments:** For a goal that is **less than 3 years away**, always choose **low-risk instruments** like **Liquid Mutual Funds** or **Short-Term Fixed Deposits** to protect your capital. Avoid equity markets entirely for short-term goals.
        """
        )

else:
    st.info("Upload your transactions CSV to begin.")