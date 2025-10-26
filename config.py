from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

CARDS_FILE = DATA_DIR / "cards.json"
DEBTS_FILE = DATA_DIR / "debts.json"
REGULARS_FILE = DATA_DIR / "regulars.json"
PAID_FLAGS_FILE = DATA_DIR / "paid_flags.json"
CARD_ALIASES_FILE = DATA_DIR / "card_aliases.json"

DEFAULT_CARDS = []
DEFAULT_DEBTS = []
DEFAULT_REGULARS = []
DEFAULT_PAID_FLAGS = {}
DEFAULT_CARD_ALIASES = {}
