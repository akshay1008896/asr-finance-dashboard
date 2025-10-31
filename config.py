# config.py
# Paths & empty defaults (no sample data)

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

CARDS_FILE = DATA_DIR / "cards.json"
DEBTS_FILE = DATA_DIR / "debts.json"
REGULARS_FILE = DATA_DIR / "regulars.json"
PAID_FLAGS_FILE = DATA_DIR / "paid_flags.json"
CARD_ALIASES_FILE = DATA_DIR / "card_aliases.json"
OVERRIDES_FILE = DATA_DIR / "card_overrides.json"

# Empty defaults — CSV is primary data
EMPTY_CARDS = []
EMPTY_DEBTS = []
EMPTY_REGULARS = []
EMPTY_PAID_FLAGS = {}
EMPTY_CARD_ALIASES = {}
EMPTY_OVERRIDES = []
