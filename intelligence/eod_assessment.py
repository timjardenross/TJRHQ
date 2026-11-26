"""End-of-day executive intelligence assessment (flag BRIEF_EOD_ASSESSMENT_V1, default OFF).

Answers one question: how has the resilience environment changed since this morning, and what matters overnight and tomorrow?

Deterministic and pure: no model call, no network, no write. It reuses the shared evidence foundation (``brief_evidence``), incident
clustering (``incident_clustering``) and the morning brief that was actually stored. It takes no capacity input, so personal data
cannot enter it; the capacity block is rendered separately by ``captains_brief``.

It has no dependency on the judgement capability (``intelligence.judgements``).

Line labels:
  FACT       officially confirmed
  REPORTED   stated by publishers, not officially confirmed (strength is shown)
  FORECAST   warning, forecast or dated future notice
  ASSESSMENT rule-based reading of the above; potential effects are worded as potential
"""
from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from intelligence import brief_evidence as be
from intelligence import event_detection as ed
from intelligence import incident_clustering as ic
from intelligence import tiered_brief as tb

FLAG = "BRIEF_EOD_ASSESSMENT_V1"
WINDOW_HOURS = 72
CHANGE_LIMIT = 6
SECTION_LIMIT = 4
WATCH_LIMIT = 6
POLICY_LIMIT = 4

NEW = "NEW"
ESCALATING = "ESCALATING"
DETERIORATING = "DETERIORATING"
IMPROVING = "IMPROVING"
RESOLVED = "RESOLVED"
STRENGTHENED = "CONFIRMATION STRENGTHENED"
UPDATED = "CONTINUING, further reporting"
UNCHANGED = "CONTINUING, no new reporting"
NOT_COMPARED = "NOT COMPARED"
CHANGE_STATES = (DETERIORATING, ESCALATING, NEW, RESOLVED, IMPROVING, STRENGTHENED)

_PRIORITY_RANK = {"REFERENCE": 0, "WATCH": 1, "VERIFY": 2, "ESCALATE": 3}
_EVIDENCE_RANK = {"unverified": 0, "reported": 1, "corroborated": 2, "officially_confirmed": 3}
_FIRM = ("officially_confirmed", "corroborated")
_STATE_WORDS = {"ongoing": "ongoing", "partially_restored": "partially restored", "restored": "restored", "unknown": "current status unknown"}

_SECTOR_EFFECT = {
    "telecom": "could affect voice, data, emergency calls and services that depend on connectivity, including payments",
    "finance": "could affect customers' access to money and payments, and attract regulatory attention to operational resilience",
    "energy": "could affect sites and services that depend on grid supply, including communications and water",
    "cloud_platform": "could affect organisations that depend on the same provider, wherever they are",
    "health": "could affect patient care and clinical systems",
    "aviation": "could affect travel and time-critical freight",
    "transport_water": "could affect movement of people and goods or water supply",
    "government": "could affect access to government services and payments",
    "emergency_services": "could affect public safety response",
    "retail_food": "could affect supply and payment at the point of sale",
}
_SECTOR_NAMES = {"telecom": "telecommunications", "finance": "banking and finance", "energy": "energy", "cloud_platform": "cloud and platforms",
                 "health": "health", "aviation": "aviation", "transport_water": "transport and water", "government": "government services",
                 "emergency_services": "emergency services", "retail_food": "retail and food supply", "consumer_service": "consumer services"}
_PROFESSIONAL = ("finance", "telecom")

