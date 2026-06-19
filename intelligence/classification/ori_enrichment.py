"""
ORI Intelligence Extraction enrichment (WP4) — 100% rule-based, no LLM.

Takes a ClassifiedEvent (produced by the existing rule classifier) plus the
brief context and derives the richer ORI fields that the daily digest needs:

  - resilience_themes   (controlled vocabulary, list)
  - regulatory_topic    (CPS230 | SOCI_Act | CIRMP | APRA_Prudential | ...)
  - organisation        (named entity, best-effort)
  - watch_item_status   (active_incident | emerging | monitoring | regulatory_horizon | closed)
  - executive_relevance (high | medium | low)

Deterministic and offline. Optional LLM refinement (WP4 §1.2 Stage 2) is layered
on top by the caller and is never required for a correct result.
"""

from __future__ import annotations

import re
from typing import Optional

from intelligence.models import ClassifiedEvent

# ─── Theme taxonomy (WP4 §2) ──────────────────────────────────────────────────

_THEME_RULES: list[tuple[str, list[str]]] = [
    ("third_party_risk",        ["third party", "third-party", "vendor", "supplier",
                                 "outsourc", "service provider", "contractor", "msp"]),
    ("concentration_risk",      ["concentration", "single provider", "market share",
                                 "hyperscaler", "dominant", "sole provider"]),
    ("single_point_of_failure", ["single point of failure", "spof", "hub failure",
                                 "core system", "one link", "sole"]),
    ("service_continuity",      ["outage", "downtime", "disruption", "restored",
                                 "unavailable", "service interruption", "continuity"]),
    ("cyber_resilience",        ["cyber", "ransomware", "malware", "breach",
                                 "intrusion", "hack", "phishing", "exploit"]),
    ("data_protection",         ["data breach", "personal information", "pii",
                                 "exfiltration", "privacy", "oaic"]),
    ("cloud_dependency",        ["cloud", "aws", "azure", "google cloud", "gcp",
                                 "saas", "datacentre", "data centre"]),
    ("telco_resilience",        ["network outage", "mobile", "nbn", "carrier",
                                 "telco", "telecommunications", "vodafone", "telstra",
                                 "optus", "tpg"]),
    ("supply_chain",            ["supply chain", "logistics", "shipping", "port",
                                 "procurement", "import"]),
    ("regulatory_change",       ["amendment", "effective", "new standard", "consultation",
                                 "legislation", "comes into force", "takes effect"]),
    ("outsourcing_risk",        ["material service provider", "outsourc", "offshoring",
                                 "managed service"]),
    ("critical_infrastructure", ["critical infrastructure", "soci", "energy", "water",
                                 "ports", "cirmp"]),
    ("payments_resilience",     ["payment", "settlement", "becs", "card scheme",
                                 "npp", "osko", "eftpos"]),
    ("geopolitical_risk",       ["sanction", "conflict", "cross-border", "nation state",
                                 "state-sponsored", "geopolitical"]),
    ("operational_recovery",    ["tolerance", "recovery time", "scenario test",
                                 "bcp", "disaster recovery", "resilience testing",
                                 "stress test"]),
]

# ─── Regulatory topic map (WP4 §3) ────────────────────────────────────────────

_REG_TOPIC_RULES: list[tuple[str, list[str]]] = [
    ("CPS230",          ["cps 230", "cps230"]),
    ("SOCI_Act",        ["soci", "security of critical infrastructure"]),
    ("CIRMP",           ["cirmp", "risk management program"]),
    ("APRA_Prudential", ["cps 234", "cps234", "cpg ", "prudential standard", "apra"]),
    ("ASIC",            ["asic", "market integrity"]),
    ("RBA",             ["rba", "payments system board", "reserve bank"]),
    ("Privacy_Act",     ["privacy act", "oaic", "notifiable data breach", "ndb scheme"]),
]

# ─── Organisation extraction (best-effort) ────────────────────────────────────

_KNOWN_ORGS = [
    "Vodafone", "Telstra", "Optus", "TPG", "NBN", "ANZ", "CBA", "NAB", "Westpac",
    "Macquarie", "APRA", "ASIC", "RBA", "ACSC", "ASD", "AEMO", "AusPayNet", "ASX",
    "AWS", "Azure", "Microsoft", "Google Cloud", "Salesforce", "Oracle", "Cloudflare",
    "Ochre Health", "Mackay Sugar", "SWIFT", "Medibank", "Latitude",
]
_ORG_CAP_RE = re.compile(r"\b([A-Z][A-Za-z0-9&]+(?:\s+[A-Z][A-Za-z0-9&]+){0,2})\b")

