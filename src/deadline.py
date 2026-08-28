"""13F filing-deadline windows.

13F-HRs are due ~45 days after each quarter end (Dec/Mar/Jun/Sep 31/30), so they
cluster in mid-Feb, mid-May, mid-Aug, and mid-Nov. During those windows the
GitHub Actions workflow polls every 5 minutes instead of every 15 (see
.github/workflows/poll.yml). This module is the single source of truth for what
"deadline window" means, kept in sync with the cron and unit-tested.
"""

from __future__ import annotations

from datetime import date

# Months that contain a 45-day filing deadline.
DEADLINE_MONTHS = {2, 5, 8, 11}
# Day-of-month range bracketing the ~14th/15th deadline (matches the cron).
WINDOW_START_DAY = 10
WINDOW_END_DAY = 20


def is_deadline_window(d: date | None = None) -> bool:
    """True if `d` falls in a 13F filing-deadline window."""
    d = d or date.today()
    return d.month in DEADLINE_MONTHS and WINDOW_START_DAY <= d.day <= WINDOW_END_DAY