# Australian regulators and agencies. A headline counts as a regulatory item when one of them is the actor (name followed by what it
# did), or when the report comes from the body's own feed.
_REGULATORS = r"APRA|ASIC|ACMA|OAIC|RBA|ACCC|AUSTRAC|AEMO|ACSC|Treasury"
_REGULATOR_SOURCE_RX = re.compile(rf"\b(?:{_REGULATORS})\b")
# Order matters: an explicit proposal or comment is never promoted to a decision.
_POLICY_KINDS = (
    (1, "PROPOSAL or consultation (no decision yet)", r"consult\w*|propos\w+|draft\w*|discussion paper|seeks? (?:feedback|views|submissions)"),
    (3, "COMMENTARY (not a decision)", r"says?|said|speech|remarks|calls? for|urges?|warns?|flags?|flagging|signals?"),
    (0, "DECISION or enforcement action", (r"su(?:es|ed|ing)|fin(?:es|ed)|penali[sz]\w+|commenc\w+|bans?|banned|disqualif\w+|cancel\w*|suspend\w*|"
                                         r"impos\w+|orders?|ordered|accepts?|finali[sz]\w+|sets?|keeps?|kept|retains?|holds?|releases?|released|launche[sd]")),
    (2, "GUIDANCE (not a rule change)", r"guidance|guide"),
)
_ACTOR_RX = [(rank, label, re.compile(rf"\b({_REGULATORS})\b(?!'s )[^,;:|]{{0,40}}?\b(?:{verbs})\b", re.IGNORECASE)) for rank, label, verbs in _POLICY_KINDS]
_GUIDANCE_RX = re.compile(r"\bguidance\b", re.IGNORECASE)
_FILLER = frozenset(["the", "a", "an", "to", "of", "for", "on", "in", "and", "with", "as", "at", "by", "its", "new", "over", "after", "despite", "more", "australia", "australian", "s", "apra", "asic", "acma", "oaic", "rba", "accc", "austrac", "aemo", "acsc", "treasury", "sues", "sued", "finalises", "finalizes", "sets", "keeps", "kept", "retains", "holds", "releases", "released", "publishes", "issues", "says", "rules", "requirements"])
_HAZARD_OUTLOOK_RX = re.compile(r"\b(?:risk|outlook|forecast|expected|could|may|season|prepar\w+|warning of)\b", re.IGNORECASE)


def enabled() -> bool:
    return os.getenv(FLAG, "").strip().lower() in ("1", "true", "yes", "on")


def source_limitations() -> list[str]:
    """Known collection gaps that apply to any public-source product."""
    return ["Reduced Telstra coverage: the Telstra service-alert feed is inactive. A quiet Telstra picture is not evidence of no disruption."]


# ── the morning record ────────────────────────────────────────────────────────

@dataclass
class MorningRecord:
    """What the stored morning brief actually carried. Only ids and incident entry lines are read from it; no other text is reused."""
    generated_at: datetime
    report_ids: frozenset
    incident_ids: frozenset
    entries: dict            # incident id -> (headline, restoration state words)
    text: str
    caveat: str | None = None


_ENTRY_RX = re.compile(r"^- (.+) \((ongoing|partially restored|restored|current status unknown); \d+ reports; (inc-[0-9a-f]{10})\)", re.MULTILINE)


# The untiered Morning V1 line: "- [TAG] headline — facts; confidence [inc-xxxxxxxxxx; ...]".
_ENTRY_V1_RX = re.compile(r"^- \[[^\]]*\] (.+) — ([^\[\n]*)\[(inc-[0-9a-f]{10});", re.MULTILINE)


def _entries(text: str) -> dict:
    found = {}
    for m in _ENTRY_V1_RX.finditer(text):
        state = next((w for w in ("partially restored", "ongoing", "restored") if re.search(rf"\b{w}\b", m.group(2))), "current status unknown")
        found[m.group(3)] = (m.group(1), state)
    found.update({m.group(3): (m.group(1), m.group(2)) for m in _ENTRY_RX.finditer(text)})
    return found


def parse_morning(row: dict | None) -> MorningRecord | None:
    """``row``: a captains_daily_briefs record (brief_text, generated_at, collection_caveat). None when it cannot be compared against."""
    if not row or not row.get("brief_text") or not row.get("generated_at"):
        return None
    try:
        at = datetime.fromisoformat(str(row["generated_at"]).replace("Z", "+00:00"))
    except ValueError:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    text = html.unescape(str(row["brief_text"]))
    short = set(re.findall(r"#([0-9a-f]{8})", text)) | set(re.findall(r"\[([0-9a-f]{8})\]", text))
    entries = _entries(text)
    return MorningRecord(at, frozenset(short), frozenset(re.findall(r"inc-[0-9a-f]{10}", text)), entries, text, row.get("collection_caveat"))


# ── items ─────────────────────────────────────────────────────────────────────

