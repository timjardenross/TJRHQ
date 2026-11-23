"""Staged event detection (method wk-detect/0.5.0-tiered-v2) — offline, not wired into any live path.

Replaces title-term scoring with four stages. Every rule is deterministic; the lexicons are data, below.

  Stage 1  candidate detection   entities/sectors, event type, potential vs actual consequence, commentary
  Stage 2  incident correlation  event class + shared entities/rare content terms + time + geography; syndication
  Stage 3  materiality/evidence  actual vs potential impact (materiality) kept separate from evidence confidence
  Stage 4  decision              ESCALATE / VERIFY / WATCH / REFERENCE with provisional marking

Uncertainty handling: nothing is dropped at Stage 1 for lacking corroboration; an uncertain high-impact candidate
is kept and routed to VERIFY. Co-occurrence never implies causation (no causal edges are produced at all).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from intelligence import weekly_evidence as we

METHOD_VERSION = "wk-detect/0.5.0-tiered-v2"

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
                       r"salesforce", r"github", r"google", r"amazon", r"apple", r"okta", r"atlassian", r"zoom", r"slack"),
    "government": (r"services australia", r"centrelink", r"mygov", r"ato", r"home affairs", r"department of"),
    "emergency_services": (r"emergency services?", r"police", r"fire (?:brigade|service|rescue)s?", r"ambulance",
                           r"triple zero", r"(?<![\d,.])000(?![\d,])", r"state emergency service", r"ses"),
    "transport_water": (r"water (?:supply|treatment)", r"rail(?:way)?", r"trains?", r"ports?", r"ferry", r"toll"),
    "consumer_service": (r"tourism", r"resorts?", r"hotels?", r"theme parks?", r"cinemas?", r"holiday parks?", r"gyms?",
                         r"booking (?:portal|service|system)s?", r"portals?", r"national parks", r"campgrounds?",
                         r"customers? (?:data|accounts?)", r"loyalty"),
}
ESSENTIAL = frozenset({"emergency_services", "retail_food", "health", "telecom", "aviation", "energy", "finance", "cloud_platform",
                       "government", "transport_water"})
# Captain's tiered operational-relevance model. A sector NEVER escalates on its own: the tier only weights a
# stated event with a stated consequence (see decide()).
#   Tier 1 critical essential services/infrastructure; Tier 2 systemically important dependencies and supply
#   chains; Tier 3 context-dependent services (including anything with no recognised sector).
SECTOR_TIER = {"emergency_services": 1, "energy": 1, "telecom": 1, "health": 1, "aviation": 1, "transport_water": 1, "finance": 1,
               "cloud_platform": 2, "retail_food": 2, "government": 2, "consumer_service": 3}
CONSEQUENCE = (r"outages?", r"offline", r"(?:is|are|went|goes) down", r"disabled", r"grounded", r"ground stops?",
               r"without power", r"power (?:is |still )?out", r"unable to (?:access|use|log ?in)", r"suspend\w*", r"cancell?ed",
               r"spoil\w*", r"useless", r"knock\w* out", r"halted", r"shut ?down", r"los(?:t|e|ing) power", r"fail(?:ure|ed|s)?",
               r"sunk", r"disrupt\w+", r"wiped", r"taken offline", r"blackouts?")
DATA_EXPOSURE = (r"data (?:was |were |has been )?(?:stolen|exposed|leaked|accessed)", r"(?:stolen|leaked|exposed) (?:data|details)",
                 r"breach(?:es)? (?:affects?|exposes?|hits?)", r"personal data", r"customer (?:data|details)",
                 r"client data", r"card details", r"\d{2,3},\d{3}\s+(?:clients|customers|users|people)")
SAFETY = (r"injur\w+", r"deaths?", r"killed", r"fatal\w*", r"evacuat\w+", r"hospitali[sz]ed", r"casualt\w+", r"trapped")
CASCADING = (r"cascad\w+", r"knock-?on", r"flow-?on", r"across (?:multiple|several) (?:sectors|services|industries)")
MINOR = (r"\w+-minute", r"minutes?", r"brief(?:ly)?", r"some customers", r"partial(?:ly)?", r"limited", r"intermittent", r"isolated")
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
_SAFETY_RX, _CASCADE_RX, _MINOR_RX = _rx(SAFETY), _rx(CASCADING), _rx(MINOR)
_CUSTOMERS_RX = re.compile(r"(\d{1,3}(?:,\d{3})+|\d{3,})\s+(?:\w+\s+){0,2}(?:customers|homes|households|properties|residents|people|users|clients)", re.IGNORECASE)
_DURATION_RX = re.compile(r"(\d+|a|an|one|two|three|four|five|six|several)[- ](minutes?|hours?|days?)", re.IGNORECASE)
_RESTORED_RX = _rx((r"restored", r"resolved", r"back online", r"power is back", r"services? resumed"))
# Proportionality (Captain, 2026-11-23): customer count is NOT a universal threshold. For Tier 1 network services (energy,
# telecom, water) an ONGOING confirmed outage of at least this many customers is high materiality even when described as regional.
ONGOING_NETWORK_OUTAGE_CUSTOMERS = 10_000
_NETWORK_SECTORS = frozenset({"energy", "telecom", "transport_water", "emergency_services"})
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
    safety: bool = False      # a safety consequence (injury, death, evacuation) is stated
    cascading: bool = False   # cascading / knock-on impact is stated
    minor: bool = False       # the disruption is described as brief/partial/limited
    customers: int | None = None   # affected customers stated in the headline
    ongoing: bool = False     # still in progress (not stated as restored/resolved)
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
    roundup = len([seg for seg in re.split(r",(?!\d{3})", title) if len(seg.split()) >= 2]) >= 3   # not the comma in 20,000
    commentary = bool(_COMM_RX.search(text)) or we.is_commentary(title) or roundup
    essential = any(s in ESSENTIAL for s in sectors)
    # Recall-oriented: any disruption/cyber/vulnerability type plus a sector OR a scale cue. A bare cyber mention with no
    # sector and no scale is NOT a candidate (otherwise every security-vendor press release would be).
    compromise = bool(_COMPROMISE_RX.search(text))      # a stated compromise needs no sector to be worth verifying
    conseq = bool(_CONSEQ_RX.search(text))
    exposure = bool(_EXPOSE_RX.search(text))
    safety = bool(_SAFETY_RX.search(text))
    cascading = bool(_CASCADE_RX.search(text))
    minor = bool(_MINOR_RX.search(text))
    cm = _CUSTOMERS_RX.search(text)
    customers = int(cm.group(1).replace(",", "")) if cm else None
    ongoing = bool(_ONGOING_RX.search(text)) or (not _RESTORED_RX.search(text) and not _RETRO_RX.search(text))
    is_cand = bool(types or exposure) and (bool(sectors) or scale or compromise or conseq or exposure or safety
                                           or ("vulnerability" in types and we.exploited(text)))
    consequence = ("essential_service" if essential else "broad_user_impact" if sectors
                   else "unknown" if (types and scale) else "none")
    tier = min((SECTOR_TIER[x] for x in sectors if x in SECTOR_TIER), default=None)
    retro = bool(_RETRO_RX.search(text)) and not _ONGOING_RX.search(text)
    if commentary or not is_cand:
        status = "potential" if (commentary and is_cand) else "none"
    elif retro:
        status = "retrospective"
    elif conseq or exposure or safety:
        status = "confirmed"
    else:
        status = "unconfirmed"
    src = event.get("source") or ""
    return Candidate(
        event_id=str(event.get("id")), title=title, source=src, published=we._parse_ts(event.get("collected_at")),
        geography=event.get("geography") or "", types=types, sectors=sectors, orgs=_orgs(title), scale=scale, compromise=compromise,
        actual=actual, potential=potential, commentary=commentary, is_candidate=is_cand, consequence=consequence,
        tier=tier, status=status, exposure=exposure, safety=safety, cascading=cascading, minor=minor, customers=customers, ongoing=ongoing,
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
    """Rarity score per stem. A stem is rare when it appears in at most max(2, 5% of the pool) headlines, so a pair of reports is
    judged the same way whether the pool holds 5 events or 5,000 (a log-IDF cut-off would call everything common in a small pool)."""
    df = Counter()
    for c in cands:
        df.update(_content_stems(c.title))
    limit = max(2, int(0.05 * len(cands)))
    return {s: (3.0 if d <= limit else 0.0) for s, d in df.items()}


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
    """Operational materiality from the STATED consequence (rubric v2): severe disruption, major safety consequence,
    essential-service interruption or cascading impact. A tier never sets materiality by itself."""
    if not c.is_candidate or c.status in ("none", "potential"):
        return "low"
    tier = c.tier or 3
    if c.status == "confirmed":
        if c.safety or c.cascading:
            return "high"
        if (c.ongoing and c.customers and c.customers >= ONGOING_NETWORK_OUTAGE_CUSTOMERS
                and "outage" in c.types and set(c.sectors) & _NETWORK_SECTORS):
            return "high"                      # significant active network outage; proportionality, not a universal threshold
        if c.minor:
            return "medium"                    # brief / partial / regional disruption is not severe on its own
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
        # An unconfirmed incident with no stated operational consequence is VERIFY, whatever the sector or tier.
        return out("VERIFY", "soon")
    if mat == "medium":
        return out("WATCH" if solid else "VERIFY", "soon")
    if status == "confirmed" and head.is_candidate:
        return out("WATCH" if solid else "REFERENCE", "routine")
    return out("REFERENCE", "routine")


def run(events: list[dict], *, now: datetime | None = None) -> list[Decision]:
    cands = [detect_candidate(e) for e in events]
    return [decide(g, now=now) for g in correlate(cands)]


_VERIFY_NEXT = {
    "outage": "confirm the customer count, affected area and restoration estimate with the network operator or regulator (primary source)",
    "cyber_incident": "obtain the organisation's own statement or the regulator's notice confirming what was affected",
    "physical": "confirm casualties, damage and service impact with the responsible authority",
    "vulnerability": "check the vendor advisory and whether affected products are in our estate",
}


def escalation_record(d: Decision) -> dict:
    """The facts the Captain needs beside every ESCALATE/VERIFY item: what is confirmed vs merely reported, scale, duration and
    restoration, critical-service dependencies, geography, source confidence and the next verification action. Recomputed whenever the
    incident gains reports, so the classification is reassessed on new evidence."""
    originals = [m for m in d.group.members if not m.commentary] or d.group.members
    h = d.headline
    counts = [m.customers for m in originals if m.customers]
    text = " ".join(m.title for m in originals)
    dur = _DURATION_RX.search(text)
    if any(_RESTORED_RX.search(m.title) for m in originals) and not any(_ONGOING_RX.search(m.title) for m in originals):
        restoration = "restored"
    elif any(m.ongoing and m.status == "confirmed" for m in originals):
        restoration = "ongoing"
    else:
        restoration = "unknown"
    return {
        "impact": "confirmed" if d.impact_status == "confirmed" else "reported" if d.impact_status in ("unconfirmed", "retrospective") else d.impact_status,
        "affected_customers": max(counts) if counts else None,
        "duration": dur.group(0) if dur else None,
        "restoration_status": restoration,
        "critical_service_dependencies": sorted({x for m in originals for x in m.sectors}),
        "sector_tier": d.sector_tier,
        "geographic_scope": sorted({m.geography for m in originals if m.geography}),
        "source_confidence": {"evidence_confidence": d.evidence_confidence, "independent_publishers": d.group.independent_publishers,
                              "source_kinds": sorted({m.kind for m in originals}), "provisional": d.provisional},
        "next_verification_action": _VERIFY_NEXT.get(h.primary_type, "confirm with an official source"),
        "report_ids": [m.event_id for m in d.group.members],
        "reassess": "re-run when new reports arrive; customer count is a proportionality input, not a universal threshold",
    }
