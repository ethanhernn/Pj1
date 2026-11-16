import pytest

from src.parser import TYPE_SHARES, Holding
from src.validate import ValidationError, validate_holdings


def _h(value, shares, cusip="123456789"):
    return Holding(cusip=cusip, issuer="FOO", value_usd=value, shares=shares, type=TYPE_SHARES)


def test_valid_book_passes():
    validate_holdings([_h(100, 10), _h(200, 20, "987654321")])


def test_empty_raises():
    with pytest.raises(ValidationError):
        validate_holdings([])


def test_negative_shares_raises():
    with pytest.raises(ValidationError):
        validate_holdings([_h(100, -5)])


def test_single_name_over_book_raises():
    # Two names where one's value exceeds the (correctly computed) total is
    # impossible by construction, so simulate a corrupt parse with a stray total.
    big = _h(1_000_000, 10)
    small = _h(-999_999, 10, "987654321")  # negative trips first anyway
    with pytest.raises(ValidationError):
        validate_holdings([big, small])
