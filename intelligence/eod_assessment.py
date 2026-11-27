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
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from intelligence import brief_evidence as be
from intelligence import event_detection as ed
from intelligence import freshness as fr
from intelligence import incident_clustering as ic
from intelligence import requirements as req
from intelligence import tiered_brief as tb

FLAG = "BRIEF_EOD_ASSESSMENT_V1"
WINDOW_HOURS = 72
CHANGE_LIMIT = 6
SECTION_LIMIT = 4
WATCH_LIMIT = 6
POLICY_LIMIT = 6              # a lower limit hid a rates-and-lending decision behind two repeats of other stories

NEW = "NEW"
ESCALATING = "ESCALATING"
DETERIORATING = "DETERIORATING"
IMPROVING = "IMPROVING"
RESOLVED = "RESOLVED"
STRENGTHENED = "CONFIRMATION STRENGTHENED"
UPDATED = "CONTINUING, further reporting"
UNCHANGED = "CONTINUING, no new reporting"
NOT_COMPARED = "NOT COMPARED"
REPORTING = "NEW REPORTING, currency not verified"   # never counted as a change: the event may be old
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
# The stored sector ``transport_water`` covers two services. Water is claimed only when the reporting names it.
_WATER_RX = re.compile(r"\b(?:water|sewage|sewerage|wastewater|dams?|desalination)\b", re.IGNORECASE)
_TRANSPORT_RX = re.compile(r"\b(?:rail\w*|trains?|trams?|bus(?:es)?|ferr(?:y|ies)|ports?|freight|roads?|highway|tunnel|bridge|transport)\b", re.IGNORECASE)


def _sector_words(sector: str, text: str) -> tuple[str, str | None]:
    """(name, potential effect) for a sector, narrowed for transport and water."""
    if sector == "transport_water":
        water, transport = bool(_WATER_RX.search(text)), bool(_TRANSPORT_RX.search(text))
        if transport and not water:
            return "transport", "could affect movement of people and goods"
        if water and not transport:
            return "water", "could affect water supply"
    return _SECTOR_NAMES[sector], _SECTOR_EFFECT.get(sector)

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
# A disruption announced for later is not one in progress.
_PLANNED_RX = re.compile(r"\b(?:to be|could be|will be|set to be|are to be)\b[^.]{0,40}\b(?:disrupted|cancelled|offline|replaced|suspended|shut)\b"
                         r"|\bfrom (?:next )?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE)
# Industrial action affirmed as stopped: the subject and the verb must be adjacent, so "trains suspended due to strike" does not match.
_ACTION = r"(?:strikes?|industrial action|stoppage|walk[- ]?out)"
_STOOD_DOWN_RX = re.compile(
    rf"\b{_ACTION}(?: action)? (?:(?:has|have) been |was |is |are )?(?:suspended|called off|cancelled|averted|abandoned|scrapped|halted)\b"
    rf"|\b(?:suspends|calls off|halts|blocks|averts|ends) (?:the |a |planned )?(?:[a-z]+ ){{0,2}}?{_ACTION}\b", re.IGNORECASE)
_HEDGE_RX = re.compile(r"\?|\b(?:could|may|might|bid|seek\w*|asks?|asked|appl\w+|not|refus\w+|reject\w+|whether|unless|if|calls? for|push\w*|"
                       r"part(?:ly|ial\w*)|one|some)\b", re.IGNORECASE)
_INDUSTRIAL_RX = re.compile(r"\b(?:strikes?|industrial|stoppage|walk[- ]?out)\b", re.IGNORECASE)
_PLACE_RX = re.compile(r"\b(?:nsw|new south wales|sydney|victoria|melbourne|queensland|brisbane|western australia|perth|south australia|"
                       r"adelaide|tasmania|hobart|act|canberra|northern territory|darwin)\b", re.IGNORECASE)
_PLACES = {"new south wales": "nsw", "sydney": "nsw", "melbourne": "victoria", "brisbane": "queensland", "perth": "western australia",
           "adelaide": "south australia", "hobart": "tasmania", "canberra": "act", "darwin": "northern territory"}
_ACTION_GENERIC = frozenset(["strike", "industrial", "action", "suspended", "fair", "work", "commission", "hearing", "decision", "union",
                             "planned", "friday", "week", "rail"])
# Consequences that, appearing for the first time after the morning brief, make an incident worse rather than merely re-reported.
_CONSEQUENCE_RX = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"\b(?:destroy\w*|homes? lost|damaged)\b", r"\b(?:killed|dead|deaths?|injur\w+)\b", r"\bevacuat\w+\b",
    r"\b(?:cancel\w*|replaced by|suspended)\b", r"\b(?:passport\w*|customer (?:data|records)|stolen data)\b"))
# Words that cannot by themselves show two reports are about the same thing.
_LINK_GENERIC = frozenset(["service", "services", "outage", "disruption", "disrupted", "after", "could", "from", "week", "with", "that", "this", "have",
                           "been", "will", "their", "says", "more", "australia", "australian", "customer", "customers", "major", "decision"])
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


