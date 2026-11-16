"""Layer 2b: quarter-over-quarter diff of 13F holdings.

Weights are computed against the total *long book* (SHARES-type holdings only),
so option positions never dilute the percentages that feed sizing. Options still
appear in their own summary line but are filtered out of every actionable bucket.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .parser import TYPE_SHARES, Holding

# Bucket names.
NEW = "NEW"
INCREASED = "INCREASED"
DECREASED = "DECREASED"
EXITED = "EXITED"
UNCHANGED = "UNCHANGED"


@dataclass
class DiffEntry:
    cusip: str
    issuer: str
    ticker: str | None
    bucket: str
    shares_prev: int
    shares_curr: int
    value_curr: int
    weight_curr: float          # % of current long book
    weight_prev: float          # % of prior long book
    weight_change: float        # percentage points
    shares_change_pct: float    # signed %, 0 for NEW/EXITED edges


@dataclass
class OptionsSummary:
    put_count: int
    call_count: int
    put_notional: int
    call_notional: int


@dataclass
class DiffResult:
    entries: list[DiffEntry]
    options: OptionsSummary

    def by_bucket(self, bucket: str) -> list[DiffEntry]:
        return [e for e in self.entries if e.bucket == bucket]

    def counts(self) -> dict[str, int]:
        out = {NEW: 0, INCREASED: 0, DECREASED: 0, EXITED: 0, UNCHANGED: 0}
        for e in self.entries:
            out[e.bucket] += 1
        return out


def _longs(holdings: Iterable[Holding]) -> list[Holding]:
    return [h for h in holdings if h.type == TYPE_SHARES]


def _long_book_value(holdings: Iterable[Holding]) -> int:
    return sum(h.value_usd for h in holdings if h.type == TYPE_SHARES)


def _weight(value: int, total: int) -> float:
    return (value / total * 100.0) if total > 0 else 0.0


def diff_holdings(
    current: list[Holding],
    previous: list[Holding],
    increase_threshold_pct: float = 5.0,
) -> DiffResult:
    """Diff current vs previous holdings into NEW / INCREASED / DECREASED /
    EXITED / UNCHANGED, plus an options summary line."""
    cur_total = _long_book_value(current)
    prev_total = _long_book_value(previous)

    cur_by_cusip = {h.cusip: h for h in _longs(current)}
    prev_by_cusip = {h.cusip: h for h in _longs(previous)}

    entries: list[DiffEntry] = []
    all_cusips = set(cur_by_cusip) | set(prev_by_cusip)

    for cusip in all_cusips:
        cur = cur_by_cusip.get(cusip)
        prev = prev_by_cusip.get(cusip)

        shares_prev = prev.shares if prev else 0
        shares_curr = cur.shares if cur else 0
        value_curr = cur.value_usd if cur else 0
        weight_curr = _weight(cur.value_usd, cur_total) if cur else 0.0
        weight_prev = _weight(prev.value_usd, prev_total) if prev else 0.0

        if cur and not prev:
            bucket = NEW
            shares_change_pct = 0.0
        elif prev and not cur:
            bucket = EXITED
            shares_change_pct = -100.0
        else:
            assert cur and prev
            shares_change_pct = (
                (shares_curr - shares_prev) / shares_prev * 100.0 if shares_prev else 0.0
            )
            if shares_change_pct > increase_threshold_pct:
                bucket = INCREASED
            elif shares_change_pct < -increase_threshold_pct:
                bucket = DECREASED
            else:
                bucket = UNCHANGED

        issuer = (cur or prev).issuer
        ticker = (cur or prev).ticker

        entries.append(
            DiffEntry(
                cusip=cusip,
                issuer=issuer,
                ticker=ticker,
                bucket=bucket,
                shares_prev=shares_prev,
                shares_curr=shares_curr,
                value_curr=value_curr,
                weight_curr=weight_curr,
                weight_prev=weight_prev,
                weight_change=weight_curr - weight_prev,
                shares_change_pct=shares_change_pct,
            )
        )

    # Sort by current weight desc, then issuer for stable ordering.
    entries.sort(key=lambda e: (-e.weight_curr, e.issuer))

    options = _summarize_options(current)
    return DiffResult(entries=entries, options=options)


def _summarize_options(holdings: list[Holding]) -> OptionsSummary:
    puts = [h for h in holdings if h.type == "PUT"]
    calls = [h for h in holdings if h.type == "CALL"]
    return OptionsSummary(
        put_count=len(puts),
        call_count=len(calls),
        put_notional=sum(h.value_usd for h in puts),
        call_notional=sum(h.value_usd for h in calls),
    )
