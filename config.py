# config.py
# Pure constants module — NO imports from app/helpers/ui_sections to avoid circular imports.

from typing import Dict, Tuple

# Default cycles: (cycle_start_day, cycle_end_day, due_day, due_offset_months)
DEFAULT_BILL_CYCLES: Dict[str, Tuple[int, int, int, int]] = {
    "Amex": (22, 21, 10, 1),
    "HSBC": (19, 18, 5, 1),
    "HSBC Cash": (8, 7, 27, 0),
    # ICICI: bill gen 21st, due 8th next month → start 22, end 21, due_offset=1
    "ICICI": (22, 21, 8, 1),
    "One": (19, 18, 8, 1),
    "SBI": (25, 24, 13, 1),
}

DEBTS = [
    {"type": "Cred EMIs", "item": "Movers & Packers", "amount": 23567, "due_day": 25, "tenure_left": 2, "outstanding": 47134},
    {"type": "Cred EMIs", "item": "CC & ITR", "amount": 18273, "due_day": 28, "tenure_left": 13, "outstanding": 237549},
    {"type": "Cred EMIs", "item": "Extra", "amount": 17567, "due_day": 28, "tenure_left": 1, "outstanding": 17567},
    {"type": "Loans", "item": "Wedding Loan", "amount": 33400, "due_day": 18, "tenure_left": 19, "outstanding": 634600},
    {"type": "Loans", "item": "Home Loan EMI", "amount": 19000, "due_day": 20, "tenure_left": "~95", "outstanding": 1805000},
]

REGULARS = [
    {"item": "Papa", "amount": 40000, "date_hint": "1"},
    {"item": "House Rent", "amount": 40000, "date_hint": "1"},
    {"item": "SIP – 3rd", "amount": 2000, "date_hint": "3"},
    {"item": "SIP – 9th", "amount": 10500, "date_hint": "9"},
    {"item": "SIP – 11th", "amount": 500, "date_hint": "11"},
]

# Canonical column names (for normalization)
CANON_COLS = {
    "date": "Date",
    "amount": "Amount",
    "paymentmode": "Payment mode",
    "payment_mode": "Payment mode",
    "payment mode": "Payment mode",
    "paymentmethod": "Payment mode",
    "payment method": "Payment mode",
    "type": "type",
    "category": "Category",
    "note": "Note",
    "tags": "Tags",
}
