# data.py
# Local JSON persistence helpers (no sample data)

import json
from typing import Any, Dict, List
from pathlib import Path

from config import (
    DATA_DIR,
    CARDS_FILE, DEBTS_FILE, REGULARS_FILE, PAID_FLAGS_FILE, CARD_ALIASES_FILE, OVERRIDES_FILE,
    EMPTY_CARDS, EMPTY_DEBTS, EMPTY_REGULARS, EMPTY_PAID_FLAGS, EMPTY_CARD_ALIASES, EMPTY_OVERRIDES,
)

def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

def _read_json(path: Path, default):
    _ensure_dir()
    if not path.exists():
        return json.loads(json.dumps(default))
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return json.loads(json.dumps(default))

def _write_json(path: Path, obj):
    _ensure_dir()
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    tmp.replace(path)

def load_cards() -> List[Dict[str, Any]]:
    return _read_json(CARDS_FILE, EMPTY_CARDS)

def save_cards(items: List[Dict[str, Any]]) -> None:
    _write_json(CARDS_FILE, items)

def load_debts() -> List[Dict[str, Any]]:
    return _read_json(DEBTS_FILE, EMPTY_DEBTS)

def save_debts(items: List[Dict[str, Any]]) -> None:
    _write_json(DEBTS_FILE, items)

def load_regulars() -> List[Dict[str, Any]]:
    return _read_json(REGULARS_FILE, EMPTY_REGULARS)

def save_regulars(items: List[Dict[str, Any]]) -> None:
    _write_json(REGULARS_FILE, items)

def load_paid_flags() -> Dict[str, bool]:
    return _read_json(PAID_FLAGS_FILE, EMPTY_PAID_FLAGS)

def save_paid_flags(flags: Dict[str, bool]) -> None:
    _write_json(PAID_FLAGS_FILE, flags)

def load_card_aliases() -> Dict[str, str]:
    return _read_json(CARD_ALIASES_FILE, EMPTY_CARD_ALIASES)

def save_card_aliases(aliases: Dict[str, str]) -> None:
    _write_json(CARD_ALIASES_FILE, aliases)

def load_overrides() -> List[Dict[str, Any]]:
    return _read_json(OVERRIDES_FILE, EMPTY_OVERRIDES)

def save_overrides(items: List[Dict[str, Any]]) -> None:
    _write_json(OVERRIDES_FILE, items)