@dataclass
class Item:
    view: be.IncidentView
    state: str               # lifecycle relative to the morning record
    restoration: str
    carried: bool            # shown in this morning's brief
    known_before: bool       # collected before this morning's brief
    area: str                # national | professional | international | other

    @property
    def sectors(self) -> list[str]:
        return [s for s in self.view.record.get("critical_service_dependencies") or [] if s in _SECTOR_NAMES]

    @property
    def is_forecast(self) -> bool:
        if self.view.event_type == "hazard" and _HAZARD_OUTLOOK_RX.search(self.view.headline):
            return True
        return self.view.impact_status in ("warning", "forecast")

    @property
    def is_disruption(self) -> bool:
        """A stated service disruption. Cyber compromise, hazards and vulnerabilities are described as what they are, not as outages."""
        return self.view.impact_status == "stated" and self.view.event_type == "outage"

    @property
    def unresolved(self) -> bool:
        return self.restoration in ed.CURRENT_DISRUPTION


def _when(value) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _area(view: be.IncidentView) -> str:
    cls = be._relevance_class(view)
    sectors = set(view.record.get("critical_service_dependencies") or [])
    platform_only = "cloud_platform" in sectors and not sectors & set(_PROFESSIONAL)
    australian = cls == "relevant" and (be._wk_au(view) or (not platform_only and any((r.get("geography") or "").upper() == "AU" for r in view.reports)))
    if australian:
        return "professional" if sectors & set(_PROFESSIONAL) else "national"
    if cls == "plausible" or (cls == "relevant" and sectors & {"cloud_platform"}):
        return "international"
    return "other"


def _material(i: Item) -> bool:
    v = i.view
    if i.area == "other" or v.impact_status == "retrospective" and not i.carried:
        return False
    if v.event_type == "vulnerability" and v.materiality == "low":
        return False
    if v.priority in ("ESCALATE", "WATCH"):
        return True
    return v.priority == "VERIFY" and v.materiality == "high"


def _lifecycle(view, restoration: str, known_before: bool, new_reports: bool, before: tuple | None, morning_entry: tuple | None) -> str:
    if not known_before:
        return NEW
    if not new_reports:
        return UNCHANGED
    b_view, b_restoration = before if before else (None, None)
    if morning_entry:                                  # what the morning brief actually printed wins over a reconstruction
        b_restoration = next((k for k, w in _STATE_WORDS.items() if w == morning_entry[1]), b_restoration)
    if b_restoration is not None:
        if restoration == "restored" and b_restoration != "restored":
            return RESOLVED
        if restoration == "partially_restored" and b_restoration == "ongoing":
            return IMPROVING
        if restoration == "ongoing" and b_restoration in ("restored", "partially_restored"):
            return DETERIORATING
    if b_view is not None:
        if _PRIORITY_RANK[view.priority] > _PRIORITY_RANK[b_view.priority]:
            return ESCALATING
        if _EVIDENCE_RANK[view.evidence_status] > _EVIDENCE_RANK[b_view.evidence_status]:
            return STRENGTHENED
    return UPDATED


def _views(events: list[dict], now: datetime) -> tuple[list[be.IncidentView], dict]:
    """Evidence incidents with canonical ids, plus restoration state per report id from the clustered lifecycle."""
    if not events:
        return [], {}
    ev = be.build_evidence(events, now=now, window_hours=WINDOW_HOURS)
    clustered = ic.cluster_incidents(events, now=now, force=True)
    restoration = {r.event_id: inc.restoration_status for inc in clustered for r in inc.reports}
    seen, views = set(), []
    for v in tb.v1_additive_view(ev, clustered).incidents:
        key = (v.incident_id, tuple(sorted(v.report_ids)))
        if key not in seen:
            seen.add(key)
            views.append(v)
    return views, restoration


def _restoration_of(view, by_report: dict) -> str:
    if view.event_type != "outage":                    # restoration is a property of a service outage only
        return "unknown"
    states = [by_report.get(r) for r in view.report_ids]
    for s in ("ongoing", "partially_restored", "restored"):
        if s in states:
            return s
    return view.record.get("restoration_status") or "unknown"


