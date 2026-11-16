"""yfinance-backed market data provider. Isolated from sizer.py so the sizing
logic can be unit-tested with a fake provider and no network."""

from __future__ import annotations

import sys

from .sizer import MarketData


class YFinanceProvider:
    """Pulls price, 14-day average volume, and next earnings date from yfinance.

    yfinance is fragile and breaks across versions; every call is wrapped so a
    single bad lookup degrades to None (the sizer drops that name) rather than
    aborting the whole sheet.
    """

    def __init__(self, avg_volume_days: int = 14) -> None:
        self.avg_volume_days = avg_volume_days

    def fetch(self, ticker: str) -> MarketData:
        import yfinance as yf  # imported lazily so importing this module is cheap

        price: float | None = None
        avg_volume: float | None = None
        next_earnings: str | None = None

        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period=f"{max(self.avg_volume_days + 5, 20)}d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
                vols = hist["Volume"].tail(self.avg_volume_days)
                if len(vols) > 0:
                    avg_volume = float(vols.mean())
        except Exception as exc:  # noqa: BLE001 - yfinance raises broadly
            print(f"[marketdata] price/volume lookup failed for {ticker}: {exc}", file=sys.stderr)

        try:
            cal = getattr(yf.Ticker(ticker), "calendar", None)
            next_earnings = _extract_earnings(cal)
        except Exception as exc:  # noqa: BLE001
            print(f"[marketdata] earnings lookup failed for {ticker}: {exc}", file=sys.stderr)

        return MarketData(price=price, avg_volume=avg_volume, next_earnings=next_earnings)


def _extract_earnings(calendar: object) -> str | None:
    """yfinance returns the calendar as a dict (newer) or DataFrame (older)."""
    if calendar is None:
        return None
    try:
        if isinstance(calendar, dict):
            val = calendar.get("Earnings Date")
            if isinstance(val, (list, tuple)) and val:
                return str(val[0])
            if val:
                return str(val)
        else:  # DataFrame-like
            if "Earnings Date" in getattr(calendar, "index", []):
                return str(calendar.loc["Earnings Date"].iloc[0])
    except Exception:  # noqa: BLE001
        return None
    return None
