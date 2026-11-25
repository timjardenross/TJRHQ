"""Integrity guard for health OSINT auto-curation (flag HEALTH_CURATION_GUARD_V1).

Two independent protections around the model's PUBLISH/REJECT/ESCALATE answer:

1. Strict schema validation of the raw model output. Anything missing,
   mistyped, out of enum, duplicated, ambiguous or oversized is treated as an
   invalid answer and the signal is ESCALATEd (left for a human). Validation
   never relaxes towards suppression.

2. A deterministic escalation guard, evaluated after the model answer and
   before any write. If a signal's stored source fields indicate possible
   safety content, a REJECT is converted to ESCALATE. The guard reads only
   structured fields of the stored row and the shape of the model answer; it
   never reads free text from the model to decide whether to escalate, and a
   model answer can only add reasons to escalate, never remove one.

Deterministic source fields (set by ingestion/parsers, not by the model):
  fda_flagged, adverse_event_text, signal_type, health_domain, severity,
  and the registered source name (authoritative safety/notice feeds).

Scope statement: this is a field/notice escalation, not a general safety
classifier. It guarantees that rows carrying structured safety fields, rows
from authoritative safety-notice sources, rows with a recorded severity at or
above "moderate", and rows using the narrow notice vocabulary are never
silently auto-rejected. It does not detect safety content expressed in other
wording; human review of REJECTs remains the control for that.
Model-provided indicators (additive only): safety_relevance,
  evidence_contribution == "SAFETY".

Pure functions, no I/O. The flag defaults OFF; callers must keep the legacy
code path when ``guard_enabled()`` is false.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any

FLAG_ENV = "HEALTH_CURATION_GUARD_V1"

DECISIONS = ("PUBLISH", "REJECT", "ESCALATE")
MISSION_RELEVANCE = frozenset({"RELEVANT", "LOW_CONFIDENCE", "NOT_RELEVANT"})
EVIDENCE_CONTRIBUTION = frozenset({
    "CONFIRMS", "CHALLENGES", "EXTENDS", "REPLICATION", "SAFETY", "BACKGROUND", "UNRESOLVED",
})

SAFETY_SIGNAL_TYPES = frozenset({"safety_alert", "adverse_event"})
SAFETY_DOMAIN_PREFIXES = ("safety", "adverse")

MAX_RAW_CHARS = 20_000
MAX_REASON_CHARS = 1_000
MAX_POPULATION_FIT_CHARS = 500
STORED_REASON_CHARS = 300

_CONTROL_AND_HIDDEN = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f"          # C0 controls except \t \n \r
    "\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]"  # zero-width, bidi
)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
# Only well-formed HTML tags of known names are removed (bare, or with name=value attributes), plus comments. Comparison
# operators and ranges such as "<2 mg", ">10 mg", "x<3 and y>5" are never tag-shaped and always survive intact.
_TAG_NAMES = (
    "a|abbr|b|base|body|br|button|center|code|div|em|embed|font|form|h[1-6]|head|hr|html|i|iframe|img|input|li|link|"
    "meta|object|ol|p|pre|script|section|select|small|span|strong|style|sub|sup|svg|table|tbody|td|textarea|th|thead|"
    "title|tr|u|ul"
)
_ATTR = r"""\s+[A-Za-z_:][-A-Za-z0-9_:.]*\s*=\s*(?:"[^"<>]{0,200}"|'[^'<>]{0,200}'|[^\s"'<>=`]{1,200})"""
_HTML_TAG = re.compile(rf"</?(?:{_TAG_NAMES})(?:{_ATTR}){{0,10}}\s*/?>", re.IGNORECASE)


def guard_enabled() -> bool:
    """Read at call time so tests and rollback behave without re-import."""
    return os.environ.get(FLAG_ENV, "").strip().lower() in ("1", "true", "yes", "on")