def build_items(events: list[dict], morning: MorningRecord | None, now: datetime) -> list[Item]:
    views, restoration = _views(events, now)
    before: dict = {}
    if morning:
        earlier = [e for e in events if (t := _when(e.get("collected_at"))) and t <= morning.generated_at]
        b_views, b_rest = _views(earlier, morning.generated_at)
        for v in b_views:
            for rid in v.report_ids:
                before[rid] = (v, _restoration_of(v, b_rest))
    collected = {str(e.get("id")): _when(e.get("collected_at")) for e in events}
    items = []
    for v in views:
        rest = _restoration_of(v, restoration)
        if not morning:
            items.append(Item(v, NOT_COMPARED, rest, False, False, _area(v)))
            continue
        ids = [str(r) for r in v.report_ids]
        carried = v.incident_id in morning.incident_ids or any(r[:8] in morning.report_ids for r in ids)
        known = carried or any((t := collected.get(r)) and t <= morning.generated_at for r in ids)
        fresh = any((t := collected.get(r)) and t > morning.generated_at for r in ids)
        prior = next((before[r] for r in ids if r in before), None)
        state = _lifecycle(v, rest, known, fresh, prior, morning.entries.get(v.incident_id))
        items.append(Item(v, state, rest, carried, known, _area(v)))
    items.sort(key=_rank)
    return items


def _rank(i: Item):
    """Materiality and decision value, not headline severity."""
    v = i.view
    return (0 if i.state in CHANGE_STATES else 1, 0 if i.unresolved else 1, -_PRIORITY_RANK[v.priority],
            -_EVIDENCE_RANK[v.evidence_status], v.sector_tier or 9, -(v.last_seen.timestamp() if v.last_seen else 0), v.incident_id)


# ── wording ───────────────────────────────────────────────────────────────────

def _short_headline(text: str, limit: int = 110) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def _claim(i: Item) -> str:
    v = i.view
    if i.is_forecast:
        return "FORECAST"
    if v.evidence_status == "officially_confirmed":
        return "FACT, officially confirmed"
    if v.evidence_status == "corroborated":
        return f"REPORTED, corroborated by {v.independent_publishers} publishers"
    return "REPORTED, single source" if v.evidence_status == "reported" else "REPORTED, unverified"


def _kind(i: Item) -> str:
    if i.is_forecast:
        return "warning or forecast, not an incident"
    if i.view.event_type == "vulnerability" or i.view.impact_status == "potential":
        return "potential exposure, no disruption established"
    if i.is_disruption:
        return "actual service disruption"
    if i.view.event_type == "cyber_incident":
        return "cyber compromise; service disruption not established"
    if i.view.event_type == "hazard":
        return "hazard or emergency; effect on services not established"
    return "impact not established"


def _why(i: Item) -> str:
    sectors = sorted(i.sectors, key=lambda s: ed.SECTOR_TIER.get(s, 9))
    effect = next((_SECTOR_EFFECT[s] for s in sectors if s in _SECTOR_EFFECT), None)
    if effect:
        effect = ("if it persists it " if i.is_disruption else "potential only: it ") + effect
    if i.view.event_type == "cyber_incident" and not i.is_disruption:
        effect = "watch for confirmation of what data or systems were affected, regulator involvement and follow-on fraud"
    where = " / ".join(_SECTOR_NAMES[s] for s in sectors[:2]) or "no recognised essential service"
    bits = [f"{where}; {_kind(i)}"]
    customers = i.view.record.get("affected_customers")
    if customers:
        bits.append(f"{customers:,} customers reported affected")
    if i.restoration == "restored":
        bits.append("service reported restored, so the remaining questions are cause and recurrence")
    elif effect:
        bits.append(effect)
    return "; ".join(bits)


def _decision(i: Item) -> str:
    if i.view.evidence_status not in _FIRM:
        return "investigate: confirm with a primary or second source before acting"
    if i.restoration == "restored":
        return "no immediate action; watch for cause and recurrence"
    if i.is_disruption and i.unresolved:
        return "prepare: check own exposure and follow restoration"
    if i.view.event_type == "cyber_incident":
        return "monitor: check whether you or your suppliers are exposed"
    return "monitor"


