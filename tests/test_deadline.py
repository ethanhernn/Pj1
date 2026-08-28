from datetime import date

from src.deadline import is_deadline_window


def test_in_window_for_each_quarter():
    assert is_deadline_window(date(2026, 2, 14))   # Q4 deadline
    assert is_deadline_window(date(2026, 5, 15))   # Q1 deadline
    assert is_deadline_window(date(2026, 8, 14))   # Q2 deadline
    assert is_deadline_window(date(2026, 11, 14))  # Q3 deadline


def test_window_edges():
    assert is_deadline_window(date(2026, 5, 10))   # start of window
    assert is_deadline_window(date(2026, 5, 20))   # end of window
    assert not is_deadline_window(date(2026, 5, 9))
    assert not is_deadline_window(date(2026, 5, 21))


def test_outside_deadline_months():
    assert not is_deadline_window(date(2026, 1, 14))
    assert not is_deadline_window(date(2026, 6, 15))
    assert not is_deadline_window(date(2026, 12, 14))
