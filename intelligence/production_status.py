"""Production status of an intelligence brief: NORMAL / DEGRADED / FAILED.

The status describes what was PRODUCED (content and collection) and nothing else. It is computed from content
and collection inputs only and has no delivery input, so a failed or unconfirmed send can never change it and a
perfect send can never improve it. Delivery truth lives in ``intelligence/delivery_record.py``.

Rules (first match wins for FAILED, every matching rule adds a reason for DEGRADED):
  FAILED    row not stored; or no usable narrative AND collection not ready.
  DEGRADED  narrative empty / boilerplate / placeholder or marked unavailable; deterministic fallback in use
            (no LLM narrative); claim gate did not pass; collection not ready; coverage degraded.
  NORMAL    none of the above.

The function is pure and always available. The flag ``BRIEF_STATUS_V1`` (default OFF) only gates the callers that
persist or display the result.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum

FLAG = "BRIEF_STATUS_V1"
_TRUE = ("1", "true", "yes", "on")


def enabled() -> bool:
    return os.getenv(FLAG, "").strip().lower() in _TRUE


class ProductionStatus(str, Enum):
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


@dataclass
class StatusResult:
    status: ProductionStatus
    reasons: list[str] = field(default_factory=list)


_MIN_SUBSTANTIVE_CHARS = 40
_BOILERPLATE = re.compile(
    r"^\W*(?:n/?a|none|null|nil|tbd|todo|unknown|empty|placeholder|lorem ipsum.*|"
    r"(?:narrative|summary|assessment|analysis|brief)\s+(?:is\s+)?(?:not\s+|un)available.*|"
    r"no\s+(?:narrative|summary|assessment|analysis)\s+(?:was\s+)?(?:available|generated|produced).*|"
    r"(?:unable|failed)\s+to\s+(?:generate|produce|parse)\b.*|"
    r"(?:llm|model|provider)\s+(?:is\s+)?(?:unavailable|failed|error).*|"
    r"nothing\s+(?:currently\s+)?(?:requires|to\s+report).*|"
    r"no\s+(?:significant\s+)?(?:events|incidents|signals|items)\b.{0,40})\W*$",
    re.IGNORECASE | re.DOTALL,
)

# Placeholder / error / template-marker / reassurance-only text anywhere in a narrative. Checked per SECTION (never on a joined composite),
# so a placeholder embedded in longer text cannot hide behind the length of its neighbours.
_PLACEHOLDER_MARKERS = (
    ("placeholder_bracketed", re.compile(r"\[[^\]\n]{0,160}\b(?:to\s+be\s+(?:generated|written|added|completed|filled)|will\s+be\s+(?:generated|added)|tbd|todo|placeholder|insert|pending|unavailable|not\s+available|n/?a)\b[^\]\n]{0,160}\]", re.IGNORECASE)),
    ("placeholder_to_be_generated", re.compile(r"\bto\s+be\s+(?:generated|written|determined|completed)\b|\bnot\s+(?:been\s+)?generated\s+yet\b|\bhas\s+not\s+been\s+generated\b", re.IGNORECASE)),
    ("placeholder_check_back", re.compile(r"\b(?:check|come)\s+back\s+(?:later|soon)\b|\bplease\s+check\s+back\b|\bunavailable[,.;:]?\s+(?:please\s+)?(?:check|try)\b", re.IGNORECASE)),
    ("placeholder_no_narrative", re.compile(r"\bno\s+(?:narrative|summary|assessment|analysis)\s+(?:could\s+be|was|is)\s+(?:produced|generated|available)\b|\bcould\s+not\s+be\s+(?:generated|produced)\b|\b(?:narrative|summary|snapshot|assessment)\s+(?:is\s+)?(?:currently\s+)?unavailable\b", re.IGNORECASE)),
    ("placeholder_todo", re.compile(r"(?:^|[\s\[(])(?:todo|fixme|tbd|xxx)\b|\blorem\s+ipsum\b|<\s*(?:insert|placeholder)[^>]*>", re.IGNORECASE)),
    ("template_marker", re.compile(r"\{\{[^}\n]{0,80}\}\}|\{%[^%\n]{0,80}%\}|<%[^%\n]{0,80}%>|\$\{[^}\n]{1,80}\}|\{[a-z_]{3,40}\}(?=\s|$)")),
    ("null_tokens", re.compile(r"(?:^|\s)(?:null|none|undefined|nan)(?:\s+(?:null|none|undefined|nan)){1,}(?:\s|$)", re.IGNORECASE)),
    ("placeholder_awaiting", re.compile(r"\b(?:awaiting|pending|waiting\s+(?:for|on))\b[^.\n]{0,50}\b(?:data|collectors?|sources?|input|inputs|analysis|results?|feeds?)\b|"
                                         r"\b(?:analysis|assessment|summary|brief|narrative|report|processing)\s+(?:is\s+|are\s+)?(?:still\s+)?(?:in\s+progress|pending|underway|being\s+(?:prepared|generated|compiled)|not\s+(?:yet\s+)?(?:ready|complete[d]?))\b", re.IGNORECASE)),
    ("placeholder_data_unavailable", re.compile(r"\b(?:data|information|content|evidence|results?|details)\s+(?:is\s+|are\s+)?(?:currently\s+|temporarily\s+)?(?:not|un)\s*available\b|"
                                                 r"\b(?:not|un)\s*available\s+at\s+this\s+time\b|\bno\s+(?:data|information|content)\s+(?:is\s+|was\s+)?(?:available|provided|returned|found)\b", re.IGNORECASE)),
    ("placeholder_coming_soon", re.compile(r"\bcoming\s+soon\b|\bwill\s+(?:appear|be\s+(?:available|published|added|provided|posted|shared|updated))\b[^.\n]{0,30}\b(?:here|shortly|soon|later)\b|\b(?:snapshot|summary|brief|analysis|narrative|assessment|report)\b[^.\n]{0,30}\b(?:to\s+follow|will\s+follow|follows?\s+(?:shortly|soon|later))\b|\bshortly\b[^.\n]{0,20}\bappear", re.IGNORECASE)),
    ("placeholder_see_elsewhere", re.compile(r"^\W*(?:please\s+)?(?:see|refer\s+to|consult)\s+(?:the\s+)?(?:attached|below|above|appendix|enclosed|linked|separate)\b|\bsee\s+(?:the\s+)?attached\s+(?:report|document|file|summary)\b", re.IGNORECASE)),
    ("model_refusal", re.compile(r"\b(?:sorry|apologies)\b[^.\n]{0,40}\b(?:i\s+(?:cannot|can'?t|am\s+unable|'m\s+unable)|unable\s+to)\b|\bi\s+(?:cannot|can'?t|am\s+unable\s+to|'m\s+unable\s+to|am\s+not\s+able\s+to|don'?t\s+have\s+(?:enough|access|the))\b|"
                                 r"\bas\s+an\s+ai\b|\bi'?m\s+sorry\b|\b(?:unable|cannot)\s+(?:to\s+)?(?:provide|produce|generate|write|create)\s+(?:a|an|the)\s+(?:summary|narrative|brief|assessment|analysis)\b", re.IGNORECASE)),
    ("draft_marker", re.compile(r"\bdraft\b[^.\n]{0,20}\b(?:do\s+not\s+(?:publish|send|distribute)|not\s+for\s+(?:publication|distribution))\b|\bdo\s+not\s+publish\b|\b(?:work\s+in\s+progress|wip)\b", re.IGNORECASE)),
    ("generation_skipped", re.compile(r"\b(?:generation|analysis|processing|brief|summary|narrative|assessment)\s+(?:was\s+|were\s+|has\s+been\s+)?(?:skipped|aborted|cancelled|canceled|not\s+performed|not\s+run|suppressed)\b|\bno\s+(?:analysis|assessment|processing)\s+(?:was|were)\s+(?:performed|done|carried\s+out|run)\b|\bcollection\s+failed\b[^.\n]{0,60}\b(?:no|not)\b", re.IGNORECASE)),
    ("error_http", re.compile(r"^\W*HTTP\s*[45]\d\d\b|\b(?:internal\s+server\s+error|bad\s+gateway|gateway\s+time-?out)\b[^.\n]{0,60}\b(?:provider|while|generat\w+|request)\b|\bwhile\s+generating\s+(?:the\s+)?(?:summary|narrative|brief|assessment)\b", re.IGNORECASE)),
    ("error_text", re.compile(r"^\W*(?:error|exception|traceback|fatal)\b\s*[:\-]|\b(?:llm|language\s+model|provider)\s+(?:request\s+)?(?:failed|error|timed\s+out|unavailable)\b|\brequest\s+failed\s+with\s+status\b", re.IGNORECASE)),
)
_ALL_CLEAR = re.compile(r"\ball[\s-]+clear\b|^\W*(?:no|nothing)\s+(?:significant|notable|material|major|of\s+concern)\b|"
                        r"\ball\s+quiet\b|\bnominal\b|\bnormal\s+parameters\b|\bnothing\s+(?:significant\s+|material\s+)?to\s+(?:flag|report|see)\b|"
                        r"\bno\s+(?:material|significant|notable|major)\s+(?:developments?|events?|incidents?|issues?|changes?|risks?)\b|\bnothing\s+of\s+(?:note|concern)\b|"
                        r"\boperating\s+(?:normally|within\s+normal)\b|\beverything\s+(?:is\s+)?(?:operating|running|fine|normal|healthy)\b|\bservices\s+(?:are\s+)?healthy\b|\bquiet\s+(?:day|morning|period)\b", re.IGNORECASE)
_SPECIFIC = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]{2,}\b|\b\d{2,}\b")
_NOT_ALL_CLEAR = re.compile(r"\b(?:not|never|no|isn'?t|is\s+not|does\s+not\s+(?:mean|confirm|indicate))\s+(?:an?\s+|the\s+)?(?:\w+\s+){0,3}?all[\s-]+clear\b", re.IGNORECASE)
_ALL_CLEAR_MAX_CHARS = 400      # an all-clear sentence on its own is reassurance, not an assessment; a long narrative that mentions one is judged on the rest


def _specific_count(text: str) -> int:
    """Incident-specific tokens in a text: capitalised words that do not start a sentence, and numbers of two or more digits. A reassurance
    sentence that names a specific incident is judged on its content, not as boilerplate."""
    n = 0
    for sent in re.split(r"(?<=[.!?:;])\s+|\n+", text):
        words = re.findall(r"[A-Za-z][A-Za-z'’-]*|\d{2,}", sent)
        n += sum(1 for i, w in enumerate(words) if i > 0 and (w[0].isupper() or w[0].isdigit()))
    return n


def placeholder_reasons(text: str | None) -> list[str]:
    """Reason codes for every placeholder/error/template/reassurance-only marker found in ONE section of text."""
    if not isinstance(text, str) or not text.strip():
        return []
    t = text.strip()
    out = [code for code, rx in _PLACEHOLDER_MARKERS if rx.search(t)]
    t_pos = _NOT_ALL_CLEAR.sub(" ", t)       # "this is not an all-clear" is a caveat, not reassurance
    if _ALL_CLEAR.search(t_pos) and len(re.sub(r"\s+", " ", t)) <= _ALL_CLEAR_MAX_CHARS and _specific_count(t_pos) < 2:
        out.append("narrative_all_clear_boilerplate")
    return out


def narrative_defect(narrative_text: str | None) -> str | None:
    """Return a reason code when the text cannot count as a real narrative, else None."""
    if narrative_text is None:
        return "narrative_missing"
    if not isinstance(narrative_text, str):
        return "narrative_not_text"
    stripped = narrative_text.strip()
    if not stripped:
        return "narrative_empty"
    if not re.search(r"[A-Za-z0-9]", stripped):
        return "narrative_empty"
    if _BOILERPLATE.match(stripped):
        return "narrative_boilerplate"
    found = placeholder_reasons(stripped)
    if found:
        return found[0]
    if len(re.sub(r"\W+", "", stripped)) < _MIN_SUBSTANTIVE_CHARS:
        return "narrative_too_short"
    return None


def coverage_degraded(coverage: dict | None) -> list[str]:
    cov = coverage if isinstance(coverage, dict) else {}
    reasons: list[str] = []
    if cov.get("degraded"):
        reasons.append("coverage_degraded")
    try:
        if int(cov.get("failed") or 0) > 0:
            reasons.append("sources_failed")
    except (TypeError, ValueError):
        reasons.append("coverage_unreadable")
    if cov.get("missing_sources"):
        reasons.append("sources_missing")
    return reasons


def compute_production_status(*, narrative_text: str | None, llm_used: bool, narrative_available: bool,
                              claim_gate: object | None, coverage: dict, row_stored: bool,
                              collection_ready: bool) -> StatusResult:
    """Status from content and collection only. There is deliberately no delivery parameter."""
    reasons: list[str] = []
    defect = narrative_defect(narrative_text)
    if not narrative_available and defect is None:
        defect = "narrative_marked_unavailable"
    usable_narrative = defect is None and bool(narrative_available)

    if not row_stored:
        reasons.append("row_not_stored")
    if not usable_narrative:
        reasons.append(defect or "narrative_marked_unavailable")
    if not collection_ready:
        reasons.append("collection_not_ready")
    if usable_narrative and not llm_used:
        reasons.append("deterministic_fallback_narrative")
    if claim_gate is not None and not bool(getattr(claim_gate, "passed", False)):
        mode = getattr(claim_gate, "mode", "unknown")
        reasons.append(f"claim_gate_not_passed:{mode}")
    for r in coverage_degraded(coverage):
        if r not in reasons:
            reasons.append(r)

    if not row_stored or (not usable_narrative and not collection_ready):
        return StatusResult(ProductionStatus.FAILED, reasons)
    if reasons:
        return StatusResult(ProductionStatus.DEGRADED, reasons)
    return StatusResult(ProductionStatus.NORMAL, [])


# ── Captain's brief status (computed from the narrative COMPONENT and the canonical ORI brief, never the joined composite) ─────────────

ORI_MAX_AGE_HOURS = 36.0          # usable-age limit of a daily canonical brief (matches the WP1 freshness rule)


def _parse_ts(value):
    from datetime import datetime, timezone
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        d = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def ori_brief_age_hours(row: dict | None, now=None):
    """Age in hours of a canonical ORI brief row (``generated_at``), or None when it cannot be established."""
    from datetime import datetime, timezone
    ts = _parse_ts((row or {}).get("generated_at"))
    if ts is None:
        return None
    return max(0.0, ((now or datetime.now(timezone.utc)) - ts).total_seconds() / 3600.0)


def ori_brief_stale(row: dict | None, now=None, max_age_hours: float = ORI_MAX_AGE_HOURS) -> bool:
    """True when the row is missing, has no usable timestamp, or is older than the usable-age limit (fail closed)."""
    if not row:
        return True
    age = ori_brief_age_hours(row, now)
    return age is None or age > max_age_hours


def text_section_defects(text: str | None) -> list[str]:
    """Placeholder markers found line by line in a composed brief (HTML removed). Each reason is reported once with its line count."""
    if not isinstance(text, str) or not text.strip():
        return []
    counts: dict[str, int] = {}
    for line in re.sub(r"<[^>]+>", "", text).splitlines():
        for code in placeholder_reasons(line):
            if code == "narrative_all_clear_boilerplate":
                continue                        # a single reassurance line inside a composed brief is judged by its component, not its line
            counts[code] = counts.get(code, 0) + 1
        if re.search(r"EVIDENCE COVERAGE INSUFFICIENT", line):
            counts["evidence_coverage_insufficient"] = counts.get("evidence_coverage_insufficient", 0) + 1
    return [f"{k}:{v}" for k, v in sorted(counts.items())]


def compute_captains_brief_status(*, brief_type: str, text: str | None, brief_id: str | None, collection_caveat: str | None,
                                  ori_brief: dict | None = None, now=None) -> StatusResult:
    """Status of a Captain's brief from content and collection only.

    * The text is checked section by section for placeholders (``text_section_defects``); a placeholder anywhere is DEGRADED.
    * For the morning brief the narrative component is the canonical ORI brief: missing, stale (> 36 h), or carrying its own
      DEGRADED/FAILED production status (an evidence-fallback brief) makes the Captain's brief DEGRADED. The ORI row's own status is read from
      its stored record, or computed from its own fields when none was stored. It is never judged by the length of the composite text.
    * No delivery input.
    """
    reasons: list[str] = [f"section:{d}" for d in text_section_defects(text)]
    row_stored = brief_id is not None
    collection_ready = not collection_caveat
    if collection_caveat:
        reasons.append("collection_caveat")
    if not isinstance(text, str) or not text.strip():
        reasons.append("brief_text_empty")
    if not row_stored:
        reasons.append("row_not_stored")
    if brief_type != "morning":
        d = narrative_defect(text)
        if d and d != "narrative_missing" and not any(r.startswith("section:") for r in reasons):
            reasons.append(d)                  # a short/empty/boilerplate non-morning brief (its own text is the narrative of record)
    if brief_type == "morning":
        if not ori_brief:
            reasons.append("canonical_brief_missing")
        else:
            age = ori_brief_age_hours(ori_brief, now)
            if age is None:
                reasons.append("canonical_brief_age_unknown")
            elif age > ORI_MAX_AGE_HOURS:
                reasons.append(f"canonical_brief_stale:{age:.0f}h")
            rec = None
            try:
                from intelligence.brief import ori_status
                rec = ori_status.from_row(ori_brief)
                if rec is None:
                    cov = ori_brief.get("coverage") if isinstance(ori_brief.get("coverage"), dict) else {}
                    rec = ori_status.compute(
                        executive_snapshot=ori_brief.get("executive_snapshot"), bottom_line=ori_brief.get("bottom_line"),
                        llm_used=bool(ori_brief.get("llm_used")), narrative_available=bool(ori_brief.get("narrative_available")),
                        coverage=cov, collection_ready=bool(cov.get("completed", 1)), now=now)
            except Exception:  # noqa: BLE001 - cannot establish the ORI status: not NORMAL
                reasons.append("canonical_brief_status_unreadable")
            if rec and rec.get("status") not in (None, "NORMAL"):
                reasons.append(f"canonical_brief_status:{rec['status']}")
    reasons = list(dict.fromkeys(reasons))
    if not row_stored or ("brief_text_empty" in reasons and not collection_ready):
        return StatusResult(ProductionStatus.FAILED, reasons)
    if reasons:
        return StatusResult(ProductionStatus.DEGRADED, reasons)
    return StatusResult(ProductionStatus.NORMAL, [])