_ENTRY_RX = re.compile(r"^- (.+) \((ongoing|partially restored|restored|current status unknown|announced, not started|action suspended|forecast, not an incident|currency not verified|no restoration status); \d+ reports; (inc-[0-9a-f]{10})\)", re.MULTILINE)


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
    linked: tuple = ()       # morning report ids this item continues although clustering kept them apart
    continues: str = ""      # the morning headline, when linked

    @property
    def sectors(self) -> list[str]:
        return [s for s in self.view.record.get("critical_service_dependencies") or [] if s in _SECTOR_NAMES]

    foreign_indicator: bool = False
    stood_down: bool = False     # the latest reporting says the announced industrial action was suspended or called off
    supersedes: tuple = ()       # headlines of the earlier notices this reporting replaces

    @property
    def status_words(self) -> str:
        """Lifecycle words that agree with the rest of the entry: restoration is claimed only for a current outage."""
        if self.stood_down:
            return "action suspended"
        if self.planned:
            return "announced, not started"
        if self.is_forecast:
            return "forecast, not an incident"
        if self.currency_unverified:
            return "currency not verified"
        if self.view.event_type != "outage":
            return "no restoration status"
        return _STATE_WORDS.get(self.restoration, "current status unknown")

    @property
    def is_forecast(self) -> bool:
        if self.stood_down:
            return False
        if self.view.event_type == "hazard" and _HAZARD_OUTLOOK_RX.search(self.view.headline):
            return True
        return self.view.impact_status in ("warning", "forecast")

    @property
    def planned(self) -> bool:
        if self.stood_down or self.view.event_type != "outage" or self.restoration in ("restored", "partially_restored"):
            return False
        text = " ".join([self.view.headline] + [str(r.get("title") or "") for r in self.view.reports])
        return bool(_PLANNED_RX.search(text))

    @property
    def currency_unverified(self) -> bool:
        """An outage seen only through aggregators: the article date does not show the disruption is happening now."""
        return not self.stood_down and self.view.event_type == "outage" and self.view.evidence_status == "unverified"

    @property
    def is_disruption(self) -> bool:
        """A stated service disruption. Cyber compromise, hazards and vulnerabilities are described as what they are, not as outages."""
        return (self.view.impact_status == "stated" and self.view.event_type == "outage" and not self.planned and not self.currency_unverified
                and not self.stood_down)

    @property
    def unresolved(self) -> bool:
        return self.restoration in ed.CURRENT_DISRUPTION and not self.planned and not self.currency_unverified and not self.stood_down


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


_LEADING_SECTORS = frozenset(["telecom", "finance", "energy", "cloud_platform", "transport_water", "government", "aviation", "health"])


def _leading_indicator(view: be.IncidentView) -> bool:
    """A material development abroad that is worth watching although no direct Australian dependency is established: an officially
    confirmed vulnerability, or a reported outage or cyber incident affecting a critical service. Aggregator-only reports and
    reference-grade news do not qualify."""
    if be._wk_au(view) or any((r.get("geography") or "").upper() == "AU" for r in view.reports) or be._relevance_class(view) != "editorial":
        return False
    if not (view.priority in ("ESCALATE", "WATCH") or (view.priority == "VERIFY" and view.materiality == "high")):
        return False
    if view.event_type == "vulnerability":
        return view.evidence_status == "officially_confirmed" and view.materiality != "low"
    return (view.event_type in ("outage", "cyber_incident") and view.evidence_status != "unverified"
            and bool(set(view.record.get("critical_service_dependencies") or []) & _LEADING_SECTORS))


# Reporting about one person's alleged conduct, and sport, is not resilience intelligence unless an essential service is affected.
# Headline wording only: a narrow exclusion that will miss other phrasings, not a relevance or privacy control.
_PERSON_ROLE_RX = re.compile(r"\b(?:teacher|principal|doctor|nurse|paramedic|officer|worker|employee|coach|player|priest|councillor|man|woman)(?:'s)?\b",
                             re.IGNORECASE)
_CONDUCT_RX = re.compile(r"\b(?:alleg\w+|charged|investigation|court|offences?|offending|abuse|assault\w*|jail\w*|sentenced|misconduct)\b", re.IGNORECASE)
_SPORT_RX = re.compile(r"\b(?:cricket|ball.tampering|sandpapergate|footy|afl|nrl|rugby|tennis|golf|olympi\w+)\b", re.IGNORECASE)


def _out_of_scope(view) -> bool:
    sectors = set(view.record.get("critical_service_dependencies") or []) & set(_SECTOR_NAMES)
    headline = view.headline
    if _PERSON_ROLE_RX.search(headline) and _CONDUCT_RX.search(headline):
        # "police", "hospital" and the like name the person's setting, not an affected service, so they do not keep the item in.
        return not sectors - {"emergency_services", "health"}
    return bool(not sectors and _SPORT_RX.search(headline))


