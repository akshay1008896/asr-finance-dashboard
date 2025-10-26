# config.py
# Central constants and local data file paths

from pathlib import Path

# -------- Formatting --------
DEC_FMT_MONEY = "₹{:,.2f}"

# -------- Data storage --------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# JSON files
DEBTS_FILE = DATA_DIR / "debts.json"
REGULARS_FILE = DATA_DIR / "regulars.json"
PAID_FLAGS_FILE = DATA_DIR / "paid_flags.json"
CARD_ALIASES_FILE = DATA_DIR / "card_aliases.json"

# -------- Defaults (empty) --------
DEFAULT_DEBTS = []          # list of debt dicts
DEFAULT_REGULARS = []       # list of regular expense dicts
DEFAULT_PAID_FLAGS = {}     # key -> bool
DEFAULT_CARD_ALIASES = {}   # "Payment mode" -> "Card"
