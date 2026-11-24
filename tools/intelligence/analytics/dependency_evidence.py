"""Deterministic extraction of EXPLICITLY STATED provider dependencies.

NON-PRODUCTION, default OFF, not wired into any service, brief or schedule. It is enabled only by
``DEPENDENCY_EVIDENCE_ENABLED=1`` or ``enabled=True``. Offline: no network, no database.

Record shape (every record keeps the verbatim ``evidence_span`` it came from)::

    provider_from   the dependent party (the one that depends on / is supplied by / is hosted on ``provider_to``)
    provider_to     the party depended on
    relation        depends_on | supplied_by | hosted_on
    relation_basis  documented | demonstrated_operational        (never merged, never promoted)
    evidence_span   verbatim text the record was read from
    source_url, source_class, observed_at

``relation_basis`` (owner direction):
    documented                 a vendor, status-page or regulator DOCUMENT states the dependency or sub-processor
                               (source_class in DOCUMENTED_CLASSES).
    demonstrated_operational   an observed incident in which a failure at ``provider_to`` is explicitly reported as
                               causing impact at ``provider_from`` (source_class in DEMONSTRATED_CLASSES).
A documented relationship is never reported as demonstrated, and an incident is never reported as documented.

What is NOT extracted (returned in ``excluded`` with a reason, never as a record): static supply claims in news text
("built on Anthropic", "hosted on AWS") because a news sentence is neither a vendor document nor an observed failure;
unnamed upstreams ("an upstream provider"); hedged, negated or unattributed statements; anything needing inference.

``concentration_eligibility`` applies a minimum-evidence rule and returns COUNTS ONLY. No score is ever produced.
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field

ENV_FLAG = "DEPENDENCY_EVIDENCE_ENABLED"

BASIS_DOCUMENTED = "documented"
BASIS_DEMONSTRATED = "demonstrated_operational"

REL_DEPENDS_ON = "depends_on"
REL_SUPPLIED_BY = "supplied_by"
REL_HOSTED_ON = "hosted_on"

CLASS_SUBPROCESSOR = "vendor_subprocessor_list"
CLASS_VENDOR_DOC = "vendor_documentation"
CLASS_STATUS_COMPONENTS = "vendor_status_components"
CLASS_REGULATOR = "regulator_register"
CLASS_STATUS_INCIDENT = "vendor_status_incident"
CLASS_NEWS_INCIDENT = "news_incident_report"

DOCUMENTED_CLASSES = {CLASS_SUBPROCESSOR, CLASS_VENDOR_DOC, CLASS_STATUS_COMPONENTS, CLASS_REGULATOR}
DEMONSTRATED_CLASSES = {CLASS_STATUS_INCIDENT, CLASS_NEWS_INCIDENT}

# canonical id -> aliases (longest first at match time). Product names are kept only inside evidence spans.
LEXICON = {
    "aws": ["Amazon Web Services, Inc.", "Amazon Web Services, Inc", "Amazon Web Services (AWS)", "Amazon Web Services", "AWS"],
    "microsoft": ["Microsoft Corporation", "Microsoft Azure", "Microsoft Outlook", "Microsoft 365", "Microsoft", "Azure"],
    "google": ["Google Cloud Platform", "Google Cloud", "Google, LLC", "Google LLC", "Google"],
    "cloudflare": ["Cloudflare, Inc", "Cloudflare, Ltd.", "Cloudflare, Ltd", "Cloudflare"],
    "oracle": ["Oracle Cloud Infrastructure", "Oracle America, Inc.", "Oracle"],
    "anthropic": ["Anthropic PBC", "Anthropic"],
    "openai": ["OpenAI, Inc.", "OpenAI"],
    "notion": ["Notion Labs, Inc", "Notion"],
    "supabase": ["Supabase, Inc.", "Supabase"],
    "zoom": ["Zoom Communications, Inc.", "Zoom"],
    "twilio": ["Twilio"],
    "salesforce": ["Salesforce, Inc.", "Salesforce"],
    "github": ["Github, Inc", "GitHub"],
    "vercel": ["Vercel, Inc", "Vercel"],
    "fly_io": ["Fly.io, Inc", "Fly.io"],
    "upstash": ["Upstash, Inc", "Upstash"],
    "coreweave": ["CoreWeave, Inc.", "CoreWeave"],
    "akamai": ["Akamai"],
    "fastly": ["Fastly"],
    "crowdstrike": ["CrowdStrike"],
    "okta": ["Okta"],
    "slack": ["Slack Technologies, Inc.", "Slack"],
    "stripe": ["Stripe"],
    "telstra": ["Telstra"],
    "optus": ["Optus"],
    "nbn_co": ["NBN Co", "NBN"],
}
_ALIAS_TO_ID = {a: cid for cid, al in LEXICON.items() for a in al}
_ALIAS_RE_SRC = "|".join(re.escape(a) for a in sorted(_ALIAS_TO_ID, key=len, reverse=True))
_ALIAS = rf"(?<![\w])(?:{_ALIAS_RE_SRC})(?![\w])(?! of )"
ALIAS_RE = re.compile(_ALIAS)

_INCIDENT_NOUN = r"(?:outage|failure|incident|disruption|issue|problem)s?"
_CAUSE = r"(?:due to|caused by|because of|as a result of|a result of|triggered by|stemming from|attributed to|disrupted by|hit by|impacted by|affected by)"
_B_PHRASE = (
    rf"(?:the |an? )?(?:(?:ongoing|global|major|widespread|wider|broader|recent) )*"
    rf"(?P<b>{_ALIAS})(?: [\w’'\-\.]+){{0,3}}? {_INCIDENT_NOUN}"
)
CAUSE_RE = re.compile(rf"\b{_CAUSE} {_B_PHRASE}")
FORWARD_RE = re.compile(
    rf"{_B_PHRASE} (?:is |was |has been |are )?(?:impacting|affecting|disrupting|disrupts|knocking out|taking down) "
    rf"(?:the |our )?(?P<a>{_ALIAS})"
)
HEDGE_RE = re.compile(
    r"\b(?:not|no evidence|unrelated|may have|might|could have|reportedly|allegedly|suspected|unconfirmed|"
    r"unclear|speculat\w+|rumou?r\w*)\b",
    re.IGNORECASE,
)
UNNAMED_UPSTREAM_RE = re.compile(
    r"\b(?:upstream (?:provider|vendor|supplier)|third[- ]party (?:provider|vendor)|service provider)\b", re.IGNORECASE
)
STATIC_CLAIM_RE = re.compile(
    rf"(?P<a>{_ALIAS}|[A-Z][\w&]+)(?:[^.]{{0,60}}?)\b(?P<rel>built on|hosted on|hosted by|powered by|supplied by|provided by)\s+(?P<b>{_ALIAS})"
)
FIRST_PERSON_RE = re.compile(r"\b(?:we|we're|we are|our)\b", re.IGNORECASE)
_FEED_SUFFIX_RE = re.compile(r"\s*(?:\(.*?\))?\s*(?:Trust Status|Service Health|Status)\s*$", re.IGNORECASE)
PROSE_HOST_RE = re.compile(
    rf"(?P<a>{_ALIAS}|\bWe\b|\bOur\b) (?:is|are) hosted (?:on|by|in|with) (?P<b>{_ALIAS})"
)
COMPONENT_DESC_RE = re.compile(
    rf"\b(?P<kw>hosted (?:on|by|with)|powered by|provided by|supplied by|relies on|depends on|upstream (?:dependency|provider))\s*:?\s*(?:the )?(?P<b>{_ALIAS})"
)


def is_enabled(enabled=None):
    if enabled is not None:
        return bool(enabled)
    return os.environ.get(ENV_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Result:
    records: list = field(default_factory=list)
    excluded: list = field(default_factory=list)  # {reason, evidence_span, source_url, ...}; never records
    disabled: bool = False


def canonical(name):
    """Canonical id for a known alias, else the cleaned raw name. Never guesses."""
    cleaned = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", name or "")
    cleaned = re.sub(r"<br>.*", "", cleaned)
    cleaned = re.sub(r"\*+|\\", "", cleaned).strip(" |")
    return _ALIAS_TO_ID.get(cleaned, cleaned), cleaned


def _record(frm, to, rel, basis, span, url, src_class, observed_at):
    assert (basis == BASIS_DOCUMENTED and src_class in DOCUMENTED_CLASSES) or (
        basis == BASIS_DEMONSTRATED and src_class in DEMONSTRATED_CLASSES
    ), "relation_basis must match source_class"
    return {
        "provider_from": frm,
        "provider_to": to,
        "relation": rel,
        "relation_basis": basis,
        "evidence_span": span.strip(),
        "source_url": url,
        "source_class": src_class,
        "observed_at": str(observed_at) if observed_at is not None else None,
    }


def _sentences(text):
    text = (text or "").replace("e.g.", "e_g_").replace("i.e.", "i_e_")
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(])|\n+", text)
    return [p.replace("e_g_", "e.g.").replace("i_e_", "i.e.").strip() for p in parts if p.strip()]


def _feed_owner(source_name):
    if not source_name:
        return None
    base = _FEED_SUFFIX_RE.sub("", source_name).strip()
    return _ALIAS_TO_ID.get(base)


def _affected_before(sentence, cue_start):
    """Nearest named alias cluster before the cue (joined only by ',', 'and', '&'); max 120 chars from the cue."""
    head = sentence[:cue_start]
    found = [(m.start(), m.end(), _ALIAS_TO_ID[m.group(0)]) for m in ALIAS_RE.finditer(head)]
    if not found or cue_start - found[-1][1] > 120:
        return []
    cluster = [found[-1]]
    for prev in reversed(found[:-1]):
        gap = head[prev[1] : cluster[0][0]]
        if re.fullmatch(r"\s*(?:,|and|&|, and)\s*", gap):
            cluster.insert(0, prev)
        else:
            break
    return [c[2] for c in cluster]


def extract_from_incident(text, source_name, source_url, observed_at, source_class=CLASS_NEWS_INCIDENT, enabled=None):
    """Demonstrated operational dependencies from ONE incident item (title + summary text)."""
    res = Result()
    if not is_enabled(enabled):
        res.disabled = True
        return res
    if source_class not in DEMONSTRATED_CLASSES:
        raise ValueError("incident text can only carry demonstrated_operational evidence")
    owner = _feed_owner(source_name) if source_class == CLASS_STATUS_INCIDENT else None
    for sent in _sentences(text):
        meta = {"evidence_span": sent, "source_url": source_url, "observed_at": str(observed_at)}
        if HEDGE_RE.search(sent):
            if CAUSE_RE.search(sent) or FORWARD_RE.search(sent):
                res.excluded.append({**meta, "reason": "hedged_or_negated_statement"})
            continue
        matched = False
        for m in CAUSE_RE.finditer(sent):
            matched = True
            b = _ALIAS_TO_ID[m.group("b")]
            affected = _affected_before(sent, m.start())
            if not affected and owner and FIRST_PERSON_RE.search(sent[: m.start()]):
                affected = [owner]  # first-person statement inside the vendor's own status feed
            affected = [a for a in affected if a != b]
            if not affected:
                res.excluded.append({**meta, "reason": "no_named_affected_party"})
                continue
            for a in affected:
                res.records.append(
                    _record(a, b, REL_DEPENDS_ON, BASIS_DEMONSTRATED, sent, source_url, source_class, observed_at)
                )
        for m in FORWARD_RE.finditer(sent):
            matched = True
            a, b = _ALIAS_TO_ID[m.group("a")], _ALIAS_TO_ID[m.group("b")]
            if a != b:
                res.records.append(
                    _record(a, b, REL_DEPENDS_ON, BASIS_DEMONSTRATED, sent, source_url, source_class, observed_at)
                )
        if not matched:
            if UNNAMED_UPSTREAM_RE.search(sent) and re.search(r"\b(?:affecting|due to|caused by|impact\w*)\b", sent, re.IGNORECASE):
                res.excluded.append({**meta, "reason": "unnamed_upstream_provider"})
            elif STATIC_CLAIM_RE.search(sent):
                res.excluded.append({**meta, "reason": "static_supply_claim_in_incident_or_news_text_not_documented"})
    res.records = _dedupe(res.records)
    seen_ex, uniq = set(), []
    for ex in res.excluded:
        k = (ex["reason"], ex["evidence_span"])
        if k not in seen_ex:
            seen_ex.add(k)
            uniq.append(ex)
    res.excluded = uniq
    return res


def _dedupe(records):
    seen, out = set(), []
    for r in records:
        k = (r["provider_from"], r["provider_to"], r["relation"], r["relation_basis"], r["evidence_span"], r["source_url"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def _split_row(line):
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return cells


def _is_sep(line):
    return bool(re.fullmatch(r"\|?\s*(?::?-+:?\s*\|\s*)+(?::?-+:?)?\s*\|?", line.strip())) or line.strip() in {"|-|-|", "|-|"}


_HOSTING_RE = re.compile(r"\b(?:hosting|cloud infrastructure|cloud service provider|infrastructure)\b", re.IGNORECASE)


def _subprocessor_relation(row_text):
    return REL_HOSTED_ON if _HOSTING_RE.search(row_text) else REL_SUPPLIED_BY


def _emit_row(res, cells, span, vendor_id, source_url, observed_at, purpose_idx=1):
    name = cells[0]
    if len(cells) < 2 or not name or name.lower().strip("* ") in {
        "name", "name of sub-processor", "entity name", "sub-processor", "subprocessor", "sub‑processor"
    }:
        return
    to_id, raw = canonical(name)
    if not raw or to_id == vendor_id:
        return
    row_text = cells[purpose_idx] if purpose_idx < len(cells) else ""  # purpose column only, never location text
    res.records.append(
        _record(vendor_id, to_id, _subprocessor_relation(row_text), BASIS_DOCUMENTED, span.strip(), source_url,
                CLASS_SUBPROCESSOR, observed_at)
    )


def extract_from_subprocessor_list(markdown, vendor, source_url, observed_at, enabled=None):
    """Documented relations from a vendor sub-processor list (markdown tables, or 'Name • Purpose' bullet rows).

    Only tables whose header has a purpose-like column (purpose/activity/description) are read; entity,
    affiliate and location-only tables are skipped. ``vendor`` is the publishing vendor (provider_from).
    """
    res = Result()
    if not is_enabled(enabled):
        res.disabled = True
        return res
    vendor_id = _ALIAS_TO_ID.get(vendor, vendor)
    lines = markdown.splitlines()
    purpose_idx = 1
    ok_cols = None  # column count of the last accepted table (lets header-less continuation tables inherit)
    in_table_ok = False
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("|") and "•" in s:  # Anthropic-style single-cell rows: "Name • Purpose<br>Location<br>Products"
            cell = _split_row(s)[0]
            name_part, _, rest = cell.partition("•")
            name = re.sub(r"!\[[^\]]*\]\([^)]*\)<br>", "", name_part).strip()
            purpose = rest.split("<br>")[0].strip()
            if name and purpose:
                span = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s).strip(" |").removeprefix("<br>")
                to_id, _raw = canonical(name)
                res.records.append(
                    _record(vendor_id, to_id, _subprocessor_relation(purpose), BASIS_DOCUMENTED, span, source_url,
                            CLASS_SUBPROCESSOR, observed_at)
                )
            continue
        if not s.startswith("|"):
            in_table_ok = False
            continue
        if _is_sep(s):
            # decide whether this table is acceptable using the header just above (if any)
            hdr = _split_row(lines[i - 1]) if i > 0 and lines[i - 1].strip().startswith("|") else None
            in_table_ok = False
            if hdr and any(c for c in hdr):
                htxt = " ".join(hdr).lower()
                if re.search(r"purpose|activity|description", htxt):
                    in_table_ok, ok_cols = True, len(hdr)
                    purpose_idx = next(
                        j for j, h in enumerate(hdr) if re.search(r"purpose|activity|description", h.lower())
                    )
                elif ok_cols is not None and len(hdr) == ok_cols and not re.search(r"location|parent|registered", htxt):
                    # continuation table split by a blank line: its first row was parsed as a header; keep it as data
                    in_table_ok = True
                    _emit_row(res, hdr, lines[i - 1].strip(), vendor_id, source_url, observed_at, purpose_idx)
                else:
                    ok_cols = None
            continue
        cells = _split_row(s)
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if nxt and _is_sep(nxt):
            continue  # this is a header row; handled at its separator
        if not in_table_ok or len(cells) < 2 or not cells[0]:
            continue
        _emit_row(res, cells, s, vendor_id, source_url, observed_at, purpose_idx)
    res.records = _dedupe(res.records)
    return res


def extract_from_vendor_prose(text, vendor, source_url, observed_at, enabled=None):
    """Documented 'hosted on' statements in a vendor's OWN documentation page ('Notion is hosted by AWS')."""
    res = Result()
    if not is_enabled(enabled):
        res.disabled = True
        return res
    vendor_id = _ALIAS_TO_ID.get(vendor, vendor)
    for sent in _sentences(text):
        for m in PROSE_HOST_RE.finditer(sent):
            subj = m.group("a")
            subj_id = vendor_id if subj in {"We", "Our"} else _ALIAS_TO_ID.get(subj)
            if subj_id != vendor_id:
                res.excluded.append({"reason": "subject_is_not_the_publishing_vendor", "evidence_span": sent,
                                     "source_url": source_url, "observed_at": str(observed_at)})
                continue
            res.records.append(_record(vendor_id, _ALIAS_TO_ID[m.group("b")], REL_HOSTED_ON, BASIS_DOCUMENTED, sent,
                                       source_url, CLASS_VENDOR_DOC, observed_at))
    res.records = _dedupe(res.records)
    return res


