# EDGAR Filing Monitor — Situational Awareness LP

Watches SEC EDGAR for new filings from one hedge fund, parses 13F holdings,
diffs them quarter-over-quarter, and generates a sized, rules-compliant trade
sheet pushed to your phone via [ntfy.sh](https://ntfy.sh).

**Target:** Situational Awareness LP (Leopold Aschenbrenner) — CIK `0002045724`.

## Hard constraint: no auto-execution. Ever.

The bot *proposes* trades as a notification + markdown sheet. You review and
execute manually. There is no broker integration, no order routing, no Signal
Stack. Options (puts/calls) are reported for context but **never** become buy
recommendations. See [Guardrails](#guardrails).

## Layers

| Layer | Module | Does |
|-------|--------|------|
| 1 — Detect | `src/poller.py` | Diff the submissions index against `state/seen_filings.json`, push a notification per new filing. |
| 2a — Parse | `src/parser.py` | Locate the 13F information-table XML, normalize `<infoTable>` rows into holdings. |
| 2b — Diff | `src/differ.py` | NEW / INCREASED / DECREASED / EXITED buckets with fund weights. Options excluded from actionable buckets. |
| 3 — Size | `src/sizer.py` | Apply `config.yaml` ruleset → sized trade sheet (price/volume/earnings via yfinance). |
| — | `src/main.py` | Orchestrator: one invocation = one poll cycle. |

## Setup

```bash
pip install -r requirements.txt
```

Edit `config.yaml`:

- `account.buying_power` — your real Trade The Pool account size.
- `ntfy.topic` — pick a hard-to-guess topic (or set `NTFY_TOPIC` as a secret).
- `cusip_overrides` — CUSIP→ticker for names the bot can't resolve (it logs unmapped CUSIPs).

> **CUSIP→ticker note:** the SEC's `company_tickers.json` is keyed by ticker/CIK,
> not CUSIP, so it can't map CUSIPs directly. Resolution currently relies on the
> manual `cusip_overrides` map; unmapped names are logged and dropped from the
> sheet rather than guessed. Slot a real CUSIP database into
> `parser.build_cusip_ticker_map` when one is available.

## Running

```bash
python -m src.main              # poll, notify, process any new 13F
python -m src.main --dry-run    # everything except sending ntfy pushes
python -m src.main --seed-only  # mark all current filings seen, send nothing
```

**First run:** use `--seed-only` once so you don't get blasted with a
notification for every historical filing. After that, only genuinely new
filings notify.

## GitHub Actions (free-tier cron)

`.github/workflows/poll.yml` runs `*/15 13-21 * * 1-5` (UTC market hours) and
commits updated state back to the branch. Set these repo **secrets** (Settings →
Secrets → Actions):

- `NTFY_TOPIC` — your private ntfy topic.
- `NTFY_SERVER` *(optional)* — defaults to `https://ntfy.sh`.
- `EDGAR_UA` *(optional)* — overrides the User-Agent; SEC requires `<name> <email>`.

Trigger manually from the Actions tab (`workflow_dispatch`) with the `dry_run` /
`seed_only` toggles.

## Notification priority

| Form | Priority | Why |
|------|----------|-----|
| `SC 13D` / `SC 13G` (+/A) | `urgent` | 5%+ stakes, time-sensitive |
| `13F-HR` / `13F-HR/A` | `high` | the main quarterly signal |
| everything else (`13F-NT`, …) | `default` | informational |

13D/13G get an **alert only** — no auto trade sheet (they lack full-book context).

## State

- `state/seen_filings.json` — accession numbers already processed.
- `state/holdings_prev.json` — parsed holdings from the last 13F (the diff baseline).
- `output/` — full markdown trade sheets, one per processed 13F.

No database. State is committed by the Action.

## Guardrails

- No order execution, no broker integration, no Signal Stack.
- Puts/calls never become buy recommendations; they appear only in the diff summary.
- Malformed numbers (negative shares/value, a name larger than the whole book) trigger an **ERROR push instead of a sheet** — a wrong sheet is worse than no sheet.
- Every sheet carries the "mechanical output of config rules" disclaimer.
- Weights are computed against the **long book only**, so the option book never dilutes sizing percentages.

> Note on 13F value scale: the SEC moved 13F holding values from thousands to
> whole dollars in 2023. This fund's filings are all post-2023, so values are
> whole dollars. Weights are ratios, so the scale doesn't affect diffs or sizing
> regardless.

## Tests

```bash
python -m pytest -q
```

Fixtures in `tests/fixtures/` model a two-quarter scenario (miner adds, a put
expansion, an exit) and exercise every layer plus the orchestrator end-to-end
with EDGAR and yfinance stubbed — no network required.

## Build status

- ✅ v0.1 — Layer 1 poller + ntfy + Actions cron
- ✅ v0.2 — parser + differ (fixture-tested)
- ✅ v0.3 — sizer + trade sheet output
- ⬜ v0.4 (optional) — deadline-week fast polling, HTML dashboard