def _detail(i: Item) -> list[str]:
    flag = "" if i.carried or i.state in (NEW, NOT_COMPARED) or not i.known_before else " (known at 07:00, not in the morning brief)"
    state = "" if i.state == NOT_COMPARED else f"[{i.state}]{flag} "
    restore = "" if i.is_forecast or i.restoration == "unknown" else f"; {_STATE_WORDS[i.restoration]}"
    return [f"- {state}{_short_headline(i.view.headline, 150)}",
            f"    {_claim(i)}{restore} {be._cite(i.view)}",
            f"    ASSESSMENT: {_why(i)}. Decision: {_decision(i)}."]


def _brief_line(i: Item) -> str:
    restore = "" if i.restoration == "unknown" else f", {_STATE_WORDS[i.restoration]}"
    return f"- Continuing, no new reporting since 07:00{restore}: {_short_headline(i.view.headline, 90)} [{i.view.incident_id}]"


def _area_section(items: list[Item], area: str, empty: str) -> list[str]:
    pool = [i for i in items if i.area == area]
    detailed = [i for i in pool if i.state != UNCHANGED]
    lines: list[str] = []
    for i in detailed[:SECTION_LIMIT]:
        lines += _detail(i)
    lines += [_brief_line(i) for i in [x for x in pool if x.state == UNCHANGED][:3]]
    if len(detailed) > SECTION_LIMIT:
        lines.append(f"- {len(detailed) - SECTION_LIMIT} further item(s) in this area not shown.")
    return lines or [f"- {empty}"]


@dataclass
class PolicyItem:
    rank: int
    kind: str
    actor: str
    title: str
    words: set
    outlets: set
    ref: str
    official: bool
    seen_before: bool = False      # a related headline was collected before the morning brief, so it is not claimed as new

    def line(self) -> str:
        basis = "FACT, from the body's own publication" if self.official else f"REPORTED by {len(self.outlets)} outlet(s)"
        earlier = "; related reporting predates the morning brief" if self.seen_before else ""
        return f"- {self.kind}: {_short_headline(self.title)} ({basis}{earlier}) [{self.ref}]"


# Words too common in regulatory headlines to identify a story on their own.
_GENERIC_WORDS = frozenset(["insurer", "insurers", "bank", "banks", "licence", "license", "firm", "company", "super", "fund", "financial",
                            "former", "director", "court", "action", "takes", "against", "data"])


def _same_story(a: set, b: set) -> bool:
    shared = a & b
    return bool(shared - _GENERIC_WORDS) or len(shared) >= 3


def policy_items(events: list[dict], since: datetime) -> list[PolicyItem]:
    """Regulatory developments collected since ``since``, separating decisions from proposals, guidance and commentary, from the headline
    only. Reports of the same actor about the same subject are one item."""
    items: list[PolicyItem] = []
    ordered = sorted(events, key=lambda e: (not _REGULATOR_SOURCE_RX.search(e.get("source") or ""), str(e.get("collected_at")), str(e.get("id"))))
    for e in ordered:
        t = _when(e.get("collected_at"))
        source, title = e.get("source") or "", " ".join((e.get("title") or "").split())
        if not t or t <= since or not title:
            continue
        own = bool(_REGULATOR_SOURCE_RX.search(source)) and not source.startswith("Google News")
        core = ed.core_title(title)
        hit = next(((rank, label, m.group(1).upper()) for rank, label, rx in _ACTOR_RX if (m := rx.search(core))), None)
        if hit and _GUIDANCE_RX.search(core) and hit[0] == 0:
            hit = (2, "GUIDANCE (not a rule change)", hit[2])
        if not hit:
            if not own:
                continue
            hit = (2, "publication, nature not established from the headline", _REGULATOR_SOURCE_RX.search(source).group(0))
        rank, kind, actor = hit
        words = {w for w in re.findall(r"[a-z]+", core.lower()) if len(w) > 2 and w not in _FILLER}
        outlet = title[len(core):].strip(" -–|") or source
        same = next((p for p in items if p.actor == actor and _same_story(p.words, words)), None)
        if same:
            same.outlets.add(outlet)
            if rank < same.rank:
                same.rank, same.kind = rank, kind
            continue
        items.append(PolicyItem(rank, kind, actor, core, words, {outlet}, f"{source} #{str(e.get('id'))[:8]}", own))
    items.sort(key=lambda p: (p.rank, not p.official, -len(p.outlets), p.title))
    return items