# --------------------------------------------------------------------------
# Text hygiene (applied to untrusted text before it is put in a prompt or in
# a stored reason)
# --------------------------------------------------------------------------

def sanitise_text(value: Any, limit: int) -> str:
    text = "" if value is None else str(value)
    text = _CONTROL_AND_HIDDEN.sub("", text)  # first, so hidden characters cannot split a tag or marker
    for _ in range(5):  # to a fixed point: removing a tag must not leave a re-formed tag behind
        stripped = _HTML_TAG.sub(" ", _HTML_COMMENT.sub(" ", text))
        if stripped == text:
            break
        text = stripped
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


# --------------------------------------------------------------------------
# Strict schema validation
# --------------------------------------------------------------------------

class SchemaError(ValueError):
    """Raised with a short machine code; the code is the only detail stored."""


def _no_duplicate_keys(pairs):
    seen: dict[str, Any] = {}
    for k, v in pairs:
        if k in seen:
            raise SchemaError("duplicate_key")
        seen[k] = v
    return seen


def _extract_object(raw: str) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise SchemaError("not_text")
    if len(raw) > MAX_RAW_CHARS:
        raise SchemaError("oversized_output")
    start = raw.find("{")
    if start < 0:
        raise SchemaError("no_object")
    if raw[:start].rstrip().endswith(("[", ",", ":")):
        raise SchemaError("not_object")  # an object nested in an array/other structure
    try:
        obj, end = json.JSONDecoder(object_pairs_hook=_no_duplicate_keys).raw_decode(raw[start:])
    except json.JSONDecodeError as exc:
        raise SchemaError("malformed_json") from exc
    if "{" in raw[start + end:]:
        raise SchemaError("ambiguous_multiple_objects")
    if not isinstance(obj, dict):
        raise SchemaError("not_object")
    return obj


def _enum(data: dict, key: str, allowed, *, required: bool) -> str | None:
    if key not in data or data[key] is None:
        if required:
            raise SchemaError(f"missing_{key}")
        return None
    value = data[key]
    if not isinstance(value, str):
        raise SchemaError(f"type_{key}")
    value = value.strip().upper()
    if value not in allowed:
        raise SchemaError(f"enum_{key}")
    return value


def validate_model_output(raw: str) -> dict[str, Any]:
    """Return a classification dict or raise SchemaError(code)."""
    data = _extract_object(raw)
    decision = _enum(data, "decision", DECISIONS, required=True)

    reason = data.get("reason")
    if not isinstance(reason, str):
        raise SchemaError("type_reason")
    if len(reason) > MAX_REASON_CHARS:
        raise SchemaError("oversized_reason")
    reason = sanitise_text(reason, STORED_REASON_CHARS)
    if not reason:
        raise SchemaError("empty_reason")

    safety = data.get("safety_relevance")
    if not isinstance(safety, bool):  # no bool("false"), no 0/1, no missing
        raise SchemaError("type_safety_relevance")

    mission_relevance = _enum(data, "mission_relevance", MISSION_RELEVANCE, required=False)
    evidence = _enum(data, "evidence_contribution", EVIDENCE_CONTRIBUTION, required=False)

    pop = data.get("population_fit")
    if pop is not None:
        if not isinstance(pop, str):
            raise SchemaError("type_population_fit")
        if len(pop) > MAX_POPULATION_FIT_CHARS:
            raise SchemaError("oversized_population_fit")
        pop = sanitise_text(pop, MAX_POPULATION_FIT_CHARS) or None

    return {
        "decision": decision,
        "reason": reason,
        "mission_relevance": mission_relevance,
        "evidence_contribution": evidence,
        "population_fit": pop,
        "safety_relevance": safety,
    }


# --------------------------------------------------------------------------
# Deterministic escalation guard
# --------------------------------------------------------------------------

