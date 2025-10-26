import json
from typing import Any, Dict, List
from config import (
    CARDS_FILE, DEBTS_FILE, REGULARS_FILE, PAID_FLAGS_FILE, CARD_ALIASES_FILE,
    DEFAULT_CARDS, DEFAULT_DEBTS, DEFAULT_REGULARS, DEFAULT_PAID_FLAGS, DEFAULT_CARD_ALIASES
)

def _read_json(path, default):
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return json.loads(json.dumps(default))

def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def load_cards() -> List[Dict[str, Any]]:
    return _read_json(CARDS_FILE, DEFAULT_CARDS)

def save_cards(items: List[Dict[str, Any]]) -> None:
    _write_json(CARDS_FILE, items)

def load_debts() -> List[Dict[str, Any]]:
    return _read_json(DEBTS_FILE, DEFAULT_DEBTS)

def save_debts(items: List[Dict[str, Any]]) -> None:
    _write_json(DEBTS_FILE, items)

def load_regulars() -> List[Dict[str, Any]]:
    return _read_json(REGULARS_FILE, DEFAULT_REGULARS)

def save_regulars(items: List[Dict[str, Any]]) -> None:
    _write_json(REGULARS_FILE, items)

def load_paid_flags() -> Dict[str, bool]:
    return _read_json(PAID_FLAGS_FILE, DEFAULT_PAID_FLAGS)

def save_paid_flags(flags: Dict[str, bool]) -> None:
    _write_json(PAID_FLAGS_FILE, flags)

def load_card_aliases() -> Dict[str, str]:
    return _read_json(CARD_ALIASES_FILE, DEFAULT_CARD_ALIASES)

def save_card_aliases(aliases: Dict[str, str]) -> None:
    _write_json(CARD_ALIASES_FILE, aliases)