def _material(i: Item) -> bool:
    v = i.view
    if _out_of_scope(v):
        return False
    if i.supersedes and i.area != "other":     # replaces a notice that would otherwise have been shown
        return True
    if i.area == "other" or v.impact_status == "retrospective" and not i.carried:
        return False
    if i.state == UNCHANGED and i.restoration == "restored" and not i.carried:   # an old, closed event is not part of today's picture
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


def _text(report: dict) -> str:
    return f"{report.get('title') or ''} {report.get('summary') or ''}"


def _words(view) -> set:
    found = re.findall(r"[a-z]{4,}", " ".join(_text(r) for r in view.reports).lower())
    return {w.rstrip("s") for w in found if w not in _LINK_GENERIC and w.rstrip("s") not in _LINK_GENERIC}


def _worse(view, morning: MorningRecord, collected: dict, headline: str = "") -> bool:
    """A consequence stated since the morning brief that neither the brief's headline nor earlier reporting stated."""
    def after(r):
        t = collected.get(str(r.get("report_id")))
        return bool(t and t > morning.generated_at)
    new = " ".join(_text(r) for r in view.reports if after(r))
    old = " ".join([headline] + [_text(r) for r in view.reports if not after(r)])
    return any(rx.search(new) and not rx.search(old) for rx in _CONSEQUENCE_RX)


def _link_continuations(items: list[Item], morning: MorningRecord, collected: dict) -> list[Item]:
    """Clustering can keep a follow-up apart from the incident the morning brief carried. Join them in this product only, when they share a
    service sector and at least three specific words, so one disruption is not reported both as new and as unchanged."""
    dropped: set = set()
    for new in [i for i in items if i.state == NEW]:
        for old in items:
            if (old.carried and old.state == UNCHANGED and id(old) not in dropped and set(old.sectors) & set(new.sectors)
                    and len(_words(old.view) & _words(new.view)) >= 3):
                headline = old.view.headline
                new.carried, new.known_before, new.continues = True, True, headline
                new.linked = tuple(str(r) for r in old.view.report_ids)
                new.state = ESCALATING if _worse(new.view, morning, collected, headline) else UPDATED
                dropped.add(id(old))
                break
    return [i for i in items if id(i) not in dropped]


def _stand_down_text(report: dict) -> str | None:
    """The report's wording if it affirms the action stopped: its headline, or the headline slug of its address (publishers rewrite
    an article in place and the stored title can lag)."""
    slug = urlsplit(str(report.get("url") or "")).path.rstrip("/").split("/")
    for text in (str(report.get("title") or ""), " ".join(slug[-2:]).replace("-", " ")):
        found = _STOOD_DOWN_RX.search(text)
        if found and not _HEDGE_RX.search(text[:found.end()]):
            return text
    return None


def _reported_at(report: dict) -> datetime:
    return (_when(report.get("published_at")) or _when(report.get("collected_at")) or _when(report.get("first_seen"))
            or datetime.min.replace(tzinfo=timezone.utc))


def _places(view) -> set:
    found = _PLACE_RX.findall(" ".join(_text(r) for r in view.reports))
    return {_PLACES.get(x.lower(), x.lower()) for x in found}


def _same_action(old: Item, new: Item) -> bool:
    evidence = " ".join(f"{_text(r)} {urlsplit(str(r.get('url') or '')).path.replace('-', ' ').replace('/', ' ')}" for r in old.view.reports)
    a, b = _places(old.view), _places(new.view)
    return bool(_INDUSTRIAL_RX.search(evidence) and set(old.sectors) & set(new.sectors) and (not a or not b or a & b)
                and (_words(old.view) & _words(new.view)) - _ACTION_GENERIC)


