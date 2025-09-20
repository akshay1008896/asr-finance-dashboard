import io
import json
import datetime as dt
from datetime import date
import pandas as pd
import numpy as np
import streamlit as st

st.set_page_config(page_title="ASR Finance Dashboard", layout="wide")
st.title("📊 ASR Finance Dashboard — Bills, SIPs, & Cash Flow")

with st.expander("How to use (read this first)", expanded=False):
    st.markdown("""
1) **Upload your CSV** — same format as you shared (Date, Category, Amount, Note, type, Payment mode, To payment mode, Tags).
2) Choose a **Reference month** (any date in that month). We compute each card's **billing cycle that ends in that month**.
3) See **Credit Card Dues**, **Regular Expenses**, and the **Cash Flow Simulator**.
4) **Expenses by Card** — full transaction tables per card for the computed cycles + category breakdowns and CSV downloads.
5) **Monthly Trends (by Card)** — monthly totals + MoM % change, anomaly highlights (>1.5× median), and **Budget Caps** (sidebar).
6) **Top Merchants per Card** — grouped by Category + Note; choose analysis window (cycle / 3 / 6 / 12 months).
""")

# ---------------------------
# Utility
# ---------------------------
CARD_RULES = {
    "Amex": ["Amex", "Plat"],
    "HSBC": ["HSBC"],
    "HSBC Cash": ["HSBCL"],
    "ICICI": ["ICI"],
    "One": ["OnceCard", "One"],
    "SBI": ["SBI"]
}

BILL_CYCLES = {
    # (cycle_start_day, cycle_end_day, due_day, due_offset_months)
    "Amex": (22, 21, 12, 1),
    "HSBC": (19, 18, 5, 1),
    "HSBC Cash": (8, 7, 22, 0),
    "ICICI": (16, 15, 1, 1),
    "One": (19, 18, 5, 1),
    "SBI": (25, 24, 13, 1),
}

REGULARS = [
    {"item": "Papa", "amount": 40000, "date_hint": "1"},
    {"item": "Home Loan EMI", "amount": 19000, "date_hint": "20"},
    {"item": "House Rent", "amount": 40000, "date_hint": "1"},
    {"item": "Wedding EMI", "amount": 33400, "date_hint": "18"},
    {"item": "SIP – 3rd", "amount": 2000, "date_hint": "3"},
    {"item": "SIP – 9th", "amount": 10500, "date_hint": "9"},
    {"item": "SIP – 11th", "amount": 500, "date_hint": "11"},
    {"item": "Cred – CC & ITR", "amount": 18273, "date_hint": "28"},
]

def detect_card(payment_mode: str):
    text = str(payment_mode or "").lower()
    for card, keys in CARD_RULES.items():
        for k in keys:
            if k.lower() in text:
                return card
    return None

def month_range(y, m):
    start = dt.date(y, m, 1)
    if m == 12:
        end = dt.date(y+1, 1, 1) - dt.timedelta(days=1)
    else:
        end = dt.date(y, m+1, 1) - dt.timedelta(days=1)
    return start, end

def cycle_window_for_month(card: str, year: int, month: int):
    """Return (cycle_start_date, cycle_end_date, bill_generation_date, due_date) for the cycle that ENDS in `year-month`."""
    start_day, end_day, due_day, due_offset = BILL_CYCLES[card]
    if month == 1:
        cycle_start = dt.date(year-1, 12, start_day)
    else:
        cycle_start = dt.date(year, month-1, start_day)
    cycle_end = dt.date(year, month, end_day)
    bill_month, bill_year = month, year
    due_month = bill_month + due_offset
    due_year = bill_year
    if due_month > 12:
        due_month -= 12
        due_year += 1
    return cycle_start, cycle_end, dt.date(bill_year, bill_month, due_day), dt.date(due_year, due_month, due_day)

# ---------------------------
# Sidebar: Budget Caps
# ---------------------------
st.sidebar.header("⚙️ Budget Caps (per card)")
budget_caps = {}
for card in BILL_CYCLES.keys():
    budget_caps[card] = st.sidebar.number_input(f"{card} cap (₹)", min_value=0, value=0, step=1000, help="0 means no cap check")

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
    extra_buffer = st.number_input("Extra buffer (₹)", min_value=0, value=0, step=500)

if "paid_flags" not in st.session_state:
    st.session_state.paid_flags = {}