def policy_lines(items: list[PolicyItem]) -> list[str]:
    lines = [p.line() for p in items[:POLICY_LIMIT]]
    if len(items) > POLICY_LIMIT:
        lines.append(f"- {len(items) - POLICY_LIMIT} further regulatory item(s) not shown.")
    return lines


def dependency_lines(items: list[Item]) -> list[str]:
    """Only what the evidence supports: one provider appearing in several separate incidents, or one disruption whose reporting names
    several services. Neither establishes cause."""
    by_subject: dict[str, list[Item]] = {}
    for i in items:
        for s in ic.subjects(i.view.headline):
            by_subject.setdefault(s, []).append(i)
    lines = []
    for subject, group in sorted(by_subject.items()):
        ids = sorted({i.view.incident_id for i in group})
        if len(ids) > 1 and any(i.is_disruption or i.view.event_type == "vulnerability" for i in group):
            lines.append(f"- ASSESSMENT: {len(ids)} separate items involve {subject.replace('_', ' ')} [{', '.join(ids[:3])}]. "
                         "A shared provider is a possible concentration point; no link between them is established.")
    for i in items:
        if i.is_disruption and i.restoration != "restored" and len(i.sectors) > 1:
            lines.append(f"- REPORTED: one disruption touches {', '.join(_SECTOR_NAMES[s] for s in i.sectors)}: "
                         f"{_short_headline(i.view.headline, 80)} [{i.view.incident_id}]. Cascade beyond what is reported is not established.")
    return lines[:4] or ["- No dependency, concentration or cascading effect is supported by the evidence collected."]


def _carried_unmatched(items: list[Item], morning: MorningRecord | None) -> list[str]:
    if not morning:
        return []
    present = {i.view.incident_id for i in items} | {be._incident_id(i.view.report_ids) for i in items}
    headlines = {" ".join(i.view.headline.split()) for i in items}
    return [f"- CARRIED FORWARD, no current reporting matched: {_short_headline(h, 90)} (morning: {state}) [{inc}]. Not treated as resolved."
            for inc, (h, state) in sorted(morning.entries.items()) if inc not in present and " ".join(h.split()) not in headlines and state in ("ongoing", "partially restored")]


def watch_lines(items: list[Item], events: list[dict], now: datetime) -> list[str]:
    lines = []
    for i in [x for x in items if x.view.event_type in ("hazard", "cyber_incident") and not x.is_forecast and x.state != UNCHANGED][:2]:
        label = "Hazard" if i.view.event_type == "hazard" else "Cyber follow-up"
        lines.append(f"- {label}: {_short_headline(i.view.headline, 90)} [{i.view.incident_id}]. Next check: {i.view.record['next_verification_action']}")
    for i in [x for x in items if x.unresolved][:3]:
        lines.append(f"- Restoration: {_short_headline(i.view.headline, 90)} [{i.view.incident_id}]. Next check: {i.view.record['next_verification_action']}")
    for i in [x for x in items if x.is_forecast][:2]:
        lines.append(f"- FORECAST: {_short_headline(i.view.headline, 100)} [{i.view.incident_id}]")
    if events:
        ev = be.build_evidence(events, now=now, window_hours=WINDOW_HOURS)
        for v, day in [x for x in be.forward_dated_items(ev, hours=48) if x[1].date() >= now.date()][:2]:
                lines.append(f"- FORECAST, dated {day.strftime('%d %b')}: {_short_headline(v.headline, 100)} [{v.incident_id}]")
    for i in [x for x in items if x.view.evidence_status not in _FIRM and not x.is_forecast and not x.unresolved and x.state != UNCHANGED
              and x.restoration != "restored"][:2]:
        lines.append(f"- Confirm: {_short_headline(i.view.headline, 90)} [{i.view.incident_id}]. Next check: {i.view.record['next_verification_action']}")
    once: dict[str, str] = {}                      # one watchpoint per incident: the first, most specific one
    for line in lines:
        found = re.search(r"inc-[0-9a-f]{10}", line)
        once.setdefault(found.group(0) if found else line, line)
    return list(once.values())[:WATCH_LIMIT] or ["- No specific watchpoint is supported by the evidence collected. This is not an all-clear."]


