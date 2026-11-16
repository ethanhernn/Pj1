"""Layer 1: detect new filings for a CIK from the EDGAR submissions index."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .edgar import EdgarClient
from .notify import PRIORITY_DEFAULT, PRIORITY_HIGH, PRIORITY_URGENT

# Form types we care about, mapped to ntfy priority.
URGENT_FORMS = {"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"}
HIGH_FORMS = {"13F-HR", "13F-HR/A"}


@dataclass
class Filing:
    """One filing from the submissions index."""

    accession_number: str  # dashed form, e.g. 0002045724-26-000012
    form: str
    filing_date: str
    primary_document: str
    cik_int: int

    @property
    def accession_no_dashes(self) -> str:
        return self.accession_number.replace("-", "")

    @property
    def index_url(self) -> str:
        """Human-facing EDGAR filing index page."""
        return (
            f"https://www.sec.gov/Archives/edgar/data/{self.cik_int}/"
            f"{self.accession_no_dashes}/{self.accession_number}-index.htm"
        )

    @property
    def priority(self) -> str:
        if self.form in URGENT_FORMS:
            return PRIORITY_URGENT
        if self.form in HIGH_FORMS:
            return PRIORITY_HIGH
        return PRIORITY_DEFAULT


def parse_submissions(payload: dict[str, Any], cik_int: int) -> list[Filing]:
    """Turn the submissions JSON `filings.recent` parallel arrays into Filings.

    Note: the submissions endpoint can page older filings into separate files
    (`filings.files`); for a fund this young everything fits in `recent`, but the
    most recent filings — which is all this bot acts on — are always in `recent`.
    """
    recent = payload.get("filings", {}).get("recent", {})
    accessions = recent.get("accessionNumber", [])
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    primaries = recent.get("primaryDocument", [])

    filings: list[Filing] = []
    for i, accession in enumerate(accessions):
        filings.append(
            Filing(
                accession_number=accession,
                form=forms[i] if i < len(forms) else "",
                filing_date=dates[i] if i < len(dates) else "",
                primary_document=primaries[i] if i < len(primaries) else "",
                cik_int=cik_int,
            )
        )
    return filings


def fetch_filings(client: EdgarClient, cik_padded: str, cik_int: int) -> list[Filing]:
    payload = client.submissions(cik_padded)
    return parse_submissions(payload, cik_int)


def load_seen(path: str | Path) -> set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    data = json.loads(p.read_text() or "[]")
    return set(data)


def save_seen(path: str | Path, seen: set[str]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(seen), indent=2) + "\n")


def find_new_filings(filings: list[Filing], seen: set[str]) -> list[Filing]:
    """Return filings whose accession number is not yet in `seen`, oldest first
    so notifications arrive in chronological order."""
    new = [f for f in filings if f.accession_number not in seen]
    # submissions index is newest-first; reverse to notify oldest-first.
    new.reverse()
    return new
