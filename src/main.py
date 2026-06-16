"""Orchestrator. One invocation = one poll cycle.

    python -m src.main                # poll, notify, process any new 13F
    python -m src.main --dry-run      # do everything except send ntfy pushes
    python -m src.main --seed-only    # mark all current filings seen, send nothing

Designed for `*/15` cron under GitHub Actions; state files are committed back by
the workflow so the next run knows what it has already seen.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import notify
from .config import Config, REPO_ROOT, load_config
from .differ import diff_holdings
from .edgar import EdgarClient, EdgarError
from .parser import (
    Holding,
    ParseError,
    apply_tickers,
    build_cusip_ticker_map,
    fetch_holdings,
)
from .poller import (
    Filing,
    fetch_filings,
    find_new_filings,
    load_seen,
    save_seen,
)
from .sizer import (
    build_trade_sheet,
    default_quarter_label,
    render_trade_sheet,
    summarize_for_ntfy,
)
from .validate import ValidationError, validate_holdings

STATE_DIR = REPO_ROOT / "state"
SEEN_PATH = STATE_DIR / "seen_filings.json"
HOLDINGS_PREV_PATH = STATE_DIR / "holdings_prev.json"
OUTPUT_DIR = REPO_ROOT / "output"

THIRTEEN_F_FORMS = {"13F-HR", "13F-HR/A"}
THIRTEEN_D_G_FORMS = {"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"}


# ---------------------------------------------------------------------------
# holdings_prev persistence
# ---------------------------------------------------------------------------


def load_prev_holdings(path: Path = HOLDINGS_PREV_PATH) -> list[Holding]:
    import json

    if not path.exists():
        return []
    data = json.loads(path.read_text() or "[]")
    return [Holding.from_dict(d) for d in data]


def save_prev_holdings(holdings: list[Holding], path: Path = HOLDINGS_PREV_PATH) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([h.to_dict() for h in holdings], indent=2) + "\n")


# ---------------------------------------------------------------------------
# per-filing handling
# ---------------------------------------------------------------------------


def notify_filing(cfg: Config, filing: Filing, dry_run: bool) -> None:
    title = f"New {filing.form} — Situational Awareness LP"
    msg = f"{filing.form} filed {filing.filing_date}\n{filing.index_url}"
    tags = ["page_facing_up"]
    if filing.form in THIRTEEN_D_G_FORMS:
        tags = ["rotating_light"]
    elif filing.form in THIRTEEN_F_FORMS:
        tags = ["bar_chart"]
    if dry_run:
        print(f"[dry-run] would notify ({filing.priority}): {title} | {filing.index_url}")
        return
    notify.push(
        cfg.ntfy.server,
        cfg.ntfy.topic,
        msg,
        title=title,
        priority=filing.priority,
        tags=tags,
        click=filing.index_url,
    )


def process_13f(cfg: Config, client: EdgarClient, filing: Filing, dry_run: bool) -> None:
    """Parse + diff + size a 13F-HR. Validation failures send an ERROR push and
    leave prior state untouched."""
    try:
        holdings = fetch_holdings(client, cfg.edgar.cik_int, filing.accession_no_dashes)
        validate_holdings(holdings)
    except (ParseError, ValidationError, EdgarError) as exc:
        _error(cfg, f"Failed to process {filing.form} {filing.accession_number}", str(exc), dry_run)
        return

    cusip_map = build_cusip_ticker_map({}, cfg.cusip_overrides)
    apply_tickers(holdings, cusip_map)

    prev = load_prev_holdings()
    diff = diff_holdings(holdings, prev, cfg.rules.increase_threshold_pct)

    quarter = default_quarter_label()
    from .marketdata import YFinanceProvider

    sheet = build_trade_sheet(
        diff,
        cfg.account,
        cfg.rules,
        YFinanceProvider(),
        quarter_label=quarter,
        filing_date=filing.filing_date,
    )
    rendered = render_trade_sheet(sheet)
    summary = summarize_for_ntfy(sheet)

    # Commit the full sheet to output/ regardless of dry-run (it's local state).
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"trade_sheet_{filing.filing_date}_{filing.accession_no_dashes}.md"
    out_path.write_text(rendered + "\n")
    print(f"[main] wrote trade sheet -> {out_path}")

    if dry_run:
        print("[dry-run] trade sheet summary:\n" + summary)
    else:
        notify.push(
            cfg.ntfy.server,
            cfg.ntfy.topic,
            summary,
            title=f"13F Trade Sheet — {quarter}",
            priority=notify.PRIORITY_HIGH,
            tags=["bar_chart"],
            click=filing.index_url,
        )

    # Advance the prior-quarter baseline only after a clean run.
    save_prev_holdings(holdings)


def handle_13d(cfg: Config, filing: Filing, dry_run: bool) -> None:
    """13D/13G get an urgent alert but NO auto-generated trade sheet (they lack
    full-book context; manual review only)."""
    msg = (
        f"{filing.form} filed {filing.filing_date} — 5%+ stake activity.\n"
        f"Manual review only (no auto sheet).\n{filing.index_url}"
    )
    if dry_run:
        print(f"[dry-run] would urgent-alert {filing.form}: {filing.index_url}")
        return
    notify.push(
        cfg.ntfy.server,
        cfg.ntfy.topic,
        msg,
        title=f"{filing.form} — Situational Awareness LP",
        priority=notify.PRIORITY_URGENT,
        tags=["rotating_light"],
        click=filing.index_url,
    )


def _error(cfg: Config, context: str, detail: str, dry_run: bool) -> None:
    print(f"[ERROR] {context}: {detail}", file=sys.stderr)
    if not dry_run:
        notify.push_error(cfg.ntfy.server, cfg.ntfy.topic, context, detail)


# ---------------------------------------------------------------------------
# poll cycle
# ---------------------------------------------------------------------------


def run_cycle(cfg: Config, dry_run: bool = False, seed_only: bool = False) -> int:
    """Run one poll cycle. Returns the number of new filings handled."""
    client = EdgarClient(cfg.edgar.user_agent, cfg.edgar.poll_sleep_seconds)

    try:
        filings = fetch_filings(client, cfg.edgar.cik_padded, cfg.edgar.cik_int)
    except EdgarError as exc:
        _error(cfg, "Failed to fetch submissions index", str(exc), dry_run)
        return 0

    seen = load_seen(SEEN_PATH)

    if seed_only:
        all_acc = {f.accession_number for f in filings}
        save_seen(SEEN_PATH, all_acc)
        print(f"[main] seeded {len(all_acc)} accession numbers; no notifications sent")
        return 0

    new = find_new_filings(filings, seen)
    if not new:
        print("[main] no new filings")
        return 0

    print(f"[main] {len(new)} new filing(s)")
    for filing in new:
        notify_filing(cfg, filing, dry_run)

        if filing.form in THIRTEEN_F_FORMS:
            process_13f(cfg, client, filing, dry_run)
        elif filing.form in THIRTEEN_D_G_FORMS:
            handle_13d(cfg, filing, dry_run)
        # 13F-NT and everything else: Layer 1 notification only.

        seen.add(filing.accession_number)
        # Persist after each filing so a mid-cycle crash never re-notifies.
        if not dry_run:
            save_seen(SEEN_PATH, seen)

    return len(new)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EDGAR filing monitor poll cycle")
    parser.add_argument("--config", default=None, help="path to config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="do not send ntfy pushes")
    parser.add_argument(
        "--seed-only",
        action="store_true",
        help="mark all current filings as seen and exit (send nothing)",
    )
    args = parser.parse_args(argv)

    cfg = load_config(args.config) if args.config else load_config()
    run_cycle(cfg, dry_run=args.dry_run, seed_only=args.seed_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
