"""Layered executive brief renderer (flag ``BRIEF_LAYERED_V1``, default OFF; shadow-only until integrated).

Pure and deterministic: no I/O, no LLM, no network, never sends anything. It turns already-assessed incidents into seven layers:

  L1 Executive BLUF (about 1,200 characters is a target, not a cap)    L5 Forward outlook and indicators
  L2 Key judgements (qualitative)                                      L6 Collection limitations (always present)
  L3 Detailed material assessments (proportionate, no character cap)   L7 Evidence and references
  L4 National, systemic and sector implications

Three axes are kept separate and never derived from each other:
  * operational posture   RED / AMBER / GREEN / UNKNOWN (UNKNOWN = NOT ASSESSED: evidence insufficient for a defensible risk judgement)
  * intelligence coverage FULL / PARTIAL / DEGRADED (with named limits)
  * assessment confidence HIGH / MODERATE / LOW (with a basis)
A collection failure is never rendered as a disruption; incomplete coverage is never a bare all-clear.

Six epistemic classes label every statement: established fact, reported-unverified, analytical assessment, inference,
forecast/scenario, known unknown. Each incident has ONE canonical treatment (L3); other layers refer to it by handle.
International developments with material national, systemic or sector relevance get the same substantive treatment as domestic
ones whether or not Australian impact has occurred; only low-relevance international items collapse into a counted summary.
Analytical depth is never reduced to meet the L1 or audio targets: L1 selects and points, L3 carries the depth.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

FLAG = "BRIEF_LAYERED_V1"
L1_TARGET_CHARS = 1200
AUDIO_DEFAULT_MINUTES = 3.0
AUDIO_WORDS_PER_MINUTE = 150
SHADOW_KEY = "shadow_v1"
SHADOW_MAX_BYTES = 64 * 1024   # was 24 KB: real days (~900 incidents) exceed it even at compact level 5, so nothing was stored (#753)
STORED_RECON_HEADROOM = 900
SHADOW_BLOCKED_DOMAINS = frozenset({"health", "capacity", "personal", "wellbeing"})


def enabled() -> bool:
    return os.getenv(FLAG, "").strip().lower() in ("1", "true", "yes", "on")


class OperationalPosture(str, Enum):
    RED = "RED"
    AMBER = "AMBER"
    GREEN = "GREEN"
    UNKNOWN = "UNKNOWN"          # NOT ASSESSED: insufficient evidence for a defensible risk judgement


class CoverageStatus(str, Enum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    DEGRADED = "DEGRADED"


class Confidence(str, Enum):
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"


class EpistemicClass(str, Enum):
    ESTABLISHED_FACT = "established fact"
    REPORTED_UNVERIFIED = "reported, unverified"
    ANALYTICAL_ASSESSMENT = "analytical assessment"
    INFERENCE = "inference"
    FORECAST = "forecast or scenario"
    KNOWN_UNKNOWN = "known unknown"


TAG = {EpistemicClass.ESTABLISHED_FACT: "FACT", EpistemicClass.REPORTED_UNVERIFIED: "REPORTED", EpistemicClass.ANALYTICAL_ASSESSMENT: "ASSESSMENT",
       EpistemicClass.INFERENCE: "INFERENCE", EpistemicClass.FORECAST: "FORECAST", EpistemicClass.KNOWN_UNKNOWN: "UNKNOWN"}

POSTURE_WORDS = {OperationalPosture.RED: "RED: confirmed disruption to an essential service",
                 OperationalPosture.AMBER: "AMBER: provisional, single-source or emerging material risk",
                 OperationalPosture.GREEN: "GREEN: no significant development identified",
                 OperationalPosture.UNKNOWN: "NOT ASSESSED: evidence is insufficient for a defensible risk judgement"}

_PRIORITY_ORDER = {"ESCALATE": 0, "VERIFY": 1, "WATCH": 2, "REFERENCE": 3}
_MATERIALITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_CONFIRMED = ("officially_confirmed", "corroborated")


# --------------------------------------------------------------------------------------------------------------------------------
# input normalisation
# --------------------------------------------------------------------------------------------------------------------------------
@dataclass
class LayeredIncident:
    incident_id: str
    headline: str
    priority: str = "WATCH"                 # ESCALATE | VERIFY | WATCH | REFERENCE
    materiality: str = "low"                # high | medium | low
    kind: str = "incident"                  # incident | collection_issue (a source-health item: never a disruption)
    scope: str = "domestic"                 # domestic | international | unknown
    relevance: str | None = None            # high | medium | low | unassessed; 'low' only when DEMONSTRATED (basis supplied by the adapter)
    relevance_basis: str = ""
    event_type: str = ""
    impact_status: str = "unconfirmed"      # stated | unconfirmed | retrospective | potential | warning | forecast
    evidence_status: str = "reported"       # officially_confirmed | corroborated | reported | unverified
    independent_publishers: int = 1
    provisional: bool = True
    state: str = ""                         # ongoing | partially restored | restored | current status unknown
    n_reports: int = 1
    sectors: list[str] = field(default_factory=list)
    summary: str = ""
    next_step: str = ""
    competing_explanation: str = ""
    known_unknowns: list[str] = field(default_factory=list)
    indicators: list[str] = field(default_factory=list)
    implications: list[str] = field(default_factory=list)   # sourced national/systemic/sector implications (class: inference)
    reports: list[dict] = field(default_factory=list)       # provenance: publisher, title, url, collected_at, role
    domain: str = ""
    pir: dict = field(default_factory=dict)                 # PirTagResult shape: {matches:[{pir_id,priority,basis}], unmatched_high_severity, emerging}
    last_seen: str | None = None
    outside_window: bool = False            # older than the brief window: never dropped, counted-with-titles (or one line if material)
    severity: str = ""                      # 'high' when the STORED classifier shows risk HIGH/CRITICAL and customer impact high/critical (adapter-supplied)
    driver: str = ""                        # '' | 'RED' | 'AMBER': set by render_layered for the incidents that drive the posture (always leads L1)
    last_seen_ts: float = 0.0               # derived epoch of last_seen (ordering only)

    @classmethod
    def from_any(cls, x: Any) -> LayeredIncident:
        if isinstance(x, cls):
            return x
        get = (lambda k, d=None: x.get(k, d)) if isinstance(x, dict) else (lambda k, d=None: getattr(x, k, d))
        names = cls.__dataclass_fields__.keys()
        kw = {k: get(k) for k in names if get(k) is not None}
        if "headline" not in kw:
            kw["headline"] = str(get("title", "") or "")
        if "incident_id" not in kw:
            raise ValueError("incident without incident_id")
        if "pir" in kw and not isinstance(kw["pir"], dict):          # WP5 PirTagResult (dataclass) -> plain dict
            res = kw["pir"]
            kw["pir"] = {"matches": [{"pir_id": m.pir_id, "priority": m.priority, "basis": m.basis, "strength": getattr(m, "strength", "strong")} for m in getattr(res, "matches", [])],
                         "unmatched_high_severity": bool(getattr(res, "unmatched_high_severity", False)), "emerging": bool(getattr(res, "emerging", False)),
                         "watch_lane": bool(getattr(res, "watch_lane", getattr(res, "unmatched_high_severity", False))),
                         "high_severity": bool(getattr(res, "high_severity", getattr(res, "unmatched_high_severity", False)))}
        for k in ("sectors", "known_unknowns", "indicators", "implications", "reports"):
            if k in kw:
                kw[k] = list(kw[k])
        if "last_seen" in kw and isinstance(kw["last_seen"], datetime):
            kw["last_seen"] = kw["last_seen"].isoformat()
        kw.pop("last_seen_ts", None)
        obj = cls(**kw)
        obj.last_seen_ts = _ts(obj.last_seen)
        return obj

    @property
    def handle(self) -> str:
        return f"[{self.incident_id}]"


def _ts(v) -> float:
    if not v:
        return 0.0
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()
    except ValueError:
        return 0.0


def _strong_a(i: LayeredIncident) -> bool:
    return any(m.get("priority") == "A" and m.get("strength", "strong") == "strong" for m in (i.pir or {}).get("matches") or [])


def in_watch_lane(i: LayeredIncident) -> bool:
    """Watch/REVIEW lane: high severity by the stored classifier, REGARDLESS of PIR match strength (a PIR match annotates, never removes)."""
    p = i.pir or {}
    return i.kind == "incident" and bool(p.get("watch_lane") or p.get("unmatched_high_severity"))


def lane_only(i: LayeredIncident) -> bool:
    """In the watch lane with no STRONG requirement match: shown on the review list, never assessed in full on classifier severity alone."""
    return in_watch_lane(i) and not any(m.get("strength", "strong") == "strong" for m in (i.pir or {}).get("matches") or [])


def decision_key(i: LayeredIncident) -> tuple:
    """Deterministic decision-value order (most decision-relevant first): posture driver, priority tier, materiality, strong Priority-A match,
    corroboration (official > corroborated/2+ publishers > single source), recency (newest first), then headline and id ONLY as the last
    tie-breaks so equal items never come out in hash order of unrelated fields."""
    conf = 0 if i.evidence_status == "officially_confirmed" else (1 if (i.evidence_status == "corroborated" or i.independent_publishers >= 2) else 2)
    return ({"RED": 0, "AMBER": 1}.get(i.driver, 2), _PRIORITY_ORDER.get(i.priority, 9), _MATERIALITY_ORDER.get(i.materiality, 9),
            0 if _strong_a(i) else 1, conf, -i.last_seen_ts, i.headline.lower(), i.incident_id)


def _norm(incidents) -> list[LayeredIncident]:
    out = [LayeredIncident.from_any(i) for i in incidents or []]
    out.sort(key=decision_key)
    return out


def relevance_of(i: LayeredIncident) -> str:
    """Relevance of an item to national, systemic or sector resilience: 'high' | 'medium' | 'low' | 'unassessed'.
    An explicit value wins. Otherwise it is derived ONLY upward from positive signals (a strong Priority-A match -> high; any PIR match,
    sector, ESCALATE/VERIFY priority, non-low materiality, unmatched high-severity or emerging flag -> medium). 'low' is never inferred
    from the absence of signals: it must be supplied with a basis. When nothing establishes relevance the answer is 'unassessed', and an
    unassessed item is surfaced (never collapsed to a count)."""
    if i.relevance in ("high", "medium", "low", "unassessed"):
        return i.relevance
    pir = i.pir or {}
    matches = pir.get("matches") or []
    if any(m.get("priority") == "A" and m.get("strength", "strong") == "strong" for m in matches):
        return "high"
    if matches or i.sectors or i.priority in ("ESCALATE", "VERIFY") or i.materiality in ("high", "medium") \
            or pir.get("unmatched_high_severity") or pir.get("emerging"):
        return "medium"
    return "unassessed"


def detail_level(i: LayeredIncident) -> str:
    """'full' (assessed in full), 'line' (one line), 'count' (counted summary, titles still listed) or 'none'.
    Only a DEMONSTRABLY low-relevance item (relevance 'low' with a stored basis) that is not urgent, not a posture driver and not in the
    watch lane may be counted; age alone never collapses a medium or high relevance item (outside the window it is one titled line).
    International items with material relevance are treated like domestic ones. A watch-lane item with no strong requirement match is a
    REVIEW line (unless the stored classifier shows risk HIGH/CRITICAL AND customer impact high/critical) but is never counted away. A posture driver is always full."""
    if i.kind != "incident":
        return "none"
    if i.driver:
        return "full"
    rel = relevance_of(i)
    urgent = i.priority in ("ESCALATE", "VERIFY") or i.materiality == "high"
    lane = in_watch_lane(i)
    if i.outside_window:
        return "count" if (rel == "low" and not urgent and not lane) else "line"
    if urgent:
        return "full"
    if rel == "low" and not lane:
        return "count" if (i.scope == "international" or i.priority == "REFERENCE") else "line"
    if lane_only(i) and i.severity != "high":
        return "line"          # classifier disposition/relevance alone: a review line (severity risk HIGH + impact high earns a full assessment)
    if rel == "high" or (rel == "medium" and i.scope == "international"):
        return "full"
    return "line"


# --------------------------------------------------------------------------------------------------------------------------------
# axes
# --------------------------------------------------------------------------------------------------------------------------------
def coverage_impaired(coverage: dict | None) -> bool:
    """True when the collection failure is large enough or critical enough to limit what any judgement can claim: completed/expected
    below 80%, a failed collection status, a cutoff, a named critical source failure, an unavailable domain, or a degraded flag with no
    ratio to grade it. A degraded flag over a nearly complete run (a few chronic missing sources) is NOT impairment on its own."""
    c = coverage or {}
    if not c:
        return True
    expected, completed = c.get("expected"), c.get("completed")
    ratio = (completed / expected) if isinstance(expected, (int, float)) and expected and isinstance(completed, (int, float)) else None
    if str(c.get("collection_status") or "").lower() in ("failed", "failure", "error") or c.get("cutoff_reached"):
        return True
    if c.get("critical_sources_failed") or c.get("critical_missing"):
        return True
    if c.get("stale_canonical_brief"):          # the canonical brief's coverage does not describe this morning
        return True
    if any(isinstance(d, dict) and (d.get("error") or d.get("available") is False) for d in (c.get("domains") or {}).values()):
        return True
    if ratio is not None:
        return ratio < 0.8
    return bool(c.get("degraded"))


def coverage_status_from(coverage: dict | None) -> tuple[CoverageStatus, list[str]]:
    """Coverage axis from the stored ``coverage`` jsonb shape (expected/completed/failed/stale/missing_sources/degraded/...). Returns
    (status, named limits). Independent of posture: nothing here is about what happened in the world. DEGRADED means impaired (see
    ``coverage_impaired``); a degraded flag over a nearly complete run grades PARTIAL with the missing sources still NAMED."""
    c = coverage or {}
    limits: list[str] = []
    missing = [str(s) for s in c.get("missing_sources") or []]
    failed, stale = int(c.get("failed") or 0), int(c.get("stale") or 0)
    expected, completed = c.get("expected"), c.get("completed")
    if missing:
        limits.append("sources not collected: " + ", ".join(missing))
    for key, label in (("critical_sources_failed", "critical sources failed"), ("critical_missing", "critical sources missing")):
        if c.get(key):
            limits.append(label + ": " + ", ".join(str(x) for x in c[key]))
    if failed:
        limits.append(f"{failed} source(s) failed collection")
    if stale:
        limits.append(f"{stale} source(s) stale")
    if c.get("cutoff_reached"):
        limits.append("collection stopped at its time cutoff")
    if c.get("reason"):
        limits.append(str(c["reason"]))
    for dom, d in (c.get("domains") or {}).items():
        if isinstance(d, dict) and (d.get("error") or d.get("available") is False):
            limits.append(f"domain '{dom}' unavailable" + (f" ({d['error']})" if d.get("error") else ""))
    ratio = (completed / expected) if isinstance(expected, (int, float)) and expected and isinstance(completed, (int, float)) else None
    status_flag = str(c.get("collection_status") or "").lower()
    if ratio is not None and ratio < 1.0:
        limits.append(f"{completed} of {expected} expected sources completed")
    if not c:
        return CoverageStatus.DEGRADED, ["no coverage record available"]
    if coverage_impaired(c):
        return CoverageStatus.DEGRADED, limits or ["collection degraded"]
    if limits or c.get("degraded") or status_flag in ("partial", "degraded"):
        return CoverageStatus.PARTIAL, limits or ["collection reported degraded"]
    return CoverageStatus.FULL, limits


MIN_JUDGEMENT_ITEMS = 3     # retained for readers of the old rule; no longer a posture input (see assess_posture)


def is_current(i: LayeredIncident) -> bool:
    """A CURRENT incident: inside the brief window, not retrospective, not restored. Restored, retrospective, out-of-window and
    REFERENCE-only items never drive RED or AMBER."""
    return (i.kind == "incident" and not i.outside_window and i.impact_status != "retrospective" and i.state != "restored"
            and i.priority != "REFERENCE")


def _corroborated(i: LayeredIncident) -> bool:
    return i.evidence_status in _CONFIRMED or i.independent_publishers >= 2


def posture_drivers(incidents) -> tuple[list[LayeredIncident], list[LayeredIncident]]:
    """(red, amber) driver incidents. RED: current ESCALATE-tier item, impact stated, officially confirmed or 2+ independent publishers,
    not provisional. AMBER (current items only): ESCALATE tier; VERIFY tier with high materiality; or a watch-lane item whose STORED
    classifier severity is high (risk HIGH/CRITICAL and customer impact high/critical), that is corroborated or officially confirmed, and
    whose tier is not REFERENCE (the justified severity + recency rule: severity from the classifier, recency = inside the window and
    current). Watch-lane items that do not meet it, and emerging-risk language, are REVIEW/Watch material and never set posture alone."""
    inc = [i for i in _norm(incidents) if is_current(i)]
    red = [i for i in inc if i.priority == "ESCALATE" and i.impact_status == "stated" and _corroborated(i) and not i.provisional]
    amber = [i for i in inc if i not in red and (i.priority == "ESCALATE" or (i.priority == "VERIFY" and i.materiality == "high")
                                                 or (in_watch_lane(i) and i.severity == "high" and _corroborated(i)))]
    return red, amber


def assess_posture(incidents, *, coverage_status: CoverageStatus, n_events: int | None = None, impaired: bool | None = None,
                   events_evaluated: int | None = None, criticality: dict | None = None, detail: dict | None = None) -> tuple[OperationalPosture, list[str]]:
    """Operational posture. Precedence (documented decision): RED, then AMBER (both only from CURRENT incidents with decision value, see
    ``posture_drivers``), then UNKNOWN, then GREEN. Evidenced RED/AMBER wins over insufficiency because an item a reader must act on
    does not become less real when collection is partly impaired; the limits are still stated beside it (``unknown_triggers`` in
    ``detail``). UNKNOWN (NOT ASSESSED) applies when no RED/AMBER evidence exists AND any of: collection impaired (``impaired``);
    a critical source lost, a PIR with no sufficient healthy serving source, or authoritative evidence unavailable (``criticality``, the
    PDB-owned producer, Priority-A requirements only); no reports evaluated at all. None of these depends on the item count or on the
    aggregate completed/expected ratio. GREEN otherwise; GREEN under non-FULL coverage is still rendered with the named limits (L1)."""
    inc = [i for i in _norm(incidents) if i.kind == "incident"]
    impaired = (coverage_status is CoverageStatus.DEGRADED) if impaired is None else bool(impaired)
    judged = [i for i in inc if is_current(i) and (i.priority in ("VERIFY", "WATCH") or i.materiality != "low")]
    triggers: list[str] = []
    if impaired:
        triggers.append("collection impaired")
    triggers += [str(x) for x in ((criticality or {}).get("posture_unknown_reasons") or [])]
    if n_events == 0 or (events_evaluated == 0 and coverage_status is not CoverageStatus.FULL and not judged):
        triggers.append("no reports evaluated: absence of reports is not evidence of absence of events")
    red, amber = posture_drivers(inc)
    watch = [i for i in inc if in_watch_lane(i) and i not in red and i not in amber]
    if detail is not None:
        detail.update({"red": [i.incident_id for i in red], "amber": [i.incident_id for i in amber], "unknown_triggers": triggers,
                       "watch_lane": [i.incident_id for i in inc if in_watch_lane(i)], "watch_not_driving": [i.incident_id for i in watch]})
    if red:
        return OperationalPosture.RED, [f"{i.handle} escalate-tier, current, impact stated, {'officially confirmed' if i.evidence_status == 'officially_confirmed' else str(i.independent_publishers) + ' independent publishers'}" for i in red]
    if amber:
        return OperationalPosture.AMBER, [f"{i.handle} current {i.priority.lower()}-tier" + (" (stored classifier severity high, corroborated)" if i.priority != "ESCALATE" and not (i.priority == "VERIFY" and i.materiality == "high") else "")
                                          + f", {i.evidence_status.replace('_', ' ')}" + (", provisional" if i.provisional else "") for i in amber]
    if triggers:
        return OperationalPosture.UNKNOWN, ["no current escalate-tier incident and the evidence cannot support a defensible judgement: " + "; ".join(triggers[:5])
                                            + (f" (+{len(triggers) - 5} more)" if len(triggers) > 5 else "")]
    return OperationalPosture.GREEN, ["no current escalate-tier or high-severity corroborated incident; watch-lane and emerging items are for review only"]


def derive_confidence(incidents, *, posture: OperationalPosture, coverage_status: CoverageStatus) -> dict:
    """Deterministic overall assessment confidence with its basis. Not LLM-assigned; not a probability."""
    inc = [i for i in _norm(incidents) if i.kind == "incident" and detail_level(i) == "full"]
    if posture is OperationalPosture.UNKNOWN:
        return {"level": Confidence.LOW.value, "basis": "no risk judgement was made"}
    if not inc:
        lvl = Confidence.MODERATE if coverage_status is CoverageStatus.FULL else Confidence.LOW
        return {"level": lvl.value, "basis": "no material item; confidence limited to what was collected" + ("" if coverage_status is CoverageStatus.FULL else " and coverage is incomplete")}
    weak = [i for i in inc if i.evidence_status in ("reported", "unverified") or i.provisional]
    if not weak and coverage_status is CoverageStatus.FULL:
        return {"level": Confidence.HIGH.value, "basis": "all material items officially confirmed or corroborated; coverage full"}
    if len(weak) == len(inc) or coverage_status is CoverageStatus.DEGRADED:
        return {"level": Confidence.LOW.value, "basis": f"{len(weak)} of {len(inc)} material items single-source or unverified" + ("; coverage degraded" if coverage_status is CoverageStatus.DEGRADED else "")}
    return {"level": Confidence.MODERATE.value, "basis": f"{len(weak)} of {len(inc)} material items single-source or unverified"}


# --------------------------------------------------------------------------------------------------------------------------------
# epistemic classification
# --------------------------------------------------------------------------------------------------------------------------------
def statements_for(i: LayeredIncident) -> list[dict]:
    """The canonical, class-labelled statements for one incident. No statement is invented: each comes from a field the evidence layer
    populated; absent fields produce nothing (an unknown stays a KNOWN UNKNOWN, never a guess)."""
    out: list[dict] = []
    confirmed = i.evidence_status in _CONFIRMED
    if i.impact_status in ("warning", "forecast"):
        cls = EpistemicClass.FORECAST
        text = f"{i.headline} (a {i.impact_status}, not a confirmed event)"
    elif confirmed and i.impact_status in ("stated", "retrospective", "unconfirmed", "potential"):
        cls, text = EpistemicClass.ESTABLISHED_FACT, i.headline
    else:
        cls, text = EpistemicClass.REPORTED_UNVERIFIED, i.headline
    out.append({"class": cls.value, "tag": TAG[cls], "text": text})
    if i.impact_status in ("unconfirmed", "potential"):
        out.append({"class": EpistemicClass.KNOWN_UNKNOWN.value, "tag": "UNKNOWN", "text": "Effect on service or operations has not been established by the cited reports."})
    if i.state == "current status unknown":
        out.append({"class": EpistemicClass.KNOWN_UNKNOWN.value, "tag": "UNKNOWN", "text": "Whether the event is still current is not established."})
    for ku in i.known_unknowns:
        out.append({"class": EpistemicClass.KNOWN_UNKNOWN.value, "tag": "UNKNOWN", "text": ku})
    if i.competing_explanation:
        out.append({"class": EpistemicClass.ANALYTICAL_ASSESSMENT.value, "tag": "ASSESSMENT", "text": f"Competing explanation: {i.competing_explanation}"})
    for imp in i.implications:
        out.append({"class": EpistemicClass.INFERENCE.value, "tag": "INFERENCE", "text": imp})
    return out


# --------------------------------------------------------------------------------------------------------------------------------
# layers
# --------------------------------------------------------------------------------------------------------------------------------
def _evq(i: LayeredIncident) -> str:
    n = f", {i.independent_publishers} independent publisher(s)" if i.independent_publishers else ""
    return f"{i.evidence_status.replace('_', ' ')}{n}" + (", provisional" if i.provisional else "")


def _scope_word(i: LayeredIncident) -> str:
    return {"international": "international", "domestic": "domestic"}.get(i.scope, "scope not established")


def _l1(incs, posture, posture_reasons, cov, cov_limits, conf, *, production_status=None, triggers=None, watch_n: int = 0) -> dict:
    material = [i for i in incs if detail_level(i) == "full"]       # incs is in decision order: posture drivers lead
    limited = ""
    if posture is OperationalPosture.GREEN and cov is not CoverageStatus.FULL:   # GREEN is never shown bare under incomplete coverage
        limited = f"; assessment limited by {'; '.join(cov_limits) if cov_limits else 'incomplete collection (no source named)'}"
    lines = [f"Posture: {POSTURE_WORDS[posture]}{limited}.",
             f"Coverage: {cov.value}" + (f" (assessment limited by: {'; '.join(cov_limits)})" if cov_limits else "") + ".",
             f"Confidence: {conf['level']} ({conf['basis']})."]
    if triggers and posture in (OperationalPosture.RED, OperationalPosture.AMBER):
        lines.append("Assessment limits beside this posture: " + "; ".join(triggers[:2]) + (f" (+{len(triggers) - 2} more, see L6)" if len(triggers) > 2 else "") + ".")
    if material:
        lines.append("Decision-first: " + " ".join(f"{i.headline} ({_evq(i)}; {_scope_word(i)}" + (f"; {i.driver} driver" if i.driver else "") + f") {i.handle}." for i in material[:3]))
        if len(material) > 3:
            lines.append(f"{len(material) - 3} further material item(s) are assessed in L3.")
    elif posture is OperationalPosture.GREEN:
        lines.append("No significant development identified in the sources collected." + (" This is limited by the collection limits above, not an all-clear." if limited else ""))
    elif posture is OperationalPosture.UNKNOWN:
        lines.append("No defensible risk judgement can be made from the evidence collected; do not read this as quiet.")
    if watch_n:
        lines.append(f"{watch_n} high-severity item(s) are on the review/watch list (L5); they do not set the posture by themselves.")
    if production_status:
        lines.append(f"Production status: {production_status['status']}" + (f" ({'; '.join(production_status.get('reasons', []))})" if production_status.get("reasons") else "") + ".")
    text = " ".join(lines)
    return {"text": text, "chars": len(text), "target_chars": L1_TARGET_CHARS, "over_target": len(text) > L1_TARGET_CHARS}


def _l2(incs, judgements) -> list[dict]:
    out = []
    for j in judgements or []:
        out.append({"statement": j["statement"], "class": j.get("class", EpistemicClass.ANALYTICAL_ASSESSMENT.value),
                    "evidence_quality": j.get("evidence_quality", "not stated"), "confidence": j.get("confidence", "not stated"),
                    "competing_explanation": j.get("competing_explanation") or "not assessed (none supplied)",
                    "known_unknowns": list(j.get("known_unknowns") or []), "indicators": list(j.get("indicators") or []),
                    "evidence": list(j.get("evidence") or []), "source": "supplied"})
    covered = {e for j in out for e in j["evidence"]}
    for i in incs:                                            # deterministic, evidence-derived judgement shells for material items
        if detail_level(i) != "full" or i.incident_id in covered:
            continue
        conf = "low" if (i.provisional or i.evidence_status in ("reported", "unverified")) else ("high" if i.evidence_status == "officially_confirmed" else "moderate")
        out.append({"statement": f"{i.headline}: {_scope_word(i)} item, {_evq(i)}.", "class": EpistemicClass.REPORTED_UNVERIFIED.value if conf == "low" else EpistemicClass.ESTABLISHED_FACT.value,
                    "evidence_quality": _evq(i), "confidence": conf,
                    "competing_explanation": i.competing_explanation or "not assessed (none supplied)",
                    "known_unknowns": [x["text"] for x in statements_for(i) if x["tag"] == "UNKNOWN"],
                    "indicators": ([i.next_step] if i.next_step else []) + list(i.indicators),
                    "evidence": [i.incident_id], "source": "derived"})
    return out


def _entry(i: LayeredIncident) -> dict:
    return {"incident_id": i.incident_id, "headline": i.headline, "priority": i.priority, "scope": i.scope,
            "relevance": relevance_of(i) if i.scope == "international" else None, "relevance_basis": i.relevance_basis or None,
            "evidence": _evq(i), "state": i.state or None, "reports": i.n_reports, "sectors": [x.replace("_", " ") for x in i.sectors],
            "statements": statements_for(i), "summary": i.summary or None, "next_step": i.next_step or None}


COUNTED_TITLES_MAX = 60       # bound on titles listed for counted items (the total is always stated)


def _l3(incs) -> dict | None:
    full = [_entry(i) for i in incs if detail_level(i) == "full"]
    lines = []
    for i in incs:
        if detail_level(i) == "line":
            rel = " ; relevance not assessed" if relevance_of(i) == "unassessed" else ""
            old = "; older than the brief window" if i.outside_window else ""
            lines.append({"incident_id": i.incident_id, "text": f"{i.headline} ({_scope_word(i)}; {_evq(i)}{old}{rel})".replace(" ;", ";"),
                          "relevance_assessed": relevance_of(i) != "unassessed"})
    counted = [i for i in incs if detail_level(i) == "count"]
    older = [i for i in counted if i.outside_window]
    intl_low = [i for i in counted if i.scope == "international" and not i.outside_window]
    other = [i for i in counted if i.scope != "international" and not i.outside_window]
    summary = []
    if intl_low:
        summary.append(f"{len(intl_low)} lower-relevance international item(s) (demonstrably low relevance) counted, not assessed individually (titles listed).")
    if other:
        summary.append(f"{len(other)} low-relevance reference-tier item(s) counted (titles listed).")
    if older:
        summary.append(f"{len(older)} item(s) older than the brief window counted (titles listed).")
    unassessed = [x for x in lines if not x["relevance_assessed"]]
    if unassessed:
        summary.append(f"{len(unassessed)} item(s) shown as one line because relevance could not be established (relevance not assessed).")
    if not (full or lines or summary):
        return None
    why = {id(i): ("older than window" if i.outside_window else "low relevance: " + (i.relevance_basis or "supplied")) for i in counted}
    items = [{"incident_id": i.incident_id, "headline": i.headline[:160], "scope": i.scope, "reason": why[id(i)]} for i in counted]   # every counted title is listed
    return {"assessments": full, "one_line": lines, "counted": summary, "counted_ids": [i.incident_id for i in counted],
            "counted_items": items, "counted_total": len(counted)}


def _l4(incs) -> list[dict] | None:
    out = []
    for i in incs:
        if detail_level(i) != "full":
            continue
        if i.implications or (i.scope == "international" and relevance_of(i) in ("high", "medium") and i.relevance_basis):
            text = "; ".join(i.implications) if i.implications else f"International development with {relevance_of(i)} relevance: {i.relevance_basis}"
            out.append({"class": EpistemicClass.INFERENCE.value, "tag": "INFERENCE", "text": text, "sectors": list(i.sectors),
                        "ref": i.incident_id, "no_australian_impact_required": i.scope == "international"})
    by_sector: dict[str, list[str]] = {}
    for i in incs:
        if detail_level(i) in ("full", "line"):
            for s in i.sectors:
                by_sector.setdefault(s, []).append(i.incident_id)
    for s, ids in sorted(by_sector.items()):
        if len(ids) >= 2:
            out.append({"class": EpistemicClass.INFERENCE.value, "tag": "INFERENCE", "text": f"{len(ids)} items touch the {s.replace('_', ' ')} sector: possible concentration, not established.", "sectors": [s], "ref": ids, "no_australian_impact_required": False})
    return out or None


def _l5(incs, outlook, judged=None) -> dict | None:
    items = [{"class": EpistemicClass.FORECAST.value, "tag": "FORECAST", "text": o["text"] if isinstance(o, dict) else str(o), "dated": bool(isinstance(o, dict) and o.get("dated")),
              "kind": "scheduled" if isinstance(o, dict) and o.get("dated") else "assessed"} for o in outlook or []]
    watch = []
    for i in incs:                                               # watch/review lane: no item cap, never silently discarded, independent of PIR match strength
        if in_watch_lane(i):
            tags = [m.get("pir_id") + ("" if m.get("strength", "strong") == "strong" else "w") for m in (i.pir or {}).get("matches") or []]
            watch.append({"incident_id": i.incident_id, "pir_tags": tags, "driver": i.driver or None,
                          "text": (f"{i.headline}: matched no standing requirement but meets severity or official signals." if not tags else
                                   f"{i.headline}: high severity; also tagged {', '.join(tags)} (a requirement tag annotates this item, it does not remove it from review).")})
    in_l2 = {x for j in (judged or []) for x in j.get("indicators", [])}      # shown once: indicators already carried by an L2 judgement are not repeated
    indicators = [{"incident_id": i.incident_id, "text": s} for i in incs if detail_level(i) == "full"
                  for s in ([i.next_step] if i.next_step else []) + list(i.indicators) if s not in in_l2]
    if not (items or watch or indicators):
        return None
    return {"outlook": items, "watch": watch, "indicators": indicators}


def _l6(cov, cov_limits, incs, *, production_status=None, claim_gate=None, posture, triggers=None) -> dict:
    notes = list(cov_limits)
    issues = [i for i in incs if i.kind == "collection_issue"]
    for i in issues:
        notes.append(f"collection issue: {i.headline} (a source-health matter, not an operational disruption)")
    single = [i for i in incs if i.kind == "incident" and i.provisional and detail_level(i) == "full"]
    if single:
        notes.append(f"{len(single)} material item(s) rest on a single or unverified source and are provisional.")
    if posture is OperationalPosture.UNKNOWN:
        notes.append("Operational posture was not assessed; absence of reports is not evidence that nothing happened.")
    elif triggers:
        notes.append("Conditions that would make the posture NOT ASSESSED are present and are overridden only by current incident evidence: " + "; ".join(triggers) + ".")
    if claim_gate is not None and not getattr(claim_gate, "passed", True):
        notes.append("AI-drafted wording was withheld because the claim gate did not pass; this brief is deterministic evidence-only.")
    if production_status and production_status.get("status") != "NORMAL":
        notes.append(f"Production status is {production_status['status']}: " + "; ".join(production_status.get("reasons", [])))
    possible_missed = "events that would have been reported only by sources not collected" if cov is not CoverageStatus.FULL else "events not reported by any monitored source"
    coll = list(cov_limits) + [n for n in notes if n.startswith("collection issue")]
    evid = [n for n in notes if n not in coll]
    statement = f"Coverage {cov.value}."
    statement += (" Assessment limited by: " + "; ".join(coll) + ".") if coll else " No named collection limit; this is not an all-clear."
    if evid:
        statement += " Evidence limits: " + " ".join(evid)
    return {"coverage": cov.value, "limits": notes, "possible_missed": possible_missed, "statement": statement}


def _l7(incs, evidence_refs, portal_base) -> list[dict] | None:
    refs = {r["incident_id"]: r for r in (evidence_refs or []) if isinstance(r, dict) and r.get("incident_id")}
    out = []
    for i in incs:
        r = refs.get(i.incident_id, {})
        reports = r.get("reports") or i.reports
        out.append({"incident_id": i.incident_id, "headline": i.headline[:160], "handling": detail_level(i), "reports": reports, "reports_n": i.n_reports,
                    "link": f"{portal_base.rstrip('/')}/intelligence-workbench?tab=incidents#{i.incident_id}" if portal_base is not None else None})
    return out or None


def reconcile(input_ids, result: dict) -> dict:
    """Real reconciliation of the INPUT incident set against what a rendered (or stored, compact) result actually contains. Computed
    from the output layers (L3 full/line/counted, L7 handling), never from the input alone, so a renderer or storage defect shows up
    as ``missing``. ``titles_*`` count counted items whose title is present."""
    ids = list(dict.fromkeys(str(x) for x in input_ids))
    l3 = result.get("L3") or {}
    full = list(l3.get("full_ids") or [a["incident_id"] for a in l3.get("assessments", [])])
    line = list(l3.get("line_ids") or [a["incident_id"] for a in l3.get("one_line", [])])
    counted_items = l3.get("counted_items", [])
    counted = list(l3.get("counted_ids") or [x["incident_id"] for x in counted_items])
    shown = full + line + counted
    seen = set(shown)
    if isinstance(result.get("L7"), list):
        l7 = {e["incident_id"] for e in result["L7"]}
    else:
        l7 = set(shown)          # compact form: handling is carried by L3 list membership
    dup = sorted({x for x in shown if shown.count(x) > 1})
    missing = sorted(set(ids) - seen)
    titles = {x["incident_id"] for x in counted_items if x.get("headline")}
    return {"input_total": len(ids), "full": len(set(full)), "line": len(set(line)), "counted": len(set(counted)),
            "missing_from_l3": missing, "missing_from_l7": sorted(set(ids) - l7), "extra_not_in_input": sorted(seen - set(ids)),
            "duplicated": dup, "counted_titles_shown": len(titles & set(counted)), "counted_titles_not_shown": len(set(counted) - titles),
            "ok": not missing and not dup and not (set(ids) - l7)}


def render_layered(incidents, *, posture, coverage, confidence, judgements=None, outlook=None, limits=None, evidence_refs=None,
                   production_status: dict | None = None, claim_gate=None, portal_base: str = "", n_events: int | None = None,
                   events_evaluated: int | None = None, criticality: dict | None = None) -> dict:
    """Render layers L1..L7. ``posture`` may be an ``OperationalPosture`` (used as given: this renderer never overrides a caller's
    posture) or None to compute it. ``coverage`` is a ``CoverageStatus`` or the stored coverage dict. ``confidence`` is a
    ``Confidence``/str or {'level', 'basis'} or None to derive. Empty sections are omitted; L1 and L6 are always present."""
    incs = _norm(incidents)
    if isinstance(coverage, CoverageStatus):
        cov, cov_limits, impaired = coverage, [], coverage is CoverageStatus.DEGRADED
    else:
        cov, cov_limits = coverage_status_from(coverage)
        impaired = coverage_impaired(coverage)
        if events_evaluated is None and isinstance(coverage, dict) and isinstance(coverage.get("events_evaluated"), int):
            events_evaluated = coverage["events_evaluated"]
    cov_limits = cov_limits + [str(x) for x in (limits or [])] + [str(x) for x in ((criticality or {}).get("limits") or [])]
    pdetail: dict = {}
    if posture is None:
        posture, why = assess_posture(incs, coverage_status=cov, n_events=n_events, impaired=impaired, events_evaluated=events_evaluated,
                                      criticality=criticality, detail=pdetail)
    else:
        posture, why = OperationalPosture(posture), ["supplied by caller"]
        assess_posture(incs, coverage_status=cov, n_events=n_events, impaired=impaired, events_evaluated=events_evaluated, criticality=criticality, detail=pdetail)
    drv = {x: "RED" for x in pdetail.get("red", [])}
    drv.update({x: "AMBER" for x in pdetail.get("amber", [])})
    if drv:                                                    # posture drivers lead every layer (stable: the rest keeps decision order)
        incs = sorted([dataclasses.replace(i, driver=drv.get(i.incident_id, "")) for i in incs], key=decision_key)
    if confidence is None:
        conf = derive_confidence(incs, posture=posture, coverage_status=cov)
    elif isinstance(confidence, dict):
        conf = {"level": Confidence(confidence["level"]).value, "basis": confidence.get("basis", "supplied by caller")}
    else:
        conf = {"level": Confidence(confidence).value, "basis": "supplied by caller"}
    layers: dict[str, Any] = {"axes": {"posture": {"value": posture.value, "reasons": why,
                                                   "limited_by": cov_limits if (posture is OperationalPosture.GREEN and cov is not CoverageStatus.FULL) else [],
                                                   "drivers": {"red": pdetail.get("red", []), "amber": pdetail.get("amber", [])},
                                                   "not_assessed_triggers": pdetail.get("unknown_triggers", []),
                                                   "watch_lane_total": len(pdetail.get("watch_lane", [])), "watch_not_driving": len(pdetail.get("watch_not_driving", [])),
                                                   "precedence": "RED > AMBER (current incidents only) > UNKNOWN (insufficient evidence, none of RED/AMBER) > GREEN"}, "coverage": {"value": cov.value, "limits": cov_limits},
                                       "confidence": conf}}
    layers["L1"] = _l1(incs, posture, why, cov, cov_limits, conf, production_status=production_status,
                       triggers=pdetail.get("unknown_triggers"), watch_n=len(pdetail.get("watch_lane", [])))
    l2 = _l2(incs, judgements)
    for key, val in (("L2", l2), ("L3", _l3(incs)), ("L4", _l4(incs)), ("L5", _l5(incs, outlook, l2))):
        if val:
            layers[key] = val
    layers["L6"] = _l6(cov, cov_limits, incs, production_status=production_status, claim_gate=claim_gate, posture=posture, triggers=pdetail.get("unknown_triggers"))
    l7 = _l7(incs, evidence_refs, portal_base)
    if l7:
        layers["L7"] = l7
    layers["meta"] = {"incidents": len(incs), "material": sum(1 for i in incs if detail_level(i) == "full"), "renderer": "layered/2"}
    layers["meta"]["reconciliation"] = reconcile([i.incident_id for i in incs], layers)
    return layers


# --------------------------------------------------------------------------------------------------------------------------------
# text output (plain text; the consumer escapes for its channel)
# --------------------------------------------------------------------------------------------------------------------------------
def to_text(r: dict, *, include_l7: bool = False) -> str:
    out = ["EXECUTIVE SUMMARY", r["L1"]["text"], ""]
    if "L2" in r:
        out.append("KEY JUDGEMENTS")
        for j in r["L2"]:
            out.append(f"- [{TAG.get(EpistemicClass(j['class']), 'ASSESSMENT')}] {j['statement']} Evidence: {j['evidence_quality']}. Confidence: {j['confidence']}. Competing explanation: {j['competing_explanation']}.")
            if j["known_unknowns"]:
                out.append("    Known unknowns: " + " ".join(j["known_unknowns"]))
            if j["indicators"]:
                out.append("    Would change the assessment: " + "; ".join(j["indicators"]))
        out.append("")
    if "L3" in r:
        out.append("MATERIAL ASSESSMENTS")
        for a in r["L3"]["assessments"]:
            hdr = f"{a['headline']} [{a['incident_id']}] ({a['scope']}; {a['evidence']}" + (f"; {a['state']}" if a["state"] else "") + ")"
            out.append("- " + hdr)
            for s in a["statements"]:
                out.append(f"    [{s['tag']}] {s['text']}")
            if a["relevance_basis"]:
                out.append(f"    Relevance: {a['relevance']} ({a['relevance_basis']})")
        for ln in r["L3"]["one_line"]:
            out.append(f"- {ln['text']} [{ln['incident_id']}]")
        out += [f"- {c}" for c in r["L3"]["counted"]]
        out.append("")
    if "L4" in r:
        out.append("NATIONAL, SYSTEMIC AND SECTOR IMPLICATIONS")
        out += [f"- [{x['tag']}] {x['text']}" for x in r["L4"]]
        out.append("")
    if "L5" in r:
        out.append("FORWARD OUTLOOK AND INDICATORS")
        out += [f"- [{x['tag']}] {x['text']}" for x in r["L5"]["outlook"]]
        out += [f"- WATCH (unmatched high severity) {x['text']} [{x['incident_id']}]" for x in r["L5"]["watch"]]
        out += [f"- Indicator: {x['text']} [{x['incident_id']}]" for x in r["L5"]["indicators"]]
        out.append("")
    out += ["COLLECTION LIMITATIONS", r["L6"]["statement"], f"Events possibly missed: {r['L6']['possible_missed']}."]
    if include_l7 and "L7" in r:
        out += ["", "EVIDENCE AND REFERENCES"]
        for e in r["L7"]:
            out.append(f"- {e['incident_id']} ({e['handling']}, {e['reports_n']} report(s))" + (f" {e['link']}" if e["link"] else ""))
    return "\n".join(out)


def mentions_of(text: str, incident_id: str) -> int:
    return text.count(incident_id)


def treatment_counts(r: dict) -> dict[str, int]:
    """Number of FULL treatments per incident id (must be 0 or 1): the single-canonical-treatment invariant."""
    counts: dict[str, int] = {}
    for a in (r.get("L3") or {}).get("assessments", []):
        counts[a["incident_id"]] = counts.get(a["incident_id"], 0) + 1
    return counts


# --------------------------------------------------------------------------------------------------------------------------------
# audio (spoken L1 + L2; no ids, URLs or tags)
# --------------------------------------------------------------------------------------------------------------------------------
_ID = re.compile(r"\s*\[?\binc-[0-9a-f]{6,}\b\]?")
_URL = re.compile(r"https?://\S+|/intelligence-workbench\S*")
_TAGS = re.compile(r"\[(FACT|REPORTED|ASSESSMENT|INFERENCE|FORECAST|UNKNOWN)\]")


def _spoken(s: str) -> str:
    s = _URL.sub("", _TAGS.sub("", _ID.sub("", s)))
    return re.sub(r"\s+", " ", s).replace(" .", ".").strip()


def audio_script(r: dict, *, minutes: float = AUDIO_DEFAULT_MINUTES) -> dict:
    """Spoken version of L1 and L2. The target (default 3 minutes) is reported, never forced: nothing is dropped from the written
    brief to hit it, and the script says so when it runs over so the Captain can set the length. L2 judgements are condensed
    (statement, confidence, the main unknown) before anything is considered over target."""
    parts = [_spoken(r["L1"]["text"])]
    for j in r.get("L2", []):
        seg = f"{_spoken(j['statement'])} Confidence {j['confidence']}."
        if j["known_unknowns"]:
            seg += f" Not known: {_spoken(j['known_unknowns'][0])}"
        parts.append(seg)
    parts.append(_spoken(r["L6"]["statement"]))
    script = "\n\n".join(parts)
    words = len(script.split())
    budget = int(minutes * AUDIO_WORDS_PER_MINUTE)
    return {"script": script, "words": words, "est_seconds": round(words / AUDIO_WORDS_PER_MINUTE * 60), "target_minutes": minutes,
            "word_budget": budget, "over_target": words > budget, "dropped_judgements": 0}


# --------------------------------------------------------------------------------------------------------------------------------
# shadow storage (existing jsonb only, one namespaced key; pure: the caller owns any write, and none happens under G0)
# --------------------------------------------------------------------------------------------------------------------------------
def _shadow_safe(r: dict, blocked_ids: set[str]) -> dict:
    r = copy.deepcopy(r)
    if "L3" in r:
        r["L3"]["assessments"] = [a for a in r["L3"]["assessments"] if a["incident_id"] not in blocked_ids]
        r["L3"]["one_line"] = [a for a in r["L3"]["one_line"] if a["incident_id"] not in blocked_ids]
    return r


def _cap(lst, n):
    return list(lst[:n]), len(lst)


_TITLE_LIMITS = {1: (110, 80, 70), 2: (90, 55, 50), 3: (70, 40, 36), 4: (60, 0, 0), 5: (60, 0, 0)}     # (full-treatment, one-line, counted) title chars per level


def compact_layers(r: dict, level: int = 1) -> dict:
    """Compact L1..L7 for storage: keeps EVERY layer and the id of EVERY incident, and drops only prose.
    Always kept in full: axes (long lists capped at 8 with totals), L1, L6. L2 keeps statement/confidence/evidence ids and the first known
    unknown (level >= 2: derived shells reduced to the ids they cover). L3 keeps id, title and tier of every full, one-line and counted
    incident (per-incident statements and L7 report lists are dropped). L4 texts and L5 outlook shorten. L5 watch keeps id and PIR tags.
    L7 becomes an id -> handling map. Levels 1-3 only shorten titles (see ``_TITLE_LIMITS``); level 4 keeps titles for full-treatment items
    only and states how many titles are not stored. Same key names as the full result, so the audio and L1/L6 readers work unchanged."""
    ax = copy.deepcopy(r.get("axes", {}))
    for sub in (ax.get("posture", {}), ax.get("coverage", {})):
        for k in ("reasons", "limits", "limited_by", "not_assessed_triggers"):
            if isinstance(sub.get(k), list) and len(sub[k]) > 8:
                sub[k + "_total"] = len(sub[k])
                sub[k] = sub[k][:8]
    drv = ax.get("posture", {}).get("drivers") or {}
    for k in ("red", "amber"):
        if len(drv.get(k, [])) > 25:
            drv[k + "_total"] = len(drv[k])
            drv[k] = drv[k][:25]
    out: dict[str, Any] = {"axes": ax, "L1": copy.deepcopy(r["L1"]), "L6": copy.deepcopy(r["L6"]), "meta": copy.deepcopy(r.get("meta", {}))}
    tl_full, tl_line, tl_cnt = _TITLE_LIMITS[level]
    titles = {e["incident_id"]: e.get("headline", "") for e in r.get("L7", [])}      # bare title (the one-line text also carries an evidence suffix)
    if "L2" in r:
        out["L2"] = [{"statement": j["statement"][:200 if level < 3 else 120], "class": j.get("class"), "confidence": j.get("confidence"),
                      "evidence": list(j.get("evidence") or []), "known_unknowns": [x[:120] for x in (j.get("known_unknowns") or [])[:1]], "source": j.get("source")}
                     for j in r["L2"] if level < 2 or j.get("source") == "supplied"]
        if 2 <= level < 5:
            out["L2_derived_ids"] = [e for j in r["L2"] if j.get("source") != "supplied" for e in (j.get("evidence") or [])]
    if "L3" in r:
        l3 = r["L3"]
        out["L3"] = {"assessments": [{"incident_id": a["incident_id"], "headline": a["headline"][:tl_full], "priority": a["priority"], "scope": a["scope"]} for a in l3["assessments"]],
                     "one_line": [({"incident_id": x["incident_id"], "text": titles.get(x["incident_id"], x["text"])[:tl_line]} if tl_line else {"incident_id": x["incident_id"]}) for x in l3["one_line"]],
                     "counted": list(l3["counted"]), "counted_total": l3.get("counted_total", 0),
                     "counted_items": [({"incident_id": x["incident_id"], "headline": x["headline"][:tl_cnt]} if tl_cnt else {"incident_id": x["incident_id"]})
                                       for x in l3.get("counted_items", [])]}
        if not tl_line:
            out["L3"]["titles_not_stored"] = len(l3["one_line"]) + len(l3.get("counted_items", []))
    if "L4" in r:
        out["L4"] = [{"text": x["text"][:200 if level < 2 else 120], "ref": x.get("ref")} for x in r["L4"]]
    if "L5" in r:
        w = r["L5"]["watch"]
        out["L5"] = {"outlook": [{"text": o["text"][:200]} for o in r["L5"]["outlook"]],
                     "watch": [x["incident_id"] for x in w], "watch_tags": {x["incident_id"]: ",".join(x["pir_tags"]) for x in w if x.get("pir_tags")},
                     "watch_drivers": [x["incident_id"] for x in w if x.get("driver")],
                     "watch_total": len(w), "indicators_total": len(r["L5"]["indicators"])}
    # L7 (evidence and references): the per-incident handling is exactly the L3 list each id appears in, so it is not repeated here; report
    # lists and links are the long prose that is dropped (they are re-derivable from the evidence set).
    out["L7"] = {"incidents": len(r.get("L7", [])), "handling": "see the L3 list each incident id appears in (assessments / one_line / counted_items)",
                 "dropped": "per-incident report lists and links"}
    out["compact_level"] = level
    if level >= 5:       # last resort for very large days: every layer still present, per-incident rows become id lists (handling = list membership)
        l3 = out.get("L3", {})
        keep = [a for a in l3.get("assessments", []) if a.get("incident_id") in {x for x in (r.get("axes", {}).get("posture", {}).get("drivers", {}).get("red", []) + r.get("axes", {}).get("posture", {}).get("drivers", {}).get("amber", []))}]
        keep = keep[:25]
        out["L3"] = {"assessments": [{"incident_id": a["incident_id"], "headline": a["headline"][:60]} for a in keep],
                     "full_ids": [a["incident_id"] for a in r["L3"]["assessments"]] if "L3" in r else [],
                     "line_ids": [a["incident_id"] for a in r["L3"]["one_line"]] if "L3" in r else [],
                     "counted_ids": list(r["L3"].get("counted_ids", [])) if "L3" in r else [], "counted": list(l3.get("counted", [])), "counted_total": l3.get("counted_total", 0),
                     "titles_not_stored": len(r["L3"]["assessments"]) - len(keep) + len(r["L3"]["one_line"]) + len(r["L3"].get("counted_ids", [])) if "L3" in r else 0}
        out["L5"] = {"watch_ids": [x["incident_id"] for x in (r.get("L5") or {}).get("watch", [])], "indicators_total": len((r.get("L5") or {}).get("indicators", []))} if "L5" in r else None
        if out["L5"] is None:
            out.pop("L5")
        out["reduced"] = True
    return out


def build_shadow_payload(r: dict, *, kind: str = "layered_brief", generated_at: datetime | None = None, blocked_ids: set[str] | None = None,
                         meta: dict | None = None) -> dict:
    """``shadow_v1`` payload: {schema, published=False, kind, generated_at, ...}. Health/personal-domain content is excluded by the caller
    via ``blocked_ids``. Bound: the whole value INCLUDING ``meta`` is at most SHADOW_MAX_BYTES. Over the bound the layers are COMPACTED in up
    to five steps (``compact_layers``), never discarded: every layer L1-L7 and the id of every incident are kept, only prose and then
    title length shrink, and ``compact_level`` records the step. Only if level 5 still exceeds the bound is the payload refused
    (ValueError), never silently reduced further."""
    ts = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    body = _shadow_safe(r, blocked_ids or set())
    base = {"schema": 1, "published": False, "kind": kind, "generated_at": ts}
    if meta:
        base["meta"] = dict(meta)
    limit = SHADOW_MAX_BYTES - (STORED_RECON_HEADROOM if meta else 0)      # room for the stored-reconciliation block the caller adds after compaction
    payload = {**base, "layers": body}
    if _size(payload) <= limit:
        return payload
    for level in (1, 2, 3, 4, 5):
        payload = {**base, "compact": True, "compact_level": level, "layers": compact_layers(body, level)}
        if level >= 5:
            payload["reduced"] = True
        if _size(payload) <= limit:
            return payload
    raise ValueError("shadow payload exceeds the size bound even at compact level 5")


def _size(o) -> int:
    return len(json.dumps(o, default=str).encode())


def merge_shadow(existing: dict | None, payload: dict) -> dict:
    """Return a copy of ``existing`` with ONLY the ``shadow_v1`` key added or its own previous value replaced. Every other key is
    preserved unchanged; ``existing`` is not mutated. Parity with ``requirements.merge_shadow``: a ``shadow_v1`` written by ANOTHER
    producer (different ``kind``) is never overwritten; the payload nests under its ``companions`` map. A previous value of the same
    kind is replaced, keeping any companions it carried."""
    if payload.get("published") is not False:
        raise ValueError("shadow payload must be published=false")
    merged = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    cur = merged.get(SHADOW_KEY)
    if not isinstance(cur, dict):
        merged[SHADOW_KEY] = payload
    elif cur.get("kind") == payload.get("kind"):
        new = dict(payload)
        if cur.get("companions") and "companions" not in new:
            new["companions"] = cur["companions"]
        merged[SHADOW_KEY] = new
    else:
        comp = dict(cur.get("companions") or {})
        comp[payload["kind"]] = payload
        cur = dict(cur)
        cur["companions"] = comp
        merged[SHADOW_KEY] = cur
    return merged


def shadow_domain_blocked(inc: LayeredIncident) -> bool:
    return (inc.domain or "").lower() in SHADOW_BLOCKED_DOMAINS
