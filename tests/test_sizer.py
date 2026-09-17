from src.config import AccountConfig, RulesConfig
from src.differ import diff_holdings
from src.parser import apply_tickers, build_cusip_ticker_map, parse_info_table
from src.sizer import (
    MarketData,
    build_trade_sheet,
    render_trade_sheet,
)


class FakeProvider:
    """Deterministic market data keyed by ticker."""

    def __init__(self, data: dict[str, MarketData]):
        self.data = data

    def fetch(self, ticker: str) -> MarketData:
        return self.data.get(ticker, MarketData(None, None, None))


def _account():
    return AccountConfig(
        buying_power=10000,
        max_position_pct=15,
        max_total_exposure_pct=70,
        max_names=6,
        stop_loss_pct=7,
    )


def _rules():
    return RulesConfig(
        min_avg_daily_volume=500000,
        longs_only=True,
        source_buckets=["NEW", "INCREASED"],
        rank_by="weight",
        increase_threshold_pct=5,
    )


def _diff(prev_xml, curr_xml):
    prev = parse_info_table(prev_xml)
    curr = parse_info_table(curr_xml)
    overrides = {
        "67066G104": "NVDA",
        "553368106": "MP",
        "916896103": "UEC",
        "21037T109": "CEG",
    }
    cmap = build_cusip_ticker_map({}, overrides)
    apply_tickers(prev, cmap)
    apply_tickers(curr, cmap)
    return diff_holdings(curr, prev, 5.0)


def test_sizes_and_drops_low_volume(prev_xml, curr_xml):
    diff = _diff(prev_xml, curr_xml)
    provider = FakeProvider(
        {
            "NVDA": MarketData(price=135.0, avg_volume=40_000_000, next_earnings="2026-07-30"),
            "MP": MarketData(price=30.0, avg_volume=3_000_000, next_earnings="2026-08-12"),
            "UEC": MarketData(price=8.0, avg_volume=10_000_000, next_earnings=None),
            "CEG": MarketData(price=250.0, avg_volume=300_000, next_earnings="2026-08-01"),  # below floor
        }
    )
    sheet = build_trade_sheet(diff, _account(), _rules(), provider, "Q1 2026", "2026-05-15")

    tickers = {l.ticker for l in sheet.lines}
    assert "CEG" not in tickers  # dropped: volume below floor
    assert {"NVDA", "MP", "UEC"}.issubset(tickers)
    assert any("500,000 floor" in d.reason for d in sheet.drops if d.ticker == "CEG")


def test_no_options_ever_sized(prev_xml, curr_xml):
    diff = _diff(prev_xml, curr_xml)
    provider = FakeProvider(
        {t: MarketData(100.0, 5_000_000, None) for t in ["NVDA", "MP", "UEC", "CEG"]}
    )
    sheet = build_trade_sheet(diff, _account(), _rules(), provider, "Q1 2026", "2026-05-15")
    # The put's issuer must never appear as a buy line.
    assert all("SEMICONDUCTOR" not in l.issuer.upper() for l in sheet.lines)


def test_position_and_exposure_caps(prev_xml, curr_xml):
    diff = _diff(prev_xml, curr_xml)
    provider = FakeProvider(
        {t: MarketData(10.0, 5_000_000, None) for t in ["NVDA", "MP", "UEC", "CEG"]}
    )
    sheet = build_trade_sheet(diff, _account(), _rules(), provider, "Q1 2026", "2026-05-15")
    # No single position exceeds 15% of $10k = $1,500.
    assert all(l.dollars <= 1500 + 1e-6 for l in sheet.lines)
    # Total exposure does not exceed 70% of $10k = $7,000.
    assert sum(l.dollars for l in sheet.lines) <= 7000 + 1e-6


def test_stop_price_and_earnings_flag(prev_xml, curr_xml):
    diff = _diff(prev_xml, curr_xml)
    provider = FakeProvider(
        {
            "NVDA": MarketData(price=100.0, avg_volume=5_000_000, next_earnings=None),
            "MP": MarketData(price=20.0, avg_volume=5_000_000, next_earnings="2026-08-12"),
            "UEC": MarketData(price=8.0, avg_volume=5_000_000, next_earnings=None),
        }
    )
    sheet = build_trade_sheet(diff, _account(), _rules(), provider, "Q1 2026", "2026-05-15")
    nvda = next(l for l in sheet.lines if l.ticker == "NVDA")
    assert nvda.stop_price == 93.0  # 100 * (1 - 0.07)
    assert "UNKNOWN" in nvda.earnings  # no earnings date -> flagged

    rendered = render_trade_sheet(sheet)
    assert "mechanical output" in rendered
    assert "NO auto-execution" in rendered
    assert "not actionable" in rendered.lower()
