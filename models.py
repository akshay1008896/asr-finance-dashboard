from typing import Dict, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

class Card(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    start_day: int
    end_day: int
    due_day: int
    due_offset: int
    extra: Dict[str, str] = Field(default_factory=dict)

class Debt(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    dtype: str
    item: str
    amount: float
    due_day: int
    tenure_left: str
    outstanding: float
    extra: Dict[str, str] = Field(default_factory=dict)

class RegularExpense(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    item: str
    amount: float
    date_hint: str
    extra: Dict[str, str] = Field(default_factory=dict)

class Override(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    card_id: str
    year: int
    month: int
    cycle_start: str
    cycle_end: str
    due_date: str
