"""Delivery tiers (offline, default OFF): what should happen to an incident, derived from materiality EVIDENCE.

The existing pipeline has one ladder (ESCALATE / VERIFY / WATCH / REFERENCE) driven by rank and disposition, which conflates three
different questions: how bad is it (materiality), how sure are we (evidence) and when does the reader need it (urgency). This module
answers the last question from the first two plus liveness, Australian relevance and report roles. It never lowers or raises a rank
threshold: it reads the decision axes ``event_detection`` already computes and the report relations from ``incident_clustering``.

  IMMEDIATE_ALERT   a LIVE, stated, high-materiality disruption with demonstrated Australian relevance, backed by an official or
                    corroborated source or a single unhedged mainstream/primary report, and a factual report in the last
                    ALERT_FRESH_HOURS. Interrupts the reader.
  SCHEDULED_BRIEF   material (high or medium), stated or unconfirmed, Australian relevance or dependency, with at least a reported
                    (non-aggregator, unhedged) source. Goes in the next scheduled brief, including the closure of an alerted incident.
  MONITOR           a candidate we cannot yet stand behind: aggregator-only, hedged or unverified evidence, a warning or forecast, a
                    planned outage, a dependency with no Australian impact stated. Re-tiered automatically when evidence arrives.
  CONTEXT           commentary, cost, aftermath or historical references: supports an incident, never an item of its own.
  REFERENCE_RETAIN  no demonstrated Australian relevance, no stated consequence or minor: kept for search and audit, never surfaced.

Flag: ``DELIVERY_TIERS_V1`` (read at call time, default OFF). Nothing here is wired into a production path.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime

from intelligence import event_detection as ed
from intelligence import freshness as fr
from intelligence import incident_clustering as ic
from intelligence import weekly_evidence as we

FLAG = "DELIVERY_TIERS_V1"
_TRUE = ("1", "true", "yes", "on")

IMMEDIATE_ALERT = "IMMEDIATE_ALERT"
SCHEDULED_BRIEF = "SCHEDULED_BRIEF"
MONITOR = "MONITOR"
CONTEXT = "CONTEXT"
REFERENCE_RETAIN = "REFERENCE_RETAIN"
TIERS = (IMMEDIATE_ALERT, SCHEDULED_BRIEF, MONITOR, CONTEXT, REFERENCE_RETAIN)

ALERT_FRESH_HOURS = fr.ALERT_FRESH_HOURS   # one shared definition (intelligence/freshness.py), the same one the dispatcher and the brief use
SOLID_EVIDENCE = frozenset({"officially_confirmed", "corroborated", "reported"})
# A PLANNED outage needs AFFIRMATIVE evidence of a future window: 'planned/scheduled ... on/from/between/this/next/<date>', 'will be
# offline', or 'face a 60-hour outage'. The words maintenance/upgrade alone prove nothing ('outages after failed upgrade' is an incident).
_MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_FUTURE_WINDOW_RX = re.compile(
    r"\b(?:planned|scheduled)\b[^.]{0,50}\b(?:on|from|between|at|this|next|tonight|tomorrow|weekend|\d{1,2}(?:st|nd|rd|th)?\s+" + _MONTH + r"|" + _MONTH + r"\s+\d{1,2})\b"
    r"|\bwill be (?:offline|unavailable|down|taken offline|out of service)\b"
    r"|\bfaces?\b[^.]{0,20}\b\d+[- ]hours?\b[^.]{0,15}\b(?:outage|shutdown|downtime)\b"
    r"|\b(?:maintenance|upgrade|outage|downtime)\b[^.]{0,30}\b(?:on|from|between)\s+(?:\d{1,2}(?:st|nd|rd|th)?\s+" + _MONTH + r"|" + _MONTH + r"\s+\d{1,2})\b", re.IGNORECASE)
# A stated live impact always wins over maintenance/upgrade wording.
_LIVE_IMPACT_RX = re.compile(r"\b(?:outages?|unable to|cannot|can't|customers? (?:are )?experiencing|experiencing|disrupt\w*|not working|(?:went|goes|is|are|was|were|been|still) down|"
                             r"(?:is|are|was|were|went|now|currently|remains?|still)\s+(?:offline|unavailable)|failed|failures?|knocked out|hit by)\b", re.IGNORECASE)


def _is_planned(originals) -> bool:
    """Planned-ness is judged on the incident's LATEST stated report (a later cause update must not suppress, nor an old notice create, the
    verdict), and only on affirmative future-window wording with no stated live impact."""
    stated = [m for m in originals if m.status == "stated" and m.published]
    if not stated:
        return False
    latest = max(stated, key=lambda m: (m.published, len(m.title)))
    title = ed.core_title(latest.title)
    return bool(_FUTURE_WINDOW_RX.search(title)) and not _LIVE_IMPACT_RX.search(title)


def enabled() -> bool:
    return os.getenv(FLAG, "").strip().lower() in _TRUE


@dataclass
class TierDecision:
    tier: str
    reasons: list[str]
    evidence: dict = field(default_factory=dict)


def _newest_factual(inc: ic.Incident, relations=(ic.NEW, ic.SUBSEQUENT)) -> datetime | None:
    times = [r.candidate.published for r in inc.reports if r.relation in relations and r.candidate.published and r.candidate.time_verified]
    return max(times) if times else None


def _fresh(inc: ic.Incident, now: datetime | None) -> bool:
    """Alert freshness: the SAME rule the dispatcher enforces (freshness.alert_fresh)."""
    return fr.alert_fresh(_newest_factual(inc), now)


def _brief_current(inc: ic.Incident, now: datetime | None) -> bool:
    """Is the incident a CURRENT brief item? Its newest factual report is inside the brief window, or it is still ongoing / partially
    restored and the newest factual report is inside the longer live window. Otherwise it is context, never a current incident."""
    if now is None:
        return True
    newest = _newest_factual(inc, (ic.NEW, ic.SUBSEQUENT, ic.RESTORATION_UPDATE))
    if newest is None:
        return False
    if fr.brief_fresh(newest, now):
        return True
    return inc.restoration_status in ed.CURRENT_DISRUPTION and fr.within(newest, now, fr.live_window())


# A story ABOUT a hazard that reports no event (staffing, funding, response-time, review, policy): 'Tsunami response window shorter after
# staff pulled from remote island' is a policy story, not a tsunami incident. A live-event cue keeps the item.
_HAZARD_POLICY_RX = re.compile(r"\b(?:response (?:window|times?|plan|capacity)|staff(?:ing)?|funding|budget|preparedness|readiness|inquiry|review of|policy|"
                               r"pulled from|cuts? to)\b", re.IGNORECASE)
_HAZARD_EVENT_CUE_RX = re.compile(r"\b(?:warning|evacuat\w*|emergency|hits|hit by|struck|strikes|destroy\w*|rescue\w*|killed|dead|injur\w*|burning|erupts?|shaken|shakes)\b", re.IGNORECASE)
_EXPOSURE_SEVERITY_RX = re.compile(r"\b(?:critical|remote code execution|rce|actively exploited|zero-?day|known exploited|exploited in the wild)\b", re.IGNORECASE)


_TIME_BOUND_WARNING_TYPES = frozenset({"severe_weather"})


def _notice_current(inc: ic.Incident, now: datetime | None) -> bool:
    """Warnings and advisories have no 'newest factual disruption report' to age: they stay visible for the live window (72 h)."""
    if now is None:
        return True
    newest = _newest_factual(inc, (ic.NEW, ic.SUBSEQUENT, ic.RESTORATION_UPDATE))
    # A hazard warning (storm, fire, flood) is time-bound by nature: it lapses with the brief window rather than lingering for the
    # 72 h an advisory gets, so a two-day-old emergency fire warning is never shown as a current monitoring item.
    if inc.decision.event_type in _TIME_BOUND_WARNING_TYPES:
        return fr.within(newest, now, fr.brief_window())
    return fr.within(newest, now, fr.live_window())


def _non_incident_hazard(originals) -> bool:
    heads = [m for m in originals if m.status == "stated"]
    return bool(heads) and all("hazard" in m.types and _HAZARD_POLICY_RX.search(ed.core_title(m.title)) and not _HAZARD_EVENT_CUE_RX.search(ed.core_title(m.title)) for m in heads)


def tier_for_incident(inc: ic.Incident, *, now: datetime | None = None) -> TierDecision:
    d = inc.decision
    originals = [r.candidate for r in inc.reports if not r.candidate.commentary and r.relation != ic.HISTORICAL_REFERENCE] or [r.candidate for r in inc.reports]
    au = ed.australian_relevance(inc.group)
    au_demonstrated = au is not None and not au.startswith("plausible dependency")
    live = inc.restoration_status in ed.CURRENT_DISRUPTION
    factual = [r for r in inc.reports if r.relation in (ic.NEW, ic.SUBSEQUENT, ic.RESTORATION_UPDATE)]
    hedged = all(m.hedged for m in originals if m.status in ("stated", "unconfirmed")) if any(m.status in ("stated", "unconfirmed") for m in originals) else False
    solid_kind = any(m.kind in (we.PRIMARY, we.MAINSTREAM) and not m.hedged and m.status == "stated" for m in originals)
    planned = _is_planned(originals)
    ev = {"materiality": d.materiality, "impact_status": d.impact_status, "evidence_status": d.evidence_status, "restoration": inc.restoration_status,
          "australian_relevance": au, "n_reports": inc.n_reports, "n_factual": len(factual), "independent_publishers": inc.group.independent_publishers}
    why: list[str] = []

    def out(tier, *reasons):
        return TierDecision(tier, [*reasons, *why], ev)

    if not factual:
        if au or ed.australian_editorial_relevance(inc.group):
            return out(CONTEXT, "no factual report of a disruption in the window: only commentary, aftermath or historical references")
        return out(REFERENCE_RETAIN, "no factual disruption report and no Australian relevance")
    current = _brief_current(inc, now)
    if _non_incident_hazard(originals):
        return out(REFERENCE_RETAIN, "policy or staffing story about a hazard: no hazard event is reported")
    if d.event_type == "vulnerability":
        # EMERGING EXPOSURE: a credible advisory has no stated operational consequence by nature, so 'impact none' must not drop it.
        ev["exposure"] = True
        if d.evidence_status not in SOLID_EVIDENCE:
            return out(REFERENCE_RETAIN, "advisory without a credible source")
        if not _notice_current(inc, now):
            return out(REFERENCE_RETAIN, f"advisory older than {fr.LIVE_BRIEF_HOURS} h")
        if d.priority in ("ESCALATE", "VERIFY", "WATCH"):
            return out(SCHEDULED_BRIEF, "emerging exposure: credible advisory (exploited or critical), exposure-driven, never an interrupt on this path")
        if any(_EXPOSURE_SEVERITY_RX.search(m.summary or "") for m in originals):
            return out(MONITOR, "emerging exposure: credible advisory describing a critical flaw; check whether affected products are in the estate")
        return out(REFERENCE_RETAIN, "advisory with no exploitation or critical severity stated")
    if d.impact_status in ("warning", "forecast"):
        # A credible warning is kept even though no disruption exists yet; it is only dropped when there is no Australian link or it is stale.
        if au is None and not ed.australian_editorial_relevance(inc.group):
            return out(REFERENCE_RETAIN, "no demonstrated Australian relevance or dependency")
        if not _notice_current(inc, now):
            return out(REFERENCE_RETAIN, f"{d.impact_status} older than {fr.LIVE_BRIEF_HOURS} h")
        return out(MONITOR, f"{d.impact_status}: credible notice kept for the forward watch, not a stated incident")
    if d.impact_status in ("none", "potential"):
        return out(REFERENCE_RETAIN, f"impact status {d.impact_status}: no stated consequence")
    if au is None and not ed.australian_editorial_relevance(inc.group):
        return out(REFERENCE_RETAIN, "no demonstrated Australian relevance or dependency")
    if d.materiality == "low":
        if d.impact_status == "unconfirmed" and (d.sector_tier in (1, 2) or d.headline.compromise):
            if d.evidence_status in ("officially_confirmed", "corroborated") and au_demonstrated and current:
                return out(SCHEDULED_BRIEF, "consequence unconfirmed at an essential-service or compromised entity, corroborated: verification target for the brief")
            return out(MONITOR, "consequence unconfirmed at an essential-service or compromised entity: verification target, not yet material")
        return out(REFERENCE_RETAIN, f"materiality {d.materiality}, impact status {d.impact_status}: no stated consequence")
    if not current:
        return out(CONTEXT, f"older than the brief window ({fr.BRIEF_FRESH_HOURS} h) and not still ongoing: context, not a current incident")
    if d.evidence_status == "unverified" or hedged:
        return out(MONITOR, "evidence unverified (aggregator-only or hedged): wait for a corroborating or primary report")
    if planned:
        return out(MONITOR, "planned or maintenance-related outage: advance notice, not an incident")
    if (d.materiality == "high" and d.impact_status == "stated" and live and au_demonstrated and not d.headline.minor
            and (d.evidence_status in ("officially_confirmed", "corroborated") or solid_kind) and _fresh(inc, now)):
        if d.provisional:
            why.append("single credible report: provisional, verify in follow-up")
        return out(IMMEDIATE_ALERT, "high materiality, stated impact, live disruption, Australian relevance demonstrated, solid evidence, fresh report")
    if d.materiality in ("high", "medium") and d.evidence_status in SOLID_EVIDENCE and not au_demonstrated:
        return out(MONITOR, "dependency only: Australian impact not established (no brief item until an Australian impact report arrives)")
    if d.materiality in ("high", "medium") and d.evidence_status in SOLID_EVIDENCE:
        if not current:
            return out(CONTEXT, f"older than the brief window ({fr.BRIEF_FRESH_HOURS} h) and not still ongoing: context, not a current incident")
        if not live and inc.restoration_status == "restored":
            return out(SCHEDULED_BRIEF, "restored: closure and impact summary for the next brief")
        return out(SCHEDULED_BRIEF, f"material ({d.materiality}) with {d.evidence_status} evidence but not an interrupt (not live or not fresh enough for an interrupt)")
    return out(MONITOR, "candidate that does not yet meet the evidence bar for a brief")
