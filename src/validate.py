"""Holdings sanity checks. A wrong sheet is worse than no sheet, so malformed
numbers raise instead of flowing downstream."""

from __future__ import annotations

from .parser import Holding


class ValidationError(RuntimeError):
    pass


def validate_holdings(holdings: list[Holding]) -> None:
    """Raise ValidationError on anything that looks malformed: empty book,
    negative shares/value, or a single position exceeding the whole book."""
    if not holdings:
        raise ValidationError("parsed holdings list is empty")

    total_value = sum(h.value_usd for h in holdings)
    for h in holdings:
        if h.shares < 0:
            raise ValidationError(f"negative shares for {h.issuer} ({h.cusip}): {h.shares}")
        if h.value_usd < 0:
            raise ValidationError(f"negative value for {h.issuer} ({h.cusip}): {h.value_usd}")
        # No single name should exceed the entire reported book.
        if total_value > 0 and h.value_usd > total_value:
            raise ValidationError(
                f"value of {h.issuer} (${h.value_usd:,}) exceeds total book (${total_value:,})"
            )