def _confidence(material: list[Item], morning, since_count: int, caveat: str | None) -> str:
    firm = sum(1 for i in material if i.view.evidence_status in _FIRM)
    if not morning or not since_count or caveat:
        why = "no morning record to compare against" if not morning else "nothing collected since 07:00" if not since_count else "collection was degraded"
        return f"LOW ({why})"
    if material and firm == len(material):
        return f"MODERATE TO HIGH (all {firm} material item(s) officially confirmed or corroborated)"
    if firm:
        return f"MODERATE ({firm} of {len(material)} material item(s) officially confirmed or corroborated)"
    return "LOW TO MODERATE (no material item is officially confirmed or corroborated)" if material else "MODERATE (coverage of collected sources only)"


def _bottom_line(material: list[Item], morning, since_count: int, carried_forward: int, confidence: str,
                 decisions: list[PolicyItem]) -> list[str]:
    if not morning:
        lines = ["- Change since this morning CANNOT BE ASSESSED: no comparable morning record. What follows is the current picture only."]
    elif not since_count:
        lines = ["- Change since this morning CANNOT BE ASSESSED: nothing was collected after the morning brief. This is not an all-clear."]
    else:
        changed = [i for i in material if i.state in CHANGE_STATES]
        if changed or decisions:
            counts = [f"{n} {s.lower()}" for s in CHANGE_STATES if (n := sum(1 for i in changed if i.state == s))]
            counts += [f"{len(decisions)} regulatory decision(s) or action(s)"] if decisions else []
            lines = [f"- {len(changed) + len(decisions)} material change(s) since the morning brief: {', '.join(counts)}."]
        else:
            lines = [f"- NO MATERIAL CHANGE since the morning brief across {since_count} report(s) collected since then."]
    open_au = [i for i in material if i.unresolved and i.area in ("national", "professional")]
    unconfirmed = sum(1 for i in open_au if i.view.evidence_status not in _FIRM)
    lines.append(f"- Australian service disruptions still open: {len(open_au)}" + (f" ({unconfirmed} not yet confirmed)" if unconfirmed else "")
                 + (f"; {carried_forward} carried from this morning without an update" if carried_forward else "") + ".")
    if decisions:
        lines.append(f"- Regulatory: {_short_headline(decisions[0].title, 100)}"
                     + (f" (+{len(decisions) - 1} more, section 4)." if len(decisions) > 1 else "."))
    australian = [i for i in material if i.area in ("national", "professional") and not i.is_forecast]
    lead = min(australian, key=lambda i: (0 if i.is_disruption else 1, _rank(i)), default=material[0] if material else None)
    if lead:
        lines.append(f"- Most decision-relevant: {_short_headline(lead.view.headline, 100)} ({_claim(lead).lower()}). {_decision(lead).capitalize()}.")
    lines.append(f"- Overall confidence: {confidence}.")
    return lines