def extract_from_status_components(components_json, vendor, source_url, observed_at, enabled=None):
    """Documented relations from a Statuspage ``components.json``: only a component description that explicitly
    states a provider relationship produces a record. Component names, groups and region labels never do."""
    res = Result()
    if not is_enabled(enabled):
        res.disabled = True
        return res
    vendor_id = _ALIAS_TO_ID.get(vendor, vendor)
    data = json.loads(components_json) if isinstance(components_json, str) else components_json
    rel_map = {"hosted": REL_HOSTED_ON, "powered": REL_SUPPLIED_BY, "provided": REL_SUPPLIED_BY,
               "supplied": REL_SUPPLIED_BY, "relies": REL_DEPENDS_ON, "depends": REL_DEPENDS_ON, "upstream": REL_DEPENDS_ON}
    for comp in data.get("components", []):
        desc = comp.get("description") or ""
        for m in COMPONENT_DESC_RE.finditer(desc):
            rel = rel_map[m.group("kw").split()[0]]
            span = f"{comp.get('name', '')}: {desc}"
            res.records.append(_record(vendor_id, _ALIAS_TO_ID[m.group("b")], rel, BASIS_DOCUMENTED, span, source_url,
                                       CLASS_STATUS_COMPONENTS, observed_at))
    res.records = _dedupe(res.records)
    return res


