import pytest
from datetime import date
from helpers import shift_month, cycle_window_for_month, safe_date

def test_shift_month():
    d = date(2023, 1, 31)
    # Shift +1 month -> Feb 28 (non-leap)
    assert shift_month(d, 1) == date(2023, 2, 28)
    
    d = date(2023, 1, 15)
    assert shift_month(d, 1) == date(2023, 2, 15)
    
    d = date(2023, 12, 1)
    assert shift_month(d, 1) == date(2024, 1, 1)

def test_safe_date():
    assert safe_date(2023, 2, 30) == date(2023, 2, 28)
    assert safe_date(2024, 2, 30) == date(2024, 2, 29) # Leap year

def test_cycle_window_for_month():
    # Case 1: Standard cycle (Start 22, End 21, Due 8, Offset 1)
    card = {
        "start_day": 22,
        "end_day": 21,
        "due_day": 8,
        "due_offset": 1
    }
    # For Oct 2023 bill generation
    # Cycle should be Sep 22 to Oct 21
    # Due date should be Nov 8
    cs, ce, bg, dd = cycle_window_for_month(card, 2023, 10)
    assert cs == date(2023, 9, 22)
    assert ce == date(2023, 10, 21)
    assert bg == date(2023, 10, 21)
    assert dd == date(2023, 11, 8)

    # Case 2: Start < End (e.g., 1st to 30th)
    card2 = {
        "start_day": 1,
        "end_day": 30,
        "due_day": 15,
        "due_offset": 1
    }
    # For Oct 2023
    cs, ce, bg, dd = cycle_window_for_month(card2, 2023, 10)
    assert cs == date(2023, 10, 1)
    assert ce == date(2023, 10, 30)
    assert dd == date(2023, 11, 15)