def _reconcile_stand_downs(items: list[Item], times: dict) -> list[Item]:
    """An announced disruption and the later suspension of the action behind it are one story, told with its latest state. Only
    notices that have not started and are older than the suspension are replaced; an actual disruption is never closed this way."""
    def stand(i: Item):
        reports = [(times.get(str(r.get("report_id")), _reported_at(r)), r) for r in i.view.reports]
        if not reports or i.view.evidence_status == "unverified":
            return None
        at, report = max(reports, key=lambda x: x[0])
        return (at, report) if _stand_down_text(report) else None

    def latest(i: Item) -> datetime:
        return max((times.get(str(r.get("report_id")), _reported_at(r)) for r in i.view.reports), default=_reported_at({}))

    stands = sorted([(i, s) for i in items if (s := stand(i))], key=lambda x: x[1][0], reverse=True)
    dropped: set = set()
    for new, (at, report) in stands:
        if id(new) in dropped:
            continue
        olds = [o for o in items if o is not new and id(o) not in dropped and not stand(o) and o.planned and latest(o) <= at
                and _same_action(o, new)]
        earlier = [o.view.headline for o in olds]
        earlier += [h for h in (new.continues, new.view.headline) if h and not _STOOD_DOWN_RX.search(h)]
        title = str(report.get("title") or "")
        if _STOOD_DOWN_RX.search(title):
            new.view = replace(new.view, headline=title)
        elif earlier:                                      # only the address carries the change: say so in the headline
            new.view = replace(new.view, headline="Industrial action behind an announced disruption reported suspended")
        new.stood_down, new.supersedes, new.continues = True, tuple(dict.fromkeys(earlier)), ""
        for old in olds:
            new.carried, new.known_before = new.carried or old.carried, new.known_before or old.known_before
            new.linked = tuple(new.linked) + tuple(str(r) for r in old.view.report_ids) + tuple(old.linked)
            new.area = old.area if new.area == "other" else new.area
            dropped.add(id(old))
        if new.state in (ESCALATING, DETERIORATING, UPDATED):          # a suspension is not a worsening
            new.state = IMPROVING
    return [i for i in items if id(i) not in dropped]


def _item(view, state: str, restoration: str, carried: bool, known_before: bool) -> Item:
    area = _area(view)
    indicator = area == "other" and _leading_indicator(view)
    return Item(view, state, restoration, carried, known_before, "international" if indicator else area, foreign_indicator=indicator)


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
            items.append(_item(v, NOT_COMPARED, rest, False, False))
            continue
        ids = [str(r) for r in v.report_ids]
        carried = v.incident_id in morning.incident_ids or any(r[:8] in morning.report_ids for r in ids)
        known = carried or any((t := collected.get(r)) and t <= morning.generated_at for r in ids)
        fresh = any((t := collected.get(r)) and t > morning.generated_at for r in ids)
        prior = next((before[r] for r in ids if r in before), None)
        state = _lifecycle(v, rest, known, fresh, prior, morning.entries.get(v.incident_id))
        if state == UPDATED and _worse(v, morning, collected):
            state = ESCALATING
        items.append(_item(v, state, rest, carried, known))
    if morning:
        items = _link_continuations(items, morning, collected)
        for i in items:
            if i.currency_unverified and i.state in CHANGE_STATES:
                i.state = REPORTING
    items = _reconcile_stand_downs(items, {str(e.get("id")): _reported_at(e) for e in events})
    items.sort(key=_rank)
    return items


