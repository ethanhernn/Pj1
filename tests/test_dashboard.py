from src.dashboard import (
    append_history,
    build_record,
    load_history,
    render_dashboard,
)
from src.differ import diff_holdings
from src.parser import apply_tickers, build_cusip_ticker_map, parse_info_table
from src.poller import Filing


def _filing():
    return Filing(
        accession_number="0002045724-26-000012",
        form="13F-HR",
        filing_date="2026-05-15",
        primary_document="primary_doc.xml",
        cik_int=2045724,
    )


def _diff(prev_xml, curr_xml):
    prev = parse_info_table(prev_xml)
    curr = parse_info_table(curr_xml)
    cmap = build_cusip_ticker_map({}, {"67066G104": "NVDA", "553368106": "MP"})
    apply_tickers(prev, cmap)
    apply_tickers(curr, cmap)
    return diff_holdings(curr, prev, 5.0)


def test_build_record_shape(prev_xml, curr_xml):
    diff = _diff(prev_xml, curr_xml)
    rec = build_record(diff, _filing(), "Q1 2026", "SHEET TEXT")
    assert rec["accession"] == "0002045724-26-000012"
    assert rec["counts"]["NEW"] == 2
    assert rec["options"]["put_notional"] == 800000000
    # The put issuer must not appear in the entry list.
    assert all("SEMICONDUCTOR" not in e["issuer"].upper() for e in rec["entries"])


def test_append_history_dedupes_by_accession(prev_xml, curr_xml, tmp_path):
    diff = _diff(prev_xml, curr_xml)
    path = tmp_path / "diff_history.json"
    rec = build_record(diff, _filing(), "Q1 2026", "v1")
    append_history(rec, path)
    rec2 = build_record(diff, _filing(), "Q1 2026", "v2")
    history = append_history(rec2, path)
    assert len(history) == 1
    assert history[0]["trade_sheet_text"] == "v2"
    assert load_history(path) == history


def test_render_dashboard_html(prev_xml, curr_xml):
    diff = _diff(prev_xml, curr_xml)
    rec = build_record(diff, _filing(), "Q1 2026", "TRADE SHEET BODY <should escape>")
    html = render_dashboard([rec])
    assert "<!DOCTYPE html>" in html
    assert "Situational Awareness LP" in html
    assert "NEW 2" in html
    assert "&lt;should escape&gt;" in html  # sheet text is HTML-escaped
    assert "NO auto-execution" in html


def test_render_empty_history():
    html = render_dashboard([])
    assert "No filings processed yet" in html
