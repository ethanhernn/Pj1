"""Thin HTTP client for SEC EDGAR with the required User-Agent and rate limiting."""

from __future__ import annotations

import time
from typing import Any

import requests

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"


class EdgarError(RuntimeError):
    """Raised when EDGAR returns a non-200 response or a request fails."""


class EdgarClient:
    """Polite EDGAR client. Sleeps `sleep_seconds` before every request so a
    batch of fetches stays well under the SEC's 10 req/s ceiling."""

    def __init__(self, user_agent: str, sleep_seconds: float = 0.2, timeout: int = 30) -> None:
        if not user_agent or "@" not in user_agent:
            raise ValueError(
                "EDGAR requires a User-Agent like '<name> <email>'; got: %r" % user_agent
            )
        self.sleep_seconds = sleep_seconds
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
        )

    def _get(self, url: str) -> requests.Response:
        time.sleep(self.sleep_seconds)
        try:
            resp = self.session.get(url, timeout=self.timeout)
        except requests.RequestException as exc:  # network failure
            raise EdgarError(f"request to {url} failed: {exc}") from exc
        if resp.status_code != 200:
            raise EdgarError(f"GET {url} returned HTTP {resp.status_code}")
        return resp

    def get_json(self, url: str) -> Any:
        return self._get(url).json()

    def get_text(self, url: str) -> str:
        return self._get(url).text

    def get_bytes(self, url: str) -> bytes:
        return self._get(url).content

    def submissions(self, cik_padded: str) -> dict[str, Any]:
        return self.get_json(SUBMISSIONS_URL.format(cik=cik_padded))

    def company_tickers(self) -> dict[str, Any]:
        return self.get_json(COMPANY_TICKERS_URL)


def filing_dir_url(cik_int: int, accession_no_dashes: str) -> str:
    return f"{ARCHIVES_BASE}/{cik_int}/{accession_no_dashes}"