def _norm_token(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return unicodedata.normalize("NFKC", value).strip().casefold()


def deterministic_safety_indicators(signal: dict[str, Any]) -> tuple[str, ...]:
    """Codes for stored source fields that indicate possible safety content.

    Fail-safe on malformed values: anything other than the expected null/false
    shape counts as an indicator.
    """
    codes: list[str] = []

    flagged = signal.get("fda_flagged")
    if flagged is not None and flagged is not False:
        codes.append("fda_flagged")

    ae = signal.get("adverse_event_text")
    if ae is not None and (not isinstance(ae, str) or ae.strip() != ""):
        codes.append("adverse_event_text")

    for field, code in (("signal_type", "safety_signal_type"),):
        value = signal.get(field)
        if value is None:
            continue
        token = _norm_token(value)
        if token is None or token in SAFETY_SIGNAL_TYPES:
            codes.append(code)

    domain = signal.get("health_domain")
    if domain is not None:
        token = _norm_token(domain)
        if token is None or token.startswith(SAFETY_DOMAIN_PREFIXES):
            codes.append("safety_health_domain")

    return tuple(codes)


# Additive deterministic source-text lexicon (reads stored title/description/adverse_event_text, never model output).
# Word-bounded, case-insensitive. Deliberately narrow: routine words such as "adverse effects" or "side effects" in study
# abstracts are NOT included, to keep reviewer workload tractable. Trade-off documented in the fix report.
_LEXICON_SRC = (
    r"recall(?:s|ed|ing)?",
    r"withdrawn\s+from\s+(?:the\s+)?market",
    r"market\s+withdrawal",
    r"(?:boxed|black[\s-]?box)\s+warning",
    r"serious\s+adverse",
    r"fatal(?:ly|ities|ity)?",
    r"deaths?",
    r"hospitali[sz](?:ed|ation|ations|e)",
    r"contaminat(?:ed|ion)",
    r"overdos(?:e|es|ed|ing)",
    r"safety\s+(?:communication|alert|warning|notice)",
    r"life[\s-]?threatening",
    r"anaphyla(?:xis|ctic)",
    # Notice-style wording (added fix-logic): regulator/agency warnings. 0 hits on 777 curator-suppressed rows (90 days).
    r"warns?\s+(?:of|about|against)",
    r"urges?\s+(?:patients|consumers|clinicians|people)",
    r"stop\s+using",
    r"do\s+not\s+(?:use|take)",
    r"drug\s+safety",
    r"safety\s+(?:issues?|concerns?)",
    r"adverse\s+event\s+report",
)
SAFETY_LEXICON = re.compile(r"\b(?:" + "|".join(_LEXICON_SRC) + r")\b", re.IGNORECASE)
# Description text of research abstracts routinely says "death", "recall" (memory), "serious adverse events" in routine
# results, so the description is checked only against the high-specificity regulatory phrases (measured on 90 days of
# suppressed rows: full lexicon on description alone would add 26 routine rows, the narrow subset adds 0).
DESCRIPTION_LEXICON = re.compile(
    r"\b(?:withdrawn\s+from\s+(?:the\s+)?market|market\s+withdrawal|(?:boxed|black[\s-]?box)\s+warning|"
    r"safety\s+(?:communication|alert|warning|notice))\b", re.IGNORECASE)
LEXICON_FIELDS = (("title", SAFETY_LEXICON), ("adverse_event_text", SAFETY_LEXICON), ("description", DESCRIPTION_LEXICON))
LEXICON_CODE = "source_text_safety_lexicon"


def source_text_lexicon_indicators(signal: dict[str, Any]) -> tuple[str, ...]:
    """Distinct reason code when stored source text contains safety vocabulary. Fail-safe: non-string values are coerced."""
    for field, pattern in LEXICON_FIELDS:
        value = signal.get(field)
        if value is None:
            continue
        text = unicodedata.normalize("NFKC", value if isinstance(value, str) else str(value))
        text = _CONTROL_AND_HIDDEN.sub("", text)
        if pattern.search(text):
            return (LEXICON_CODE,)
    return ()


# Authoritative safety / outbreak-notice feeds. Names normalised (NFKC, casefold, whitespace collapsed). Derived from
# health_source_registry (source_type health_agency): the feeds below publish recalls, safety communications or outbreak
# notices. Deliberately NOT listed: "WHO" (general news), "NIH", "NIH Research Alerts" (grant/project listings) and
# journals/preprints/trial registries. The regulator names that are not yet registered (TGA, EMA, MHRA, Health Canada,
# Medsafe, FDA Recalls) are listed so a future registry entry is covered without a code change.
AUTHORITATIVE_SAFETY_SOURCES = frozenset({
    "fda", "fda medwatch", "fda recalls", "fda drug safety communications",
    "cdc", "cdc epidemic tracking", "cdc health alert network",
    "who outbreak alerts",
    "tga", "ema", "mhra", "health canada", "medsafe",
})
SOURCE_CODE = "authoritative_safety_source"

# Severity values recorded by ingestion on safety-typed rows: moderate/severe/critical/mild (production, all time).
# Conservative rule: anything recorded other than an explicit low value counts, including unknown spellings and
# non-string values. Only these explicit low values do not trigger.
LOW_SEVERITY_VALUES = frozenset({"", "mild", "low", "minor", "none", "n/a"})
SEVERITY_CODE = "severity_at_or_above_moderate"


def authoritative_source_indicators(signal: dict[str, Any]) -> tuple[str, ...]:
    """Stored registered source name is an authoritative safety/notice feed. Reads only the stored row."""
    name = signal.get("source_name")
    if not isinstance(name, str):
        return ()
    token = " ".join(unicodedata.normalize("NFKC", name).casefold().split())
    return (SOURCE_CODE,) if token in AUTHORITATIVE_SAFETY_SOURCES else ()


def severity_indicators(signal: dict[str, Any]) -> tuple[str, ...]:
    """Recorded severity at or above moderate (fail-safe: unknown or malformed values count)."""
    value = signal.get("severity")
    if value is None:
        return ()
    token = _norm_token(value)
    if token is not None and token in LOW_SEVERITY_VALUES:
        return ()
    return (SEVERITY_CODE,)


def model_safety_indicators(classification: dict[str, Any]) -> tuple[str, ...]:
    """Additive-only: the model can raise a reason to escalate, never lower one."""
    codes: list[str] = []
    if classification.get("safety_relevance") is True:
        codes.append("model_safety_relevance")
    if classification.get("evidence_contribution") == "SAFETY":
        codes.append("model_evidence_safety")
    return tuple(codes)


def apply_guard(signal: dict[str, Any] | None, classification: dict[str, Any]) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Return (classification, codes). Only ever turns REJECT (or an
    unrecognised decision) into ESCALATE; PUBLISH/ESCALATE pass through
    untouched. ``signal=None`` (no source context) fails closed for REJECT."""
    decision = classification.get("decision")
    if decision not in DECISIONS:
        return {**classification, "decision": "ESCALATE",
                "reason": "integrity guard: unrecognised decision, escalated"}, ("invalid_decision",)
    if decision != "REJECT":
        return classification, ()

    if signal is None:
        codes: tuple[str, ...] = ("no_source_context",)
    else:
        codes = (deterministic_safety_indicators(signal) + authoritative_source_indicators(signal)
                 + severity_indicators(signal) + source_text_lexicon_indicators(signal))
    codes = codes + model_safety_indicators(classification)
    if not codes:
        return classification, ()

    original = sanitise_text(classification.get("reason"), 200)
    note = f"integrity guard: REJECT converted to ESCALATE for human review [{','.join(codes)}]"
    if original:
        note += f"; model reason: {original}"
    return {**classification, "decision": "ESCALATE", "reason": note[:STORED_REASON_CHARS + 120]}, codes