def extract_events(rows, enabled=None):
    """Run the incident extractor over export rows (event_id, source_name, published_at, canonical_url,
    raw_title, raw_summary). Status-feed rows are classed vendor_status_incident, all others news_incident_report."""
    out = Result()
    if not is_enabled(enabled):
        out.disabled = True
        return out
    for r in rows:
        name = r.get("source_name") or ""
        cls = CLASS_STATUS_INCIDENT if re.search(r"(?:Status|Service Health)\s*$", name) else CLASS_NEWS_INCIDENT
        text = f"{r.get('raw_title') or ''}. {r.get('raw_summary') or ''}"
        one = extract_from_incident(text, name, r.get("canonical_url"), r.get("published_at"), cls, enabled=True)
        for rec in one.records:
            rec["event_id"] = r.get("event_id")
        for ex in one.excluded:
            ex["event_id"] = r.get("event_id")
        out.records += one.records
        out.excluded += one.excluded
    return out


def concentration_eligibility(records, provider_to, min_dependents=3, min_events=2):
    """Minimum-evidence rule. Returns COUNTS PER BASIS, never a score and never a merged figure.

    A concentration statement about ``provider_to`` is permitted for a basis only when, using VERIFIED records
    (``record['verified'] is True``, set by a reviewer after reading the span) of that basis alone:
      * documented: at least ``min_dependents`` distinct provider_from, each documenting provider_to in a document
        published by that provider_from (so distinct, independent publishers);
      * demonstrated_operational: at least ``min_dependents`` distinct provider_from AND at least ``min_events``
        distinct incident dates/URLs (independent events).
    The statement is limited to the examined set of dependents; it says nothing about market share or exposure of
    any organisation not named by a record.
    """
    by_basis = defaultdict(list)
    for r in records:
        if r.get("verified") is True and r["provider_to"] == provider_to:
            by_basis[r["relation_basis"]].append(r)
    out = {}
    for basis in (BASIS_DOCUMENTED, BASIS_DEMONSTRATED):
        rs = by_basis.get(basis, [])
        dependents = sorted({r["provider_from"] for r in rs})
        events = sorted({r["source_url"] for r in rs})
        ok = len(dependents) >= min_dependents and (basis == BASIS_DOCUMENTED or len(events) >= min_events)
        out[basis] = {"eligible": ok, "distinct_dependents": len(dependents), "dependents": dependents,
                      "distinct_sources": len(events)}
    out["note"] = "counts only; bases are never combined; no score is computed"
    return out


def main(argv=None):  # pragma: no cover - thin CLI
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--events-jsonl", help="export of intelligence_events rows (JSONL)")
    ap.add_argument("--enable", action="store_true", help="required (or set DEPENDENCY_EVIDENCE_ENABLED=1)")
    args = ap.parse_args(argv)
    if not is_enabled(args.enable or None):
        print("dependency_evidence is OFF (set DEPENDENCY_EVIDENCE_ENABLED=1 or pass --enable)")
        return 0
    with open(args.events_jsonl, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    res = extract_events(rows, enabled=True)
    print(json.dumps({"records": res.records, "excluded": res.excluded}, indent=2, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