# Genuine in-progress indicators only — the nouns "outage"/"incident" describe
# the event, not its current status, so they are deliberately excluded.
_ACTIVE_WORDS = ["investigating", "ongoing", "unresolved", "still down",
                 "escalating", "currently", "live incident"]
_CLOSED_WORDS = ["restored", "resolved", "remediated", "recovered", "cleared", "closed"]
_FUTURE_WORDS = ["effective", "from july", "comes into force", "takes effect",
                 "will apply", "upcoming", "amendments effective"]


# ─── Public API ────────────────────────────────────────────────────────────────

def map_themes(text: str, event_type: str) -> list[str]:
    t = text.lower()
    themes: list[str] = []
    for theme, kws in _THEME_RULES:
        if any(kw in t for kw in kws):
            themes.append(theme)
    # Event-type guarantees baseline themes even if keywords are sparse. A
    # telco/tech/payments outage is, by definition, an external dependency event
    # (mission worked example lists third-party risk for a telco outage).
    et_defaults = {
        "telecom_outage":         ["telco_resilience", "third_party_risk", "service_continuity"],
        "cyber":                  ["cyber_resilience"],
        "regulatory":             ["regulatory_change"],
        "payments_disruption":    ["payments_resilience", "third_party_risk"],
        "technology_outage":      ["cloud_dependency", "third_party_risk", "service_continuity"],
        "third_party_disruption": ["third_party_risk"],
        "supply_chain":           ["supply_chain", "third_party_risk"],
        "energy_disruption":      ["critical_infrastructure"],
    }.get(event_type, [])
    for theme in et_defaults:
        if theme not in themes:
            themes.append(theme)
    return themes


def map_regulatory_topic(text: str) -> Optional[str]:
    t = text.lower()
    for topic, kws in _REG_TOPIC_RULES:
        if any(kw in t for kw in kws):
            return topic
    return None


def extract_organisation(text: str) -> Optional[str]:
    for org in _KNOWN_ORGS:
        if org.lower() in text.lower():
            return org
    # Fallback: first capitalised multi-word phrase that isn't a sentence start noise.
    for m in _ORG_CAP_RE.finditer(text):
        cand = m.group(1)
        if cand.lower() not in ("major", "the", "australia", "australian", "key", "cps"):
            return cand
    return None


def derive_watch_status(text: str, event_type: str, recurrence: int = 0) -> str:
    t = text.lower()
    if event_type == "regulatory" and any(w in t for w in _FUTURE_WORDS):
        return "regulatory_horizon"
    active = any(w in t for w in _ACTIVE_WORDS)
    if any(w in t for w in _CLOSED_WORDS) and not active:
        return "closed"
    if active:
        return "active_incident"
    if recurrence >= 3:
        return "emerging"
    return "monitoring"


def derive_executive_relevance(event: ClassifiedEvent, in_implications: bool) -> str:
    high_types = {"telecom_outage", "payments_disruption", "cyber", "regulatory"}
    if (event.cps230_relevance
            or event.banking_relevance == "high"
            or in_implications
            or (event.event_type in high_types and event.geography == "AU")):
        return "high"
    if event.banking_relevance == "medium":
        return "medium"
    # medium if a notable concentration/dependency theme is present
    return "low"


def enrich(event: ClassifiedEvent, *, in_implications: bool = False,
           recurrence: int = 0) -> dict:
    """Return the ORI column dict for an event. Deterministic, offline."""
    text = f"{event.raw_title} {event.raw_summary or ''}"
    themes = map_themes(text, event.event_type)
    exec_rel = derive_executive_relevance(event, in_implications)
    if exec_rel == "low" and any(
        th in themes for th in ("concentration_risk", "third_party_risk", "cloud_dependency")
    ):
        exec_rel = "medium"
    return {
        "resilience_themes":   themes,
        "regulatory_topic":    map_regulatory_topic(text),
        "organisation":        extract_organisation(text),
        "watch_item_status":   derive_watch_status(text, event.event_type, recurrence),
        "executive_relevance": exec_rel,
    }
