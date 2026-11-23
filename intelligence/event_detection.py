"""Staged event detection (method wk-detect/0.5.1-v1) — offline, not wired into any live path.

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

METHOD_VERSION = "wk-detect/0.6.0-v1c"

# ── Lexicons (data) ──────────────────────────────────────────────────────────────────────────────────
EVENT_TYPES = {
    "cyber_incident": (r"cyber[- ]?attacks?", r"cyber ?security (?:incident|breach|event|attack)", r"cyber incident",
                       r"data breach(?:es)?", r"breach(?:ed)?", r"hack(?:ed|ers?|ing)?", r"ransomware", r"malware",
                       r"data (?:was |were |has been )?stolen", r"stolen data", r"security incident",
                       r"compromis(?:ed|e)", r"unauthori[sz]ed access", r"data (?:likely |was )?accessed",
                       r"personal data", r"leak(?:ed|s)?", r"wiped", r"card skimmers?", r"skimmers?", r"hijacked"),
    "outage": (r"unable to (?:access|use|log ?in)", r"outages?", r"blackouts?", r"power cuts?", r"power outages?", r"without power", r"goes? down",
               r"went down", r"is down", r"offline", r"disruptions?", r"disrupted", r"ground stops?", r"grounded",
               r"flights? (?:cancell?ed|delayed)", r"shut ?down", r"(?:system|network|service|power) failures?", r"degraded",
               r"restor(?:e|ed|ing) services?", r"services? (?:restored|disabled|suspended)", r"portal disabled",
               r"power (?:is |still |remains? )?out", r"knock(?:s|ed|ing)? out power", r"cuts? power", r"cut power",
               r"los(?:t|e|es|ing) power", r"supply (?:is )?at risk", r"(?:power|energy|fuel) shortages?",
               r"(?:towers?|lines?|poles?|substations?) (?:\w+ )?(?:crushed|toppled?|downed|collapsed?|damaged)",
               r"(?:crushed|toppl\w+|downed|collapsed) (?:\w+ )?(?:transmission )?(?:towers?|lines?|poles?)"),
    "hazard": (r"earthquakes?", r"tsunamis?", r"cyclones?", r"bushfires?", r"fire warnings?", r"emergency warnings?", r"flash flood\w*", r"(?:major|severe|moderate) flood(?:ing)?", r"flood (?:warnings?|emergency|evacuation\w*)",
               r"hail(?:storm)?", r"severe (?:thunder)?storms?", r"(?:severe|extreme|catastrophic) heatwaves?", r"heatwave warnings?", r"tornado(?:es)?", r"tremors?", r"storm warnings?",
               r"evacuation (?:order|warning)s?", r"damaging winds?"),
    "supply_shortfall": (r"lack of reserve", r"lor[123]", r"reserve shortfalls?", r"supply (?:gap|shortfall)s?", r"(?:power|energy|gas|fuel) shortages?",
                         r"load shedding", r"grid (?:emergency|strain)"),
    "water_quality": (r"contaminat\w+", r"boil[- ]water", r"do not drink", r"unsafe to drink", r"above (?:health |safety )?guidelines",
                      r"water quality", r"e\.? coli"),
    "service_disruption": (r"ambulance (?:delays?|ramping|shortages?)", r"waiting for an ambulance", r"hospital (?:bypass|diversion)",
                           r"ambulances? unavailable", r"tech(?:nology)? failure"),
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
    "transport_water": (r"water (?:supply|treatment)", r"(?:tap|drinking) water", r"water quality", r"rail(?:way)?", r"trains?", r"ports?", r"ferry", r"toll"),
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
               r"spoil\w*", r"useless", r"knock\w* out", r"halted", r"shut ?down", r"los(?:t|e|ing) power", r"(?:power|grid|network|service|system|payment|platform|cloud|server)s? (?:\w+ )?fail\w*",
               r"(?:system|network|service|power) failures?", r"sunk", r"disrupt\w+", r"wiped", r"taken offline", r"blackouts?")
DATA_EXPOSURE = (r"data (?:was |were |has been )?(?:stolen|exposed|leaked|accessed)", r"(?:stolen|leaked|exposed) (?:data|details)",
                 r"breach(?:es)? (?:affects?|exposes?|hits?)", r"personal data", r"customer (?:data|details)",
                 r"client data", r"card details", r"\d{2,3},\d{3}\s+(?:clients|customers|users|people)")
SAFETY = (r"injur\w+", r"deaths?", r"killed", r"fatal\w*", r"evacuat\w+", r"hospitali[sz]ed", r"casualt\w+", r"trapped")
CASCADING = (r"cascad\w+", r"knock-?on", r"flow-?on", r"across (?:multiple|several) (?:sectors|services|industries)")
MINOR = (r"\w+-minute", r"minutes?", r"brief(?:ly)?", r"some customers", r"partial(?:ly)?", r"limited", r"intermittent", r"isolated")
RETROSPECTIVE = (r"investigated", r"post-(?:blackout|outage|incident)", r"convicted", r"charged", r"sentenced", r"jailed", r"guilty", r"trial", r"verdict", r"inquest", r"court", r"fined",
                 r"complaints?", r"compensation", r"claims?", r"agm", r"inquiry", r"review", r"restored", r"resolved",
                 r"apolog\w+", r"lessons?", r"anniversary", r"fallout",
                 r"near[- ]miss(?:es)?", r"post-?mortems?",
                 # a root cause that HAS BEEN found is retrospective; 'engineers investigate root cause' is a live incident
                 r"root[- ]cause\b[^.;]{0,40}\b(?:identified|found|revealed|confirmed|analysis|report)",
                 r"(?:identified|found|reveals?|revealed|confirmed|confirms)\b[^.;]{0,40}\broot[- ]cause")        # #669: commentary and analysis about a PAST event
HEDGE = (r"likely", r"may have", r"might have", r"possibly", r"suspected", r"reportedly", r"apparent", r"alleged\w*", r"believed to")
POLITICS = (r"liberal", r"labor", r"coalition", r"opposition", r"minister", r"premier", r"election", r"policy", r"parliament",
            r"senator", r"prime minister", r"government plan", r"throws open")
WARNING = (r"warnings?", r"alerts?", r"watch", r"advis(?:ory|ed)", r"issued", r"expected", r"possible", r"could")
FORECAST = (r"forecast", r"lor[123]", r"scheduled", r"planned", r"projected", r"outlook")
CANCELLED = (r"cancell?ation of", r"cancell?ed:", r"reclassification of", r"ceased operating", r"resolved")
CONFLICT = (r"troops?", r"military", r"missiles?", r"drones?", r"air ?strikes?", r"\bwar\b", r"rebels?", r"shelling", r"invasion",
            r"insurgents?", r"strikes on", r"killed in", r"blast after", r"projectile")
ROUTINE_CAUSE = (r"due to (?:the )?(?:weather|fog|wind|storms?|bad weather|weather conditions)", r"weather (?:conditions|delays?)")
ANON_SOURCE = (r"(?<![-\w])sources?\b(?!\s+code)", r"anonymous", r"unnamed")
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
              r"reliance on", r"explainer", r"fallout", r"wake-?up call", r"shows? how", r"anxiety", r"unready", r"unprepared")
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
_HEDGE_RX, _POLITICS_RX = _rx(HEDGE), _rx(POLITICS)
_WARN_RX, _FORECAST_RX, _CANCEL_RX, _CONFLICT_RX, _ROUTINE_RX = _rx(WARNING), _rx(FORECAST), _rx(CANCELLED), _rx(CONFLICT), _rx(ROUTINE_CAUSE)
_ANON_RX = re.compile("|".join(ANON_SOURCE), re.IGNORECASE)
_CUSTOMERS_RX = re.compile(r"(\d{1,3}(?:,\d{3})+|\d{3,})\s+(?:\w+\s+){0,2}(?:customers|homes|households|properties|residents|people|users|clients)", re.IGNORECASE)
_DURATION_RX = re.compile(r"(\d+|a|an|one|two|three|four|five|six|several)[- ](minutes?|hours?|days?)", re.IGNORECASE)
# 'Inquiry continues into the Telstra outage' / 'review ongoing' / 'trial continues': a PROCESS about a past event continues; the service
# disruption does not. It is not a continuation cue for the outage itself.
_PROCESS_CONT_RX = re.compile(r"\b(?:inquiry|inquest|investigation|investigations|probe|review|reviews|hearing|hearings|trial|audit|talks|negotiations|"
                              r"court case|class action|royal commission|search|clean-?up)\b(?:(?!\b(?:as|while|after|when|but|and|amid|because|although|though)\b)[^.;,]){0,30}?"
                              r"\b(?:continues?|ongoing|still|remains?)\b", re.IGNORECASE)


def _ongoing_cue(text: str) -> bool:
    """An explicit continuation cue about the SERVICE (still / continues / ongoing / remains), not about an inquiry or other process."""
    return bool(_ONGOING_RX.search(_PROCESS_CONT_RX.sub(" ", text or "")))


_RESTORED_RX = _rx((r"restored", r"resolved", r"back online", r"power is back", r"services? resumed"))
# Negated / in-progress / partial restoration ('power not restored', 'services yet to come back online', 'being restored', 'partially back
# online', 'restoration unlikely'): the service is NOT restored. These spans are removed before looking for an affirmative restoration.
_NEG_RESTORE_RX = re.compile(
    r"(?:\b(?:not|never|no longer|yet to|\w+n't)\s+(?:\w+\s+){0,3}?(?:be\s+)?(?:restored|resolved|back online))"
    r"|(?:\bbeing\s+(?:\w+\s+){0,2}?(?:restored|resolved))"
    r"|(?:\bpartial(?:ly)?\s+(?:\w+\s+){0,1}?(?:restored|resolved|back online))"
    r"|(?:\brestoration\s+(?:is\s+)?(?:unlikely|delayed|uncertain|postponed))", re.IGNORECASE)


def _negated_restore(text: str) -> bool:
    return bool(_NEG_RESTORE_RX.search(text))


def _affirmative_restored(text: str) -> bool:
    """True when the text affirms restoration, ignoring negated, in-progress and partial phrasings."""
    return bool(_RESTORED_RX.search(_NEG_RESTORE_RX.sub(" ", text)))


# 'restored' / 'resolved' make a report retrospective only when they state a COMPLETED restoration. A forecast ('will be restored by 5pm'),
# a wait ('remain down until resolved'), or a negated / in-progress / partial restoration describes a live outage.
_UNTIL_RESTORE_RX = re.compile(r"\buntil\s+(?:\w+\s+){0,3}?(?:restored|resolved|fixed)\b", re.IGNORECASE)


def _strip_live_restore(text: str) -> str:
    text = _NEG_RESTORE_RX.sub(" ", text or "")
    text = _FORECAST_RESTORE_RX.sub(" ", text)
    return _UNTIL_RESTORE_RX.sub(" ", text)


# A forecast ('will be restored by 5pm', 'restoration expected') says the service is NOT yet restored; a hedged claim ('reportedly restored',
# 'believed to be restored') is not an affirmative status statement. Neither may override explicit ongoing evidence as 'restored'.
_FORECAST_RESTORE_RX = _rx((r"(?:will|would|should|could|may|might|expected to|due to|set to|hoped? to|likely to|yet to|not yet|aim(?:s|ing)? to|working to)\s+(?:be\s+)?(?:fully\s+)?(?:restored|resolved|back online)",
                            r"restoration\s+(?:expected|due|estimated|forecast|by|time)", r"(?:until|before)\s+(?:power|service|services|supply)\s+(?:is|are|can be|has been)\s+(?:restored|resolved)"))
_HEDGED_RESTORE_RX = _rx((r"(?:reportedly|allegedly|apparently|supposedly|believed to be|said to be|claims? to be|understood to be|thought to be|possibly|perhaps)\s+(?:\w+\s+){0,2}(?:restored|resolved|back online)",
                          r"(?:restored|resolved|back online)\b[^.;]{0,60}\b(?:reportedly|allegedly|apparently|unconfirmed)"))
# Proportionality (Captain, 2026-11-23): customer count is NOT a universal threshold. For Tier 1 network services (energy,
# telecom, water) an ONGOING confirmed outage of at least this many customers is high materiality even when described as regional.
ONGOING_NETWORK_OUTAGE_CUSTOMERS = 10_000
_NETWORK_SECTORS = frozenset({"energy", "telecom", "transport_water", "emergency_services"})
_SCALE_RX, _ACTUAL_RX, _POTENTIAL_RX, _COMM_RX = _rx(SCALE), _rx(ACTUAL), _rx(POTENTIAL), _rx(COMMENTARY)
_COMPROMISE_RX = re.compile(r"(?<![a-z])(?:hijacked|hacked|breached|ransomware|stolen|skimmers?|compromised|wiped|malware|hit (?:by|with) (?:a )?(?:cyber\w*|ransomware|malware))(?![a-z])", re.IGNORECASE)
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
    status: str = "none"      # stated | unconfirmed | retrospective | potential | warning | forecast | none  (what the HEADLINE says about impact)
    exposure: bool = False    # a data-exposure consequence is stated
    safety: bool = False      # a safety consequence (injury, death, evacuation) is stated
    cascading: bool = False   # cascading / knock-on impact is stated
    minor: bool = False       # the disruption is described as brief/partial/limited
    customers: int | None = None   # affected customers stated in the headline
    ongoing: bool = False     # still in progress (not stated as restored/resolved)
    conflict: bool = False    # armed-conflict reporting (never escalated on its own)
    hedged: bool = False      # hedged or anonymously sourced (likely / reportedly / 'sources say')
    legacy: dict = field(default_factory=dict)

    @property
    def primary_type(self) -> str:
        for t in ("cyber_incident", "outage", "supply_shortfall", "water_quality", "service_disruption", "hazard", "physical", "vulnerability"):
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


def _report_time(event: dict):
    """When the report was PUBLISHED. Report chronology (restored vs ongoing) must follow publication, not ingestion: an older
    restoration article collected after a newer ongoing report must not win. The stored ``published_at`` is used when it parses
    and is not later than collection (plus a small clock skew); otherwise collection time, which is the only time we have."""
    collected = we._parse_ts(event.get("collected_at"))
    published = we._parse_ts(event.get("published_at")) if event.get("published_at") else None
    if published and (collected is None or published <= collected + timedelta(hours=1)):
        return published
    return collected


def detect_candidate(event: dict) -> Candidate:
    title = event.get("title") or ""
    text = title        # headline only: this is what every measurement was made on; summaries add unmeasured noise
    types = tuple(k for k, rx in _TYPE_RX.items() if rx.search(text))
    sectors = tuple(k for k, rx in _SECTOR_RX.items() if rx.search(text))
    scale = bool(_SCALE_RX.search(text))
    actual = bool(_ACTUAL_RX.search(text))
    potential = bool(_POTENTIAL_RX.search(text))
    # A multi-topic roundup headline ("A, B, C") reports no single incident, so it can never carry one.
    roundup = len([seg for seg in re.split(r",(?!\d{3})", title) if len(seg.split()) >= 2 and seg.strip()[:1].isupper()]) >= 3   # topics, not a list "…, taking out banks, airlines"
    commentary = (bool(_COMM_RX.search(text)) or we.is_commentary(title) or roundup
                  or we.source_kind(event.get("source") or "") == we.CONTENT
                  or (bool(_POLITICS_RX.search(text)) and not _SAFETY_RX.search(text) and not _COMPROMISE_RX.search(text)))       # magazines/newsletters comment, they do not report
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
    ongoing = _ongoing_cue(text) or (not _affirmative_restored(text) and not _RETRO_RX.search(text))
    conflict = bool(_CONFLICT_RX.search(text))
    hedged = bool(_HEDGE_RX.search(text) or _ANON_RX.search(text))
    if _ROUTINE_RX.search(text):
        minor = True        # a routine cause (weather) is not a severe disruption on its own
    forward = bool(_FORECAST_RX.search(text))
    hazardous = any(t in types for t in ("hazard", "supply_shortfall", "water_quality", "service_disruption"))
    cancelled = bool(_CANCEL_RX.search(_strip_live_restore(text)))
    is_cand = (bool(types or exposure or (conseq and essential)) and (bool(sectors) or scale or compromise or conseq or exposure or safety
                                           or ("vulnerability" in types and we.exploited(text)))) or hazardous
    consequence = ("essential_service" if essential else "broad_user_impact" if sectors
                   else "unknown" if (types and scale) else "none")
    tier = min((SECTOR_TIER[x] for x in sectors if x in SECTOR_TIER), default=None)
    retro = bool(_RETRO_RX.search(_strip_live_restore(text))) and not _ongoing_cue(text)
    if commentary or not is_cand:
        status = "potential" if (commentary and is_cand) else "none"
    elif cancelled:
        status = "retrospective"                       # a cancelled / resolved notice is no longer live
    elif retro or _historic_at(title, _report_time(event)):
        status = "retrospective"                       # about a past event (named older date): not a stated live disruption, so never an escalation on its own
    elif hazardous and forward and not any(t in types for t in ("water_quality", "service_disruption")):
        status = "forecast"                            # a forecast is not a stated outage
    elif "hazard" in types and bool(_WARN_RX.search(text)):
        status = "warning"                             # an emergency warning is not a stated consequence
    elif conseq or exposure or safety or hazardous:
        status = "unconfirmed" if hedged else "stated"       # "likely accessed" is a report, not a statement of fact
    else:
        status = "unconfirmed"
    src = event.get("source") or ""
    return Candidate(
        event_id=str(event.get("id")), title=title, source=src, published=_report_time(event),
        geography=event.get("geography") or "", types=types, sectors=sectors, orgs=_orgs(title), scale=scale, compromise=compromise,
        actual=actual, potential=potential, commentary=commentary, is_candidate=is_cand, consequence=consequence,
        tier=tier, status=status, exposure=exposure, safety=safety, cascading=cascading, minor=minor, customers=customers, ongoing=ongoing, conflict=conflict, hedged=hedged,
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


# #669: the class two reports share decides their comparison window and whether they can be one incident. Outages and cyber
# incidents come first (unchanged); the other prose-correlated classes (hazards, supply shortfalls, water quality, service
# disruptions) are now correlated on their OWN class instead of being lumped under "vulnerability" and rejected.
_CLASS_PRIORITY = ("outage", "cyber_incident", "hazard", "supply_shortfall", "water_quality", "service_disruption")


def _shared_class(a: Candidate, b: Candidate) -> str | None:
    shared = set(a.types) & set(b.types)
    if not shared:
        return None
    for cls in _CLASS_PRIORITY:
        if cls in shared:
            return cls
    return "vulnerability" if "vulnerability" in shared else min(shared)


def _comparable(a: Candidate, b: Candidate) -> bool:
    """True when two reports fall inside the time window of their shared event class (a pair outside it is simply not comparable)."""
    cls = _shared_class(a, b)
    if cls is None or not (a.published and b.published):
        return True
    return abs(a.published - b.published) <= _WINDOW.get(cls, _WINDOW["other"])


def _idf(cands: list[Candidate]) -> dict[str, float]:
    """Rarity score per stem. A stem is rare when it appears in at most max(2, 5% of the pool) headlines, so a pair of reports is
    judged the same way whether the pool holds 5 events or 5,000 (a log-IDF cut-off would call everything common in a small pool)."""
    df = Counter()
    for c in cands:
        df.update(_content_stems(c.title))
    n = len(cands)
    limit = max(2, int(0.05 * n)) if n >= 200 else max(2, int(0.4 * n))      # small pools: a term in under 40% of headlines still carries information
    return {s: (3.0 if d <= limit else 0.0) for s, d in df.items()}


def _link(a: Candidate, b: Candidate, idf: dict[str, float]) -> tuple[float, str] | None:
    """Confidence (0-1) that two candidates report ONE incident, with the reason; None if they do not."""
    if not (a.is_candidate and b.is_candidate):
        return None
    cls = _shared_class(a, b)
    if cls is None:
        return None
    if a.published and b.published and abs(a.published - b.published) > _WINDOW.get(cls, _WINDOW["other"]):
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
    # #669: hazards, supply shortfalls, water quality and service disruptions are place-specific. Two reports that each name a
    # place, and name DIFFERENT places, are different incidents however alike their headlines (a Sydney and a Melbourne boil
    # water notice). Outage and cyber links keep their existing guards.
    if cls in _PLACE_SPECIFIC_CLASSES and _location_conflict(a, b):
        return None
    if score >= 0.6 or (score >= 0.5 and (shared_orgs or rare >= 2)):
        return round(min(1.0, score), 2), "; ".join(reasons) + f"; class {cls}"
    return None


_PLACE_SPECIFIC_CLASSES = ("hazard", "supply_shortfall", "water_quality", "service_disruption")
_PLACES = ("sydney", "melbourne", "brisbane", "perth", "adelaide", "canberra", "hobart", "darwin", "newcastle", "wollongong", "illawarra",
           "gold coast", "sunshine coast", "geelong", "cairns", "townsville", "launceston", "alice springs", "kimberley", "pilbara",
           "eyre peninsula", "nsw", "new south wales", "victoria", "victorian", "queensland", "tasmania", "tasmanian", "south australia",
           "western australia", "northern territory", "act")
_PLACE_RX = re.compile(r"\b(" + "|".join(re.escape(p) for p in sorted(_PLACES, key=len, reverse=True)) + r")\b", re.IGNORECASE)
_PLACE_ALIAS = {"victorian": "victoria", "tasmanian": "tasmania", "new south wales": "nsw"}


def _places(title: str) -> frozenset:
    return frozenset(_PLACE_ALIAS.get(m.lower(), m.lower()) for m in _PLACE_RX.findall(title))


def _location_conflict(a: Candidate, b: Candidate) -> bool:
    """True when both reports name places and share none of them."""
    pa, pb = _places(a.title), _places(b.title)
    return bool(pa and pb and not (pa & pb))


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
            # Only pairs that fall inside the class time window are comparable: a week-long incident has early and late reports that were
            # never within 72 h of each other, which must not count as "not linked".
            cross = [(x, y) for x in core_a for y in core_b if _comparable(cands[x], cands[y])] or [(x, y) for x in core_a for y in core_b]
            coverage = sum(linked(x, y) for x, y in cross) / len(cross)
            # every member must be tied to the other cluster unless it has no comparable partner there (early and late reports of a long incident)
            every_member_tied = all(any(linked(x, y) for y in core_b) for x in core_a if any(_comparable(cands[x], cands[y]) for y in core_b)) and \
                all(any(linked(x, y) for x in core_a) for y in core_b if any(_comparable(cands[x], cands[y]) for x in core_a))
            if coverage < 0.5 or not every_member_tied:
                continue                               # average linkage: stops one chance pair chaining incidents
        if (not core_a and len(ca) > 1) or (not core_b and len(cb) > 1):
            continue                                   # a commentary-only cluster does not absorb others
        clusters[a] = ca + cb
        clusters[b] = []
        for m in cb:
            where[m] = a
    # Follow-up pass: a lone commentary/retrospective report ("blackout prompts questions over the network upgrade", "to be investigated
    # post-blackout") carries no entity or term that links it to the incident. Attach it, at LOW grouping confidence, only when exactly one
    # active incident of the same sector and event class lies within 96 h. It can never carry an escalation (commentary/retrospective).
    followups: dict[int, tuple[int, str]] = {}
    for k in list(range(len(clusters))):
        v = clusters[k]
        if len(v) != 1:
            continue
        f = cands[v[0]]
        if not (f.is_candidate and (f.commentary or f.status == "retrospective") and f.published and f.sectors):
            continue
        targets = [kk for kk, vv in enumerate(clusters) if kk != k and vv and any(
            (not cands[m].commentary) and cands[m].status == "stated" and cands[m].published
            and set(cands[m].sectors) & set(f.sectors) and set(cands[m].types) & set(f.types)
            and abs(f.published - cands[m].published) <= timedelta(hours=96) for m in vv)]
        if len(targets) == 1:
            followups[v[0]] = (targets[0], "probable follow-up: same sector and event class, only one active incident within 96 h")
            clusters[targets[0]] = clusters[targets[0]] + v
            clusters[k] = []
    buckets = {k: v for k, v in enumerate(clusters) if v}
    groups: list[Group] = []
    for n, idxs in enumerate(sorted(buckets.values(), key=lambda v: v[0])):
        members = [cands[i] for i in idxs]
        plist = [(cands[i].event_id, cands[j].event_id, *pairs[(i, j)]) for (i, j) in pairs if i in idxs and j in idxs]
        plist += [(cands[i].event_id, cands[idxs[0]].event_id, 0.4, followups[i][1]) for i in idxs if i in followups]
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
            if len(members) > 1 and _SYNDICATION_SUFFIX.search(m.title):
                synd.append(m.event_id)         # a wire suffix marks a copy only when the group holds other reports of it
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
    impact_status: str        # what the headline states: stated | unconfirmed | retrospective | potential | warning | forecast | none
    materiality: str          # high | medium | low (operational, not sector)
    evidence_confidence: float
    urgency: str              # immediate | soon | routine
    priority: str             # ESCALATE | VERIFY | WATCH | REFERENCE
    provisional: bool
    reasons: list[str]
    evidence_status: str = "unverified"       # officially_confirmed | corroborated | reported | unverified (source-level, see evidence_status())
    evidence_basis: list[str] = field(default_factory=list)   # the sources that support that status
    method_version: str = METHOD_VERSION


_STATUS_ORDER = {"stated": 6, "warning": 5, "forecast": 4, "unconfirmed": 3, "retrospective": 2, "potential": 1, "none": 0}


def _materiality(c: Candidate) -> str:
    """Operational materiality from the STATED consequence (rubric 2.1): severe disruption, major safety consequence tied to a critical service,
    essential-service interruption or cascading impact. A tier never sets materiality by itself; armed-conflict reporting and routine causes never
    reach high; a forecast or warning is a different status, not a stated outage."""
    if not c.is_candidate or c.status in ("none", "potential", "warning", "forecast"):
        return "low"
    tier = c.tier or None
    if c.status == "stated":
        if c.cascading and not c.conflict:
            return "high"
        if c.safety:
            return "high" if (tier and not c.conflict) else "medium"      # needs a dependency link; geography alone is not enough
        if c.conflict:
            return "medium"
        if (c.ongoing and c.customers and c.customers >= ONGOING_NETWORK_OUTAGE_CUSTOMERS
                and "outage" in c.types and set(c.sectors) & _NETWORK_SECTORS):
            return "high"                      # significant active network outage; proportionality, not a universal threshold
        if c.minor:
            return "medium"                    # brief / partial / routine-cause disruption is not severe on its own
        if any(t in c.types for t in ("hazard", "supply_shortfall", "water_quality", "service_disruption")) and not ({"outage"} & set(c.types)):
            return "high" if ("do not drink" in c.title.lower() or "boil" in c.title.lower()) else "medium"
        if (tier == 1) or (tier == 2 and c.scale) or (c.scale and c.exposure):
            return "high"
        return "medium"
    if c.status == "retrospective":
        return "medium" if tier == 1 else "low"
    return "medium" if tier == 1 else "low"       # unconfirmed: a Tier 1 candidate is worth a look, others are not


def evidence_status(group: Group) -> tuple[str, list[str]]:
    """Source-level evidence status, independent of what the headline says about impact.
    officially_confirmed: a primary/official source (regulator, operator, advisory body) is among the original reports.
    corroborated: at least two INDEPENDENT publishers (syndicated copies excluded) including a non-aggregator.
    reported: one non-aggregator original report. unverified: aggregator-only, hedged or anonymously sourced, or no original report."""
    originals = [m for m in group.members if not m.commentary and m.event_id not in group.syndicated_ids]
    basis = [f"{m.source or m.family} ({m.kind})" for m in originals]
    if any(m.kind == we.PRIMARY and not m.hedged for m in originals):
        return "officially_confirmed", basis
    solid = [m for m in originals if m.kind != we.AGGREGATOR and not m.hedged]
    if not solid:
        return "unverified", basis
    # #669: corroboration needs two independent publishers among the SOLID reports. group.independent_publishers also
    # counts hedged / anonymously sourced publishers, so a "reportedly ..." second report must not lift the status.
    solid_publishers = {m.family for m in solid}
    return ("corroborated" if len(solid_publishers) >= 2 and group.independent_publishers >= 2 else "reported"), basis


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

    ev_status, ev_basis = evidence_status(group)
    reasons.append(f"evidence status {ev_status}")

    def out(pr, urgency, prov=False):
        return Decision(group, head, tier, head.primary_type, status, mat, conf, urgency, pr, prov, reasons, ev_status, ev_basis)

    if status in ("warning", "forecast") and head.primary_type != "vulnerability":
        # A warning or forecast is a different thing from a stated outage: it goes to WATCH (forward watch) when an authoritative or
        # mainstream source issues it, and only an imminent shortfall (LOR3 / load shedding) is raised to VERIFY.
        imminent = bool(re.search(r"lor3|load shedding", head.title, re.IGNORECASE))
        reasons.append(f"{status}, not a stated incident")
        if imminent and solid:
            return out("VERIFY", "immediate")
        return out("WATCH" if solid else "REFERENCE", "soon")

    if head.primary_type == "vulnerability":
        exploited_, exposed = we.exploited(head.title), we.known_exposure(head.title)
        mat = "high" if (exploited_ and exposed) else "medium" if exploited_ else "low"
        reasons.append(f"advisory: exploited={exploited_} known_exposure={exposed} (KEV alone is not critical)")
        if exploited_ and exposed and primary:
            return out("ESCALATE", "immediate")
        return out("WATCH" if exploited_ or "critical" in head.title.lower() else "REFERENCE", "soon" if exploited_ else "routine")
    if mat == "high" and head.hedged:
        reasons.append("hedged or anonymously sourced: verify before acting")
        return out("VERIFY", "soon")
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
    if status == "stated" and head.is_candidate:
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


def _next_action(primary_type: str, impact_status: str, restoration: str) -> str:
    """The verification step that fits the incident class AND its chronology. A retrospective investigation, or a disruption reported
    restored, never receives a live-restoration task; a disruption whose current status is unknown is first checked for currency."""
    if primary_type == "outage" and restoration == "restored":
        return "confirm the restoration time, root cause and any customer remediation with the operator (reported restored; no live restoration action)"
    if impact_status == "retrospective":
        return "read the cited review, inquiry or analysis and confirm its findings and any remedial actions with the operator or regulator (no live restoration action)"
    if primary_type == "outage":
        if restoration == "ongoing":
            return "confirm the customer count, affected area and restoration estimate with the operator or regulator (primary source)"
        return ("confirm the disruption is current (operator status page or a dated primary statement); if it is not, treat the report as "
                "historical and take no live restoration action")
    return _VERIFY_NEXT.get(primary_type, "confirm with an official source")


# A report that says service is restored AND says some of it is not: 'restored to some customers but thousands without power',
# 'partially restored', 'yet to be restored', 'not all restored'. It has no 'still' / 'continues' word, but it is not a restoration.
_PARTIAL_RX = _rx((r"restored (?:to|for) (?:some|part|parts|a number)", r"partial(?:ly)? restor\w*", r"(?:yet|not yet) (?:to be )?restored",
                   r"not all (?:\w+ ){0,3}restored", r"(?:but|although|while|however)\b[^.;]{0,60}\b(?:without|remain\w*|yet to|outstanding|still)"))


# ── Historical dated references ────────────────────────────────────────────────────────────────────────────
# A headline such as "Microsoft's Friday 13th outage continues ..." re-surfaced on the 22nd names an event nine days old. 'continues'
# in such a headline is a historical reference, not current evidence that the service is still disrupted. A report that names a
# calendar date well before its own publication time cannot, by its wording alone, establish an ongoing status.
HISTORIC_DATE_HOURS = 48
_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_DMY_RX = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b")
_DAY_MONTH_RX = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + "|".join(_MONTHS) + r")\b", re.IGNORECASE)
_MONTH_DAY_RX = re.compile(r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b(?!,\d)", re.IGNORECASE)
_WEEKDAY_ORD_RX = re.compile(r"\b(" + "|".join(_WEEKDAYS) + r")\s+(\d{1,2})(?:st|nd|rd|th)\b", re.IGNORECASE)


def named_date(title: str, ref: datetime) -> datetime | None:
    """The latest calendar date the headline names that is not after ``ref`` (a weekday-and-day-of-month such as 'Friday 13th', a
    'day month', a 'month day', or dd/mm/yyyy), or None. Dates are read, never inferred."""
    t = core_title(title or "")
    found: list[datetime] = []

    def add(y: int, mo: int, d: int):
        try:
            dt = datetime(y, mo, d, tzinfo=timezone.utc)
        except ValueError:
            return
        if dt > ref:                                   # a future date (e.g. an estimated restoration time) is never a historical reference
            return
        found.append(dt)

    for m in _DMY_RX.finditer(t):
        add(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    for m in _DAY_MONTH_RX.finditer(t):
        add(ref.year, _MONTHS.index(m.group(2).lower()) + 1, int(m.group(1)))
    for m in _MONTH_DAY_RX.finditer(t):
        if m.group(1).lower() == "may" and m.group(1) != "May":
            continue                                   # lowercase / shouty 'may 10,000' is the modal verb, not a date
        add(ref.year, _MONTHS.index(m.group(1).lower()) + 1, int(m.group(2)))
    for m in _WEEKDAY_ORD_RX.finditer(t):
        wd, day = _WEEKDAYS.index(m.group(1).lower()), int(m.group(2))
        y, mo = ref.year, ref.month
        for _ in range(14):                            # latest month (back from ref) whose day-th falls on that weekday
            try:
                dt = datetime(y, mo, day, tzinfo=timezone.utc)
                if dt <= ref and dt.weekday() == wd:
                    found.append(dt)
                    break
            except ValueError:
                pass
            mo -= 1
            if mo == 0:
                y, mo = y - 1, 12
    return max(found) if found else None


def _historic_at(title: str, published) -> bool:
    """True when the headline names a date more than HISTORIC_DATE_HOURS before it was published."""
    if not published:
        return False
    d = named_date(title, published)
    return d is not None and published - d > timedelta(hours=HISTORIC_DATE_HOURS)


def _historic(m: Candidate) -> bool:
    return _historic_at(m.title, m.published)


def _report_state(m: Candidate, now: datetime | None = None, active_default: bool = False) -> str | None:
    """What one report says about service: 'restored' only if it says so and nothing in it is still ongoing or only partly
    restored (a mixed 'power restored but thousands still without' is ongoing); None when it says neither."""
    forecast = bool(_FORECAST_RESTORE_RX.search(m.title))
    hedged_restore = bool(_HEDGED_RESTORE_RX.search(m.title))
    negated = _negated_restore(m.title)
    restored = _affirmative_restored(m.title) and not forecast and not hedged_restore      # only an affirmative, unhedged statement restores
    cue = _ongoing_cue(m.title) or forecast or negated or (restored and bool(_PARTIAL_RX.search(m.title)))
    if _historic(m):
        # An old dated event: its continuation cue is not current evidence, but a negated or partial restoration ('yet to be
        # restored') can never be read as a restoration either. No state at all unless it cleanly says restored.
        return None if cue else ("restored" if restored else None)
    if cue:
        return "ongoing"
    if active_default and not restored and m.ongoing and m.status == "stated":
        # A stated, still-active interruption with no explicit 'still' ('... without power again') reopens an earlier restoration. It is
        # live evidence only while current; once it ages out it can no longer establish an outage, but it still INVALIDATES the earlier
        # restoration, so the status becomes unknown rather than resurrecting 'restored'.
        if now is None or (m.published and timedelta(0) <= now - m.published <= timedelta(hours=FRESH_REPORT_HOURS)):
            return "ongoing"
        return "reopened"
    return "restored" if restored else None


FRESH_REPORT_HOURS = 12       # a stated, non-retrospective report this recent is current evidence that a disruption is live


def _restoration_status(originals: list[Candidate], now: datetime | None = None) -> str:
    """#669: decide by report CHRONOLOGY. The latest dated report that states restored or ongoing wins, so an earlier 'still
    without power' report no longer vetoes a later 'power restored' (and a later 'still ongoing' reopens an earlier
    'restored'). Ties go to 'ongoing'. Reports without a date cannot be ordered, so with no dated statement the previous
    any-report rule applies."""
    dated = sorted((m for m in originals if m.published), key=lambda m: m.published)
    for m in reversed(dated):
        latest = m.published
        states = {_report_state(x, now, active_default=True) for x in dated if x.published == latest} - {None}
        if states:
            return "ongoing" if "ongoing" in states else "unknown" if "reopened" in states else "restored"
    states = {_report_state(m) for m in originals}
    if "ongoing" in states:                  # an explicit 'still' / 'partly restored' statement, whatever the report order
        return "ongoing"
    if "restored" in states:
        return "restored"
    if now is None:                         # callers that do not say what time it is keep the previous rule
        return "ongoing" if any(m.ongoing and m.status == "stated" and not _historic(m) for m in originals) else "unknown"
    # #669: "ongoing" needs CURRENT evidence: an explicit continuation cue (still / ongoing / continues ...) in a stated
    # report, or a stated, non-retrospective report from the last FRESH_REPORT_HOURS. Retrospective reporting about a past
    # event, or an old report with no continuation cue, is "unknown" rather than a live disruption.
    for m in originals:
        if m.status != "stated" or _historic(m):   # retrospective, unconfirmed, warning or a re-surfaced old dated event: not a live disruption
            continue
        if _ongoing_cue(m.title):
            return "ongoing"
        if m.ongoing and m.published and timedelta(0) <= now - m.published <= timedelta(hours=FRESH_REPORT_HOURS):
            return "ongoing"
    return "unknown"


def escalation_record(d: Decision, *, now: datetime | None = None) -> dict:
    """The facts the Captain needs beside every ESCALATE/VERIFY item: what is confirmed vs merely reported, scale, duration and
    restoration, critical-service dependencies, geography, source confidence and the next verification action. Recomputed whenever the
    incident gains reports, so the classification is reassessed on new evidence."""
    originals = [m for m in d.group.members if not m.commentary] or d.group.members
    h = d.headline
    counts = [m.customers for m in originals if m.customers]
    text = " ".join(m.title for m in originals)
    dur = _DURATION_RX.search(text)
    # A probable follow-up was attached only by sector/class proximity (low confidence), not by an incident-specific link, so its
    # restoration wording must not close the incident (Codex P2: an unrelated operator's 'restored' report removed an ongoing outage).
    speculative = {p[0] for p in d.group.pairs if str(p[3]).startswith("probable follow-up")}
    restoration = _restoration_status([m for m in originals if m.event_id not in speculative] or originals, now)
    return {
        "impact": "stated in headline" if d.impact_status == "stated" else "reported" if d.impact_status in ("unconfirmed", "retrospective") else d.impact_status,
        "evidence_status": d.evidence_status, "evidence_basis": d.evidence_basis,
        "affected_customers": max(counts) if counts else None,
        "duration": dur.group(0) if dur else None,
        "restoration_status": restoration,
        "critical_service_dependencies": sorted({x for m in originals for x in m.sectors}),
        "sector_tier": d.sector_tier,
        "geographic_scope": sorted({m.geography for m in originals if m.geography}),
        "source_confidence": {"evidence_confidence": d.evidence_confidence, "independent_publishers": d.group.independent_publishers,
                              "source_kinds": sorted({m.kind for m in originals}), "provisional": d.provisional},
        "next_verification_action": _next_action(h.primary_type, d.impact_status, restoration),
        "report_ids": [m.event_id for m in d.group.members],
        "reassess": "re-run when new reports arrive; customer count is a proportionality input, not a universal threshold",
    }