def _rank(i: Item):
    """Materiality and decision value, not headline severity."""
    v = i.view
    return (0 if i.state in CHANGE_STATES else 1, 0 if i.carried else 1, 0 if i.unresolved or i.planned else 1, -_PRIORITY_RANK[v.priority],
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
    if i.stood_down:
        return "industrial action reported suspended or called off; resumption of services not established"
    if i.planned:
        return "announced disruption, not reported as started"
    if i.currency_unverified:
        return "disruption reported, but not verified as current; may be historical"
    if i.is_disruption:
        return "actual service disruption"
    if i.view.event_type == "cyber_incident":
        return "cyber compromise; service disruption not established"
    if i.view.event_type == "hazard":
        return "hazard or emergency; effect on services not established"
    return "impact not established"


def _why(i: Item) -> str:
    sectors = sorted(i.sectors, key=lambda s: ed.SECTOR_TIER.get(s, 9))
    words = [_sector_words(s, i.view.headline) for s in sectors]
    effect = next((e for _, e in words if e), None)
    if effect:
        effect = ("if it persists it " if i.is_disruption else "potential only: it ") + effect
    if i.view.event_type == "cyber_incident" and not i.is_disruption:
        effect = "watch for confirmation of what data or systems were affected, regulator involvement and follow-on fraud"
    where = " / ".join(n for n, _ in words[:2]) or "no recognised essential service"
    bits = [f"{where}; {_kind(i)}"]
    if i.foreign_indicator:
        bits.append("international leading indicator; no direct Australian dependency established")
    customers = i.view.record.get("affected_customers")
    if customers:
        bits.append(f"{customers:,} customers reported affected")
    if i.stood_down:
        pass
    elif i.restoration == "restored":
        bits.append("service reported restored, so the remaining questions are cause and recurrence")
    elif effect:
        bits.append(effect)
    return "; ".join(bits)


def _decision(i: Item) -> str:
    if i.stood_down:
        return "check: confirm with the operator that services are running before relying on them"
    if i.planned:
        return "prepare: check the operator's timetable and own travel or freight exposure from the stated start; confirm with a second source"
    if i.currency_unverified:
        return "investigate: establish whether it is happening now before any action"
    if i.view.evidence_status not in _FIRM:
        return "investigate: confirm with a primary or second source before acting"
    if i.restoration == "restored":
        return "no immediate action; watch for cause and recurrence"
    if i.is_disruption and i.unresolved:
        return "prepare: check own exposure and follow restoration"
    if i.view.event_type == "cyber_incident":
        return "monitor: check whether you or your suppliers are exposed"
    return "monitor"


def _supersedes_lines(i: Item) -> list[str]:
    return [f"    Replaces earlier notice (no longer current): {_short_headline(h, 90)}" for h in i.supersedes[:3]]


def _detail(i: Item) -> list[str]:
    flag = "" if i.carried or i.state in (NEW, NOT_COMPARED) or not i.known_before else " (known at 07:00, not in the morning brief)"
    state = "" if i.state == NOT_COMPARED else f"[{i.state}]{flag} "
    restore = ("" if i.is_forecast or i.planned or i.stood_down or i.currency_unverified or i.restoration == "unknown"
               else f"; {_STATE_WORDS[i.restoration]}")
    follows = [f"    Continues this morning's item: {_short_headline(i.continues, 90)}"] if i.continues else []
    return [f"- {state}{_short_headline(i.view.headline, 150)}", *follows, *_supersedes_lines(i),
            f"    {_claim(i)}{restore} {be._cite(i.view)}",
            f"    ASSESSMENT: {_why(i)}. Decision: {_decision(i)}."]


def _brief_line(i: Item) -> str:
    words = "" if i.status_words in ("no restoration status", "current status unknown") else f", {i.status_words}"
    if i.status_words == "restored":
        return f"- Restored earlier, no new reporting since 07:00: {_short_headline(i.view.headline, 90)} [{i.view.incident_id}]"
    return f"- Continuing, no new reporting since 07:00{words}: {_short_headline(i.view.headline, 90)} [{i.view.incident_id}]"


def _area_shown(items: list[Item], area: str) -> list[Item]:
    pool = [i for i in items if i.area == area]
    return [i for i in pool if i.state != UNCHANGED][:SECTION_LIMIT] + [i for i in pool if i.state == UNCHANGED][:3]


def _area_section(items: list[Item], area: str, empty: str) -> list[str]:
    pool = [i for i in items if i.area == area]
    detailed = [i for i in pool if i.state != UNCHANGED]
    lines: list[str] = []
    for i in _area_shown(items, area):
        lines += _brief_line(i).splitlines() if i.state == UNCHANGED else _detail(i)
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


# Words that name the same subject in one regulator's headlines. Kept per regulator: "director" is not one subject elsewhere.
_SUBJECT = {"APRA": {"board": "governance", "tenure": "governance", "director": "governance"}}


def _stem(word: str, actor: str) -> str:
    word = word[:-1] if len(word) > 4 and word.endswith("s") and not word.endswith("ss") else word
    return _SUBJECT.get(actor, {}).get(word, word)


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
        words = {_stem(w, actor) for w in re.findall(r"[a-z]+", core.lower()) if len(w) > 2 and w not in _FILLER}
        words -= {"rule", "requirement"}
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
        if i.view.event_type == "hazard" and i.sectors and not i.is_forecast:
            lines.append(f"- REPORTED: hazard reporting involves {', '.join(_SECTOR_NAMES[s] for s in i.sectors)}: "
                         f"{_short_headline(i.view.headline, 80)} [{i.view.incident_id}]. Extent of any service effect is not established.")
    for i in items:
        if i.is_disruption and i.restoration != "restored" and len(i.sectors) > 1:
            lines.append(f"- REPORTED: one disruption touches {', '.join(_SECTOR_NAMES[s] for s in i.sectors)}: "
                         f"{_short_headline(i.view.headline, 80)} [{i.view.incident_id}]. Cascade beyond what is reported is not established.")
    return lines[:4] or ["- No dependency, concentration or cascading effect is supported by the evidence collected."]


def _morning_open(morning: MorningRecord) -> list[tuple[str, str, str, set]]:
    """The morning brief's incident entries above its background section: (incident id, headline, class, report ids)."""
    text = morning.text.split("WORTH KNOWING")[0]
    entries = _entries(text)
    kinds, reports, kind, current = {}, {}, "open", None
    for line in text.splitlines():
        upper = line.strip()
        if upper.startswith(("MATERIAL INCIDENTS", "EMERGING EXPOSURES", "MONITORING")):
            kind = "exposure" if upper.startswith("EMERGING") else "watch" if upper.startswith("MONITORING") else "open"
        found = re.search(r"inc-[0-9a-f]{10}", line)
        if line.startswith("- "):
            current = found.group(0) if found else None
        inc = found.group(0) if found else current
        if not inc:
            continue
        kinds.setdefault(inc, kind)
        if "retrospective" in line:
            kinds[inc] = "retrospective"
        elif "emerging exposure" in line:
            kinds[inc] = "exposure"
        reports.setdefault(inc, set()).update(re.findall(r"#([0-9a-f]{8})", line) + re.findall(r"\[([0-9a-f]{8})\]", line))
    return [(inc, h, kinds.get(inc, "open"), reports.get(inc, set())) for inc, (h, _state) in entries.items()]


_OPEN_WORDS = (("open", "Reported this morning, no further reporting matched"),
               ("exposure", "Technology exposure still open, no update on exploitation or patching"),
               ("retrospective", "Regulatory finding about a past incident, not a current disruption"),
               ("watch", "Still unverified from this morning"))


def _carried_unmatched(shown: list[Item], morning: MorningRecord | None) -> list[str]:
    """Every morning incident that the sections above do not cover. Silence is never read as resolution, whatever state it had."""
    if not morning:
        return []
    ids = {str(r)[:8] for i in shown for r in (*i.view.report_ids, *i.linked)}
    incidents = {i.view.incident_id for i in shown} | {be._incident_id(i.view.report_ids) for i in shown}
    headlines = {" ".join(i.view.headline.split()) for i in shown}
    left = [(kind, inc, h) for inc, h, kind, reports in _morning_open(morning)
            if inc not in incidents and not reports & ids and " ".join(h.split()) not in headlines]
    return [f"- {words}: {_short_headline(h, 90)} [{inc}]. Not treated as resolved."
            for key, words in _OPEN_WORDS for kind, inc, h in left if kind == key]


def watch_lines(items: list[Item], events: list[dict], now: datetime) -> list[str]:
    lines = []
    for i in [x for x in items if x.stood_down][:2]:
        lines.append(f"- Resumption: {_short_headline(i.view.headline, 90)} [{i.view.incident_id}]. Next check: operator confirmation that "
                     "services are running, and any notice of further action")
    for i in [x for x in items if x.planned][:2]:
        lines.append(f"- Announced disruption: {_short_headline(i.view.headline, 90)} [{i.view.incident_id}]. Next check: operator timetable and "
                     "any industrial or regulatory decision before the stated start")
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
    local = [i for i in material if i.area in ("national", "professional")]
    pending = [f"{n} {words}" for n, words in ((sum(1 for i in local if i.planned), "announced and not yet started"),
                                             (sum(1 for i in local if i.currency_unverified), "reported but not verified as current")) if n]
    lines.append(f"- Australian service disruptions still open: {len(open_au)}" + (f" ({unconfirmed} not yet confirmed)" if unconfirmed else "") + (f"; also {', '.join(pending)}" if pending else "")
                 + (f"; {carried_forward} item(s) from this morning not otherwise covered (section 6)" if carried_forward else "") + ".")
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
    """Return [(heading, lines)] for sections 1 to 8. Plain text (the caller escapes). ``events`` as ``brief_evidence.load_events``."""
    now = now or datetime.now(timezone.utc)
    morning = parse_morning(morning_row)
    items = build_items(events, morning, now)
    material = [i for i in items if _material(i)]
    since = morning.generated_at if morning else now - timedelta(hours=24)
    since_count = sum(1 for e in events if (t := _when(e.get("collected_at"))) and t > since)
    shown = [i for area in ("national", "professional", "international") for i in _area_shown(material, area)]
    carried_forward = _carried_unmatched(shown, morning)
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
        restored_earlier = [i for i in material if i.state == UNCHANGED and i.status_words == "restored"]
        if restored_earlier:
            lifecycle.append(f"- Restored earlier, no new reporting: {len(restored_earlier)} [{', '.join(i.view.incident_id for i in restored_earlier[:4])}]")
        for s in (NEW, ESCALATING, DETERIORATING, IMPROVING, RESOLVED, STRENGTHENED, UPDATED, REPORTING, UNCHANGED):
            group = [i for i in material if i.state == s and i not in restored_earlier]
            if group:
                lifecycle.append(f"- {s[0] + s[1:].lower()}: {len(group)} [{', '.join(i.view.incident_id for i in group[:4])}{' …' if len(group) > 4 else ''}]")
    else:
        for state, words in _STATE_WORDS.items():
            group = [i for i in material if i.view.event_type == "outage" and i.restoration == state and not i.is_forecast]
            if group:
                lifecycle.append(f"- Service outages, {words}: {len(group)}")
        other = [i for i in material if i.view.event_type != "outage" or i.is_forecast]
        if other:
            lifecycle.append(f"- Cyber, hazard and other items (no restoration state): {len(other)}")
    if morning and not any(i.state == RESOLVED for i in material):
        lifecycle.append("- No incident is confirmed resolved since the morning brief.")
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
        ("4. PROFESSIONAL AND SECTOR DEVELOPMENTS (banking, telecommunications, regulation)", professional),
        ("5. INTERNATIONAL LEADING INDICATORS", _area_section(material, "international", "No material international development identified in collected reporting.")),
        ("6. INCIDENT CONTINUITY AND SYSTEMIC EXPOSURE", (lifecycle or ["- No material incident to track."]) + ["Systemic exposure:", *dependency_lines(material)]),
        ("7. OVERNIGHT WATCH", watch_lines(material, events, now)),
        ("8. OUTSTANDING UNCERTAINTY AND INTELLIGENCE GAPS", gaps),
    ]


