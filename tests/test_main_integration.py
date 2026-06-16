"""End-to-end orchestrator test: stub EDGAR + market data, run a full cycle and
assert a trade sheet is produced for the new 13F while the put is excluded."""

from pathlib import Path

import pytest

import src.main as main
import src.marketdata as marketdata
from src.parser import parse_info_table
from src.poller import Filing
from src.sizer import MarketData


class FakeProvider:
    def fetch(self, ticker: str) -> MarketData:
        return MarketData(price=100.0, avg_volume=5_000_000, next_earnings="2026-08-01")


@pytest.fixture
def cfg():
    return main.load_config()


def test_full_cycle_produces_sheet(monkeypatch, tmp_path, cfg, prev_xml, curr_xml):
    new_13f = Filing(
        accession_number="0002045724-26-000012",
        form="13F-HR",
        filing_date="2026-05-15",
        primary_document="primary_doc.xml",
        cik_int=2045724,
    )
    sc13d = Filing(
        accession_number="0002045724-26-000008",
        form="SC 13D",
        filing_date="2026-03-10",
        primary_document="sc13d.htm",
        cik_int=2045724,
    )

    monkeypatch.setattr(main, "fetch_filings", lambda *a, **k: [new_13f, sc13d])
    monkeypatch.setattr(main, "fetch_holdings", lambda *a, **k: parse_info_table(curr_xml))
    monkeypatch.setattr(main, "load_prev_holdings", lambda *a, **k: parse_info_table(prev_xml))
    monkeypatch.setattr(main, "load_seen", lambda *a, **k: set())
    monkeypatch.setattr(main, "save_prev_holdings", lambda *a, **k: None)
    monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(marketdata, "YFinanceProvider", FakeProvider)
    # add ticker overrides so names resolve
    cfg.cusip_overrides = {
        "67066G104": "NVDA",
        "553368106": "MP",
        "916896103": "UEC",
        "21037T109": "CEG",
    }

    handled = main.run_cycle(cfg, dry_run=True)
    assert handled == 2

    sheets = list(Path(tmp_path).glob("trade_sheet_*.md"))
    assert len(sheets) == 1
    text = sheets[0].read_text()
    assert "13F TRADE SHEET" in text
    assert "SEMICONDUCTOR" not in text.upper()  # put never sized
    assert "NO auto-execution" in text
