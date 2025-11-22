import uuid
import streamlit as st
import pandas as pd
from typing import List, Optional

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
