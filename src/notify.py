"""ntfy.sh push helpers. Fail loudly: in a cron context a swallowed error means
a missed filing, so notification failures are logged to stderr and re-raised by
the caller's discretion."""

from __future__ import annotations

import sys
from typing import Iterable

import requests

# ntfy priority names, lowest -> highest.
PRIORITY_MIN = "min"
PRIORITY_LOW = "low"
PRIORITY_DEFAULT = "default"
PRIORITY_HIGH = "high"
PRIORITY_URGENT = "urgent"


def push(
    server: str,
    topic: str,
    message: str,
    *,
    title: str | None = None,
    priority: str = PRIORITY_DEFAULT,
    tags: Iterable[str] | None = None,
    click: str | None = None,
    timeout: int = 15,
) -> bool:
    """Send a single ntfy notification. Returns True on success, False on failure
    (and prints the failure to stderr). Never raises so one bad push can't abort a
    poll cycle that may still have other filings to report."""
    url = f"{server.rstrip('/')}/{topic}"
    headers: dict[str, str] = {"Priority": priority}
    if title:
        headers["Title"] = title
    if tags:
        headers["Tags"] = ",".join(tags)
    if click:
        headers["Click"] = click
    try:
        resp = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=timeout)
        if resp.status_code >= 300:
            print(f"[notify] ntfy returned HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
            return False
        return True
    except requests.RequestException as exc:
        print(f"[notify] ntfy push failed: {exc}", file=sys.stderr)
        return False


def push_error(server: str, topic: str, context: str, detail: str) -> bool:
    """Standardized ERROR push. A wrong sheet is worse than no sheet, so parsing
    and validation failures surface here instead of producing output."""
    return push(
        server,
        topic,
        message=f"{context}\n\n{detail}",
        title="EDGAR BOT ERROR",
        priority=PRIORITY_HIGH,
        tags=["rotating_light"],
    )