# ── morning product (flag BRIEF_MORNING_PDB_V1, default OFF) ──────────────────
# The same evidence, rules and wording as the evening assessment, ordered for strategic orientation. Incident lines keep the
# form ``_entries`` reads, so the evening assessment can compare itself against this product.

MORNING_FLAG = "BRIEF_MORNING_PDB_V1"
MORNING_SECTION_LIMIT = 5


def morning_enabled() -> bool:
    return os.getenv(MORNING_FLAG, "").strip().lower() in ("1", "true", "yes", "on")


def _requirement(view, pirs: list) -> str:
    """Standing requirement the item matches (strong matches only). An annotation: it never selects or removes an item."""
    if not pirs:
        return ""
    originals = [r for r in view.reports if r.get("role") == "original"] or view.reports
    item = {"id": view.incident_id, "title": " . ".join([view.headline] + [str(r.get("title") or "") for r in originals[:4]]),
            "summary": str(originals[0].get("summary") or "")[:600] if originals else "", "materiality": view.materiality}
    ids = sorted({m.pir_id for m in req.tag_item(item, pirs).strong_matches})
    return f" Requirement: {', '.join(ids[:3])}." if ids else ""


def _morning_pool(items: list[Item], now: datetime) -> list[Item]:
    """Material items still current for this morning: recent reporting, or an open or announced disruption already carried."""
    cutoff = now - fr.brief_window()
    return [i for i in items if _material(i) and ((i.view.last_seen and i.view.last_seen >= cutoff) or (i.carried and (i.unresolved or i.planned)))]


