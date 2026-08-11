"""USS-TJR-MSN-0092 Advisory Runtime.

Operationalises the existing (previously CLI-only) advisory engine behind one
shared service and one standard response schema. Reuse before rebuild — see
service.py for the engines it composes.

Typical use:

    from core.advisory import request_advice
    resp = request_advice("Should we prioritise X over Y?")
    print(resp.to_markdown())
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# Allow `import core.advisory` (package) AND flat-style imports used internally.
_HERE = _Path(__file__).resolve().parent
if str(_HERE) not in _sys.path:
    _sys.path.insert(0, str(_HERE))

from schema import (  # noqa: E402,F401
    AdvisoryResponse,
    ConfidenceLevel,
    EvidenceItem,
    LessonRef,
    OfficerPerspective,
    RelatedDecision,
    ADVISORY_AUTHORITY_NOTE,
)
from _local_import_advisory import import_sibling as _import_sibling  # noqa: E402

_service = _import_sibling("service")
request_advice = _service.request_advice
request_challenge = _service.request_challenge
invoke = _service.invoke
available_officers = _service.available_officers
evidence_brief = _service.evidence_brief

lessons_brief = _import_sibling("lessons").lessons_brief

_outcomes = _import_sibling("outcomes")
record_advisory = _outcomes.record_advisory
record_outcome = _outcomes.record_outcome

from calibration import calibration_report  # noqa: E402,F401
from metrics import advisory_metrics  # noqa: E402,F401

historical_signal = _import_sibling("learning").historical_signal

__all__ = [
    "AdvisoryResponse",
    "ConfidenceLevel",
    "EvidenceItem",
    "LessonRef",
    "OfficerPerspective",
    "RelatedDecision",
    "ADVISORY_AUTHORITY_NOTE",
    "request_advice",
    "request_challenge",
    "invoke",
    "available_officers",
    "evidence_brief",
    "lessons_brief",
    "record_advisory",
    "record_outcome",
    "calibration_report",
    "advisory_metrics",
    "historical_signal",
]
