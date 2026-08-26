"""Secure NT — Alerts and Warnings.

No structured extraction yet, same reasoning as wa_dfes.py. Live-checked
2026-08-26: the only confirmed RSS on an NT Government emergency domain is
pfes.nt.gov.au/newsroom/rss-feeds, which is general newsroom content, not
the alerts/warnings feed itself — using it would misrepresent press
releases as emergency alerts. No feed URL discoverable for
securent.nt.gov.au/alerts-warnings via plain fetch.
"""

from __future__ import annotations

import logging

from .base import CanonicalAlert

log = logging.getLogger(__name__)

NOT_YET_IMPLEMENTED = (
    "nt_securent: no alerts-specific feed found live (checked 2026-08-26); "
    "pfes.nt.gov.au/newsroom/rss-feeds is general news, not alerts — see "
    "module docstring"
)


def fetch() -> list[CanonicalAlert]:
    return []