def _morning_entry(i: Item, pirs: list) -> list[str]:
    v = i.view
    change = "" if i.state == NOT_COMPARED else "no new reporting since the previous brief; " if i.state == UNCHANGED else f"{i.state}; "
    extra = ("; emerging exposure" if v.event_type == "vulnerability" else "") + ("; retrospective" if v.impact_status == "retrospective" else "")
    if i.state == UNCHANGED and i.status_words == "restored":
        change = "restored earlier; no new reporting since the previous brief; "
    return [f"- {_short_headline(v.headline, 150)} ({i.status_words}; {len(v.report_ids)} reports; {v.incident_id})", *_supersedes_lines(i),
            f"    {change}{_claim(i)}{extra} {be._cite(v)}",
            f"    ASSESSMENT: {_why(i)}. Decision: {_decision(i)}.{_requirement(v, pirs)}"]


def _morning_area(pool: list[Item], area: str, pirs: list, empty: str) -> list[str]:
    found = [i for i in pool if i.area == area]
    lines = [x for i in found[:MORNING_SECTION_LIMIT] for x in _morning_entry(i, pirs)]
    if len(found) > MORNING_SECTION_LIMIT:
        lines.append(f"- {len(found) - MORNING_SECTION_LIMIT} further item(s) in this area not shown.")
    return lines or [f"- {empty}"]


def _patterns(pool: list[Item]) -> list[str]:
    """Counts of items sharing a service sector. A count is not a trend or a common cause, and is worded that way."""
    lines = []
    for sector, name in _SECTOR_NAMES.items():
        group = [i for i in pool if sector in i.sectors]
        if sector == "transport_water" and group:
            names = {_sector_words(sector, i.view.headline)[0] for i in group}
            name = names.pop() if len(names) == 1 else name
        if len(group) >= 2:
            ids = ", ".join(i.view.incident_id for i in group[:4])
            lines.append(f"- {len(group)} current items involve {name} [{ids}]. A common cause or trend is not established.")
    return lines or ["- No sector has more than one current material item."]