# ---------------------------
# Data prep
# ---------------------------
if uploaded is not None:
    df = pd.read_csv(uploaded)

    # Basic validation
    required_cols = {"Date", "Amount", "Payment mode"}
    missing = required_cols.difference(df.columns)
    if missing:
        st.error(f"CSV missing required columns: {missing}")
        st.stop()

    # Clean
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Card"] = df["Payment mode"].apply(detect_card)

    # -------- Per-card cycle totals for chosen month --------
    y, m = today.year, today.month
    rows = []
    per_card_transactions = {}
    for card in BILL_CYCLES.keys():
        cstart, cend, bill_dt, due_dt = cycle_window_for_month(card, y, m)
        mask = (df["Card"] == card) & (df["Date"].dt.date >= cstart) & (df["Date"].dt.date <= cend)
        sub = df.loc[mask, ["Date", "Category", "Amount", "Note", "Payment mode", "Tags"]].copy()
        sub = sub.sort_values("Date")
        amount = float(sub["Amount"].sum()) if not sub.empty else 0.0
        txn_count = int(sub.shape[0])
        per_card_transactions[card] = {"window": (cstart, cend, bill_dt, due_dt), "df": sub, "amount": amount, "count": txn_count}
        rows.append({
            "Card": card,
            "Cycle Start": cstart,
            "Cycle End": cend,
            "Bill Generation": bill_dt,
            "Due Date": due_dt,
            "Transactions": txn_count,
            "Amount (₹)": round(amount, 2)
        })
    card_due_df = pd.DataFrame(rows).sort_values(by="Due Date")

    st.subheader("Credit Card Dues (cycle that ends this month → due next month)")
    st.dataframe(card_due_df, use_container_width=True)

    # -------- Regular Expenses with Paid toggles --------
    start_m, end_m = month_range(y, m)
    regs = []
    for r in REGULARS:
        d = int(r["date_hint"])
        d = min(d, end_m.day)
        due = dt.date(y, m, d)
        key = f"REG::{r['item']}::{due.isoformat()}"
        paid = st.session_state.paid_flags.get(key, False)
        regs.append({"Item": r["item"], "Amount (₹)": r["amount"], "Due Date": due, "Paid": paid, "Key": key})
    regs_df = pd.DataFrame(regs).sort_values(by="Due Date")

    st.subheader("Regular Expenses (toggle Paid to exclude from cash-out)")
    for i, row in regs_df.iterrows():
        c1, c2, c3, c4 = st.columns([3,2,2,1])
        with c1: st.markdown(f"**{row['Item']}**")
        with c2: st.markdown(f"₹{row['Amount (₹)']:,}")
        with c3: st.markdown(f"{row['Due Date'].isoformat()}")
        with c4:
            paid = st.checkbox("Paid", value=row["Paid"], key=row["Key"])
            st.session_state.paid_flags[row["Key"]] = paid
    regs_df["Paid"] = regs_df["Key"].map(lambda k: st.session_state.paid_flags.get(k, False))

    # -------- Cash Flow Simulator --------
    st.subheader("Cash Flow Simulator (by date)")
    balance = starting_balance + extra_buffer
    events = []
    for _, r in card_due_df.iterrows():
        events.append({"Date": r["Due Date"], "Event": f"{r['Card']} Bill", "Amount (₹)": r["Amount (₹)"]})
    for _, r in regs_df.iterrows():
        if not r["Paid"]:
            events.append({"Date": r["Due Date"], "Event": r["Item"], "Amount (₹)": r["Amount (₹)"]})
    ev_df = pd.DataFrame(events).sort_values(by="Date")
    rows2 = []
    for _, ev in ev_df.iterrows():
        balance -= ev["Amount (₹)"]
        rows2.append([ev["Date"], ev["Event"], ev["Amount (₹)"], balance])
    sim_df = pd.DataFrame(rows2, columns=["Date","Event","Amount (₹)","Balance After (₹)"])
    st.dataframe(sim_df, use_container_width=True)

    # -------- Expenses by Card (detailed) --------
    st.markdown("---")
    st.header("🧾 Expenses by Card (for this cycle)")
    st.caption("These are the transactions included in each card's cycle window above.")
    st.dataframe(
        card_due_df[["Card","Transactions","Amount (₹)","Cycle Start","Cycle End","Bill Generation","Due Date"]],
        use_container_width=True
    )

    for card in BILL_CYCLES.keys():
        detail = per_card_transactions[card]
        cstart, cend, bill_dt, due_dt = detail["window"]
        sub = detail["df"]
        with st.expander(f"{card} — {cstart} → {cend} | Bill: {bill_dt} | Due: {due_dt} | Total: ₹{detail['amount']:.2f} | Txns: {detail['count']}"):
            if sub.empty:
                st.info("No transactions for this cycle.")
            else:
                if "Category" in sub.columns:
                    cat = sub.groupby(["Category","Note"], dropna=False)["Amount"].sum().reset_index().sort_values("Amount", ascending=False)
                    st.markdown("**Top Merchants (Category + Note)** — cycle window")
                    st.dataframe(cat.head(10), use_container_width=True)
                st.markdown("**Transactions**")
                st.dataframe(sub, use_container_width=True)
                csv_buf = io.StringIO()
                sub.to_csv(csv_buf, index=False)
                st.download_button(f"Download {card} Cycle CSV", data=csv_buf.getvalue(),
                                   file_name=f"{card}_cycle_{cstart}_to_{cend}.csv", mime="text/csv")

    # -------- Top Merchants per Card (selectable window) --------
    st.markdown("---")
    st.header("🏷️ Top Merchants per Card — choose analysis window")
    window_choice = st.radio("Window", ["Cycle window", "Last 3 months", "Last 6 months", "Last 12 months"], horizontal=True, index=1)

    def months_back(n, ref_date):
        y, m = ref_date.year, ref_date.month
        end = dt.date(y, m, month_range(y, m)[1].day)
        # n months back inclusive
        start_period = (pd.Period(f"{y}-{m}", freq="M") - n + 1)
        start = dt.date(start_period.year, start_period.month, 1)
        return start, end

    if window_choice == "Cycle window":
        global_start = None
        global_end = None
    else:
        nmap = {"Last 3 months": 3, "Last 6 months": 6, "Last 12 months": 12}
        n = nmap[window_choice]
        global_start, global_end = months_back(n, today)

    for card in BILL_CYCLES.keys():
        if window_choice == "Cycle window":
            cstart, cend, _, _ = per_card_transactions[card]["window"]
            mask = (df["Card"] == card) & (df["Date"].dt.date >= cstart) & (df["Date"].dt.date <= cend)
            window_label = f"{cstart} → {cend}"
        else:
            mask = (df["Card"] == card) & (df["Date"].dt.date >= global_start) & (df["Date"].dt.date <= global_end)
            window_label = f"{global_start} → {global_end}"

        sub = df.loc[mask, ["Date","Category","Note","Amount"]].copy().sort_values("Amount", ascending=False)
        with st.expander(f"{card} — Top Merchants | Window: {window_label}"):
            if sub.empty:
                st.info("No transactions in this window.")
            else:
                top = sub.groupby(["Category","Note"], dropna=False)["Amount"].sum().reset_index().sort_values("Amount", ascending=False)
                st.dataframe(top.head(10), use_container_width=True)
                buf = io.StringIO()
                top.to_csv(buf, index=False)
                st.download_button(f"Download Top Merchants — {card}", data=buf.getvalue(),
                                   file_name=f"top_merchants_{card}.csv", mime="text/csv")

    # -------- Monthly Trends (by Card) with MoM %, Anomaly, Budget Caps --------
    st.markdown("---")
    st.header("📈 Monthly Trends (by Card)")
    st.caption("Rolling monthly totals; anomaly highlight (>1.5× median). Budget caps from sidebar.")

    trends_df = df.copy()
    trends_df["YYYY-MM"] = trends_df["Date"].dt.to_period("M").astype(str)
    include_credits = st.checkbox("Include credits/refunds as negative in monthly totals", value=True)
    if not include_credits:
        trends_df = trends_df[trends_df["Amount"] > 0]
    trends_df = trends_df[trends_df["Card"].notna()]

    monthly = (
        trends_df.groupby(["YYYY-MM", "Card"])["Amount"]
        .sum()
        .reset_index()
        .pivot(index="YYYY-MM", columns="Card", values="Amount")
        .fillna(0.0)
        .sort_index()
    )

    window = st.radio("Window", ["Last 6 months", "Last 12 months"], horizontal=True, index=0)
    n_months = 6 if window == "Last 6 months" else 12
    if monthly.shape[0] > n_months:
        monthly = monthly.iloc[-n_months:, :]

    available_cards = [c for c in BILL_CYCLES.keys() if c in monthly.columns]
    selected_cards = st.multiselect("Choose cards to plot", options=available_cards, default=available_cards)

    def style_anomalies_and_caps(df_in: pd.DataFrame):
        df = df_in.copy()
        med = df.median(axis=0)
        styled = df.style

        def color_cells(val, col):
            cap = budget_caps.get(col, 0) or 0
            is_anom = val > 1.5 * med[col]
            is_over_cap = cap > 0 and val > cap
            if is_over_cap or is_anom:
                return "background-color: #ffcccc; font-weight: 600"  # light red
            return ""

        styled = styled.apply(
            lambda col: [color_cells(v, col.name) for v in col], axis=0
        ).format("{:,.0f}")
        return styled

    if selected_cards:
        st.subheader("Trend Chart")
        st.line_chart(monthly[selected_cards])

        st.subheader("Monthly Totals (₹) — anomalies & over-cap highlighted")
        st.dataframe(style_anomalies_and_caps(monthly[selected_cards]), use_container_width=True)

        # MoM % change table
        mom = monthly[selected_cards].pct_change().replace([np.inf, -np.inf], np.nan) * 100.0
        mom = mom.round(1)
        st.subheader("MoM % Change")
        st.dataframe(mom, use_container_width=True)

        # Export
        buf_tot = io.StringIO()
        monthly[selected_cards].to_csv(buf_tot)
        st.download_button("Download Monthly Totals CSV", data=buf_tot.getvalue(),
                           file_name=f"monthly_totals_{n_months}m.csv", mime="text/csv")

        buf_mom = io.StringIO()
        mom.to_csv(buf_mom)
        st.download_button("Download MoM % CSV", data=buf_mom.getvalue(),
                           file_name=f"monthly_mom_{n_months}m.csv", mime="text/csv")
    else:
        st.info("Select at least one card to plot monthly trends.")

else:
    st.info("Upload your transactions CSV to begin.")