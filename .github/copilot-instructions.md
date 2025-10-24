## Quick orientation

This repository is a small Streamlit app (`finance_dashboard.py`) that ingests a transactions CSV and produces per-card billing-cycle summaries, cash-flow simulation, and simple financial guidance.

Primary entrypoint: `finance_dashboard.py` (open and edit here). The app is run with Streamlit from the repo folder:

```
streamlit run finance_dashboard.py
```

## Big picture / architecture

- Single-process Streamlit dashboard. No backend services or DBs. Data flows: uploaded CSV -> pandas DataFrame -> in-memory transforms -> Streamlit UI and downloadable CSVs.
- Key data shapes: transaction rows with columns Date (parseable), Amount (numeric), Payment mode, type, Category, Note, Tags. The app enforces required columns: `Date`, `Amount`, `Payment mode`, `type`.
- Billing cycle logic is centralized in two places:
  - `BILL_CYCLES` dict — canonical per-card cycle tuple: (cycle_start_day, cycle_end_day, due_day, due_offset_months).
  - `cycle_window_for_month(card, year, month)` — computes cycle start/end, bill generation date and due date for the cycle that ends in the given month.

## Important files and symbols

- `finance_dashboard.py` — the entire app. Search here for:
  - `BILL_CYCLES` — add or modify card cycles here.
  - `detect_card(payment_mode)` — maps free-text `Payment mode` values to canonical cards (Amex, ICICI, SBI, One, HSBC, HSBC Cash). Update to add new mapping heuristics.
  - `DEBTS` and `REGULARS` — hard-coded lists used for EMI/regular-expense displays and cash-flow simulation.
  - `st.session_state.paid_flags` — persistent checkbox state keys for marking regular items as paid. Keys are generated as `CASH::{Item}::{YYYY-MM-DD}`.

## Project-specific conventions and patterns

- Card canonicalization: the app expects one of the canonical card keys (keys of `BILL_CYCLES`). Always keep `detect_card` and `BILL_CYCLES` in sync when you add or rename cards.
- Cycle tuples: (start_day, end_day, due_day, due_offset_months). Example: `"Amex": (22, 21, 10, 1)` — cycle runs 22→21, bill due on the 10th of next month.
- Date filtering: code uses pandas timestamps and compares via `.dt.date` (so timezone-naive dates). Invalid/ unparsable dates are dropped early.
- CSV requirements: required cols are enforced (see `required_cols` set). Optional columns are created if missing to avoid KeyError.
- Session-state keys: UI elements (Paid toggles) use deterministic string keys so state survives reruns. Use the same `CASH::...` format when adding similar toggles.

## How to add a new card or change cycles

1. Add a new entry to `BILL_CYCLES` with the tuple described above.
2. Update `detect_card` to map likely `Payment mode` text fragments to the new canonical name.
3. Run the app and upload a sample CSV to validate mapping and cycle calculations.

## Running & debugging

- Run the app locally with Streamlit: `streamlit run finance_dashboard.py` and open the URL printed by Streamlit.
- Typical debug loop:
  1. Add `st.write(...)` or `print(...)` near the transformation you want to inspect (the app writes to the Streamlit UI or console).
  2. Use a small sample CSV (columns: `Date, Category, Amount, Note, type, Payment mode, To payment mode, Tags`) to quickly iterate.

## Dependencies (discoverable from imports)

- The script imports: `pandas`, `numpy`, `streamlit`, `dateutil` (relativedelta). Ensure your environment has these packages available. A minimal requirements list to install:

```
pip install streamlit pandas numpy python-dateutil
```

## UI / UX conventions

- Budget caps are set via the sidebar and stored in local variables `budget_caps` keyed by card.
- The app uses `st.expander` extensively for per-card details and diagnostic sections.
- Download buttons generate CSV from in-memory pandas objects (no filesystem writes).

## Examples & quick code snippets (from the codebase)

- Required CSV columns enforced in code:
  - `required_cols = {"Date", "Amount", "Payment mode", "type"}`

- Cycle computation: call `cycle_window_for_month("Amex", 2025, 10)` to get start/end/dates for Amex cycle that ends in Oct 2025.

## What to watch for / gotchas

- `detect_card` uses substring matching (lowercased). Some ambiguous `Payment mode` strings may be unmapped (returns `None`) — added transactions with unmapped cards are ignored in card-specific views.
- The app assumes dates are valid after `pd.to_datetime`; rows with invalid dates are filtered out. Test CSVs with multiple date formats to ensure parsing works.
- Hard-coded financial data (`DEBTS`, `REGULARS`) are part of the UI and not persisted — update these in the file if you want them to reflect real data.

## Suggested small tasks for new contributors

- Add a minimal `requirements.txt` or `pyproject.toml` to pin versions (currently inferred from imports).
- Add a sample_transactions.csv (with the required columns) in a `sample_data/` folder to make manual testing faster.

If anything above is unclear or you'd like the instructions expanded (for example, including a pinned requirements file or a sample CSV), tell me which section to expand and I will update this file.