def assess_morning(events: list[dict], previous_row: dict | None, *, now: datetime | None = None, caveat: str | None = None,
                   coverage: list[str] | None = None, limitations: list[str] | None = None,
                   retained: list[str] | None = None) -> list[tuple[str, list[str]]]:
    """Return [(heading, lines)] for the morning product. ``previous_row``: the last stored morning brief before today, or None.
    Deterministic: no model call, no capacity input."""
    now = now or datetime.now(timezone.utc)
    previous = parse_morning(previous_row)
    items = build_items(events, previous, now)
    pool = _morning_pool(items, now)
    pirs = req.load_pirs()
    shown = [i for area in ("national", "professional", "international") for i in [x for x in pool if x.area == area][:MORNING_SECTION_LIMIT]]
    since = previous.generated_at if previous else now - timedelta(hours=24)
    policy = policy_items(events, since)
    if previous:
        earlier = policy_items([e for e in events if (t := _when(e.get("collected_at"))) and t <= since], datetime.min.replace(tzinfo=timezone.utc))
        for p in policy:
            p.seen_before = p.ref.rsplit("#", 1)[1] in previous.report_ids or any(q.actor == p.actor and q.words & p.words for q in earlier)
    decisions = [p for p in policy if p.rank == 0 and not p.seen_before]

    firm = sum(1 for i in shown if i.view.evidence_status in _FIRM)
    if caveat:
        confidence = "LOW (collection was degraded)"
    elif not shown:
        confidence = "LOW (no material item identified; this describes collected sources only and is not an all-clear)"
    elif firm == len(shown):
        confidence = f"MODERATE TO HIGH (all {firm} item(s) shown officially confirmed or corroborated)"
    elif firm:
        confidence = f"MODERATE ({firm} of {len(shown)} item(s) shown officially confirmed or corroborated)"
    else:
        confidence = "LOW TO MODERATE (no item shown is officially confirmed or corroborated)"

    local = [i for i in pool if i.area in ("national", "professional")]
    open_au = [i for i in local if i.unresolved]
    unconfirmed = sum(1 for i in open_au if i.view.evidence_status not in _FIRM)
    planned = sum(1 for i in local if i.planned)
    unverified = sum(1 for i in local if i.currency_unverified)
    bluf = [f"- Material items: {len(local)} Australian, {sum(1 for i in pool if i.area == 'international')} international.",
            f"- Australian service disruptions open: {len(open_au)}" + (f" ({unconfirmed} not yet confirmed)" if unconfirmed else "")
            + (f"; {planned} announced and not yet started" if planned else "") + (f"; {unverified} reported but not verified as current" if unverified else "") + "."]
    lead = min([i for i in local if not i.is_forecast], key=lambda i: (0 if i.is_disruption else 1, _rank(i)), default=None)
    if lead:
        bluf.append(f"- Most decision-relevant: {_short_headline(lead.view.headline, 100)} ({_claim(lead).lower()}). {_decision(lead).capitalize()}.")
    else:
        bluf.append("- No Australian development met the materiality bar in collected reporting. This is not an all-clear.")
    if decisions:
        bluf.append(f"- Regulatory: {_short_headline(decisions[0].title, 100)}" + (f" (+{len(decisions) - 1} more, section 4)." if len(decisions) > 1 else "."))
    bluf.append(f"- Confidence: {confidence}.")

    professional = _morning_area(pool, "professional", pirs, "No material banking or telecommunications development identified.")
    professional += ["Regulation and policy since " + ("the previous brief:" if previous else "24 hours ago:")]
    professional += policy_lines(policy) or ["- No regulatory development identified in collected reporting."]

    if not previous:
        changes = ["- Change cannot be assessed: there is no previous morning brief to compare against."]
    else:
        changed = [i for i in pool if i.state in CHANGE_STATES]
        changes = [f"- {i.state}: {_short_headline(i.view.headline, 100)} [{i.view.incident_id}]" for i in changed[:CHANGE_LIMIT]]
        if len(changed) > CHANGE_LIMIT:
            changes.append(f"- {len(changed) - CHANGE_LIMIT} further change(s) not shown.")
        changes = changes or ["- No material change identified since the previous brief."]
    changes += ["Patterns:", *_patterns(pool), "Dependencies and concentration:", *dependency_lines(pool)]
    if retained:
        changes += ["From the standing intelligence products and theme watch:", *retained]

    gaps = [f"- Confidence: {confidence}."]
    if caveat:
        gaps.append(f"- Collection: {caveat}.")
    gaps.append(f"- {len(shown) - firm} of {len(shown)} item(s) shown rest on a single or unverified source.")
    gaps += [f"- {x}" for x in limitations or []]
    gaps.append("- Assessment lines are rule-based from headline and summary evidence; they are not analyst or model judgement and can miss "
                "connections or misread wording.")
    supporting = [f"- {len(items)} incident(s) formed from {len(events)} report(s) in {WINDOW_HOURS} h; {len(items) - len(pool)} not material or not current."]
    supporting += list(coverage or [])

    return [
        ("1. EXECUTIVE BOTTOM LINE", bluf),
        ("2. KEY INTELLIGENCE JUDGEMENTS", [("- NOT AVAILABLE. No analytical judgement capability is operating yet (planned: Milestone 3). "
                                            "Nothing in this brief is an analyst or model judgement.")]),
        ("3. NATIONAL AND SYSTEMIC RESILIENCE", _morning_area(pool, "national", pirs, "No material national development identified.")),
        ("4. PROFESSIONAL AND SECTOR INTELLIGENCE", professional),
        ("5. INTERNATIONAL LEADING INDICATORS",
         _morning_area(pool, "international", pirs, "No material international development identified in collected reporting.")),
        ("6. MATERIAL CHANGES AND EMERGING PATTERNS", changes),
        ("7. FORWARD WATCH AND MONITORING PRIORITIES", watch_lines(pool, events, now)),
        ("8. INTELLIGENCE GAPS, EVIDENCE LIMITATIONS AND CONFIDENCE", gaps),
        ("SUPPORTING DETAIL: collection", supporting),
    ]
