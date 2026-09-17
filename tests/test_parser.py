import pytest

from src.parser import (
    TYPE_PUT,
    TYPE_SHARES,
    ParseError,
    apply_tickers,
    build_cusip_ticker_map,
    parse_info_table,
)


def test_parses_all_rows(curr_xml):
    holdings = parse_info_table(curr_xml)
    # 4 long positions + 1 put.
    assert len(holdings) == 5


def test_put_is_typed(curr_xml):
    holdings = parse_info_table(curr_xml)
    puts = [h for h in holdings if h.type == TYPE_PUT]
    assert len(puts) == 1
    assert puts[0].cusip == "464288687"
    assert puts[0].value_usd == 800000000


def test_share_holding_fields(curr_xml):
    holdings = parse_info_table(curr_xml)
    nvda = next(h for h in holdings if h.cusip == "67066G104")
    assert nvda.type == TYPE_SHARES
    assert nvda.shares == 12000
    assert nvda.value_usd == 2600000
    assert nvda.issuer == "NVIDIA CORP"


def test_aggregates_duplicate_cusip_rows():
    xml = b"""<?xml version="1.0"?>
    <informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
      <infoTable><nameOfIssuer>FOO</nameOfIssuer><cusip>123456789</cusip>
        <value>100</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt></shrsOrPrnAmt></infoTable>
      <infoTable><nameOfIssuer>FOO</nameOfIssuer><cusip>123456789</cusip>
        <value>50</value><shrsOrPrnAmt><sshPrnamt>5</sshPrnamt></shrsOrPrnAmt></infoTable>
    </informationTable>"""
    holdings = parse_info_table(xml)
    assert len(holdings) == 1
    assert holdings[0].shares == 15
    assert holdings[0].value_usd == 150


def test_missing_cusip_raises():
    xml = b"""<?xml version="1.0"?>
    <informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
      <infoTable><nameOfIssuer>FOO</nameOfIssuer>
        <value>100</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt></shrsOrPrnAmt></infoTable>
    </informationTable>"""
    with pytest.raises(ParseError):
        parse_info_table(xml)


def test_no_info_table_raises():
    with pytest.raises(ParseError):
        parse_info_table(b"<root><nope/></root>")


def test_apply_overrides_and_logs_unmapped(curr_xml):
    holdings = parse_info_table(curr_xml)
    cusip_map = build_cusip_ticker_map({}, {"67066G104": "nvda", "553368106": "MP"})
    unmapped = apply_tickers(holdings, cusip_map)
    nvda = next(h for h in holdings if h.cusip == "67066G104")
    assert nvda.ticker == "NVDA"
    # The put and the two unmapped longs come back as unmapped CUSIPs.
    assert "464288687" in unmapped
