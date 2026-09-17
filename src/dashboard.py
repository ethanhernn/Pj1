"""Layer 4 (optional): historical diff persistence + a static HTML dashboard.

Each processed 13F appends a structured record to `state/diff_history.json`.
`render_dashboard` turns that history into a self-contained `docs/index.html`
(no external assets, trade sheets embedded inline) suitable for GitHub Pages.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .differ import DiffResult
from .poller import Filing


def build_record(
    diff: DiffResult,
    filing: Filing,
    quarter_label: str,
    trade_sheet_text: str,
) -> dict[str, Any]:
    """Serialize one processed 13F into a history record."""
    return {
        "accession": filing.accession_number,
        "filing_date": filing.filing_date,
        "quarter_label": quarter_label,
        "processed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "index_url": filing.index_url,
        "counts": diff.counts(),
        "options": {
            "put_count": diff.options.put_count,
            "put_notional": diff.options.put_notional,
            "call_count": diff.options.call_count,
            "call_notional": diff.options.call_notional,
        },
        "entries": [
            {
                "ticker": e.ticker,
                "issuer": e.issuer,
                "cusip": e.cusip,
                "bucket": e.bucket,
                "weight_curr": round(e.weight_curr, 2),
                "weight_change": round(e.weight_change, 2),
                "shares_change_pct": round(e.shares_change_pct, 1),
            }
            for e in diff.entries
        ],
        "trade_sheet_text": trade_sheet_text,
    }


def load_history(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    return json.loads(p.read_text() or "[]")


def append_history(record: dict[str, Any], path: str | Path) -> list[dict[str, Any]]:
    """Append a record, replacing any prior record for the same accession so a
    re-run (e.g. an amendment reprocessed) doesn't duplicate rows."""
    p = Path(path)
    history = load_history(p)
    history = [r for r in history if r.get("accession") != record.get("accession")]
    history.append(record)
    history.sort(key=lambda r: r.get("filing_date", ""))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(history, indent=2) + "\n")
    return history


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

_BUCKET_COLORS = {
    "NEW": "#1a7f37",
    "INCREASED": "#0969da",
    "DECREASED": "#9a6700",
    "EXITED": "#cf222e",
    "UNCHANGED": "#6e7781",
}

_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
       margin: 0; padding: 1.5rem; line-height: 1.45; max-width: 1000px; margin: 0 auto; }
h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
.sub { color: #6e7781; font-size: 0.85rem; margin-bottom: 1.5rem; }
.filing { border: 1px solid #d0d7de; border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 1.5rem; }
.filing h2 { font-size: 1.15rem; margin: 0 0 0.25rem; }
.meta { color: #6e7781; font-size: 0.8rem; margin-bottom: 0.75rem; }
.badges { margin-bottom: 0.75rem; }
.badge { display: inline-block; color: #fff; border-radius: 999px; padding: 0.1rem 0.6rem;
         font-size: 0.75rem; font-weight: 600; margin-right: 0.35rem; }
table { width: 100%; border-collapse: collapse; font-size: 0.85rem; margin-bottom: 0.5rem; }
th, td { text-align: left; padding: 0.35rem 0.5rem; border-bottom: 1px solid #eaeef2; }
th { color: #6e7781; font-weight: 600; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
.tag { font-size: 0.72rem; font-weight: 600; padding: 0.05rem 0.4rem; border-radius: 4px; color: #fff; }
.opts { font-size: 0.8rem; color: #6e7781; margin: 0.5rem 0; }
details { margin-top: 0.5rem; }
summary { cursor: pointer; font-size: 0.85rem; color: #0969da; }
pre { background: #f6f8fa; padding: 0.75rem; border-radius: 6px; overflow-x: auto;
      font-size: 0.78rem; white-space: pre-wrap; }
.disclaimer { color: #cf222e; font-size: 0.8rem; margin-top: 2rem; border-top: 1px solid #d0d7de; padding-top: 1rem; }
@media (prefers-color-scheme: dark) {
  body { background: #0d1117; color: #c9d1d9; }
  .filing { border-color: #30363d; }
  th, td { border-color: #21262d; }
  pre { background: #161b22; }
}
"""


def _badge(label: str, count: int) -> str:
    color = _BUCKET_COLORS.get(label, "#6e7781")
    return f'<span class="badge" style="background:{color}">{label} {count}</span>'


def _entry_row(entry: dict[str, Any]) -> str:
    color = _BUCKET_COLORS.get(entry["bucket"], "#6e7781")
    ticker = html.escape(entry.get("ticker") or "—")
    issuer = html.escape(entry.get("issuer") or "")
    wc = entry["weight_change"]
    wc_str = f"{wc:+.2f}" if wc else "0.00"
    sc = entry["shares_change_pct"]
    sc_str = f"{sc:+.1f}%" if sc else "—"
    return (
        "<tr>"
        f'<td>{ticker}</td>'
        f'<td>{issuer}</td>'
        f'<td><span class="tag" style="background:{color}">{entry["bucket"]}</span></td>'
        f'<td class="num">{entry["weight_curr"]:.2f}%</td>'
        f'<td class="num">{wc_str}</td>'
        f'<td class="num">{sc_str}</td>'
        "</tr>"
    )


def _filing_section(record: dict[str, Any]) -> str:
    counts = record["counts"]
    badges = "".join(
        _badge(b, counts.get(b, 0))
        for b in ("NEW", "INCREASED", "DECREASED", "EXITED")
        if counts.get(b, 0)
    )
    opts = record["options"]
    opt_line = ""
    if opts["put_count"] or opts["call_count"]:
        opt_line = (
            f'<div class="opts">Options (not actionable): '
            f'{opts["put_count"]} puts / ${opts["put_notional"]:,} notional, '
            f'{opts["call_count"]} calls / ${opts["call_notional"]:,} notional</div>'
        )
    rows = "".join(_entry_row(e) for e in record["entries"]) or (
        '<tr><td colspan="6">No long positions.</td></tr>'
    )
    sheet = html.escape(record.get("trade_sheet_text", ""))
    index_url = html.escape(record.get("index_url", "#"))
    return f"""<section class="filing">
  <h2>{html.escape(record['quarter_label'])} 13F</h2>
  <div class="meta">Filed {html.escape(record['filing_date'])} ·
    accession {html.escape(record['accession'])} ·
    <a href="{index_url}">EDGAR filing</a></div>
  <div class="badges">{badges}</div>
  {opt_line}
  <table>
    <thead><tr><th>Ticker</th><th>Issuer</th><th>Bucket</th>
      <th class="num">Weight</th><th class="num">Δ wt (pp)</th><th class="num">Δ shares</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <details><summary>View trade sheet</summary><pre>{sheet}</pre></details>
</section>"""


def render_dashboard(history: list[dict[str, Any]]) -> str:
    """Render the full self-contained HTML dashboard, newest filing first."""
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections = "\n".join(_filing_section(r) for r in reversed(history)) or (
        "<p>No filings processed yet.</p>"
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Situational Awareness LP — 13F Monitor</title>
<style>{_CSS}</style>
</head>
<body>
<h1>Situational Awareness LP — 13F Monitor</h1>
<div class="sub">CIK 0002045724 · {len(history)} filing(s) tracked · generated {generated}</div>
{sections}
<div class="disclaimer">⚠️ Mechanical output of config rules. Estimates only.
NO auto-execution — review and trade manually.</div>
</body>
</html>
"""


def write_dashboard(history: list[dict[str, Any]], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_dashboard(history))
