"""Layer 3: turn the diff into a sized, rules-compliant trade sheet.

Mechanical application of config rules only. No execution, no broker calls. The
output is a markdown sheet and a short ntfy summary; a human reviews and trades.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from .config import AccountConfig, RulesConfig
from .differ import DiffEntry, DiffResult, INCREASED, NEW

EARNINGS_UNKNOWN = "EARNINGS DATE UNKNOWN — check manually"


@dataclass
class MarketData:
    price: float | None
    avg_volume: float | None      # 14-day average daily volume
    next_earnings: str | None     # ISO date string or None


class MarketDataProvider(Protocol):
    def fetch(self, ticker: str) -> MarketData: ...


@dataclass
class TradeLine:
    ticker: str
    issuer: str
    bucket: str
    fund_weight: float
    price: float
    shares: int
    dollars: float
    bp_pct: float
    stop_price: float
    earnings: str


@dataclass
class DropLine:
    ticker: str
    issuer: str
    reason: str


@dataclass
class TradeSheet:
    quarter_label: str
    filing_date: str
    account: AccountConfig
    lines: list[TradeLine]
    drops: list[DropLine]
    diff: DiffResult


def _candidate_entries(diff: DiffResult, rules: RulesConfig) -> list[DiffEntry]:
    """NEW + INCREASED longs (per config source_buckets), ranked by fund weight."""
    wanted = set(rules.source_buckets) or {NEW, INCREASED}
    cands = [e for e in diff.entries if e.bucket in wanted]
    cands.sort(key=lambda e: -e.weight_curr if rules.rank_by == "weight" else 0)
    return cands


def build_trade_sheet(
    diff: DiffResult,
    account: AccountConfig,
    rules: RulesConfig,
    provider: MarketDataProvider,
    quarter_label: str,
    filing_date: str,
) -> TradeSheet:
    """Apply the ruleset to produce a TradeSheet. Options never reach here —
    they are excluded upstream in the diff's actionable buckets."""
    max_total_dollars = account.buying_power * account.max_total_exposure_pct / 100.0
    max_position_dollars = account.buying_power * account.max_position_pct / 100.0

    lines: list[TradeLine] = []
    drops: list[DropLine] = []
    remaining_budget = max_total_dollars

    for entry in _candidate_entries(diff, rules):
        if len(lines) >= account.max_names:
            break

        ticker = entry.ticker
        if not ticker:
            drops.append(DropLine(ticker="?", issuer=entry.issuer, reason="no ticker mapping"))
            continue

        md = provider.fetch(ticker)
        if md.price is None or md.price <= 0:
            drops.append(DropLine(ticker, entry.issuer, "no price available"))
            continue
        if md.avg_volume is None:
            drops.append(DropLine(ticker, entry.issuer, "no volume data"))
            continue
        if md.avg_volume < rules.min_avg_daily_volume:
            drops.append(
                DropLine(
                    ticker,
                    entry.issuer,
                    f"avg vol {int(md.avg_volume):,} < {rules.min_avg_daily_volume:,} floor",
                )
            )
            continue

        position_dollars = min(max_position_dollars, remaining_budget)
        if position_dollars < md.price:  # can't afford even one share
            drops.append(DropLine(ticker, entry.issuer, "exposure budget exhausted"))
            continue

        shares = math.floor(position_dollars / md.price)
        if shares < 1:
            drops.append(DropLine(ticker, entry.issuer, "share price exceeds position budget"))
            continue

        dollars = shares * md.price
        remaining_budget -= dollars
        stop_price = round(md.price * (1 - account.stop_loss_pct / 100.0), 2)

        lines.append(
            TradeLine(
                ticker=ticker,
                issuer=entry.issuer,
                bucket=entry.bucket,
                fund_weight=entry.weight_curr,
                price=md.price,
                shares=shares,
                dollars=dollars,
                bp_pct=dollars / account.buying_power * 100.0,
                stop_price=stop_price,
                earnings=md.next_earnings or EARNINGS_UNKNOWN,
            )
        )

    return TradeSheet(
        quarter_label=quarter_label,
        filing_date=filing_date,
        account=account,
        lines=lines,
        drops=drops,
        diff=diff,
    )


def render_trade_sheet(sheet: TradeSheet) -> str:
    """Render the full markdown trade sheet."""
    acct = sheet.account
    max_exposure = acct.buying_power * acct.max_total_exposure_pct / 100.0
    out: list[str] = []
    out.append(f"# 13F TRADE SHEET — {sheet.quarter_label} (filed {sheet.filing_date})")
    out.append("")
    out.append(
        f"Account BP: ${acct.buying_power:,.0f} | "
        f"Max exposure: ${max_exposure:,.0f} ({acct.max_total_exposure_pct:.0f}%) | "
        f"Max names: {acct.max_names}"
    )
    out.append("")

    if not sheet.lines:
        out.append("_No actionable entries passed the rules this quarter._")
    for i, line in enumerate(sheet.lines, start=1):
        earnings_flag = " ⚠️" if "UNKNOWN" in line.earnings else ""
        out.append(
            f"{i}. BUY ~{line.shares} sh {line.ticker} @ ~${line.price:,.2f} | "
            f"${line.dollars:,.0f} ({line.bp_pct:.1f}% BP) | "
            f"stop ${line.stop_price:,.2f} | earnings: {line.earnings}{earnings_flag} | "
            f"[{line.bucket}, fund wt {line.fund_weight:.1f}%]"
        )
    out.append("")

    if sheet.drops:
        for d in sheet.drops:
            out.append(f"Dropped: {d.ticker} ({d.reason})")
        out.append("")

    counts = sheet.diff.counts()
    opts = sheet.diff.options
    opt_note = ""
    if opts.put_count or opts.call_count:
        opt_note = (
            f", put book {opts.put_count} names / ${opts.put_notional:,} notional, "
            f"call book {opts.call_count} names / ${opts.call_notional:,} notional "
            f"(NOT actionable)"
        )
    out.append(
        f"Diff summary: {counts['NEW']} NEW, {counts['INCREASED']} INCREASED, "
        f"{counts['DECREASED']} DECREASED, {counts['EXITED']} EXITED{opt_note}"
    )
    out.append("")
    out.append("---")
    out.append(
        "⚠️ Sheet is mechanical output of config rules. Entries are estimates. "
        "Stagger entries over 1-2 weeks, use limit orders, do not buy day-of-filing spikes. "
        "NO auto-execution — review and trade manually."
    )
    return "\n".join(out)


def summarize_for_ntfy(sheet: TradeSheet) -> str:
    """Short body for the ntfy push (the full sheet is committed to output/)."""
    counts = sheet.diff.counts()
    head = f"{sheet.quarter_label}: {len(sheet.lines)} buys, {len(sheet.drops)} dropped"
    picks = ", ".join(f"{l.ticker} ${l.dollars:,.0f}" for l in sheet.lines) or "none"
    diff_line = (
        f"{counts['NEW']} NEW / {counts['INCREASED']} INCR / "
        f"{counts['EXITED']} EXIT"
    )
    return f"{head}\n{picks}\n{diff_line}"


def default_quarter_label(today: date | None = None) -> str:
    """Best-effort label like 'Q1 2026 filing' from the *prior* quarter, since a
    13F filed mid-quarter reports the quarter that just ended."""
    today = today or date.today()
    q = (today.month - 1) // 3 + 1
    reported_q = q - 1 or 4
    year = today.year if q != 1 else today.year - 1
    return f"Q{reported_q} {year}"