def assess(events: list[dict], morning_row: dict | None, *, now: datetime | None = None, caveat: str | None = None,
           coverage: list[str] | None = None, limitations: list[str] | None = None) -> list[tuple[str, list[str]]]:
    """Return [(heading, lines)] for sections 1 to 9. Plain text (the caller escapes). ``events`` as ``brief_evidence.load_events``."""
    now = now or datetime.now(timezone.utc)
    morning = parse_morning(morning_row)
    items = build_items(events, morning, now)
    material = [i for i in items if _material(i)]
    since = morning.generated_at if morning else now - timedelta(hours=24)
    since_count = sum(1 for e in events if (t := _when(e.get("collected_at"))) and t > since)
    carried_forward = _carried_unmatched(items, morning)
    confidence = _confidence(material, morning, since_count, caveat)
    policy = [p for p in policy_items(events, since) if not (morning and p.ref.rsplit("#", 1)[1] in morning.report_ids)]
    if morning:
        earlier = policy_items([e for e in events if (t := _when(e.get("collected_at"))) and t <= since], datetime.min.replace(tzinfo=timezone.utc))
        for p in policy:
            p.seen_before = any(q.actor == p.actor and q.words & p.words for q in earlier)
    decisions = [p for p in policy if p.rank == 0 and not p.seen_before]

    if not morning:
        changes = ["- Not assessed: there is no comparable morning record, so nothing is labelled new or changed."]
    else:
        changed = [i for i in material if i.state in CHANGE_STATES]
        changes = [f"- {i.state}: {_short_headline(i.view.headline, 100)} [{i.view.incident_id}]" for i in changed[:CHANGE_LIMIT]]
        if len(changed) > CHANGE_LIMIT:
            changes.append(f"- {len(changed) - CHANGE_LIMIT} further change(s) not shown.")
        changes += [f"- NEW regulatory {p.kind.lower()}: {_short_headline(p.title, 90)}" for p in decisions[:3]]
        changes = changes or ["- No material change identified." if since_count else "- Not assessed: nothing collected since the morning brief."]

    professional = _area_section(material, "professional", "No material banking or telecommunications development identified.")
    professional += ["Regulation and policy since " + ("the morning brief:" if morning else "24 hours ago:")]
    professional += policy_lines(policy) or ["- No regulatory development identified in collected reporting."]

    lifecycle = []
    if morning:
        for s in (NEW, ESCALATING, DETERIORATING, IMPROVING, RESOLVED, STRENGTHENED, UPDATED, UNCHANGED):
            group = [i for i in material if i.state == s]
            if group:
                lifecycle.append(f"- {s.capitalize()}: {len(group)} [{', '.join(i.view.incident_id for i in group[:4])}{' …' if len(group) > 4 else ''}]")
    else:
        for state, words in _STATE_WORDS.items():
            group = [i for i in material if i.view.event_type == "outage" and i.restoration == state and not i.is_forecast]
            if group:
                lifecycle.append(f"- Service outages, {words}: {len(group)}")
        other = [i for i in material if i.view.event_type != "outage" or i.is_forecast]
        if other:
            lifecycle.append(f"- Cyber, hazard and other items (no restoration state): {len(other)}")
    lifecycle += carried_forward

    gaps = [f"- Overall confidence: {confidence}."]
    if caveat:
        gaps.append(f"- Collection: {caveat}.")
    if morning and morning.caveat:
        gaps.append(f"- This morning's brief carried a coverage caveat: {morning.caveat}.")
    unconfirmed = sum(1 for i in material if i.view.evidence_status not in _FIRM)
    gaps.append(f"- {unconfirmed} of {len(material)} material item(s) rest on a single or unverified source.")
    hidden = sum(1 for i in items if not _material(i))
    gaps.append(f"- {len(items)} incident(s) formed from {len(events)} report(s) in {WINDOW_HOURS} h; {hidden} below the materiality or relevance bar.")
    gaps += [f"- {x}" for x in limitations or []]
    gaps += list(coverage or [])
    gaps.append("- Assessment lines are rule-based from headline and summary evidence; they are not analyst or model judgement and can miss "
                "connections or misread wording.")

    return [
        ("1. EXECUTIVE BOTTOM LINE", _bottom_line(material, morning, since_count, len(carried_forward), confidence, decisions)),
        ("2. MATERIAL CHANGES SINCE THE MORNING BRIEF", changes),
        ("3. NATIONAL AND SYSTEMIC RESILIENCE (Australia)", _area_section(material, "national", "No material national development identified.")),
        ("4. BANKING, TELECOMMUNICATIONS AND REGULATED SECTORS", professional),
        ("5. INTERNATIONAL AND LEADING INDICATORS", _area_section(material, "international", "No international development with a plausible Australian dependency identified.")),
        ("6. INCIDENT LIFECYCLE", lifecycle or ["- No material incident to track."]),
        ("7. DEPENDENCIES, CONCENTRATION AND CASCADE", dependency_lines(material)),
        ("8. OVERNIGHT AND TOMORROW", watch_lines(material, events, now)),
        ("9. GAPS, UNCERTAINTY AND CONFIDENCE", gaps),
    ]
