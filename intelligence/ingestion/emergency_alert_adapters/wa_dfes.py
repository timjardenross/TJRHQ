"""DFES — Emergency WA Warnings & Incidents.

No structured extraction yet — deliberately, not an oversight. Live-checked
2026-08-26: DFES's public incident-points dataset (DFES-055) was
decommissioned 2024-09-13; its replacement (DFES-058..070) is
access-restricted (apply via gis@dfes.wa.gov.au, per data.wa.gov.au). The
public page (emergencywa/prepare) returns no embedded feed/API reference
(checked via plain fetch — likely a JS-rendered SPA), so this is a
Firecrawl-render candidate, not a plain-fetch one.

Returns [] until either (a) DFES access is granted and this is rewritten
as a real feed adapter like nsw_rfs.py, or (b) the rendered DOM is
inspected and real CSS/text selectors are written here — guessing
selectors against a page never actually rendered would silently produce
wrong or empty data indistinguishable from "no current warnings", which
is worse than an honest not-yet-implemented skip.
"""

from __future__ import annotations

import logging

from .base import CanonicalAlert

log = logging.getLogger(__name__)

NOT_YET_IMPLEMENTED = (
    "wa_dfes: no public feed (DFES-055 retired 2024-09-13, replacement "
    "access-restricted); page requires JS render, selectors not yet "
    "written against verified DOM — see module docstring"
)


def fetch() -> list[CanonicalAlert]:
    return []
