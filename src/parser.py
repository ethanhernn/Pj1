"""Layer 2a: parse a 13F information-table XML into normalized holdings.

The information table is an XML attachment inside the filing directory. Its
elements live under a namespace that varies slightly across filings, so we match
on local element names rather than hard-coding the namespace URI.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any

from lxml import etree

from .edgar import EdgarClient, filing_dir_url

# Holding types after normalization.
TYPE_SHARES = "SHARES"
TYPE_PUT = "PUT"
TYPE_CALL = "CALL"


class ParseError(RuntimeError):
    """Raised when the info table cannot be located or is malformed."""


@dataclass
class Holding:
    cusip: str
    issuer: str
    value_usd: int          # as reported (whole dollars for post-2023 filings)
    shares: int
    type: str               # SHARES | PUT | CALL
    ticker: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cusip": self.cusip,
            "ticker": self.ticker,
            "issuer": self.issuer,
            "value_usd": self.value_usd,
            "shares": self.shares,
            "type": self.type,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Holding":
        return cls(
            cusip=d["cusip"],
            issuer=d["issuer"],
            value_usd=int(d["value_usd"]),
            shares=int(d["shares"]),
            type=d["type"],
            ticker=d.get("ticker"),
        )


def _local(tag: Any) -> str:
    """Strip namespace from an lxml tag name."""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _find_child_text(element: etree._Element, name: str) -> str | None:
    for child in element.iter():
        if _local(child.tag) == name and child.text is not None:
            return child.text.strip()
    return None


def _normalize_type(put_call: str | None) -> str:
    if not put_call:
        return TYPE_SHARES
    pc = put_call.strip().upper()
    if pc == "PUT":
        return TYPE_PUT
    if pc == "CALL":
        return TYPE_CALL
    return TYPE_SHARES


def parse_info_table(xml_bytes: bytes) -> list[Holding]:
    """Parse info-table XML bytes into aggregated holdings.

    Real 13Fs frequently split a single position across multiple <infoTable>
    rows (e.g. by investment discretion). Rows are aggregated by (cusip, type):
    shares and value are summed.
    """
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as exc:
        raise ParseError(f"info table is not valid XML: {exc}") from exc

    rows = [el for el in root.iter() if _local(el.tag) == "infoTable"]
    if not rows:
        raise ParseError("no <infoTable> entries found in document")

    aggregated: dict[tuple[str, str], Holding] = {}
    for row in rows:
        cusip = _find_child_text(row, "cusip")
        issuer = _find_child_text(row, "nameOfIssuer") or ""
        value_raw = _find_child_text(row, "value")
        shares_raw = _find_child_text(row, "sshPrnamt")
        put_call = _find_child_text(row, "putCall")

        if not cusip or value_raw is None or shares_raw is None:
            raise ParseError(
                f"infoTable row missing required fields (issuer={issuer!r}, cusip={cusip!r})"
            )

        try:
            value_usd = int(round(float(value_raw)))
            shares = int(round(float(shares_raw)))
        except ValueError as exc:
            raise ParseError(f"non-numeric value/shares for {issuer!r}: {exc}") from exc

        htype = _normalize_type(put_call)
        key = (cusip, htype)
        if key in aggregated:
            existing = aggregated[key]
            existing.value_usd += value_usd
            existing.shares += shares
        else:
            aggregated[key] = Holding(
                cusip=cusip,
                issuer=issuer,
                value_usd=value_usd,
                shares=shares,
                type=htype,
            )

    return list(aggregated.values())


def find_info_table_url(client: EdgarClient, cik_int: int, accession_no_dashes: str) -> str:
    """Locate the information-table XML inside a filing directory.

    Strategy: read the directory's index.json, take every `.xml` file except
    `primary_doc.xml`, and return the first whose contents actually contain
    `<infoTable`. Filenames are not standardized, so content sniffing is the
    only reliable discriminator.
    """
    base = filing_dir_url(cik_int, accession_no_dashes)
    index = client.get_json(f"{base}/index.json")
    items = index.get("directory", {}).get("item", [])
    candidates = [
        it["name"]
        for it in items
        if it.get("name", "").lower().endswith(".xml")
        and it.get("name", "").lower() != "primary_doc.xml"
    ]
    if not candidates:
        raise ParseError(f"no candidate XML attachments in {base}")

    for name in candidates:
        url = f"{base}/{name}"
        text = client.get_text(url)
        if "infoTable" in text:
            return url
    raise ParseError(f"none of {candidates} in {base} contained an info table")


def fetch_holdings(client: EdgarClient, cik_int: int, accession_no_dashes: str) -> list[Holding]:
    """Locate and parse the info table for a 13F filing into holdings."""
    url = find_info_table_url(client, cik_int, accession_no_dashes)
    xml_bytes = client.get_bytes(url)
    return parse_info_table(xml_bytes)


# ---------------------------------------------------------------------------
# CUSIP -> ticker mapping
# ---------------------------------------------------------------------------


def build_cusip_ticker_map(
    company_tickers: dict[str, Any], overrides: dict[str, str] | None = None
) -> dict[str, str]:
    """The SEC company_tickers.json is keyed by ticker/CIK, not CUSIP, so it does
    not contain CUSIPs directly. We therefore rely on the manual override map for
    CUSIP->ticker resolution and keep this function as the single place overrides
    are applied. (A richer CUSIP database can be slotted in here later.)
    """
    mapping: dict[str, str] = {}
    if overrides:
        mapping.update({k.upper(): v.upper() for k, v in overrides.items()})
    return mapping


def apply_tickers(
    holdings: list[Holding], cusip_to_ticker: dict[str, str]
) -> list[str]:
    """Annotate holdings in place with tickers where known. Returns the list of
    CUSIPs that could not be mapped (logged by the caller, never fatal)."""
    unmapped: list[str] = []
    for h in holdings:
        ticker = cusip_to_ticker.get(h.cusip.upper())
        if ticker:
            h.ticker = ticker
        else:
            unmapped.append(h.cusip)
    if unmapped:
        print(f"[parser] unmapped CUSIPs (no ticker): {sorted(set(unmapped))}", file=sys.stderr)
    return unmapped
