"""
Event classifier — 100% rule-based, no LLM dependency.

Classifies each IntelligenceItem across:
  - event_type
  - geography
  - sector
  - operational_relevance (0.0–1.0)
  - customer_impact (low/medium/high)
  - banking_relevance (low/medium/high)
  - cps230_relevance (bool)
  - dependency_risk (bool)
  - confidence (0.0–1.0)

All rules are keyword-based against title + summary text.
Rules are additive: later rules can increase scores, not decrease them.
"""

import re
from intelligence.models import ClassifiedEvent, IntelligenceItem
from intelligence.classification.deduplicator import compute_hash


# ─── Keyword tables ───────────────────────────────────────────────────────────

_EVENT_TYPE_RULES: list[tuple[str, list[str]]] = [
    ("cyber",                ["cyber", "ransomware", "malware", "phishing", "breach", "vulnerability",
                              "exploit", "cve", "ddos", "intrusion", "threat actor", "zero-day",
                              "data leak", "credential", "acsc", "incident response", "patch",
                              "critical security", "advisory"]),
    ("regulatory",           ["apra", "asic", "rba", "oaic", "asd", "austrac", "accc",
                              "regulation", "compliance", "cps 230", "cps230", "prudential",
                              "enforcement", "licence", "penalty", "breach notice",
                              "consultation paper", "information paper", "policy", "legislation"]),
    ("technology_outage",    ["outage", "incident", "degraded", "unavailable", "service disruption",
                              "system failure", "service interruption", "aws", "azure", "google cloud",
                              "microsoft", "salesforce", "servicenow", "cloud", "platform",
                              "api failure", "latency", "error rate"]),
    ("telecom_outage",       ["telstra", "optus", "tpg", "vodafone", "nbn", "network outage",
                              "mobile network", "broadband", "telecommunications", "telco",
                              "internet outage", "connectivity"]),
    ("payments_disruption",  ["payment", "eftpos", "bpay", "osko", "npp", "rba payment",
                              "clearing", "settlement", "swift", "cards", "atm",
                              "auspaynet", "direct entry", "pe/cs", "high value", "hvcs"]),
    ("energy_disruption",    ["aemo", "power outage", "electricity", "gas supply", "energy",
                              "grid", "load shedding", "blackout", "generation", "nem"]),
    ("severe_weather",       ["storm", "cyclone", "flood", "bushfire", "fire", "heatwave",
                              "bom", "bureau of meteorology", "emergency warning", "evacuation",
                              "cfa", "ses", "rfs", "severe weather", "rainfall", "wind warning"]),
    ("transport_disruption", ["ptv", "train", "tram", "bus", "airport", "flight", "disruption",
                              "transurban", "toll", "road closure", "freeway", "motorway",
                              "sydney trains", "metro", "transport"]),
    ("physical_security",    ["physical security", "bomb threat", "suspicious package",
                              "armed robbery", "protest", "blockade", "building evacuation",
                              "lockdown", "security incident"]),
    ("third_party_disruption", ["third party", "vendor", "supplier", "outsourced", "managed service",
                                "service provider", "contractor", "dependency failure"]),
    ("geopolitical",         ["sanctions", "geopolitical", "nation state", "espionage",
                              "critical infrastructure attack", "state-sponsored", "tariff",
                              "trade disruption", "diplomatic"]),
    ("supply_chain",         ["supply chain", "logistics disruption", "port", "customs",
                              "import", "shipping delay", "procurement"]),
    ("workforce",            ["strike", "industrial action", "workforce", "staffing",
                              "pandemic", "covid", "illness", "absenteeism"]),
]

_GEOGRAPHY_AU = [
    "australia", "australian", "victoria", "new south wales", "queensland",
    "south australia", "western australia", "tasmania", "northern territory",
    "act", "canberra", "melbourne", "sydney", "brisbane", "perth", "adelaide",
    "hobart", "darwin", "apra", "asic", "rba", "acsc", "asd", "aemo",
    "bom", "cfa", "ses", "ptv", "transurban", "telstra", "optus", "nbn",
    "vic", "nsw", "qld", "sa", "wa", "tas", "nt",
]

_GEOGRAPHY_APAC = [
    "asia pacific", "apac", "singapore", "new zealand", "hong kong", "japan",
    "china", "india", "south korea", "indonesia", "malaysia", "philippines",
    "thailand", "taiwan",
]

_BANKING_KEYWORDS = [
    "bank", "banking", "financial institution", "anz", "cba", "nab", "westpac",
    "big four", "big 4", "macquarie", "credit union", "building society",
    "superannuation", "super fund", "insurance", "apra regulated",
    "payment system", "clearing", "settlement", "npp", "osko",
]

_CPS230_KEYWORDS = [
    "cps 230", "cps230", "operational risk", "operational resilience",
    "material service provider", "msp", "third party risk", "service continuity",
    "business continuity", "bcp", "drp", "disaster recovery",
    "critical operations", "critical functions", "prudential standard",
    "apra", "regulated entity", "incident management",
]

_DEPENDENCY_KEYWORDS = [
    "cloud", "aws", "azure", "google cloud", "microsoft", "salesforce",
    "servicenow", "third party", "outsourced", "managed service",
    "vendor", "supplier", "service provider", "critical dependency",
    "telstra", "optus", "nbn", "swift", "visa", "mastercard",
]

_HIGH_IMPACT_KEYWORDS = [
    "critical", "severe", "major", "significant", "widespread", "nationwide",
    "national outage", "extended outage", "data breach", "ransomware", "zero-day",
    "emergency", "evacuation", "fatalities", "mass disruption",
]

