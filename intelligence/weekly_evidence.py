"""Shared weekly intelligence evidence foundation — OFFLINE PROTOTYPE (Gate 2).

One validated, read-only evidence layer for every weekly reporting product. This
module is pure: it takes already-gathered dicts and returns structures. It does
not read or write any database, is not imported by any report or scheduler, and
changes no live scoring. It exists to be tested and compared offline.

Design (Captain's review of the Weekly Intelligence Uplift):

1. Three independent axes — evidence CONFIDENCE, operational MATERIALITY, action
   PRIORITY — computed from content features. Legacy rank/risk/disposition/
   confidence fields are carried for comparison only and never feed an axis.
2. Incident correlation (same story, any size) is separate from thematic
   clustering (several distinct incidents). A high-impact single event is never
   dropped for failing a cluster-size threshold.
3. Health records are typed (registration / finding / review / guideline / safety
   advisory / non-evidence); a registration is never a demonstrated result.
4. Narrative claims are validated against the cited evidence, not merely for the
   presence of IDs; failure falls back to deterministic text.
5. Everything is stamped with a methodology version; comparisons across versions
   are refused rather than silently drawn.
6. Absence is typed: observed / not observed / insufficient sample / source outage.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# ── Methodology versioning (historical comparability) ─────────────────────────

METHOD_VERSION = "wk-evidence/0.2.0-prototype"

# Each entry is one methodology epoch. `breaks_comparability` lists earlier
# versions whose figures must NOT be trended against this one.
METHOD_CHANGELOG: tuple[dict, ...] = (
    {"version": "legacy/confidence-count", "effective": "2026-08-10",
     "notes": "Weekly report counted osint_confidence_level of the top-1000 rows by rank as 'high/medium/low'.",
     "breaks_comparability": []},
    {"version": "wk-evidence/0.1.0-prototype", "effective": "unreleased",
     "notes": "Three-axis assessment, incident vs theme separation, typed health evidence.",
     "breaks_comparability": ["legacy/confidence-count"]},
    {"version": METHOD_VERSION, "effective": "unreleased",
     "notes": "Calibrated materiality (power-loss vocabulary, scale/third-party/co-occurrence cues, AU entities), "
              "entity+event-class incident grouping, exposure-aware advisory and provisional-incident escalation.",
     "breaks_comparability": ["legacy/confidence-count", "wk-evidence/0.1.0-prototype"]},
)

# Classifier epochs: the keyword classifier that populates event_type / relevance.
# A future change (e.g. word-boundary matching) must add an epoch so the
# discontinuity is visible in any trend that spans it.
CLASSIFIER_EPOCHS: tuple[dict, ...] = (
    {"epoch": "classifier-kw-v1-substring", "effective": "until-changed",
     "notes": "Keyword rules with substring matching; 83% of events typed 'other' in 17-23 Nov 2026."},
)


def comparable(version_a: str, version_b: str) -> tuple[bool, str]:
    """(ok, reason). Same version is comparable; a documented break is not;
    unknown versions are refused (fail closed)."""
    known = {e["version"]: e for e in METHOD_CHANGELOG}
    if version_a == version_b and version_a in known:
        return True, "same methodology version"
    if version_a not in known or version_b not in known:
        return False, "unknown methodology version — not comparable"
    later, earlier = (version_a, version_b) if _order(version_a) > _order(version_b) else (version_b, version_a)
    if earlier in known[later]["breaks_comparability"]:
        return False, f"discontinuity: {earlier} → {later} ({known[later]['notes']})"
    return True, "no documented break between versions"


def _order(version: str) -> int:
    return [e["version"] for e in METHOD_CHANGELOG].index(version)


# ── Tokenising helpers ────────────────────────────────────────────────────────

_STOP = frozenset(["the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "with", "is", "are", "be", "as", "at", "by", "from", "that", "this", "it", "its", "after", "before", "over", "into", "new", "says", "said", "will", "has", "have", "had", "not", "but", "out", "up", "more"])


def _wb(term: str, hay: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + term + r"(?![a-z0-9])", hay) is not None


def tokens(text: str) -> frozenset[str]:
    return frozenset(w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
                     if len(w) > 3 and w not in _STOP)


def similarity(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def _parse_ts(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        s = str(value).strip().replace(" ", "T")
        s = s[:-1] + "+00:00" if s.endswith("Z") else s
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ── Source kinds and publisher families ───────────────────────────────────────

PRIMARY, MAINSTREAM, SPECIALIST, AGGREGATOR, CONTENT, REGISTRY, UNKNOWN = (
    "primary", "mainstream", "specialist", "aggregator", "content", "registry", "unknown")

# Order matters: an aggregator feed ABOUT a regulator ("Google News - APRA/ASIC ...") is an
# aggregator, not that regulator, so aggregators and registries are tested first.
_KIND_TERMS = (
    (REGISTRY, ("clinicaltrials",)),
    (AGGREGATOR, ("google news",)),
    (PRIMARY, ("cisa", "cisco security", "google cloud security", "aemo", "acsc", "cyber.gov.au",
               "nist", "apra", "asic", "rba ", "fda", "cdc", "who ", "ato online services")),
    (MAINSTREAM, ("bloomberg", "abc news", "bbc", "financial times", "guardian", "reuters",
                  "associated press", "the age", "financial review", "new york times")),
    (SPECIALIST, ("arn", "sans ", "financial newswire", "industrial cyber", "the register", "itnews")),
    # wellness / thought-leadership registry feeds are commentary, not event reporting (MIT Technology Review is
    # technology journalism and is deliberately NOT listed).
    (CONTENT, ("psychology today", "inc.", "fast company", "mckinsey", "harvard business", "mit sloan", "gartner",
               "world economic forum", "stanford social innovation", "deloitte insights", "pwc strategy", "greater good",
               "mindful.org", "gallup", "positive psychology", "harvard health", "black dog institute", "the conversation",
               "international coach federation", "center for creative leadership", "cambridge wellbeing", "people management")),
)
_KIND_GRADE = {PRIMARY: 0.90, MAINSTREAM: 0.60, SPECIALIST: 0.50, AGGREGATOR: 0.30,
               CONTENT: 0.20, REGISTRY: 0.0, UNKNOWN: 0.30}


def source_kind(source_name: str) -> str:
    n = (source_name or "").lower()
    for kind, terms in _KIND_TERMS:
        if any(_wb(re.escape(t.strip()), n) for t in terms):     # whole words/phrases: "arn" is not inside "Warnings"
            return kind
    return UNKNOWN


def publisher_family(source_name: str, title: str = "") -> str:
    """Normalised publisher. Aggregator items are attributed to the underlying
    publisher when the title carries a ' - Publisher' suffix."""
    n = (source_name or "unknown").strip().lower()
    if source_kind(source_name) == AGGREGATOR:
        m = re.search(r"\s[-–]\s([^-–]{2,40})$", title or "")
        if m:
            return _canonical_publisher(m.group(1).strip().lower())
        return "aggregator"
    return _canonical_publisher(re.sub(r"[^a-z0-9]+", " ", n).strip().split(" — ")[0])


# One organisation under several names must be ONE publisher, otherwise an aggregator re-posting of an outlet's own story
# (e.g. a Google News item whose title ends "- Australian Broadcasting Corporation") counts as an independent second source
# for that outlet's reporting. Narrow, evidence-based table: only name variants seen in the real feed for the same organisation.
_PUBLISHER_ALIASES = {
    "abc news": "abc news", "abc news business": "abc news", "abc": "abc news", "abc net au": "abc news",
    "australian broadcasting corporation": "abc news", "abc news australia": "abc news",
    "guardian australia": "guardian australia", "the guardian": "guardian australia", "guardian": "guardian australia",
    "the guardian australia": "guardian australia", "theguardian com": "guardian australia",
    "bbc news": "bbc news", "bbc": "bbc news", "bbc com": "bbc news",
    "afr": "afr", "australian financial review": "afr", "financial review": "afr",
    "reserve bank of australia": "rba",
}

# Controlled sub-brand sets: the same organisation's other desks/editions are one publisher (a repost from "BBC Sport" is not
# an independent second source for "BBC News"). Exact, closed lists on purpose: "ABC7 Chicago" (a US affiliate, one token
# "abc7") and "BBC Watch Blog" are NOT in them and keep their own family.
_SUB_BRANDS = {
    "guardian": ("guardian australia", frozenset({"us", "uk", "australia", "international", "europe", "world", "business"})),
    "the guardian": ("guardian australia", frozenset({"us", "uk", "australia", "international", "europe", "world", "business"})),
    "bbc": ("bbc news", frozenset({"sport", "world service", "culture", "world", "news world", "news uk", "future", "worklife",
                                   "travel", "earth", "innovation", "reel", "science"})),
    "abc": ("abc news", frozenset({"radio national", "science", "news australia", "sport", "triple j", "rural", "life",
                                   "radio", "listen", "everyday", "health"})),
    "afr": ("afr", frozenset({"weekend", "street talk", "chanticleer", "rear window", "markets", "companies", "property"})),
}


# Organisations that register several feeds under one name prefix ("APRA Media Releases", "APRA Publications"). Matched on
# the first whole token only, so "Cisco ..." is not cisa and "Asian ..." is not asic. abc/bbc are handled by the alias table.
_ORG_PREFIXES = frozenset({"apra", "asic", "cisa", "acsc", "aemo", "nist", "rba"})
# ...and only when everything after the org token is a known feed-descriptor word. An unknown suffix ("CISA-Watch Blog",
# "rba-watch.com", "Rba Foo") is a different publisher that merely shares a prefix, so it keeps its own family.
_FEED_SUFFIX_WORDS = frozenset({
    "media", "releases", "release", "publications", "alerts", "news", "advisories", "feed", "rss", "updates", "press",
    "announcements", "enforcement", "known", "exploited", "vulnerabilities", "market", "notices", "csrc", "bulletin",
    "speeches", "statements", "reports", "guidance", "gov", "au", "com", "us",
})


def _canonical_publisher(name: str) -> str:
    key = re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()
    if key in _PUBLISHER_ALIASES:
        return _PUBLISHER_ALIASES[key]
    toks = key.split(" ")
    first, rest = toks[0], toks[1:]
    if first in _ORG_PREFIXES and all(t in _FEED_SUFFIX_WORDS for t in rest):
        return first
    for brand in (" ".join(toks[:2]), first):
        sub = _SUB_BRANDS.get(brand)
        if sub and " ".join(toks[len(brand.split(" ")):]) in sub[1]:
            return sub[0]
    return name


# ── Materiality lexicon ───────────────────────────────────────────────────────

_IMPACT_TERMS = {
    # supply of essential services
    "blackouts?": 3, "power outages?": 3, "power out": 2, "outages?": 2, "transmission lines?": 2,
    "transmission towers?": 2, "without power": 3, "cut power": 3, "power cuts?": 3, "knocking out power": 3,
    "loss of power": 3, "electricity supply": 2, "power shortages?": 2, "gas reservation": 1, "grid": 1,
    "triple zero": 2, "essential services": 2, "critical infrastructure": 2, "systemic risk": 2,
    # cyber
    "ransomware": 3, "known exploited": 3, "actively exploited": 3, "zero-day": 3, "critical vulnerability": 2,
    "cyber incident": 3, "security incident": 3, "data breach": 2, "security breach": 2, "cyberattacks?": 2,
    "cyber attacks?": 2, "card skimmer": 2, "client data": 1, "data (?:likely )?accessed": 2,
    "unauthori[sz]ed access": 2, "patch": 1,
    # operational resilience / regulation
    "supply chain": 1, "data cent(?:er|re)": 1, "cps 230": 3, "soci act": 2, "business continuity": 1,
}
# Co-occurrence terms: (all-of patterns, points). A pair is stronger evidence than either word alone.
_PAIR_TERMS = (
    (("national security", "ai"), 3),
    (("data cent(?:er|re)", "risk|demand|strain|grid|power"), 2),
    (("third[- ]party|vendors?|suppliers?", "cyber ?attacks?|breach|ransomware|hack(?:ed|ing)?"), 1),
)
# Scale / urgency cues only AMPLIFY an event that already matched a term (max +2 in total).
_SCALE_CUES = (
    r"major|widespread|nationwide|national|global|worldwide|massive",
    r"continues?|ongoing|still",
    r"\d{1,3}(?:,\d{3})+\s+(?:\w+\s+){0,3}(?:customers|homes|households|people|users|residents|without power)",
)
_AU_TERMS = ("australia", "australian", "victoria", "victorian", "south australia", "nsw",
             "new south wales", "queensland", "melbourne", "sydney", "aemo", "canberra", "tasmania",
             # recognised Australian organisations (a Coles/Optus story is Australian whatever the feed tags it)
             "coles", "woolworths", "telstra", "optus", "qantas", "nbn", "ausgrid", "electranet", "agl",
             "origin energy", "services australia", "commonwealth bank", "westpac", "anz", "asx",
             "apra", "asic", "rba", "acsc")
_EVENT_CLASS_TERMS = {
    "advisory": ("known exploited", "actively exploited", "zero-day", "critical vulnerability", r"cve-\d+",
                 "vulnerabilit(?:y|ies)", "advisory", "patch(?:ing)?"),
    "incident": ("blackouts?", "outages?", "power out", "without power", "cut power", "power cuts?",
                 "cyber incident", "cyber ?attacks?", "data breach", "security breach", "ransomware",
                 "data (?:likely )?accessed", "card skimmer", "triple zero", "degradation"),
}
_SEVERE_CONSEQUENCE = (
    "blackouts?", "without power", "cut power", "power cuts?", "knocking out power", "power outages?",
    "triple zero", "emergency services?", "hospitals?", "payments?", "banking", "air traffic",
    "telco|telecom|mobile network|national network", "essential services", "critical infrastructure",
    "ransomware", "data breach", "client data", "cyber incident",
)
_EXPLOITED = ("known exploited", "actively exploited", "exploited in the wild", "in the wild", "zero-day")
# Technologies the Captain's own platform runs on; an advisory only counts as "known exposure" when it
# names one. PROPOSED defaults inferred from this repository — the Captain should replace them with the
# real estate (including any employer stack) via COMMS/INTEL config before this is relied on.
DEFAULT_EXPOSURE_TERMS = ("supabase", "vercel", "github", "cloudflare", "nginx", "ollama", "postgres",
                          "node\\.?js", "next\\.?js", "openjdk|java", "linux", "google cloud|gcp",
                          "gemini", "mistral", "notion", "telegram", "cisco", "microsoft|m365|outlook|teams")
_THEMES = {
    "energy_grid": ("blackout", "power outage", "power out", "transmission line", "electricity supply",
                    "power shortage", "gas reservation", "grid", "data cent(?:er|re)", "aemo"),
    "vulnerability_advisories": ("known exploited", "actively exploited", "critical vulnerability",
                                 "zero-day", "vulnerabilit(?:y|ies)", "cve-\\d+", "patch"),
    "ai_cyber": ("ai-fuell?ed", "ai-powered", "ai-enabled", "ai cyber", "ai and cyber", "agentic"),
    "technology_outages": ("outages?", "global outage", "service disruption", "triple zero"),
}


def _term_hits(text: str, terms) -> list[str]:
    hay = (text or "").lower()
    return [t for t in terms if _wb(t, hay)]


def themes_of(text: str) -> list[str]:
    """Controlled-vocabulary themes whose terms appear (>=1 term). Never invented."""
    return [k for k, terms in _THEMES.items() if _term_hits(text, terms)]


# ── Quality flags: misleading headline, conflicts, causal language ────────────

_CAUSAL = ("because", "caused by", "caused", "due to", "led to", "result of", "blamed", "blame",
           "triggered", "driven by", "behind the", "responsible for")
_DENY = ("denies", "denied", "disputes", "disputed", "refutes", "rejects", "no evidence", "false claim")
_AFFIRM = ("confirms", "confirmed", "admits", "admitted", "acknowledges")
_NUM_UNIT = re.compile(r"(\d[\d,\.]*)\s*(customers|homes|households|people|users|deaths|mw|megawatts)\b", re.IGNORECASE)


def has_causal_language(text: str) -> bool:
    low = (text or "").lower()
    return any(re.search(r"(?<![a-z])" + re.escape(c) + r"(?![a-z])", low) for c in _CAUSAL)


def headline_flags(title: str, summary: str) -> list[str]:
    """Headline-vs-body support. With no body the headline is 'unverifiable', not 'supported'."""
    flags = []
    if not (summary or "").strip():
        return ["headline_unverifiable_no_body"]
    ht, st = tokens(title), tokens(summary)
    if ht and len(ht & st) / len(ht) < 0.30:
        flags.append("headline_not_supported_by_body")
    if has_causal_language(title) and not has_causal_language(summary):
        flags.append("headline_causal_claim_not_in_body")
    return flags


def _numbers(text: str) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for num, unit in _NUM_UNIT.findall(text or ""):
        try:
            out.setdefault(unit.lower(), []).append(float(num.replace(",", "")))
        except ValueError:
            continue
    return out


def conflict_flags(texts_by_publisher: dict[str, str]) -> list[str]:
    """Different publishers reporting opposing polarity or materially different figures."""
    flags = []
    pubs = list(texts_by_publisher)
    deny = {p for p in pubs if any(w in texts_by_publisher[p].lower() for w in _DENY)}
    affirm = {p for p in pubs if any(w in texts_by_publisher[p].lower() for w in _AFFIRM)}
    if deny and affirm and (deny - affirm or affirm - deny):
        flags.append("conflicting_assertions")
    per_unit: dict[str, list[float]] = {}
    for t in texts_by_publisher.values():
        for unit, vals in _numbers(t).items():
            per_unit.setdefault(unit, []).extend(vals)
    for unit, vals in per_unit.items():
        if len(vals) >= 2 and min(vals) > 0 and max(vals) / min(vals) > 1.25:
            flags.append(f"conflicting_figures:{unit}")
    return flags


# ── Event model and the three axes ────────────────────────────────────────────

@dataclass
class Assessment:
    event_id: str
    title: str
    source: str
    source_kind: str
    family: str
    published: datetime | None
    confidence: float
    confidence_level: str
    materiality: float
    materiality_level: str
    priority: str                       # ESCALATE / WATCH / VERIFY / REFERENCE
    escalation: dict | None = None      # provisional/uncorroborated marking + required follow-up
    flags: list[str] = field(default_factory=list)
    legacy: dict = field(default_factory=dict)   # comparison only, never an input
    method_version: str = METHOD_VERSION


def _level(x: float, hi: float, mid: float) -> str:
    return "high" if x >= hi else "medium" if x >= mid else "low"


# Follow-up / commentary framing: reports ABOUT an incident (concern, advice, questions, explainers) rather
# than the incident itself. They stay visible but cannot reach "high" materiality on their own.
_COMMENTARY = (r"worried|urged?|prepare for|what to know|how to|questions? over|explained|explainer|opinion|lessons?|"
               r"analysis|could\b.*\?|can\b.*\?|should\b.*\?|why\b.*\?")
COMMENTARY_CAP = 0.49


def is_commentary(title: str) -> bool:
    low = (title or "").lower()
    return bool(re.search(r"(?<![a-z0-9])(?:" + _COMMENTARY + r")", low)) or low.rstrip().endswith("?")


def materiality(title: str, summary: str, geography: str | None = None) -> float:
    """0-1 operational materiality from a controlled vocabulary. Only events that matched a term are
    amplified by scale/urgency cues or the Australian bonus (ordinary news stays at zero)."""
    text = f"{title} {summary}".lower()
    base = sum(w for t, w in _IMPACT_TERMS.items() if _wb(t, text))
    base += sum(pts for pats, pts in _PAIR_TERMS if all(_wb(p, text) for p in pats))
    if base == 0:
        return 0.0
    cues = min(2, sum(1 for c in _SCALE_CUES if re.search(r"(?<![a-z0-9])(?:" + c + r")(?![a-z0-9])", text)))
    au = (geography or "").upper() == "AU" or any(_wb(t, text) for t in _AU_TERMS)
    score = min(1.0, (base + cues + (1 if au else 0)) / 6)
    if is_commentary(title):
        score = min(score, COMMENTARY_CAP)
    return round(score, 3)


def event_class(text: str) -> str:
    """'advisory' (vulnerability/KEV style), 'incident' (outage, blackout, breach...), else 'other'."""
    low = (text or "").lower()
    for cls in ("advisory", "incident"):
        if any(_wb(t, low) for t in _EVENT_CLASS_TERMS[cls]):
            return cls
    return "other"


def severe_consequence(text: str) -> bool:
    low = (text or "").lower()
    return any(_wb(t, low) for t in _SEVERE_CONSEQUENCE)


def exploited(text: str) -> bool:
    low = (text or "").lower()
    return any(_wb(t, low) for t in _EXPLOITED)


def known_exposure(text: str, terms=DEFAULT_EXPOSURE_TERMS) -> bool:
    low = (text or "").lower()
    return any(_wb(t, low) for t in terms)


def confidence(kind: str, independent_publishers: int, flags: list[str]) -> float:
    c = _KIND_GRADE.get(kind, 0.3) + min(0.3, 0.1 * max(0, independent_publishers - 1))
    if any(f.startswith("headline_") and f != "headline_unverifiable_no_body" for f in flags):
        c -= 0.2
    if any(f.startswith("conflicting_") for f in flags):
        c = min(c, 0.5)
    return round(max(0.0, min(1.0, c)), 3)


def decide_priority(materiality_: float, confidence_: float, kind: str, independent_publishers: int,
                    age_hours: float | None, *, cls: str = "other", severe: bool = False,
                    is_exploited: bool = False, exposure: bool = False) -> tuple[str, dict | None]:
    """Action priority and, when escalated, the marking the Captain needs.

    Policy (Captain's direction):
    * A vulnerability/KEV advisory is NOT automatically critical. It escalates only with exploitation
      evidence AND known exposure, while fresh and credible; otherwise it is WATCH (exposure unknown).
    * A single credible report of a severe-consequence incident MAY escalate provisionally. It is then
      marked uncorroborated with a required follow-up. Multiple publishers are not a prerequisite.
    * Material but only aggregator/secondary evidence is VERIFY."""
    fresh = age_hours is not None and age_hours <= 72
    credible = confidence_ >= 0.5
    corroborated = kind == PRIMARY or independent_publishers >= 2
    if materiality_ >= 0.5 and credible and fresh:
        if cls == "advisory":
            if is_exploited and exposure:
                return "ESCALATE", {"provisional": False, "uncorroborated": False, "follow_up": None,
                                    "reason": "exploitation evidence and known exposure"}
        elif severe:
            return "ESCALATE", {"provisional": not corroborated, "uncorroborated": not corroborated,
                                "follow_up": None if corroborated else "verify with a primary source or a second report",
                                "reason": "severe operational consequence"}
    if materiality_ >= 0.5 and credible:
        return "WATCH", ({"note": "exposure unknown: check whether affected products are in use"}
                         if cls == "advisory" and not exposure else None)
    if materiality_ >= 0.5:
        return "VERIFY", None            # material but poorly evidenced: confirm before acting
    if materiality_ >= 0.25 and credible:
        return "WATCH", None
    return "REFERENCE", None


def priority(materiality_: float, confidence_: float, kind: str, independent_publishers: int,
             age_hours: float | None, **kw) -> str:
    return decide_priority(materiality_, confidence_, kind, independent_publishers, age_hours, **kw)[0]


# ── Incident correlation (any size) vs thematic clustering ────────────────────

@dataclass
class Incident:
    incident_id: str
    members: list[Assessment]
    independent_publishers: int
    first_seen: datetime | None
    last_seen: datetime | None
    flags: list[str]

    @property
    def headline(self) -> Assessment:
        return max(self.members, key=lambda a: (a.materiality, a.confidence))



# ── Incident grouping v2: entity + event class, with light stemming ────────────

_NORM = {"center": "centre", "australian": "australia", "australias": "australia", "centers": "centre"}
_GENERIC_ENTITIES = frozenset(["breaking", "live", "australia", "australian", "government", "minister", "morning", "mail", "news", "says", "after", "with", "from", "how", "why", "what", "the", "new", "friday", "monday", "tuesday", "wednesday", "thursday", "saturday", "sunday", "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december", "federal", "state"])


def _stem(w: str) -> str:
    w = _NORM.get(w, w)
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def stems(text: str) -> frozenset[str]:
    return frozenset(_stem(w) for w in tokens(text))


def entities(title: str) -> frozenset[str]:
    """Capitalised names in a headline (organisations, places), without possessives or generic words."""
    out = set()
    for w in re.findall(r"\b([A-Z][A-Za-z]{2,})(?:['’]s)?\b", title or ""):
        lw = w.lower()
        if lw not in _GENERIC_ENTITIES:
            out.add(lw)
    return frozenset(out)


def _classes(text: str) -> frozenset[str]:
    low = (text or "").lower()
    cls = set()
    if any(_wb(t, low) for t in ("blackouts?", "outages?", "without power", "cut power", "power cuts?", "power out",
                                  "transmission (?:lines?|towers?)", "degradation", "triple zero")):
        cls.add("outage")
    if any(_wb(t, low) for t in ("cyber", "breach", "ransomware", "hack(?:ed|ing)?", "attacks?", "data (?:likely )?accessed",
                                  "card skimmer", "vulnerabilit(?:y|ies)", "exploited")):
        cls.add("cyber")
    return frozenset(cls)


def same_incident_v2(a_title: str, b_title: str) -> bool:
    """Title-only judgement that two reports describe one event. Rules (any):
    1. stemmed Jaccard >= 0.45 (as v1, after stemming);
    2. same event class and >= 3 shared stems covering >= half of the shorter headline;
    3. a shared named entity, same event class and >= 2 shared stems."""
    sa, sb = stems(a_title), stems(b_title)
    if not sa or not sb:
        return False
    shared = sa & sb
    if len(shared) / len(sa | sb) >= 0.45:
        return True
    same_class = bool(_classes(a_title) & _classes(b_title))
    if same_class and len(shared) >= 3 and len(shared) / min(len(sa), len(sb)) >= 0.5:
        return True
    return bool(same_class and (entities(a_title) & entities(b_title)) and len(shared) >= 2)


def correlate_incidents(events: list[dict], *, now: datetime | None = None,
                        same_story: float = 0.45, window_hours: int = 72, grouping: str = "v2") -> list[Incident]:
    """Group reports of the SAME incident. A single report is a valid incident of size 1,
    and the result carries every incident — nothing is dropped for being small."""
    now = now or datetime.now(timezone.utc)
    items = []
    for e in events:
        ts = _parse_ts(e.get("collected_at") or e.get("published_at"))
        items.append({**e, "_ts": ts, "_family": publisher_family(e.get("source", ""), e.get("title", ""))})
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            if a["_ts"] and b["_ts"] and abs((a["_ts"] - b["_ts"]).total_seconds()) > window_hours * 3600:
                continue
            same = (same_incident_v2(a.get("title", ""), b.get("title", "")) if grouping == "v2"
                    else similarity(a.get("title", ""), b.get("title", "")) >= same_story)
            if same:
                parent[find(i)] = find(j)
    groups: dict[int, list[dict]] = {}
    for i, it in enumerate(items):
        groups.setdefault(find(i), []).append(it)

    incidents: list[Incident] = []
    for n, members in enumerate(sorted(groups.values(), key=lambda g: g[0].get("id", "")), 1):
        fams = _independent_families(members)
        texts = {m["_family"]: f"{m.get('title', '')} {m.get('summary', '')}" for m in members}
        shared_flags = conflict_flags(texts) if len(texts) >= 2 else []
        assessed = []
        for m in members:
            kind = source_kind(m.get("source", ""))
            f = headline_flags(m.get("title", ""), m.get("summary", "")) + shared_flags
            mat = materiality(m.get("title", ""), m.get("summary", ""), m.get("geography"))
            conf = confidence(kind, len(fams), f)
            age = (now - m["_ts"]).total_seconds() / 3600 if m["_ts"] else None
            text = f"{m.get('title', '')} {m.get('summary', '')}"
            prio, esc = decide_priority(mat, conf, kind, len(fams), age, cls=event_class(text),
                                        severe=severe_consequence(text), is_exploited=exploited(text),
                                        exposure=known_exposure(text))
            assessed.append(Assessment(
                event_id=str(m.get("id", "")), title=m.get("title", ""), source=m.get("source", ""),
                source_kind=kind, family=m["_family"], published=m["_ts"],
                confidence=conf, confidence_level=_level(conf, 0.75, 0.5),
                materiality=mat, materiality_level=_level(mat, 0.5, 0.25),
                priority=prio, escalation=esc, flags=f,
                legacy=m.get("legacy", {}),
            ))
        ts = [m["_ts"] for m in members if m["_ts"]]
        incidents.append(Incident(f"inc-{n:04d}", assessed, len(fams), min(ts) if ts else None,
                                  max(ts) if ts else None, shared_flags))
    return incidents


def _independent_families(members: list[dict]) -> set[str]:
    """Distinct publisher families after collapsing near-identical (syndicated) copies. An aggregator item (Google News) is a
    discovery route, never an independent corroborating publisher, whatever outlet its title names."""
    fams: dict[str, str] = {}
    for m in members:
        if source_kind(m.get("source", "")) == AGGREGATOR:
            continue
        fam = m["_family"]
        title = m.get("title", "")
        # A copy with a near-identical title from another family is syndication of
        # the same piece and adds no independent corroboration.
        if any(similarity(title, t) >= 0.85 and f != fam for f, t in fams.items()):
            continue
        fams.setdefault(fam, title)
    return set(fams)


MIN_THEME_INCIDENTS, MIN_THEME_PUBLISHERS, MIN_THEME_DAYS = 3, 3, 2


def cluster_themes(incidents: list[Incident]) -> dict:
    """Thematic trend clusters across DISTINCT incidents. A theme must be in the controlled
    vocabulary and meet all three thresholds; otherwise it is reported as not identified."""
    by_theme: dict[str, list[Incident]] = {}
    for inc in incidents:
        for t in themes_of(" ".join(f"{a.title}" for a in inc.members)):
            by_theme.setdefault(t, []).append(inc)
    themes, near_misses = [], []
    for name, incs in sorted(by_theme.items()):
        pubs = {a.family for i in incs for a in i.members if a.source_kind != CONTENT}
        days = {a.published.date() for i in incs for a in i.members if a.published}
        row = {"theme": name, "incidents": len(incs), "publishers": len(pubs), "days": len(days),
               "incident_ids": [i.incident_id for i in incs]}
        if (len(incs) >= MIN_THEME_INCIDENTS and len(pubs) >= MIN_THEME_PUBLISHERS
                and len(days) >= MIN_THEME_DAYS):
            themes.append(row)
        else:
            near_misses.append(row)
    return {"themes": themes, "below_threshold": near_misses,
            "statement": None if themes else "no thematic cluster identified"}


def incident_watch(incidents: list[Incident]) -> list[Incident]:
    """Every incident whose lead report is high-materiality — regardless of size or any cluster."""
    return sorted((i for i in incidents if i.headline.materiality_level == "high"),
                  key=lambda i: (-i.headline.materiality, -i.headline.confidence))


# ── Health evidence kinds ─────────────────────────────────────────────────────

REGISTRATION, FINDING, REVIEW, GUIDELINE, SAFETY, NON_EVIDENCE, UNCLASSIFIED = (
    "registration", "finding", "systematic_review", "guideline", "safety_advisory",
    "non_evidence", "publication_unclassified")

_REVIEW = re.compile(r"systematic review|meta-?analysis|umbrella review|scoping review|cochrane", re.IGNORECASE)
_GUIDE = re.compile(r"\bguidelines?\b|consensus statement|position statement|practice parameter|"
                    r"recommendations for|clinical practice", re.IGNORECASE)
_SAFETY = re.compile(r"safety communication|drug safety|recall|boxed warning|safety alert|"
                     r"health advisory|\bwithdrawn\b|\bterminated\b|\bsuspended\b", re.IGNORECASE)
_NON_EVIDENCE = re.compile(r"^\s*\[(world report|obituary|editorial|comment|correspondence|news|"
                           r"perspective|in brief|offline)\b", re.IGNORECASE)
_DESIGN = re.compile(r"randomi[sz]ed|cohort|case-control|cross-sectional|observational|"
                     r"double-blind|placebo-controlled|prospective|retrospective", re.IGNORECASE)


def classify_health_record(title: str, source: str, signal_type: str | None = None,
                           summary: str = "") -> dict:
    """Typed evidence kind. `signal_type` (which labels every registry entry 'study_result')
    is deliberately ignored for registry sources."""
    text = f"{title} {summary}"
    src = (source or "").lower()
    is_registry = "clinicaltrials" in src or bool(re.search(r"\bNCT\d{8}\b", text))
    if _NON_EVIDENCE.search(title or ""):
        kind = NON_EVIDENCE
    elif is_registry:
        kind = SAFETY if (signal_type == "safety_alert" or _SAFETY.search(summary or "")) else REGISTRATION
    elif signal_type == "safety_alert" or _SAFETY.search(text) or any(
            k in src for k in ("fda", "cdc", "who", "tga")):
        kind = SAFETY
    elif _REVIEW.search(text):
        kind = REVIEW
    elif _GUIDE.search(text):
        kind = GUIDELINE
    elif _DESIGN.search(text):
        kind = FINDING
    else:
        kind = UNCLASSIFIED
    return {"kind": kind, "demonstrated_result": kind in (FINDING, REVIEW),
            "design": (m.group(0).lower() if (m := _DESIGN.search(text)) else None)}


def summarise_health(records: list[dict]) -> dict:
    typed = [classify_health_record(r.get("title", ""), r.get("source", ""), r.get("signal_type"),
                                    r.get("summary", "")) for r in records]
    counts = Counter(t["kind"] for t in typed)
    return {"total": len(records), "by_kind": dict(counts),
            "demonstrated_results": sum(1 for t in typed if t["demonstrated_result"]),
            "registrations_counted_as_results": 0}


# ── Absence typing ────────────────────────────────────────────────────────────

OBSERVED, NOT_OBSERVED, INSUFFICIENT, SOURCE_OUTAGE = (
    "observed", "not_observed", "insufficient_sample", "source_outage")


def observation_state(count: int, *, minimum: int = 1, collector_failed: bool = False,
                      baseline_per_week: float | None = None) -> str:
    """Lack of evidence is never evidence of no issue. A silent source relative to its own
    baseline, or a failed collector, is an outage — not a quiet week."""
    if collector_failed:
        return SOURCE_OUTAGE
    if count == 0:
        return SOURCE_OUTAGE if baseline_per_week and baseline_per_week >= 5 else NOT_OBSERVED
    return OBSERVED if count >= minimum else INSUFFICIENT


# ── Narrative assurance ───────────────────────────────────────────────────────

@dataclass
class Claim:
    text: str
    evidence_ids: list[str]


@dataclass
class ValidationResult:
    ok: bool
    failures: list[str]


def _content_tokens(text: str) -> set[str]:
    return set(tokens(text))


def validate_claims(claims: list[Claim], evidence: dict[str, dict], *, min_support: float = 0.6) -> ValidationResult:
    """A claim is supported only if (a) it cites evidence that exists, (b) the cited text
    actually contains its content terms and exact figures, and (c) a causal claim is
    backed by >=2 independent publishers and a source that itself states the causation."""
    failures: list[str] = []
    for n, c in enumerate(claims, 1):
        tag = f"claim {n}"
        if not c.evidence_ids:
            failures.append(f"{tag}: no evidence cited")
            continue
        missing = [i for i in c.evidence_ids if i not in evidence]
        if missing:
            failures.append(f"{tag}: unknown evidence id {missing[0]}")
            continue
        cited = [evidence[i] for i in c.evidence_ids]
        corpus = " ".join(f"{e.get('title', '')} {e.get('summary', '')}" for e in cited)
        want = _content_tokens(c.text)
        if want and len(want & _content_tokens(corpus)) / len(want) < min_support:
            failures.append(f"{tag}: cited evidence does not support the wording")
        flat = corpus.replace(",", "")
        for num in re.findall(r"\d[\d,\.]*\d|\d", c.text):
            if num.replace(",", "") not in flat:
                failures.append(f"{tag}: figure {num} not found in cited evidence")
        if has_causal_language(c.text):
            fams = {publisher_family(e.get("source", ""), e.get("title", "")) for e in cited
                    if source_kind(e.get("source", "")) != AGGREGATOR}      # an aggregator copy never corroborates
            states = any(has_causal_language(f"{e.get('title', '')} {e.get('summary', '')}") for e in cited)
            if len(fams) < 2 or not states:
                failures.append(f"{tag}: causal claim without two independent sources stating the cause")
    return ValidationResult(not failures, failures)


def render_narrative(claims: list[Claim], evidence: dict[str, dict], deterministic_text: str) -> dict:
    """Use the narrative only if every claim validates; otherwise the deterministic fallback."""
    result = validate_claims(claims, evidence)
    if result.ok and claims:
        return {"text": " ".join(c.text for c in claims), "mode": "narrative", "failures": []}
    return {"text": deterministic_text, "mode": "deterministic_fallback", "failures": result.failures}


# ── Durable snapshots and gated forecasts ─────────────────────────────────────

MIN_FORECAST_SNAPSHOTS, MIN_FORECAST_SPAN_DAYS = 4, 21


class SnapshotStore:
    """Append-only JSONL with atomic, fsynced writes and explicit retention.
    Each row carries the methodology version so history is never reinterpreted."""

    def __init__(self, path: str, retention_weeks: int = 104):
        self.path = path
        self.retention_weeks = retention_weeks

    def append(self, snapshot: dict) -> None:
        row = {**snapshot, "method_version": snapshot.get("method_version", METHOD_VERSION)}
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def load(self) -> list[dict]:
        rows = []
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        continue          # a torn/corrupt line must never break the series
        except FileNotFoundError:
            return []
        return sorted(rows, key=lambda r: r.get("date", ""))

    def prune(self, now: datetime | None = None) -> int:
        """Drop rows older than the retention window; returns how many were removed."""
        now = now or datetime.now(timezone.utc)
        cutoff = (now - timedelta(weeks=self.retention_weeks)).date().isoformat()
        rows = self.load()
        keep = [r for r in rows if r.get("date", "") >= cutoff]
        if len(keep) == len(rows):
            return 0
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(r, sort_keys=True) + "\n" for r in keep)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
        return len(rows) - len(keep)


def forecast_growth(snapshots: list[dict], limit_mb: float = 500.0) -> dict:
    """Gated forecast: refuses to forecast until there is enough, ordered history. A drop in size
    (cleanup/retention) starts a new segment so deletions don't masquerade as shrinking growth."""
    pts = []
    for s in snapshots:
        d = _parse_ts(s.get("date"))
        if d is not None and isinstance(s.get("size_mb"), (int, float)):
            pts.append((d, float(s["size_mb"])))
    pts.sort()
    start = 0
    for i in range(1, len(pts)):
        if pts[i][1] < pts[i - 1][1] * 0.95:             # >5% drop = cleanup/retention event
            start = i
    seg = pts[start:]
    notes = [] if start == 0 else ["size dropped >5% earlier (cleanup/retention); forecast uses the segment after it"]
    span = (seg[-1][0] - seg[0][0]).days if len(seg) >= 2 else 0
    if len(seg) < MIN_FORECAST_SNAPSHOTS or span < MIN_FORECAST_SPAN_DAYS:
        return {"available": False, "reason": (f"insufficient history: {len(seg)} snapshot(s) over "
                f"{span} day(s); need {MIN_FORECAST_SNAPSHOTS}+ over {MIN_FORECAST_SPAN_DAYS}+ days"),
                "notes": notes}
    slopes = sorted(((b[1] - a[1]) / max((b[0] - a[0]).days, 1)) * 7
                    for i, a in enumerate(seg) for b in seg[i + 1:] if (b[0] - a[0]).days > 0)
    mid = slopes[len(slopes) // 2]
    low, high = slopes[len(slopes) // 4], slopes[(3 * len(slopes)) // 4]
    cur = seg[-1][1]

    def weeks(rate):
        return None if rate <= 0 else round((limit_mb - cur) / rate, 1)
    return {"available": True, "current_mb": cur, "mb_per_week": round(mid, 2),
            "mb_per_week_range": [round(low, 2), round(high, 2)],
            "weeks_to_limit": weeks(mid), "weeks_to_limit_range": [weeks(high), weeks(low)],
            "notes": notes}


def _split_future(rows: list[dict], now: datetime, keys: tuple[str, ...], *, hours: int):
    keep, future = [], []
    for r in rows:
        ts = next((_parse_ts(r.get(k)) for k in keys if r.get(k)), None)
        (future if ts is not None and ts > now + timedelta(hours=hours) else keep).append(r)
    return keep, future


# ── Weekly evidence assembly (prototype) ──────────────────────────────────────

def build_weekly_evidence(*, events: list[dict], universe: dict, health_records: list[dict],
                          capacity: dict, db_snapshots: list[dict], now: datetime | None = None) -> dict:
    """Everything a weekly product needs, from one place. `universe` carries EXACT totals from
    aggregate queries; `events` may be a candidate pool, and the result says so."""
    now = now or datetime.now(timezone.utc)
    # Future-dated data is never evidence: exclude it from events and capacity, and say so.
    events, future_events = _split_future(events, now, ("collected_at", "published_at"), hours=1)
    cap_rows, future_cap = _split_future(capacity.get("entries", []), now, ("log_date",), hours=24)
    incidents = correlate_incidents(events, now=now)
    heads = [i.headline for i in incidents]
    return {
        "method_version": METHOD_VERSION,
        "universe": {**universe, "assessed_pool": len(events), "pool_is_sample": len(events) < universe.get("usable", len(events))},
        "axes": {
            "confidence": dict(Counter(a.confidence_level for a in heads)),
            "materiality": dict(Counter(a.materiality_level for a in heads)),
            "priority": dict(Counter(a.priority for a in heads)),
        },
        "incident_watch": [{"incident": i.incident_id, "title": i.headline.title,
                            "source": i.headline.source, "confidence": i.headline.confidence_level,
                            "priority": i.headline.priority, "publishers": i.independent_publishers,
                            "flags": i.headline.flags} for i in incident_watch(incidents)],
        "themes": cluster_themes(incidents),
        "health": summarise_health(health_records),
        "capacity": {"state": observation_state(len(cap_rows), minimum=4),
                     "observations": len(cap_rows), "excluded_future": len(future_cap),
                     **{k: capacity[k] for k in ("source",) if k in capacity}},
        "excluded_future_events": len(future_events),
        "database": forecast_growth(db_snapshots),
        "incidents": incidents,
    }


# ── Deterministic rendering of the Weekly Intelligence & Decision Brief ───────

_PRIO_ORDER = {"ESCALATE": 0, "WATCH": 1, "VERIFY": 2, "REFERENCE": 3}


def render_intelligence_brief(evidence: dict, *, week_label: str, health: dict | None = None,
                              health_leads: list[str] | None = None, max_items: int = 8) -> str:
    """Plain-text brief built ONLY from structured facts in `evidence` (no LLM, no free prose
    claims). Every statement is a count, a typed label, or a quoted headline with its source and
    the words 'as reported by'. Nothing here is sent anywhere."""
    u = evidence["universe"]
    incs = evidence["incidents"]
    watch = sorted(incident_watch(incs), key=lambda i: (_PRIO_ORDER[i.headline.priority], -i.headline.materiality))
    themes = evidence["themes"]
    cap, db = evidence["capacity"], evidence["database"]
    L: list[str] = [f"WEEKLY INTELLIGENCE & DECISION BRIEF — {week_label}",
                    f"Method {evidence['method_version']} · shadow output, not sent", ""]

    L += ["1. EXECUTIVE SUMMARY"]
    n_esc = sum(1 for i in watch if i.headline.priority == "ESCALATE")
    L.append(f"- {len(watch)} high-materiality incident(s) identified from {len(incs)} assessed incidents; "
             f"{n_esc} meet the escalation rule.")
    named = [t["theme"].replace("_", " ") for t in themes["themes"]]
    L.append("- Themes meeting the threshold: " + (", ".join(named) if named else "none (no thematic cluster identified)") + ".")
    L.append(f"- Evidence base: {u.get('usable', '?')} usable events this week; {u['assessed_pool']} assessed"
             + (" (a candidate pool, not the full week)" if u.get("pool_is_sample") else "") + ".")
    L.append("")

    L += ["2. PRIORITY DEVELOPMENTS (priority · confidence · materiality are separate judgements)"]
    for i in watch[:max_items]:
        h = i.headline
        L.append(f"- [{h.priority}] {h.title[:90]} — as reported by {h.source}"
                 f" ({i.independent_publishers} independent publisher(s)); confidence {h.confidence_level}, "
                 f"materiality {h.materiality_level}" + (f"; flags: {', '.join(h.flags)}" if h.flags and h.flags != ['headline_unverifiable_no_body'] else ""))
    if len(watch) > max_items:
        L.append(f"- … and {len(watch) - max_items} more high-materiality incident(s) not shown.")
    if not watch:
        L.append("- None. (Absence of high-materiality incidents in the assessed pool is not evidence of no issue.)")
    L.append("")

    def theme_line(t):
        return (f"- {t['theme'].replace('_', ' ')}: {t['incidents']} distinct incidents from {t['publishers']} "
                f"evidence-bearing publishers over {t['days']} day(s) (keyword-defined, not yet reviewed).")
    L += ["3. OPERATIONAL RESILIENCE IMPLICATIONS"]
    res = [t for t in themes["themes"] if t["theme"] in ("energy_grid", "technology_outages")]
    L += [theme_line(t) for t in res] or ["- No resilience theme met the threshold."]
    L += ["- Implications are limited to what the cited reports state; no causal link between incidents is asserted.", ""]

    L += ["4. AI AND GOVERNANCE IMPLICATIONS"]
    ai = [t for t in themes["themes"] + themes["below_threshold"] if t["theme"] == "ai_cyber"]
    for t in ai:
        met = t in themes["themes"]
        L.append(theme_line(t) + ("" if met else " Below threshold: not reported as a theme."))
    if not ai:
        L.append("- No AI-related theme observed.")
    L.append("")

    L += ["5. HEALTH AND NEUROSCIENCE FINDINGS"]
    hs = health or evidence["health"]
    L.append(f"- {hs.get('total', 0)} health records; {hs.get('registrations', 0)} are trial registrations "
             f"(a registration shows a study exists, not what it found) and {hs.get('other', 0)} are other records.")
    L.append(f"- Demonstrated results counted from registrations: {evidence['health'].get('registrations_counted_as_results', 0)}.")
    for lead in (health_leads or []):
        L.append(f"- Lead (title only, not read in full): {lead}")
    L.append("- No efficacy or safety conclusion is drawn from records that were not read.")
    L.append("")

    L += ["6. CROSS-DOMAIN DEPENDENCIES"]
    if len(themes["themes"]) >= 2:
        L.append("- Themes co-occurring this week: " + ", ".join(t["theme"].replace("_", " ") for t in themes["themes"])
                 + ". No dependency between them is asserted unless a cited source states it.")
    else:
        L.append("- No co-occurring themes met the threshold.")
    L.append("")

    L += ["7. AUSTRALIAN RELEVANCE"]
    au = u.get("au_events")
    L.append(f"- {au} of {u.get('usable', '?')} usable events are tagged Australian." if au is not None
             else "- Australian share not supplied.")
    L.append("")

    L += ["8. EMERGING RISKS AND RESEARCH GAPS"]
    verify = [i for i in watch if i.headline.priority == "VERIFY"]
    L.append(f"- {len(verify)} material incident(s) rest on aggregator/secondary evidence only and need primary confirmation.")
    L.append(f"- Capacity data: {cap['state'].replace('_', ' ')} ({cap['observations']} observation(s)); "
             "no inference about recovery is made."
             + (f" {cap['excluded_future']} future-dated record(s) excluded." if cap.get("excluded_future") else ""))
    L.append("- Database growth: " + (f"{db['mb_per_week']} MB/week (range {db['mb_per_week_range']})" if db["available"]
                                      else f"no forecast — {db['reason']}"))
    L.append("")

    L += ["9. RECOMMENDED ACTIONS (for the Captain's decision)"]
    for i in watch:
        if i.headline.priority == "ESCALATE":
            L.append(f"- Review now: {i.headline.title[:80]}")
    for i in verify[:5]:
        L.append(f"- Seek primary confirmation: {i.headline.title[:80]}")
    L.append("- Treat every item above as a lead for verification, not a finding, until a primary source is checked.")
    L.append("")

    L += ["10. EVIDENCE CONFIDENCE AND LIMITATIONS",
          "- Materiality uses a controlled keyword vocabulary; recall on the labelled set is limited (see evaluation).",
          "- Incident grouping uses title similarity and splits differently-worded reports of one event.",
          "- Headline-support checks need article bodies; without them headlines are 'unverifiable', not 'supported'.",
          "- Themes are keyword-defined and unreviewed."]
    return "\n".join(L)
