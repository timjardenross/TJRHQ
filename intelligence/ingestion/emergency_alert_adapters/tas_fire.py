"""TasALERT — Current Warnings and Incidents.

No structured extraction yet, same reasoning as wa_dfes.py. Live-checked
2026-08-26: no feed/API URL discoverable in alert.tas.gov.au's page source
via plain fetch — Tasmania Fire Service's own docs mention RSS/KML/CAP-AU
formats exist but do not publish the URLs on the pages checked. Needs
either a direct answer from TFS on the real feed endpoint, or the
JS-rendered DOM inspected for real selectors, before this can safely
return real records.
"""

from __future__ import annotations

import logging

from .base import CanonicalAlert

log = logging.getLogger(__name__)

NOT_YET_IMPLEMENTED = (
    "tas_fire: no feed URL discoverable live (checked 2026-08-26); TFS "
    "documents RSS/KML/CAP-AU formats exist but not their URLs — needs "
    "confirmation or rendered-DOM selectors, see module docstring"
)


def fetch() -> list[CanonicalAlert]:
    return []