_MEDIUM_IMPACT_KEYWORDS = [
    "degraded", "partial", "some customers", "intermittent", "delays",
    "affected users", "impacted", "disruption", "warning", "advisory",
]

# Category → base operational relevance
_CATEGORY_RELEVANCE = {
    "regulatory":             0.7,
    "emergency_management":   0.6,
    "critical_infrastructure": 0.75,
    "cloud_technology":       0.65,
    "banking_payments":       0.80,
    "transport":              0.35,
    "media":                  0.25,
}


def classify(item: IntelligenceItem) -> ClassifiedEvent:
    """
    Classify a single IntelligenceItem.
    All scoring is deterministic and LLM-free.
    """
    text = f"{item.raw_title} {item.raw_summary or ''}".lower()
    words = set(re.findall(r"[\w\-']+", text))

    # ── Event type ────────────────────────────────────────────────────────────
    event_type = "other"
    best_match = 0
    for etype, keywords in _EVENT_TYPE_RULES:
        count = sum(1 for kw in keywords if kw in text)
        if count > best_match:
            best_match = count
            event_type = etype

    # ── Geography ─────────────────────────────────────────────────────────────
    au_hits    = sum(1 for kw in _GEOGRAPHY_AU   if kw in text)
    apac_hits  = sum(1 for kw in _GEOGRAPHY_APAC if kw in text)
    if au_hits > 0:
        geography = "AU"
    elif apac_hits > 0:
        geography = "APAC"
    else:
        geography = "GLOBAL"

    # ── Sector ────────────────────────────────────────────────────────────────
    sector = _infer_sector(event_type, text)

    # ── Operational relevance ─────────────────────────────────────────────────
    # Start from category base, boost for AU geography and high-impact signals
    from intelligence.persistence import intelligence_store as store
    # We don't have category here — use event_type to approximate
    op_rel = _base_op_relevance(event_type)
    if geography == "AU":
        op_rel = min(1.0, op_rel + 0.15)
    if any(kw in text for kw in _HIGH_IMPACT_KEYWORDS):
        op_rel = min(1.0, op_rel + 0.20)

    # ── Customer impact ───────────────────────────────────────────────────────
    if any(kw in text for kw in _HIGH_IMPACT_KEYWORDS):
        customer_impact = "high"
    elif any(kw in text for kw in _MEDIUM_IMPACT_KEYWORDS):
        customer_impact = "medium"
    else:
        customer_impact = "low"

    # ── Banking relevance ─────────────────────────────────────────────────────
    banking_hits = sum(1 for kw in _BANKING_KEYWORDS if kw in text)
    if banking_hits >= 3 or event_type in ("regulatory", "payments_disruption"):
        banking_relevance = "high"
    elif banking_hits >= 1 or event_type in ("technology_outage", "cyber"):
        banking_relevance = "medium"
    else:
        banking_relevance = "low"

    # ── CPS 230 relevance ─────────────────────────────────────────────────────
    cps230_hits = sum(1 for kw in _CPS230_KEYWORDS if kw in text)
    cps230_relevance = cps230_hits >= 1 or event_type == "regulatory"

    # ── Dependency risk ───────────────────────────────────────────────────────
    dep_hits = sum(1 for kw in _DEPENDENCY_KEYWORDS if kw in text)
    dependency_risk = dep_hits >= 2 or event_type in ("technology_outage", "telecom_outage", "third_party_disruption")

    # ── Confidence ────────────────────────────────────────────────────────────
    # Source confidence weight + signal strength (more keyword hits = higher confidence)
    confidence = round(
        min(1.0, item.source_confidence_weight * 0.7 + min(best_match, 5) * 0.06), 2
    )

    dedup_hash = compute_hash(item)

    return ClassifiedEvent(
        event_id=str(__import__("uuid").uuid4()),
        source_id=item.source_id,
        source_name=item.source_name,
        source_priority=item.source_priority,
        source_confidence_weight=item.source_confidence_weight,
        raw_title=item.raw_title,
        raw_summary=item.raw_summary,
        canonical_url=item.canonical_url,
        published_at=item.published_at,
        collected_at=item.collected_at,
        dedup_hash=dedup_hash,
        event_type=event_type,
        geography=geography,
        sector=sector,
        operational_relevance=round(op_rel, 2),
        customer_impact=customer_impact,
        banking_relevance=banking_relevance,
        cps230_relevance=cps230_relevance,
        dependency_risk=dependency_risk,
        confidence=confidence,
    )


def _base_op_relevance(event_type: str) -> float:
    return {
        "regulatory":              0.70,
        "cyber":                   0.75,
        "technology_outage":       0.65,
        "telecom_outage":          0.60,
        "payments_disruption":     0.80,
        "energy_disruption":       0.65,
        "severe_weather":          0.55,
        "transport_disruption":    0.35,
        "physical_security":       0.45,
        "third_party_disruption":  0.60,
        "geopolitical":            0.40,
        "supply_chain":            0.40,
        "workforce":               0.35,
        "other":                   0.20,
    }.get(event_type, 0.20)


def _infer_sector(event_type: str, text: str) -> str:
    if event_type in ("regulatory", "payments_disruption") or any(k in text for k in ["bank", "financial"]):
        return "financial_services"
    if event_type in ("technology_outage", "telecom_outage"):
        return "technology"
    if event_type == "energy_disruption":
        return "energy"
    if event_type == "severe_weather":
        return "emergency_management"
    if event_type == "transport_disruption":
        return "transport"
    if event_type == "cyber":
        return "cyber_security"
    return "cross_sector"
