import uuid
import streamlit as st
import pandas as pd
from typing import List, Optional

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
