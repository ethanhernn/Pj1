from src.differ import DECREASED, EXITED, INCREASED, NEW, diff_holdings
from src.parser import parse_info_table


def _diff(prev_xml, curr_xml):
    prev = parse_info_table(prev_xml)
    curr = parse_info_table(curr_xml)
    return diff_holdings(curr, prev, increase_threshold_pct=5.0)


def test_bucket_counts(prev_xml, curr_xml):
    result = _diff(prev_xml, curr_xml)
    counts = result.counts()
    # NVDA +20%, MP +60% -> 2 INCREASED; UEC + CEG -> 2 NEW; PLTR -> 1 EXITED.
    assert counts[NEW] == 2
    assert counts[INCREASED] == 2
    assert counts[EXITED] == 1
    assert counts[DECREASED] == 0


def test_options_excluded_from_buckets(prev_xml, curr_xml):
    result = _diff(prev_xml, curr_xml)
    cusips = {e.cusip for e in result.entries}
    assert "464288687" not in cusips  # the put never appears as an entry


def test_options_summary_captures_put_expansion(prev_xml, curr_xml):
    result = _diff(prev_xml, curr_xml)
    assert result.options.put_count == 1
    assert result.options.put_notional == 800000000


def test_weights_use_long_book_only(prev_xml, curr_xml):
    result = _diff(prev_xml, curr_xml)
    # Long book current = 2.6M + 0.8M + 0.6M + 0.7M = 4.7M.
    nvda = next(e for e in result.entries if e.cusip == "67066G104")
    assert abs(nvda.weight_curr - (2600000 / 4700000 * 100)) < 1e-6
    # weight is a share of the long book, never diluted by the $800M put.
    assert nvda.weight_curr < 100


def test_new_and_exited_edges(prev_xml, curr_xml):
    result = _diff(prev_xml, curr_xml)
    exited = result.by_bucket(EXITED)[0]
    assert exited.cusip == "69608A108"
    assert exited.shares_curr == 0
    assert exited.weight_curr == 0.0
    new = {e.cusip for e in result.by_bucket(NEW)}
    assert new == {"916896103", "21037T109"}
