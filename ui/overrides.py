import uuid
import streamlit as st
import pandas as pd
from datetime import date as _date
from typing import List, Optional

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
