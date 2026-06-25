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
from service import (  # noqa: E402,F401
    request_advice,
    request_challenge,
    invoke,
    available_officers,
    evidence_brief,
)
from lessons import lessons_brief  # noqa: E402,F401
from outcomes import record_advisory, record_outcome  # noqa: E402,F401
from calibration import calibration_report  # noqa: E402,F401
from metrics import advisory_metrics  # noqa: E402,F401
from learning import historical_signal  # noqa: E402,F401

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
