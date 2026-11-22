"""Staged event detection (method wk-detect/0.4.0-tiered) — offline, not wired into any live path.

Replaces title-term scoring with four stages. Every rule is deterministic; the lexicons are data, below.

  Stage 1  candidate detection   entities/sectors, event type, potential vs actual consequence, commentary
  Stage 2  incident correlation  event class + shared entities/rare content terms + time + geography; syndication
  Stage 3  materiality/evidence  actual vs potential impact (materiality) kept separate from evidence confidence
  Stage 4  decision              ESCALATE / VERIFY / WATCH / REFERENCE with provisional marking

Uncertainty handling: nothing is dropped at Stage 1 for lacking corroboration; an uncertain high-impact candidate
is kept and routed to VERIFY. Co-occurrence never implies causation (no causal edges are produced at all).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from intelligence import weekly_evidence as we

METHOD_VERSION = "wk-detect/0.4.0-tiered"

# ── Lexicons (data) ──────────────────────────────────────────────────────────────────────────────────
EVENT_TYPES = {
    "cyber_incident": (r"cyber[- ]?attacks?", r"cyber ?security (?:incident|breach|event|attack)", r"cyber incident",
                       r"data breach(?:es)?", r"breach(?:ed)?", r"hack(?:ed|ers?|ing)?", r"ransomware", r"malware",
                       r"data (?:was |were |has been )?stolen", r"stolen data", r"security incident",
                       r"compromis(?:ed|e)", r"unauthori[sz]ed access", r"data (?:likely |was )?accessed",
                       r"personal data", r"leak(?:ed|s)?", r"wiped", r"card skimmers?", r"skimmers?", r"hijacked"),
    "outage": (r"unable to (?:access|use|log ?in)", r"outages?", r"blackouts?", r"power cuts?", r"power outages?", r"without power", r"goes? down",
               r"went down", r"is down", r"offline", r"disruptions?", r"disrupted", r"ground stops?", r"grounded",
               r"flights? (?:cancell?ed|delayed)", r"shut ?down", r"system failures?", r"degraded",
               r"restor(?:e|ed|ing) services?", r"services? (?:restored|disabled|suspended)", r"portal disabled",
               r"power (?:is |still |remains? )?out", r"knock(?:s|ed|ing)? out power", r"cuts? power", r"cut power",
               r"los(?:t|e|es|ing) power", r"supply (?:is )?at risk", r"(?:power|energy|fuel) shortages?",
               r"(?:towers?|lines?|poles?|substations?) (?:\w+ )?(?:crushed|toppled?|downed|collapsed?|damaged)",
               r"(?:crushed|toppl\w+|downed|collapsed) (?:\w+ )?(?:transmission )?(?:towers?|lines?|poles?)"),
    "physical": (r"fires?", r"explosions?", r"blasts?", r"sunk", r"sinks?", r"derail\w*", r"collapse[sd]?",
                 r"(?:missile|drone|rocket) (?:strike|attack)s?", r"attacks? on"),
    "vulnerability": (r"cve-\d{4}-\d+", r"vulnerabilit(?:y|ies)", r"zero-?days?", r"known exploited",
                      r"actively exploited", r"exploited in the wild", r"security bulletins?", r"patch(?:es)?",
                      r"security advisor(?:y|ies)", r"authorization bypass", r"remote code execution"),
}
# Sectors whose disruption is a consequence in itself, with the entity words that identify them.
SECTORS = {
    "retail_food": (r"coles", r"woolworths", r"aldi", r"supermarkets?", r"grocer(?:y|ies)", r"food (?:supply|chain)",
                    r"freezers?", r"fridges?", r"refrigerat\w*", r"cold chain"),
    "health": (r"hospitals?", r"nsw health", r"sa health", r"qld health", r"health (?:system|service|network)s?",
               r"ambulance", r"medicare", r"pharmac(?:y|ies)", r"medibank", r"clinics?"),
    "telecom": (r"telstra", r"optus", r"vodafone", r"tpg", r"nbn", r"telecom\w*", r"mobile network",
                r"triple zero", r"emergency calls?", r"telco"),
    "aviation": (r"airlines?", r"airports?", r"qantas", r"virgin australia", r"jetstar", r"flights?",
                 r"air traffic", r"ground stops?", r"faa", r"grounded"),
    "energy": (r"aemo", r"power grid", r"electricity", r"blackouts?", r"power (?:cuts?|outages?)", r"without power",
               r"transmission (?:lines?|towers?)", r"ausgrid", r"electranet", r"powercor", r"energy (?:market|supply)"),
    "finance": (r"banks?", r"banking", r"financial(?: services?| firm| group)?", r"brokers?", r"brokerage", r"insurers?",
                r"superannuation", r"super funds?", r"westpac", r"anz", r"commonwealth bank", r"nab", r"payments?", r"eftpos",
                r"visa", r"mastercard", r"asx", r"apra", r"financial system"),
    "cloud_platform": (r"microsoft", r"azure", r"aws", r"amazon web services", r"google cloud", r"cloudflare",
                       r"crowdstrike", r"outlook", r"office 365", r"microsoft 365", r"m365", r"oracle cloud",
                       r"salesforce", r"github"),
    "government": (r"services australia", r"centrelink", r"mygov", r"ato", r"home affairs", r"department of"),
    "transport_water": (r"water (?:supply|treatment)", r"rail(?:way)?", r"trains?", r"ports?", r"ferry", r"toll"),
    "consumer_service": (r"booking (?:portal|service|system)s?", r"portals?", r"national parks", r"campgrounds?",
                         r"customers? (?:data|accounts?)", r"loyalty"),
}
ESSENTIAL = frozenset({"retail_food", "health", "telecom", "aviation", "energy", "finance", "cloud_platform",
                       "government", "transport_water"})
# Captain's tiered operational-relevance model. A sector NEVER escalates on its own: the tier only weights a
# stated event with a stated consequence (see decide()).
#   Tier 1 critical essential services/infrastructure; Tier 2 systemically important dependencies and supply
#   chains; Tier 3 context-dependent services (including anything with no recognised sector).
SECTOR_TIER = {"energy": 1, "telecom": 1, "health": 1, "aviation": 1, "transport_water": 1, "finance": 1,
               "cloud_platform": 2, "retail_food": 2, "government": 2, "consumer_service": 3}
CONSEQUENCE = (r"outages?", r"offline", r"(?:is|are|went|goes) down", r"disabled", r"grounded", r"ground stops?",
               r"without power", r"power (?:is |still )?out", r"unable to (?:access|use|log ?in)", r"suspend\w*", r"cancell?ed",
               r"spoil\w*", r"useless", r"knock\w* out", r"halted", r"shut ?down", r"los(?:t|e|ing) power", r"fail(?:ure|ed|s)?",
               r"sunk", r"disrupt\w+", r"wiped", r"taken offline", r"blackouts?")
DATA_EXPOSURE = (r"data (?:was |were |has been )?(?:stolen|exposed|leaked|accessed)", r"(?:stolen|leaked|exposed) (?:data|details)",
                 r"breach(?:es)? (?:affects?|exposes?|hits?)", r"personal data", r"customer (?:data|details)",
                 r"client data", r"card details", r"\d{2,3},\d{3}\s+(?:clients|customers|users|people)")
RETROSPECTIVE = (r"complaints?", r"compensation", r"claims?", r"agm", r"inquiry", r"review", r"restored", r"resolved",
                 r"apolog\w+", r"lessons?", r"anniversary", r"fallout")
ONGOING = (r"continues?", r"still", r"ongoing", r"remains?", r"races? to", r"live:")
SCALE = (r"nation(?:wide|al)", r"global(?:ly)?", r"worldwide", r"widespread", r"millions?", r"major incident",
         r"in (?:three|four|five|\d+) states", r"across (?:the )?(?:country|australia|us|world)", r"hundreds of",
         r"billions?", r"almost 24 hours")
ACTUAL = (r"hit by", r"disabled", r"stolen", r"(?:is|are|went|goes) down", r"outages?", r"grounded", r"ground stop",
          r"declared", r"wiped", r"knocked out", r"races? to (?:restore|fix)", r"apologis\w+", r"(?:deeply )?sorry",
          r"suffering", r"hacked", r"breached", r"confirmed", r"investigat\w+", r"affected", r"impacted",
          r"without power", r"offline", r"taken offline", r"useless", r"disrupt\w+", r"restor\w+")
POTENTIAL = (r"warns?", r"could", r"risk", r"threat", r"may ", r"might", r"fears?", r"experts? say", r"just the start",
             r"at risk", r"vulnerab\w+", r"potential")
COMMENTARY = (r"exposes? (?:global )?reliance", r"under scrutiny", r"opinion", r"analysis[:,]", r"what we know",
              r"lessons?", r"why ", r"how .* (?:could|might)", r"just the start", r"puts? .* (?:under|at risk)",
              r"reliance on", r"explainer", r"fallout")
# A single named-feed suffix marks a syndicated copy of that wire/outlet's story.
_SYNDICATION_SUFFIX = re.compile(r"\s[-–]\s(reuters|ap news|aap|bloomberg|afp)\s*$", re.IGNORECASE)

_WORDS = re.compile(r"[a-z0-9][a-z0-9'\-]+")
_STOP = frozenset(["the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "with", "after", "as", "at", "by", "from", "is", "are", "was", "were", "be", "been", "it", "its", "this", "that", "into", "over", "amid", "about", "says", "said", "say", "new", "breaking", "live", "how", "why", "what", "who", "will", "can", "could", "may", "might", "not", "no", "more", "most", "than", "their", "they", "them", "his", "her", "he", "she", "we", "you", "our", "your", "up", "out", "off", "per", "vs", "via", "also", "still", "just", "now", "today", "week", "day", "year"])


def _rx(terms) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(terms) + r")(?![a-z0-9])", re.IGNORECASE)


_TYPE_RX = {k: _rx(v) for k, v in EVENT_TYPES.items()}
_SECTOR_RX = {k: _rx(v) for k, v in SECTORS.items()}
_CONSEQ_RX, _EXPOSE_RX, _RETRO_RX, _ONGOING_RX = _rx(CONSEQUENCE), _rx(DATA_EXPOSURE), _rx(RETROSPECTIVE), _rx(ONGOING)
_SCALE_RX, _ACTUAL_RX, _POTENTIAL_RX, _COMM_RX = _rx(SCALE), _rx(ACTUAL), _rx(POTENTIAL), _rx(COMMENTARY)
_COMPROMISE_RX = re.compile(r"(?<![a-z])(?:hijacked|hacked|breached|ransomware|stolen|skimmers?|compromised|wiped|malware)(?![a-z])", re.IGNORECASE)
_PROPER = re.compile(r"\b([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,})*)\b")
_PROPER_STOP = frozenset({"breaking", "live", "the", "australia", "australian", "government", "minister", "morning",
                          "why", "how", "what", "who", "nationwide", "monday", "tuesday", "wednesday", "thursday",
                          "friday", "saturday", "sunday"})


# ── Stage 1: candidate detection ─────────────────────────────────────────────────────────────────────────
@dataclass
class Candidate:
    event_id: str
    title: str
    source: str
    published: datetime | None
    geography: str
    types: tuple[str, ...]
    sectors: tuple[str, ...]
    orgs: frozenset
    scale: bool
    compromise: bool
    actual: bool
    potential: bool
    commentary: bool
    is_candidate: bool
    consequence: str          # essential_service | broad_user_impact | unknown | none
    family: str
    kind: str
    tier: int | None = None   # 1/2/3 from the sectors found; None = no recognised sector
    status: str = "none"      # confirmed | unconfirmed | retrospective | potential | none (impact status)
    exposure: bool = False    # a data-exposure consequence is stated
    legacy: dict = field(default_factory=dict)

    @property
    def primary_type(self) -> str:
        for t in ("cyber_incident", "outage", "physical", "vulnerability"):
            if t in self.types:
                return t
        return "other"


_ORG_LEX = _rx((r"coles", r"woolworths", r"aldi", r"medibank", r"telstra", r"optus", r"vodafone", r"tpg", r"nbn",
                r"qantas", r"jetstar", r"virgin australia", r"westpac", r"anz", r"commonwealth bank", r"nab",
                r"microsoft", r"azure", r"aws", r"amazon web services", r"google cloud", r"cloudflare", r"crowdstrike",
                r"oracle", r"salesforce", r"github", r"aemo", r"ausgrid", r"electranet", r"nsw health", r"sa health",
                r"services australia", r"national parks"))
_PUBLISHER_SUFFIX = re.compile(r"\s[-–|]\s[^-–|]{2,60}$")


def core_title(title: str) -> str:
    """Title without a trailing ' - Publisher' feed suffix (aggregators append the outlet name)."""
    return _PUBLISHER_SUFFIX.sub("", title or "").strip()


def _orgs(title: str) -> frozenset:
    t = core_title(title)
    first, _, rest = t.partition(" ")
    t = rest if first[:1].isupper() else t              # a sentence-initial word is capitalised by position, not as a name
    found = {m.group(1).lower() for m in _PROPER.finditer(t)} | {m.group(0).lower() for m in _ORG_LEX.finditer(core_title(title))}
    return frozenset(o for o in found if o not in _PROPER_STOP and len(o) > 2)


def detect_candidate(event: dict) -> Candidate:
    title = event.get("title") or ""
    text = f"{title} {event.get('summary') or ''}"
    types = tuple(k for k, rx in _TYPE_RX.items() if rx.search(text))
    sectors = tuple(k for k, rx in _SECTOR_RX.items() if rx.search(text))
    scale = bool(_SCALE_RX.search(text))
    actual = bool(_ACTUAL_RX.search(text))
    potential = bool(_POTENTIAL_RX.search(text))
    # A multi-topic roundup headline ("A, B, C") reports no single incident, so it can never carry one.
    roundup = len([seg for seg in title.split(",") if len(seg.split()) >= 2]) >= 3
    commentary = bool(_COMM_RX.search(text)) or we.is_commentary(title) or roundup
    essential = any(s in ESSENTIAL for s in sectors)
    # Recall-oriented: any disruption/cyber/vulnerability type plus a sector OR a scale cue. A bare cyber mention with no
    # sector and no scale is NOT a candidate (otherwise every security-vendor press release would be).
    compromise = bool(_COMPROMISE_RX.search(text))      # a stated compromise needs no sector to be worth verifying
    conseq = bool(_CONSEQ_RX.search(text))
    exposure = bool(_EXPOSE_RX.search(text))
    is_cand = bool(types or exposure) and (bool(sectors) or scale or compromise or conseq or exposure
                                           or ("vulnerability" in types and we.exploited(text)))
    consequence = ("essential_service" if essential else "broad_user_impact" if sectors
                   else "unknown" if (types and scale) else "none")
    tier = min((SECTOR_TIER[x] for x in sectors if x in SECTOR_TIER), default=None)
    retro = bool(_RETRO_RX.search(text)) and not _ONGOING_RX.search(text)
    if commentary or not is_cand:
        status = "potential" if (commentary and is_cand) else "none"
    elif retro:
        status = "retrospective"
    elif conseq or exposure:
        status = "confirmed"
    else:
        status = "unconfirmed"
    src = event.get("source") or ""
    return Candidate(
        event_id=str(event.get("id")), title=title, source=src, published=we._parse_ts(event.get("collected_at")),
        geography=event.get("geography") or "", types=types, sectors=sectors, orgs=_orgs(title), scale=scale, compromise=compromise,
        actual=actual, potential=potential, commentary=commentary, is_candidate=is_cand, consequence=consequence,
        tier=tier, status=status, exposure=exposure,
        family=we.publisher_family(src, title), kind=we.source_kind(src), legacy=event.get("legacy") or {})


# ── Stage 2: incident correlation ──────────────────────────────────────────────────────────────────────────
_WINDOW = {"outage": timedelta(hours=72), "cyber_incident": timedelta(days=7), "vulnerability": timedelta(days=3),
           "other": timedelta(hours=48)}


def _content_stems(title: str) -> frozenset:
    return frozenset(we._stem(w) for w in _WORDS.findall(core_title(title).lower()) if w not in _STOP and len(w) > 2)


@dataclass
class Group:
    incident_id: str
    members: list[Candidate]
    pairs: list[tuple[str, str, float, str]]      # (id_a, id_b, confidence, reason) — why members were joined
    grouping_confidence: float
    independent_publishers: int
    syndicated_ids: list[str]
    commentary_ids: list[str]


def _idf(cands: list[Candidate]) -> dict[str, float]:
    df = Counter()
    for c in cands:
        df.update(_content_stems(c.title))
    n = max(1, len(cands))
    return {s: math.log((n + 1) / (d + 0.5)) for s, d in df.items()}


def _link(a: Candidate, b: Candidate, idf: dict[str, float]) -> tuple[float, str] | None:
    """Confidence (0-1) that two candidates report ONE incident, with the reason; None if they do not."""
    if not (a.is_candidate and b.is_candidate):
        return None
    shared_types = set(a.types) & set(b.types)
    if not shared_types:
        return None
    cls = "outage" if "outage" in shared_types else "cyber_incident" if "cyber_incident" in shared_types else "vulnerability"
    if a.published and b.published and abs(a.published - b.published) > _WINDOW[cls]:
        return None
    if cls == "vulnerability":
        return None            # advisories are grouped by CVE/product, never by prose similarity
    shared_orgs = (a.orgs & b.orgs) - {"australia", "microsoft"} | ((a.orgs & b.orgs) & {"microsoft"})
    shared_sectors = set(a.sectors) & set(b.sectors)
    shared = _content_stems(a.title) & _content_stems(b.title)
    rare = sum(1 for s in shared if idf.get(s, 0) >= 2.0)
    score, reasons = 0.0, []
    if shared_orgs:
        score += 0.5
        reasons.append("named entity " + "/".join(sorted(shared_orgs)))
    if shared_sectors & ESSENTIAL or shared_sectors:
        score += 0.2
        reasons.append("sector " + "/".join(sorted(shared_sectors)))
    if rare:
        score += min(0.3, 0.15 * rare)
        reasons.append(f"{rare} rare shared term(s)")
    if a.geography and b.geography and a.geography != b.geography and {a.geography, b.geography} != {"GLOBAL", "AU"} \
            and "GLOBAL" not in (a.geography, b.geography):
        score -= 0.2
    # distinct-incident guard: same organisation but disjoint specific services/locations -> separate incidents
    if shared_orgs and _service_conflict(a, b):
        return None
    if score >= 0.6 or (score >= 0.5 and (shared_orgs or rare >= 2)):
        return round(min(1.0, score), 2), "; ".join(reasons) + f"; class {cls}"
    return None


_SERVICE_RX = re.compile(r"\b(outlook|teams|azure|aws|gmail|sharepoint|onedrive|exchange|office|xbox|github|"
                         r"mobile|broadband|nbn|triple zero|payments?|app|website|portal)\b", re.IGNORECASE)


def _service_conflict(a: Candidate, b: Candidate) -> bool:
    sa = {m.lower() for m in _SERVICE_RX.findall(a.title)}
    sb = {m.lower() for m in _SERVICE_RX.findall(b.title)}
    return bool(sa and sb and not (sa & sb))


def correlate(cands: list[Candidate]) -> list[Group]:
    """Agglomerate by descending link confidence with average linkage: two clusters merge only if at least half of the
    cross pairs of non-commentary members are linked and every member is tied to the other cluster, so one chance
    pairing cannot chain unrelated incidents together. Commentary
    attaches to a cluster through any single link and never bridges two clusters."""
    idf = _idf(cands)
    pairs: dict[tuple[int, int], tuple[float, str]] = {}
    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            link = _link(cands[i], cands[j], idf)
            if link:
                pairs[(i, j)] = link

    def linked(i, j):
        return (min(i, j), max(i, j)) in pairs
    clusters: list[list[int]] = [[i] for i in range(len(cands))]
    where = {i: i for i in range(len(cands))}
    for (i, j), _ in sorted(pairs.items(), key=lambda kv: -kv[1][0]):
        a, b = where[i], where[j]
        if a == b:
            continue
        ca, cb = clusters[a], clusters[b]
        if cands[i].commentary and cands[j].commentary:
            continue                                   # commentary never bridges to other commentary
        core_a = [m for m in ca if not cands[m].commentary]
        core_b = [m for m in cb if not cands[m].commentary]
        if core_a and core_b:
            cross = [(x, y) for x in core_a for y in core_b]
            coverage = sum(linked(x, y) for x, y in cross) / len(cross)
            every_member_tied = all(any(linked(x, y) for y in core_b) for x in core_a) and \
                all(any(linked(x, y) for x in core_a) for y in core_b)
            if coverage < 0.5 or not every_member_tied:
                continue                               # average linkage: stops one chance pair chaining incidents
        if (not core_a and len(ca) > 1) or (not core_b and len(cb) > 1):
            continue                                   # a commentary-only cluster does not absorb others
        clusters[a] = ca + cb
        clusters[b] = []
        for m in cb:
            where[m] = a
    buckets = {k: v for k, v in enumerate(clusters) if v}
    groups: list[Group] = []
    for n, idxs in enumerate(sorted(buckets.values(), key=lambda v: v[0])):
        members = [cands[i] for i in idxs]
        plist = [(cands[i].event_id, cands[j].event_id, *pairs[(i, j)]) for (i, j) in pairs if i in idxs and j in idxs]
        conf = round(min((p[2] for p in plist), default=1.0), 2)
        gid = "inc-" + "-".join(sorted(m.event_id for m in members))[:40]
        synd, seen = [], {}
        for m in members:
            key = _content_stems(m.title)
            for ks in seen.values():
                if ks and len(key & ks) / max(1, len(key | ks)) >= 0.8:
                    synd.append(m.event_id)
                    break
            seen[m.event_id] = key
            if _SYNDICATION_SUFFIX.search(m.title):
                synd.append(m.event_id)
        original = [m for m in members if not m.commentary and m.event_id not in synd]
        fams = {m.family for m in original if m.kind != we.AGGREGATOR or m.family != "aggregator"}
        groups.append(Group(gid, members, plist, conf, len(fams), sorted(set(synd)),
                            [m.event_id for m in members if m.commentary]))
    return groups


# ── Stage 3 + 4: operational materiality, evidence confidence, urgency, decision ─────────────────────────────
@dataclass
class Decision:
    """Six separate axes: sector relevance (tier), event type, impact status, operational materiality,
    evidence confidence and action urgency; the priority is derived from them by the rules in decide()."""
    group: Group
    headline: Candidate
    sector_tier: int | None   # 1 critical services | 2 systemic dependencies/supply chains | 3 context-dependent | None
    event_type: str
    impact_status: str        # confirmed | unconfirmed | retrospective | potential | none
    materiality: str          # high | medium | low (operational, not sector)
    evidence_confidence: float
    urgency: str              # immediate | soon | routine
    priority: str             # ESCALATE | VERIFY | WATCH | REFERENCE
    provisional: bool
    reasons: list[str]
    method_version: str = METHOD_VERSION


_STATUS_ORDER = {"confirmed": 4, "unconfirmed": 3, "retrospective": 2, "potential": 1, "none": 0}


def _materiality(c: Candidate) -> str:
    """Operational materiality from the STATED consequence, never from the sector alone."""
    if not c.is_candidate or c.status in ("none", "potential"):
        return "low"
    tier = c.tier or 3
    if c.status == "confirmed":
        if tier == 1 or (tier == 2 and c.scale) or (c.scale and c.exposure):
            return "high"
        return "medium"
    if c.status == "retrospective":
        return "medium" if tier == 1 else "low"
    return "medium" if tier == 1 else "low"       # unconfirmed: a Tier 1 candidate is worth a look, others are not


def decide(group: Group, *, now: datetime | None = None) -> Decision:
    originals = [m for m in group.members if not m.commentary] or group.members
    head = max(originals, key=lambda c: (_STATUS_ORDER[c.status], -(c.tier or 3), c.kind == we.PRIMARY,
                                         c.published or datetime.min.replace(tzinfo=timezone.utc)))
    status = max((c.status for c in originals), key=_STATUS_ORDER.get)
    mat = max((_materiality(c) for c in originals), key={"high": 2, "medium": 1, "low": 0}.get)
    kinds = {c.kind for c in originals}
    primary = we.PRIMARY in kinds
    flags: list[str] = []
    conf = we.confidence(we.PRIMARY if primary else (we.MAINSTREAM if we.MAINSTREAM in kinds else head.kind),
                         group.independent_publishers, flags)
    solid = bool(primary or kinds & {we.MAINSTREAM, we.SPECIALIST} or group.independent_publishers >= 2)
    provisional = group.independent_publishers < 2 and not primary
    tier = head.tier
    reasons = [f"tier={tier}", f"type={head.primary_type}", f"status={status}", f"materiality={mat}",
               f"evidence confidence {conf}", f"{group.independent_publishers} independent publisher(s)"]

    def out(pr, urgency, prov=False):
        return Decision(group, head, tier, head.primary_type, status, mat, conf, urgency, pr, prov, reasons)

    if head.primary_type == "vulnerability":
        exploited_, exposed = we.exploited(head.title), we.known_exposure(head.title)
        mat = "high" if (exploited_ and exposed) else "medium" if exploited_ else "low"
        reasons.append(f"advisory: exploited={exploited_} known_exposure={exposed} (KEV alone is not critical)")
        if exploited_ and exposed and primary:
            return out("ESCALATE", "immediate")
        return out("WATCH" if exploited_ or "critical" in head.title.lower() else "REFERENCE", "soon" if exploited_ else "routine")
    if mat == "high":
        if solid:
            if provisional:
                reasons.append("single credible report: provisional, follow-up verification required")
            return out("ESCALATE", "immediate", provisional)
        reasons.append("high operational materiality but weak evidence: verify before acting")
        return out("VERIFY", "soon")
    if status == "unconfirmed" and head.is_candidate and (tier in (1, 2) or head.compromise):
        # Unconfirmed incident without a demonstrated operational consequence: VERIFY, unless it is a Tier 1 incident
        # that a credible source describes as major/widespread (severe potential consequences -> provisional escalation).
        if tier == 1 and head.scale and solid:
            reasons.append("severe potential consequence, credible single source: provisional escalation")
            return out("ESCALATE", "immediate", True)
        return out("VERIFY", "soon")
    if mat == "medium":
        return out("WATCH" if solid else "VERIFY", "soon")
    if status == "confirmed" and head.is_candidate:
        return out("WATCH" if solid else "REFERENCE", "routine")
    return out("REFERENCE", "routine")


def run(events: list[dict], *, now: datetime | None = None) -> list[Decision]:
    cands = [detect_candidate(e) for e in events]
    return [decide(g, now=now) for g in correlate(cands)]
