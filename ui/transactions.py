import streamlit as st
import pandas as pd
from typing import Dict, Optional
from helpers import normalize_csv, unique_payment_modes, apply_card_mapping
from persistence import save_card_aliases

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
