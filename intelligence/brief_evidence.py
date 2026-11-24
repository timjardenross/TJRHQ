"""Shared evidence foundation for the three briefs (V1) — one event identity, one materiality assessment, one provenance trail.

Morning Command Brief, Weekly Intelligence & Decision Brief and Communications & Presence Brief all read the SAME ``EvidenceSet`` built
once from validated reports by the staged detector (``intelligence.event_detection``). The ``*_view`` functions only SELECT and ARRANGE
incidents; none of them scores, classifies severity or invents a claim. Every statement a view emits carries the incident id and its report
ids so it can be traced back to publisher, URL and timestamp.

Evidence status (source-level, identical in all three briefs): OFFICIALLY CONFIRMED (a primary/official source is among the original reports),
CORROBORATED (two independent publishers, syndicated copies excluded), REPORTED (one non-aggregator report), UNVERIFIED (aggregator-only,
hedged or anonymously sourced). What a headline merely *states* about impact is shown separately and is never called "confirmed".

Feature flags (all default OFF; nothing changes in a live brief unless one is set):
    BRIEF_EVIDENCE_V1            enable all three
    BRIEF_EVIDENCE_V1_MORNING / _WEEKLY / _COMMS   enable one
    BRIEF_EVIDENCE_SNAPSHOT_PATH optional JSONL path for the weekly comparison (unset: no snapshot is read or written)
Publication is never automatic: the comms view only recommends and always states that Captain approval is required.
"""
from __future__ import annotations

import hashlib
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from intelligence import event_detection as ed
from intelligence import freshness as fr
from intelligence import weekly_evidence as we

MASTER_FLAG = "BRIEF_EVIDENCE_V1"
FLAGS = {"morning": "BRIEF_EVIDENCE_V1_MORNING", "weekly": "BRIEF_EVIDENCE_V1_WEEKLY", "comms": "BRIEF_EVIDENCE_V1_COMMS"}
SNAPSHOT_ENV = "BRIEF_EVIDENCE_SNAPSHOT_PATH"
_TRUE = ("1", "true", "yes", "on")
_ACTIONABLE = ("ESCALATE", "VERIFY", "WATCH")
# ed.RESTORATION_STATUSES as shown to the reader; 'unknown' has no label because it is never stated as a fact.
RESTORATION_LABEL = {"ongoing": "ongoing", "partially_restored": "partially restored", "restored": "restored"}
STATUS_LABEL = {"officially_confirmed": "officially confirmed", "corroborated": "corroborated", "reported": "reported", "unverified": "unverified"}


def enabled(brief: str) -> bool:
    """True only on an explicit opt-in for this brief (or the master flag)."""
    def on(name):
        return os.getenv(name, "").strip().lower() in _TRUE
    return on(MASTER_FLAG) or on(FLAGS[brief])


@dataclass
class IncidentView:
    incident_id: str
    headline: str
    priority: str                   # ESCALATE | VERIFY | WATCH | REFERENCE
    materiality: str                # high | medium | low (operational)
    sector_tier: int | None
    event_type: str
    impact_status: str              # what the headline states: stated | unconfirmed | retrospective | potential | warning | forecast
    evidence_status: str            # officially_confirmed | corroborated | reported | unverified
    evidence_basis: list[str]       # the sources that support that status
    evidence_confidence: float
    independent_publishers: int
    provisional: bool
    grouping_confidence: float
    reports: list[dict]             # provenance: report_id, publisher, source_kind, title, url, collected_at, role
    first_seen: datetime | None
    last_seen: datetime | None
    record: dict                    # ed.escalation_record()
    reasons: list[str] = field(default_factory=list)
    urgent_verify: bool = False     # VERIFY + high materiality + immediate urgency + stated impact: potentially severe, not yet corroborated

    @property
    def report_ids(self) -> list[str]:
        return [r["report_id"] for r in self.reports]


@dataclass
class EvidenceSet:
    method_version: str
    generated_at: datetime
    window_hours: int
    n_events: int
    incidents: list[IncidentView]

    def by_priority(self, *priorities: str) -> list[IncidentView]:
        return [i for i in self.incidents if i.priority in priorities]


def _incident_id(report_ids: list[str]) -> str:
    return "inc-" + hashlib.sha1("|".join(sorted(report_ids)).encode(), usedforsecurity=False).hexdigest()[:10]  # nosec B324 - identity hash, not security


URGENT_MAX_AGE_HOURS = fr.BRIEF_FRESH_HOURS      # 'urgent' is about what is happening now: an incident whose newest report is older than this is never flagged (nor promoted in the weekly view)


def build_evidence(events: list[dict], *, now: datetime | None = None, window_hours: int = 24) -> EvidenceSet:
    """events: dicts with id, title, source, geography, collected_at, optional url. Pure; no I/O."""
    now = now or datetime.now(timezone.utc)
    meta = {str(e.get("id")): e for e in events}
    decisions = ed.run(events, now=now)
    incidents: list[IncidentView] = []
    for d in decisions:
        members = d.group.members
        reports = []
        for m in members:
            e = meta.get(m.event_id, {})
            role = "commentary" if m.commentary else "syndicated" if m.event_id in d.group.syndicated_ids else "original"
            reports.append({"report_id": m.event_id, "publisher": m.family, "source_name": m.source, "source_kind": m.kind,
                            "title": m.title, "url": e.get("url"), "collected_at": e.get("collected_at"),
                            "published_at": m.published.isoformat() if m.published else None,
                            "role": role, "geography": e.get("geography") or "", "summary": e.get("summary") or ""})
        times = [m.published for m in members if m.published]
        incidents.append(IncidentView(
            incident_id=_incident_id([m.event_id for m in members]), headline=d.headline.title, priority=d.priority,
            materiality=d.materiality, sector_tier=d.sector_tier, event_type=d.event_type, impact_status=d.impact_status,
            evidence_status=d.evidence_status, evidence_basis=d.evidence_basis,
            evidence_confidence=d.evidence_confidence, independent_publishers=d.group.independent_publishers,
            provisional=d.provisional, grouping_confidence=d.group.grouping_confidence, reports=reports,
            first_seen=min(times) if times else None, last_seen=max(times) if times else None,
            record=ed.escalation_record(d, now=now), reasons=list(d.reasons),
            urgent_verify=(d.priority == "VERIFY" and d.materiality == "high" and d.urgency == "immediate" and d.impact_status == "stated"
                           and bool(times) and now - max(times) <= timedelta(hours=URGENT_MAX_AGE_HOURS))))
    order = {"ESCALATE": 0, "VERIFY": 1, "WATCH": 2, "REFERENCE": 3}
    incidents.sort(key=lambda i: (order[i.priority], not i.urgent_verify, -(i.last_seen.timestamp() if i.last_seen else 0)))
    return EvidenceSet(ed.METHOD_VERSION, now, window_hours, len(events), incidents)


# Sources that publish only AFTER an outage is rectified (statutory registers). They are authoritative confirmation and restoration
# evidence for analysis and the portal, never a live signal, so they are not incident seeds for the brief.
_RETROSPECTIVE_SOURCE_MARKERS = ("outage register",)


def _retrospective_import(source: str, published_at, now: datetime, hours: int) -> bool:
    """True when a report is a historical import, not a recent development: it comes from a retrospective register, or its own
    publication date is older than the evidence window (a newly activated or repaired source back-fills old publications, e.g.
    ASIC releases from weeks ago, which keep their original dates but must not be shown as new). Reports with no usable publication
    date are kept: absence of a date is not evidence of age."""
    if any(m in source.lower() for m in _RETROSPECTIVE_SOURCE_MARKERS):
        return True
    if not published_at:
        return False
    published = we._parse_ts(published_at)
    return published is not None and now - published > timedelta(hours=hours)


def load_events(sb_get, *, hours: int, limit: int = 3000, now: datetime | None = None) -> list[dict]:
    """Read validated reports through an injected PostgREST getter (captains_brief._sb_get). Fails soft: returns [] on any error so a
    brief is never blocked by the evidence layer."""
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        rows = sb_get("intelligence_events",
                      f"collected_at=gte.{since}&suppressed=eq.false&signal_status=neq.DUPLICATE&order=collected_at.desc&limit={limit}"
                      "&select=event_id,raw_title,raw_summary,geography,collected_at,published_at,canonical_url,intelligence_source_registry(source_name)")
    except Exception:  # noqa: BLE001 - evidence layer is additive; the legacy brief must still render
        return []
    out = []
    for r in rows or []:
        reg = r.get("intelligence_source_registry") or {}
        if _retrospective_import(reg.get("source_name") or "", r.get("published_at"), now, hours):
            continue
        out.append({"id": str(r.get("event_id")), "title": r.get("raw_title") or "", "summary": r.get("raw_summary") or "",
                    "source": reg.get("source_name") or "", "geography": r.get("geography") or "",
                    "collected_at": r.get("collected_at"), "published_at": r.get("published_at"), "url": r.get("canonical_url")})
    return out


# ── helpers shared by the views ───────────────────────────────────────────────────────────────────────

_CITE_REFS = 3                                   # report references shown per citation (bounded: briefs are read on a phone)
_ROLE_ORDER = {"original": 0, "syndicated": 1, "commentary": 2}
_CITE_URL_MAX = 120                              # a URL longer than this is not shown inline (it stays in the evidence data)
_REDIRECT_HOSTS = ("news.google.com",)           # aggregator wrapper links: long, and they hide the publisher


_UUID_RX = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")


def _short_id(report_id: str) -> str:
    """First 8 characters of the report id (the leading segment of a UUID); enough to find the report in the evidence data."""
    rid = str(report_id)
    return rid.split("-")[0] if _UUID_RX.fullmatch(rid) else rid[:8]


def _resolve_short_ids(report_ids: list[str]) -> dict[str, str]:
    """Short ids that are unique across ALL of an incident's reports (not just the ones displayed), so a displayed reference
    can never be ambiguous with a hidden one. Colliding ids are lengthened just enough to be distinct (the full id at worst)."""
    ids = [str(r) for r in report_ids]
    out = {r: _short_id(r) for r in ids}
    by_short: dict[str, list[str]] = {}
    for r, sid in out.items():
        by_short.setdefault(sid, []).append(r)
    for group in by_short.values():
        if len(group) < 2:
            continue
        n = len(out[group[0]])
        while n < max(len(g) for g in group) and len({g[:n] for g in group}) < len(group):
            n += 1
        for g in group:
            out[g] = g[:n]
    return out


def _url_for_display(url: str | None) -> str | None:
    """Selective display (Captain, Option A): show a URL inline only when it is short and is the publisher's own link. Never a
    truncated URL: a link is either shown whole or not shown. The complete URL is always kept in ``IncidentView.reports``."""
    if not url or len(url) > _CITE_URL_MAX:
        return None
    try:
        host = (urlsplit(url).hostname or "").lower()                # handles ports, userinfo and an upper-case scheme
    except ValueError:
        return None
    return None if any(host == h or host.endswith("." + h) for h in _REDIRECT_HOSTS) else url


def evidence_refs(i: IncidentView) -> list[dict]:
    """Every report behind an incident with its COMPLETE source URL (never shortened), in citation order: originals before
    syndicated copies and commentary, primary sources first. This is the underlying evidence data; the brief shows a subset.
    ``short_id`` is unique across all of the incident's reports and is the id the citation prints."""
    ranked = sorted(i.reports, key=lambda r: (_ROLE_ORDER.get(r["role"], 3), r["source_kind"] != we.PRIMARY, r["report_id"]))
    short = _resolve_short_ids([r["report_id"] for r in ranked])
    return [{"report_id": r["report_id"], "short_id": short[str(r["report_id"])], "publisher": r["source_name"] or r["publisher"],
             "url": r.get("url"), "role": r["role"], "source_kind": r["source_kind"]} for r in ranked]


def _cite(i: IncidentView) -> str:
    """Incident id and report count, then up to three references, each ``<publisher> #<short id>`` with the publisher's own
    URL only when it is short and not an aggregator redirect. #669: ids and URLs were collected per report but dropped, so a
    reader could not retrieve the evidence behind an escalation or contribution candidate. Originals come first, primary
    sources ahead of the rest. Complete URLs stay available through ``evidence_refs()``."""
    refs = evidence_refs(i)
    parts = []
    for r in refs[:_CITE_REFS]:
        shown_url = _url_for_display(r["url"])
        parts.append(f"{r['publisher']} #{r['short_id']}" + (f" <{shown_url}>" if shown_url else ""))
    more = f" +{len(refs) - _CITE_REFS} more" if len(refs) > _CITE_REFS else ""
    return f"[{i.incident_id}; {len(i.reports)} report(s); evidence: " + ", ".join(parts) + more + "]"


def _facts(i: IncidentView) -> str:
    r = i.record
    bits = []
    if i.impact_status == "stated":
        bits.append("impact stated in headline")
    elif i.impact_status in ("warning", "forecast"):
        bits.append(f"{i.impact_status} (not a stated outage)")
    else:
        bits.append(r["impact"])
    if r.get("affected_customers"):
        bits.append(f"{r['affected_customers']:,} customers")
    if r.get("restoration_status") in RESTORATION_LABEL:     # 'unknown' (current state not established) is not stated as a fact
        bits.append(RESTORATION_LABEL[r["restoration_status"]])
    if r.get("duration"):
        bits.append(r["duration"])
    return ", ".join(bits)


def _tag(i: IncidentView) -> str:
    kinds = {r["source_kind"] for r in i.reports if r["role"] not in ("commentary",)}
    note = ""
    if i.evidence_status in ("corroborated", "reported") and kinds <= {we.AGGREGATOR}:
        note = " via aggregator feeds only"
    # #669: two different uncertainties, worded differently. SOURCE credibility (is the report itself reliable?) is the evidence
    # status; operational IMPACT (has the effect on service been established?) is what the report states.
    base = ("SOURCE UNVERIFIED" if i.evidence_status == "unverified" else STATUS_LABEL[i.evidence_status]) + note
    retro = " · retrospective report" if i.impact_status == "retrospective" else ""        # say so, never imply a live disruption
    cls = _relevance_class(i)
    retro += _EDITORIAL_TAG if cls == "editorial" else (_DEPENDENCY_TAG if cls == "plausible" else "")
    impact = " · IMPACT NOT YET ESTABLISHED" if _impact_open(i) else ""
    return f"{i.priority} · {base}{retro}{impact}" + (" · provisional" if i.priority == "ESCALATE" and i.provisional else "")


EDITORIAL_REASON = "Australian-audience outlet only"
_EDITORIAL_TAG = " · editorial relevance only (Australian operational impact not established)"
_DEPENDENCY_TAG = " · plausible dependency; Australian impact not established"
_RELEVANCE_PREFIX = "Australian relevance:"
_NO_RELEVANCE_REASON = "no demonstrated Australian relevance"

# Global platforms an Australian organisation plausibly depends on (used ONLY when the upstream relevance gate is absent).
_DEPENDENCY_RX = re.compile(
    r"\baws\b|amazon web services|\bazure\b|microsoft 365|office 365|microsoft 365|google cloud|\bgcp\b|cloudflare|akamai|fastly|"
    r"crowdstrike|okta|\bslack\b|\bzoom\b|github|atlassian|salesforce|openai|anthropic|\bstripe\b", re.IGNORECASE)
_AU_NAMED_RX = re.compile(
    r"australia\w*|aussie\w*|\bnsw\b|new south wales|queensland\w*|tasmania\w*|victorian\b|sydney|melbourne|brisbane|perth|adelaide|"
    r"canberra|hobart|darwin|\basx\b|\bnbn\b|\bapra\b|\bacsc\b|\baemo\b|ausgrid|endeavour energy|ergon|energex|essential energy|ausnet|"
    r"powercor|jemena|western power|telstra|optus|\btpg\b|qantas|jetstar|westpac|\banz\b|\bNAB\b|commonwealth bank|coles|woolworths|"
    r"medibank|services australia|centrelink|\bagl\b|origin energy|suncorp|\bbhp\b|woodside|transurban", re.IGNORECASE)


def _upstream_verdict(i: IncidentView) -> str | None:
    """The relevance gate's own decision (event_detection.decide, #677), read from the recorded reasons; None when that gate is absent.
    'editorial' | 'plausible' | 'relevant' | 'reference'."""
    verdict = None
    for r in i.reasons:
        if EDITORIAL_REASON in r:
            return "editorial"
        if r.startswith(_RELEVANCE_PREFIX):
            verdict = "plausible" if "plausible dependency" in r else "relevant"
        elif _NO_RELEVANCE_REASON in r:
            verdict = "reference"
    return verdict


def _fallback_class(i: IncidentView) -> str:
    """Outlet-independent local derivation used only without the upstream verdict: a foreign incident is 'editorial' (or 'plausible'
    when it names a global platform) whichever outlet reports it; AU geography or an Australian marker makes it 'relevant'."""
    if i.priority == "REFERENCE":          # never-actionable general news is not published at all
        return "reference"
    originals = [r for r in i.reports if r["role"] == "original"] or i.reports
    if not originals:
        return "relevant"
    if any((r.get("geography") or "").strip().upper() == "AU" for r in originals):
        return "relevant"
    texts = [f"{r.get('title') or ''} {r.get('summary') or ''}" for r in originals]
    if any(_AU_NAMED_RX.search(t) for t in texts):
        return "relevant"
    if any(_DEPENDENCY_RX.search(r.get("title") or "") for r in originals):
        return "plausible"
    return "editorial"


def _relevance_class(i: IncidentView) -> str:
    return _upstream_verdict(i) or _fallback_class(i)


def _derived_editorial_only(i: IncidentView) -> bool:
    return _fallback_class(i) == "editorial"


def _editorial_only(i: IncidentView) -> bool:
    """Relevance rests on editorial grounds alone, not on an established Australian operational impact. Uses the upstream relevance
    decision when present, else an outlet-independent local derivation."""
    return _relevance_class(i) == "editorial"


def _quality_source(i: IncidentView) -> bool:
    """At least one ORIGINAL report from a primary, mainstream or specialist source (not unknown, content or aggregator-only)."""
    return any(r["role"] == "original" and r["source_kind"] in (we.PRIMARY, we.MAINSTREAM, we.SPECIALIST) for r in i.reports)


def _impact_open(i: IncidentView) -> bool:
    """A credible source whose report does not establish an operational impact (investigation, unconfirmed or potential effect)."""
    return i.evidence_status != "unverified" and i.impact_status in ("unconfirmed", "potential", "none")


def _confidence_words(c: float) -> str:
    """Plain words for evidence confidence; the raw score stays in the evidence data, not on the page."""
    return "high confidence" if c >= 0.75 else "moderate confidence" if c >= 0.5 else "low confidence"


def _line(i: IncidentView, with_action: bool = False) -> str:
    s = f"- [{_tag(i)}] {i.headline} — {_facts(i)}; {_confidence_words(i.evidence_confidence)} {_cite(i)}"
    if with_action:
        s += f"\n    next: {i.record['next_verification_action']}"
    return s


_DATE_RX = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b")


def forward_dated_items(ev: EvidenceSet, *, hours: int = 72) -> list[tuple[IncidentView, datetime]]:
    """Notices whose headline names a date inside the next ``hours`` (e.g. 'LOR1 forecast … on 20/11/2026'). Dates are read, never inferred."""
    out = []
    for i in ev.incidents:
        if i.priority == "REFERENCE":      # demoted by the relevance gate (or never actionable): not published as a dated notice
            continue
        for m in _DATE_RX.finditer(i.headline):
            try:
                d = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=timezone.utc)
            except ValueError:
                continue
            if ev.generated_at - timedelta(hours=24) <= d <= ev.generated_at + timedelta(hours=hours):
                out.append((i, d))
    return out


# ── Morning Command Brief view ────────────────────────────────────────────────────────────────────────

def _fw_credible(i: IncidentView) -> bool:
    """A 24-72h Forward Watch entry needs a credible current reason. A report supported ONLY by an aggregator feed (evidence status
    'unverified') is not one: it stays visible in its own 'source not yet verified' section but is not carried into the watch list."""
    kinds = {r["source_kind"] for r in i.reports if r["role"] != "commentary"}
    return not (i.evidence_status == "unverified" and kinds <= {we.AGGREGATOR})


def _unverified_why(i: IncidentView) -> str:
    """Why a potentially severe incident is not yet treated as fact, in plain words."""
    originals = [r for r in i.reports if r["role"] == "original"] or [r for r in i.reports if r["role"] != "commentary"]
    if originals and all(r["source_kind"] == we.AGGREGATOR for r in originals):
        named = sorted({r["publisher"] for r in originals if r["publisher"] != "aggregator"})
        return "seen only via aggregators" + (f" (naming {', '.join(named)})" if named else "") + "; no direct report from a publisher yet"
    if len(originals) == 1:
        return "single report from a source not rated credible; no second independent source yet"
    return "no primary, mainstream or specialist source yet"


def _urgent_verify_lines(urgent: list[IncidentView]) -> list[str]:
    """High materiality + weak evidence: a prominent verification priority (Captain's rule). Nothing at all when there is none."""
    if not urgent:
        return []
    return (["URGENT TO VERIFY (potentially severe, not yet corroborated)"]
            + [f"- {i.headline} — reported: {_facts(i)}; unverified: {_unverified_why(i)}; next: {i.record['next_verification_action']} {_cite(i)}"
               for i in urgent[:6]] + [""])


def morning_view(ev: EvidenceSet) -> list[str]:
    recent = [i for i in ev.incidents if i.last_seen and i.last_seen >= ev.generated_at - fr.brief_window()]
    editorial = [i for i in recent if i.impact_status not in ("warning", "forecast") and _editorial_only(i)]
    active = [i for i in recent if i.impact_status not in ("warning", "forecast") and i not in editorial]
    firm = [i for i in active if i.priority in ("ESCALATE", "WATCH") and i.impact_status == "stated"
            and i.evidence_status in ("officially_confirmed", "corroborated")]
    single = [i for i in active if i.priority in ("ESCALATE", "WATCH") and i.impact_status == "stated" and i.evidence_status == "reported"]
    urgent = [i for i in active if i.urgent_verify]       # shown once, in its own prominent section
    verify = [i for i in active if i not in urgent and (i.priority == "VERIFY" or (i.priority in ("ESCALATE", "WATCH") and i not in firm and i not in single))]
    notices = [i for i in recent if i.impact_status in ("warning", "forecast") and i.priority in _ACTIONABLE]
    # Section choice uses SOURCE QUALITY as well as evidence status: only an incident with an original report from a primary, mainstream
    # or specialist source is an 'impact not yet established' / exposure / retrospective question; the rest is a source question.
    credible = [i for i in verify if i.evidence_status != "unverified" and _quality_source(i)]
    # A retrospective report from a weak source that currency rules left at REFERENCE (e.g. a stale aggregator item) stays visible here.
    stale_ref = [i for i in active if i.priority == "REFERENCE" and i.impact_status == "retrospective" and not (i.evidence_status != "unverified" and _quality_source(i))]
    source_open = [i for i in verify if i not in credible] + stale_ref + editorial
    retro_open = [i for i in credible if i.impact_status == "retrospective"]
    impact_open = [i for i in credible if i.impact_status != "retrospective" and i.event_type != "vulnerability"]
    exposure = [i for i in credible if i.impact_status != "retrospective" and i.event_type == "vulnerability"]
    # Only CURRENT evidence counts as a current disruption: an incident whose restoration status is unknown (current status not
    # established, e.g. a historic outage still being written about, a stale cue or an unverified report time) is listed but not
    # counted. A partially restored incident is still a current disruption and is counted with ongoing ones.
    firm_n = [i for i in firm if i.record["restoration_status"] != "unknown"]
    single_n = [i for i in single if i.record["restoration_status"] != "unknown"]
    stale_n = len(firm) + len(single) - len(firm_n) - len(single_n)
    stale = (f" ({stale_n} more reported with current status unknown — not counted as current disruptions)" if stale_n else "")
    lines = []
    if not recent:
        lines.append("⚠️ EVIDENCE COVERAGE INSUFFICIENT: no reports collected in the last 24 hours; nothing below should be read as all quiet.")
    if not recent:
        based = f"Based on reports from the last {ev.window_hours} hours; none were collected in the last 24 hours, so this is not a current picture."
    elif ev.window_hours > 24:
        based = f"Based on reports from the last {ev.window_hours} hours (newest within 24 hours)."
    else:
        based = f"Based on reports from the last {ev.window_hours} hours."
    lines += ["🛰 EVIDENCE-BASED PICTURE", based, ""]
    if not recent:
        lines.append("Operational situation: evidence coverage is insufficient (no recent reports), so no judgement about current disruption can be made.")
    elif firm_n or single_n:
        lines.append(f"Operational situation: {len(firm_n)} confirmed or corroborated and {len(single_n)} single-source reported disruption(s) in the last 24 hours.{stale}")
    else:
        lines.append(f"Operational situation: no confirmed, corroborated or single-source reported current disruption in the last 24 hours{stale}.")
    if notices or exposure:
        lines.append("Credible warnings and emerging exposures are listed separately below; they are not current disruptions and no operational consequence is inferred from them.")
    lines.append("")
    lines += _urgent_verify_lines(urgent)
    lines.append("What matters today — OFFICIALLY CONFIRMED or CORROBORATED incidents")
    lines += [_line(i, True) for i in firm[:6]] or ["- None officially confirmed or corroborated in the last 24 hours."]
    imp = [f"- {'tier ' + str(i.sector_tier) if i.sector_tier else 'unclassified sector'}: "
           f"{', '.join(i.record['critical_service_dependencies']) or 'no recognised service'} — {_facts(i)} {_cite(i)}"
           for i in firm[:4] + single[:2]]
    fw = [f"- {RESTORATION_LABEL[i.record['restoration_status']].capitalize()}: {i.headline} "
          f"(restoration {RESTORATION_LABEL[i.record['restoration_status']]}) {_cite(i)}"
          for i in active if i.record["restoration_status"] in ed.CURRENT_DISRUPTION and i.priority in ("ESCALATE", "WATCH") and _fw_credible(i)][:4]
    fw += [f"- Forecast/warning: {i.headline} {_cite(i)}" for i in notices[:4]]
    fw += [f"- Dated notice for {d.strftime('%d %b')}: {i.headline} {_cite(i)}" for i, d in forward_dated_items(ev) if i not in notices and _fw_credible(i)][:3]
    fw += [f"- Verify: {i.headline} → {i.record['next_verification_action']} {_cite(i)}" for i in [x for x in impact_open + exposure + source_open if _fw_credible(x)][:2]]
    # Sections with nothing to show are collapsed into ONE line instead of a heading and a 'None' each; sections with content keep their heading.
    sections = [
        ("REPORTED by one source (provisional until a second or primary source)", "reported by one source", [_line(i, True) for i in single[:6]]),
        ("IMPACT NOT YET ESTABLISHED (credible source; effect on service not yet shown)", "impact not yet established", [_line(i, True) for i in impact_open[:6]]),
        ("RETROSPECTIVE REPORTS (about past events; not live disruptions)", "retrospective reports", [_line(i, True) for i in retro_open[:6]]),
        ("SOURCE NOT YET VERIFIED (hedged, aggregator-only, low-quality source, editorial relevance only or weakly evidenced; not treated as fact)",
         "source not yet verified", [_line(i, True) for i in source_open[:6]]),
        ("WARNINGS AND FORECASTS (not confirmed incidents)", "warnings and forecasts", [_line(i) for i in notices[:6]]),
        ("EMERGING EXPOSURE (credible advisories and risks; no confirmed current disruption; nothing here states an operational consequence)",
         "emerging exposure", [_line(i, True) for i in exposure[:6]]),
        ("Operational implications (only what the cited reports state)", "operational implications", imp),
        ("Forward watch, next 24–72 hours", "forward watch", fw),
    ]
    empty = []
    for heading, short, body in sections:
        if body:
            lines += ["", heading] + body
        else:
            empty.append(short)
    if empty:
        lines += ["", "Nothing to report in: " + "; ".join(empty) + "."]
    lines += worth_knowing_lines(ev)
    return lines


# ── Worth Knowing (informative developments that do not meet an escalation threshold) ───────────────────────────
# Selects and arranges only: it never changes an incident's priority, evidence status or escalation outcome. It adds credible, relevant
# technology news that has no confirmed outage or immediate operational impact, so the brief informs as well as alerts.
WORTH_KNOWING_LIMIT = 5
WORTH_KNOWING_HOURS = 72
_WK_FUTURE_SKEW_HOURS = 1     # last_seen must lie in [generated_at - 72h, generated_at + 1h]: a future-dated story is not "last 72 hours"
_WK_PER_CATEGORY = 2
_WK_CATEGORIES = (   # (name, weight, pattern); the highest-weight match names the item
    ("cyber", 3, (r"ransomware|malware|zero[- ]day|vulnerabilit(?:y|ies)|cyber ?(?:attack|attacks|security|incident|crime|criminal|espionage|threat)s?|data breach|"
                 r"\bhack(?:ed|er|ers|ing)?\b|phishing|exploited|CVE-\d|botnet|ddos|infostealer|spyware|backdoor|supply[- ]chain attack")),
    ("critical infrastructure", 3, (r"critical infrastructure|power grid|scada|industrial control|operational technology|semiconductors?|chip ?makers?|"
                                   r"submarine cable|undersea cable")),
    ("cloud", 3, (r"\bcloud (?:computing|services?|platforms?|providers?|storage|infrastructure|security|outages?|migration|regions?|native|customers?|software|accounts?|environments?|workloads?)\b|"
                r"\b(?:public|private|hybrid|multi|sovereign)[- ]cloud\b|\bcloud-(?:based|native)\b|\bin the cloud\b|\baws\b|\bazure\b|google cloud|data ?cent(?:er|re)s?|hyperscal|cloudflare")),
    ("telecommunications", 3, r"telecom|\btelcos?\b|telstra|optus|\btpg\b|vodafone|\b5g\b|mobile network|broadband|\bnbn\b|satellite|spectrum"),
    ("payments", 3, (r"\bpayments? (?:systems?|platforms?|networks?|providers?|processors?|processing|fraud|cards?|terminals?|rails?|infrastructure|security|apps?|outages?|gateways?|services?|schemes?)\b|"
                    r"\b(?:card|online|digital|mobile|real-time|instant|contactless|cross-border|instalment|merchant) payments?\b|mastercard|\bvisa (?:inc|payments|network)|paypal|stripe|eftpos|bpay|apple pay|fintech|digital wallet")),
    # AI counts only as a technology subject (models, chips, servers, agents, safety, regulation …), not as a market or insurance talking point.
    ("AI", 2, (r"(?:\bAI\b|artificial intelligence|\bllms?\b|generative ai|chatbots?|openai|anthropic|nvidia)[^.]{0,60}(?:models?|chips?|servers?|compute|data ?cent(?:er|re)s?|agents?|safety|"
               r"regulation|cyber|security|infrastructure|training|launch|release|outage|breach|vulnerab)|(?:models?|chips?|servers?|compute|agents?|safety|regulation|"
               r"security|infrastructure)[^.]{0,60}(?:\bAI\b|artificial intelligence|\bllms?\b|generative ai|openai|anthropic|nvidia)|\bgpus?\b|large language model")),
    ("software", 2, (r"software|\bsaas\b|open[- ]source|firmware|operating system|\bwindows (?:\d+|update|server)|\blinux\b|\bandroid\b|microsoft|oracle|vmware|"
                     r"google chrome|chrome (?:browser|update|extension)|web browser")),
)
_WK_CAT_RX = [(n, w, re.compile(p, re.IGNORECASE)) for n, w, p in _WK_CATEGORIES]
_WK_AU_RX = re.compile(r"\baustralia(?:n|ns)?\b|\bsydney\b|\bmelbourne\b|\bbrisbane\b|\bperth\b|\badelaide\b|\bcanberra\b|\bnsw\b|\bqueensland\b|"
                       r"\basic\b|\bapra\b|\bacsc\b|\bofaic\b|telstra|optus|\bnbn\b|\btpg\b", re.IGNORECASE)
# Editorial quality: promotional, list, awards, how-to, opinion and speculative-question headlines do not qualify as intelligence.
_WK_LOW_QUALITY_RX = re.compile(r"\b(?:how to|best|top \d+|\d+ (?:ways|things|tips)|reviews?|sponsored|webinar|podcast|opinion|fast 50|awards?|ranked|ranking|"
                                r"hiring|jobs?|(?:best|top|black friday|cyber monday) deals?|giveaway|quiz|sale|discount|coupon)\b|^(?:could|should|why|what|how|is|are|will|can|does|do)\b|\?\s*(?:-\s.*)?$", re.IGNORECASE)
# Company results and funding news is business reporting, not technology intelligence (checked against headline and summary).
_WK_CORPORATE_RX = re.compile(r"\b(?:revenue|year[- ]on[- ]year|yoy|(?<!non-)(?<!non )(?<!for-)(?<!for )profits?|earnings|funding round|series [a-d]|ipo|share price|market cap)\b", re.IGNORECASE)
_WK_CREDIBLE_KINDS = (we.PRIMARY, we.MAINSTREAM, we.SPECIALIST)
_WK_EVIDENCE_POINTS = {"officially_confirmed": 3, "corroborated": 2, "reported": 1}
# An aggregator feed item whose trailing ' - Outlet' names a primary or specialist publisher is attributable reporting by that outlet
# (e.g. 'Industrial Cyber'). It is evidence_status 'unverified' only because of the feed, so it is allowed here, labelled "via aggregator
# feed", and only when the headline carries no hedge. DELIBERATE EXCEPTION (acceptance criteria, see tests): primary/specialist outlet
# attributed through an aggregator feed + non-hedged headline + no stated disruption => eligible, always labelled
# "single source via aggregator feed"; unknown/mainstream-only attributions and hedged headlines stay excluded.
_WK_HEDGE_RX = re.compile(r"\b(?:reportedly|allegedly|alleged|claims?|claimed|sources?|rumou?rs?|unconfirmed|said to|may have|might|suspected)\b", re.IGNORECASE)


_WK_SUMMARY_DISRUPTION_RX = re.compile(r"\b(?:outage|outages|blackout|without (?:power|service|electricity|internet|mobile)|(?:unable|cannot|can't|can not|couldn't) (?:to )?(?:make|access|use|connect|log|call|send|reach|load|pay)|"
                                        r"(?:currently |now )?unavailable|degraded (?:service|performance|network)|dropped calls?|(?:elevated )?error rates?|hit by errors|"
                                        r"network (?:fault|faults|problems?|issues?|failure)|stranded|"
                                        r"went offline|knocked offline|taken offline|(?:is|are|was|were|remain(?:s|ed)?|still|now|currently|been) offline\b|service(?:s)? (?:is|are|was|were) down|systems? (?:is|are|was|were) down|disrupt(?:ed|ion|s)\b)", re.IGNORECASE)
_WK_POTENTIAL_RX = re.compile(r"\b(?:could|may|might|risk of|potential(?:ly)?|warns? (?:of|that)|warned (?:of|that)|would|if exploited|can lead to|could lead to|prevent|avoid)\b", re.IGNORECASE)


def _wk_disruption(i: IncidentView) -> bool:
    """A stated disruption, or an outage whose impact is only unconfirmed, is an incident (even when the Australian-relevance gate demoted it
    to REFERENCE) and must not be republished under a 'no outage or service impact' heading. Informative reporting (vulnerability or
    advisory-style cyber warnings, potential or retrospective impact, no stated impact) stays eligible; an unconfirmed cyber_incident is
    kept because advisory headlines ('FBI warns hackers ...') classify that way."""
    if i.impact_status == "stated" or (i.event_type == "outage" and i.impact_status in ("unconfirmed", "retrospective")):
        return True      # a retrospective outage-restoration story ("services restored after ...") is a past incident, not a development
    texts = [i.headline] + [r.get("summary") or "" for r in i.reports if r["role"] == "original"]
    # The summary shown beneath the heading may state an outage the headline does not. The potential-impact exception applies to the CLAUSE
    # that states the consequence, so an unrelated precaution or purpose clause ("should use Wi-Fi to avoid further problems") cannot negate
    # a stated outage elsewhere, even in the same sentence.
    return any(_wk_clause_disruption(sent) for t in texts for sent in re.split(r"(?<=[.!?])\s+", t))


_WK_CLAUSE_SPLIT_RX = re.compile(r"(\s*;\s*|\s*,\s*|\s+(?:and|but|so that|so|while|as)\s+|\s+(?=to (?:avoid|prevent)\b))", re.IGNORECASE)
_WK_MODAL_RX = re.compile(r"\b(?:could|may|might|would|can)\b", re.IGNORECASE)
_WK_SOFT_JOINERS = frozenset({",", "and"})


def _wk_clause_disruption(sentence: str) -> bool:
    """True when some clause of the sentence states a disruption and is not itself potential/hypothetical. A modal clause ('could cause
    outages') also covers an immediately coordinated clause joined by a comma or 'and' ('... and leave users unable to log in')."""
    parts = _WK_CLAUSE_SPLIT_RX.split(sentence)
    prev_modal = False
    for idx in range(0, len(parts), 2):
        clause = parts[idx]
        joiner = parts[idx - 1].strip().lower() if idx else ""
        inherited = prev_modal and joiner in _WK_SOFT_JOINERS
        if _WK_SUMMARY_DISRUPTION_RX.search(clause) and not _WK_POTENTIAL_RX.search(clause) and not inherited:
            return True
        prev_modal = bool(_WK_MODAL_RX.search(clause)) or (inherited and clause.strip() != "")
    return False


def _wk_credible_original(i: IncidentView) -> bool:
    for r in i.reports:
        if r["role"] != "original":
            continue
        if r["source_kind"] in _WK_CREDIBLE_KINDS:
            return True
    return False


def _wk_via_aggregator(i: IncidentView) -> str | None:
    """The attributed primary/specialist publisher when the only support is an aggregator feed item that names one, else None."""
    if (i.evidence_status != "unverified" or _WK_HEDGE_RX.search(i.headline) or ed._HEDGE_RX.search(i.headline) or ed._ANON_RX.search(i.headline)):
        return None
    for r in i.reports:
        if r["role"] == "original" and r["source_kind"] == we.AGGREGATOR and we.source_kind(r["publisher"]) in (we.PRIMARY, we.SPECIALIST):
            return r["publisher"]
    return None


_WK_SOFTWARE_SOURCE_RX = re.compile(r"\b(?:open[- ]source|source[- ]code|source[- ]available|source[- ]control|source[- ]map|data source|resource)\b", re.IGNORECASE)


def _wk_summary_hedged(i: IncidentView) -> bool:
    """A hedged or anonymously sourced original report summary ('unnamed sources say', 'may have') disqualifies the item here only.
    Software terminology that merely contains the word 'source' ('open source software', 'source code') is not anonymous sourcing."""
    for r in i.reports:
        if r["role"] != "original":
            continue
        txt = _WK_SOFTWARE_SOURCE_RX.sub(" ", r.get("summary") or "")
        if ed._HEDGE_RX.search(txt) or ed._ANON_RX.search(txt):
            return True
    return False


def _wk_tokens(i: IncidentView) -> frozenset:
    return frozenset(t for t in re.findall(r"[a-z0-9]+", ed.core_title(i.headline).lower()) if len(t) > 2 and t not in ed._STOP)


def _wk_entities(i: IncidentView) -> frozenset:
    """Named entities in the headline (capitalised words and mixed-case names such as 'OpenAI'), used to tell apart similar-looking
    developments from different vendors."""
    return frozenset(w.lower() for w in re.findall(r"\b[A-Z][A-Za-z0-9]{2,}\b", ed.core_title(i.headline)) if w.lower() not in ed._STOP)


def _wk_same_development(a: frozenset, b: frozenset, ea: frozenset = frozenset(), eb: frozenset = frozenset()) -> bool:
    """Same development = similar wording AND compatible named entities. 'OpenAI releases new AI model' and 'Anthropic releases new
    AI model' share most words but name different vendors: separate developments."""
    if ea and eb and not (ea & eb):
        return False
    return bool(a and b) and len(a & b) / len(a | b) >= 0.5


def _wk_text(i: IncidentView) -> str:
    return " ".join([i.headline] + [r["title"] for r in i.reports if r["role"] != "commentary"])


def _wk_au_text(i: IncidentView) -> str:
    """Text checked for an Australian mention. For aggregator-fed reports the trailing ' - Outlet' attribution (e.g. ' - Guardian Australia')
    is stripped from the title and the outlet name from the summary: the publisher's identity is not the story's geography."""
    agg = any(r["source_kind"] == we.AGGREGATOR for r in i.reports)
    parts = [ed.core_title(i.headline) if agg else i.headline]
    for r in i.reports:
        if r["role"] == "commentary":
            continue
        title, summary = r["title"] or "", r.get("summary") or ""
        if r["source_kind"] == we.AGGREGATOR:
            core = ed.core_title(title)
            outlet = title[len(core):].lstrip(" -–|").strip() if core != title else ""
            for name in {outlet, r.get("publisher") or ""} - {""}:
                summary = re.sub(re.escape(name), " ", summary, flags=re.IGNORECASE)
            title = core
        parts += [title, summary]
    return " ".join(parts)


def _wk_au(i: IncidentView) -> bool:
    """Australia is named in the headline, a report title or a report summary (publisher identity alone, including an aggregator's
    ' - Outlet' attribution, does not count)."""
    return bool(_WK_AU_RX.search(_wk_au_text(i)))


def _wk_category(text: str) -> tuple[str, int] | None:
    best = None
    for name, weight, rx in _WK_CAT_RX:
        if rx.search(text) and (best is None or weight > best[1]):
            best = (name, weight)
    return best


_WK_SUMMARY_MAX = 200


def _wk_first_sentence(txt: str) -> str:
    """The first COMPLETE sentence, at most _WK_SUMMARY_MAX characters; '' when there is none (a summary is omitted rather than cut
    mid-sentence). Abbreviation-style full stops ('U.S.', 'No. 5') do not end a sentence."""
    for m in re.finditer(r"[.!?](?=\s|$)", txt):
        head = txt[:m.end()]
        if re.search(r"(?:\b[A-Z]|\bNo|\bSt|\bDr|\bMr|\bMs|\bInc|\bLtd|\bCorp|\bvs)\.$", head):
            continue
        return head.strip() if 40 <= len(head) <= _WK_SUMMARY_MAX else ""
    return txt if 40 <= len(txt) <= _WK_SUMMARY_MAX and txt.endswith(("\"", "”")) else ""


def _wk_summary(i: IncidentView) -> str:
    """First sentence of the best original report's own summary, trimmed. Empty when it only repeats the headline."""
    head = re.sub(r"\W+", " ", i.headline).strip().lower()
    for r in i.reports:
        if r["role"] != "original":
            continue
        txt = re.sub(r"<[^>]+>|&\w+;", " ", r.get("summary") or "")
        txt = re.sub(r"get our (?:breaking )?news .*$", " ", txt, flags=re.IGNORECASE)   # newsletter boilerplate some feeds append
        txt = re.sub(r"\s+", " ", txt).strip()
        if len(txt) < 40 or re.sub(r"\W+", " ", txt).strip().lower().startswith(head[:50]):
            continue
        sentence = _wk_first_sentence(txt)
        if sentence:
            return sentence
    return ""


def worth_knowing(ev: EvidenceSet, *, limit: int = WORTH_KNOWING_LIMIT) -> list[tuple[IncidentView, str, int]]:
    """Credible, relevant technology developments from the last 72 hours that are NOT actionable incidents (priority REFERENCE).

    Topic relevance and editorial quality decide inclusion (``disposition = BRIEF`` is deliberately not used: it admits sport and politics).
    Needs a non-aggregator original report from a primary, mainstream or specialist publisher; aggregator-only, hedged or anonymous
    (unverified) items are left out. Returns (incident, category, score) best first, at most ``limit``, at most two per category.
    """
    cutoff = ev.generated_at - timedelta(hours=WORTH_KNOWING_HOURS)
    latest = ev.generated_at + timedelta(hours=_WK_FUTURE_SKEW_HOURS)
    scored = []
    for i in ev.incidents:
        via = _wk_via_aggregator(i)
        if i.priority != "REFERENCE" or not i.last_seen or not (cutoff <= i.last_seen <= latest) or (i.evidence_status not in _WK_EVIDENCE_POINTS and not via):
            continue
        if _wk_disruption(i):
            continue
        if len(i.headline) < 25 or _WK_LOW_QUALITY_RX.search(i.headline):
            continue
        if not via and not _wk_credible_original(i):
            continue
        if _wk_summary_hedged(i):
            continue
        if _WK_CORPORATE_RX.search(i.headline + " " + " ".join(r.get("summary") or "" for r in i.reports if r["role"] == "original")):
            continue
        text = _wk_text(i)
        cat = _wk_category(text)
        if not cat:
            continue
        kinds = {r["source_kind"] for r in i.reports if r["role"] == "original"}
        score = (cat[1] + _WK_EVIDENCE_POINTS.get(i.evidence_status, 0) + (2 if we.PRIMARY in kinds else 1 if we.SPECIALIST in kinds else 0)
                 + (2 if _wk_au(i) else 0) + (1 if i.last_seen >= ev.generated_at - timedelta(hours=24) else 0)
                 + (1 if i.materiality in ("high", "medium") else 0))
        scored.append((i, cat[0], score))
    scored.sort(key=lambda t: (-t[2], -(t[0].last_seen.timestamp())))
    out, per, seen = [], Counter(), []
    for i, cat, score in scored:
        toks, ents = _wk_tokens(i), _wk_entities(i)
        if any(_wk_same_development(toks, t, ents, e) for t, e in seen):   # the same development from another publisher must not use a second slot
            continue
        seen.append((toks, ents))
        if per[cat] >= _WK_PER_CATEGORY:
            continue
        per[cat] += 1
        out.append((i, cat, score))
        if len(out) >= limit:
            break
    return out


def _wk_official_source(i: IncidentView) -> str:
    """The primary publisher the official confirmation comes from (e.g. the vendor advisory feed), named so the line says WHO confirmed."""
    for r in i.reports:
        if r["role"] == "original" and r["source_kind"] == we.PRIMARY:
            return r["source_name"] or r["publisher"]
    return "a primary source"


def _wk_line(i: IncidentView, cat: str) -> str:
    au = "Australian relevance stated in report" if _wk_au(i) else "International development; no Australian operational impact established"
    via = _wk_via_aggregator(i)
    basis = (f"single source via aggregator feed (publisher: {via})" if via
             else "single-source report" if i.evidence_status == "reported"
             else f"officially confirmed by {_wk_official_source(i)}" if i.evidence_status == "officially_confirmed"
             else f"independently corroborated ({i.independent_publishers} publishers)")
    tags = [cat, basis, au] + (["retrospective report"] if i.impact_status == "retrospective" else [])
    summary = _wk_summary(i)
    return f"- [{' · '.join(tags)}] {i.headline}" + (f" — {summary}" if summary else "") + f" {_cite(i)}"


def worth_knowing_lines(ev: EvidenceSet) -> list[str]:
    items = worth_knowing(ev)
    lines = ["", f"WORTH KNOWING (last {WORTH_KNOWING_HOURS}h; credible technology developments with no confirmed outage or immediate service impact; informative, not escalated)"]
    return lines + ([_wk_line(i, c) for i, c, _ in items] or ["- No credible technology development outside the incident sections."])


# ── Weekly change detection (existing SnapshotStore; no database migration) ─────────────────────────────

def _patterns(ev: EvidenceSet) -> dict[str, list[IncidentView]]:
    acts = [i for i in ev.incidents if i.priority in _ACTIONABLE and i.impact_status not in ("warning", "forecast")]
    bysec: dict[str, list[IncidentView]] = defaultdict(list)
    for i in acts:
        for s in i.record["critical_service_dependencies"]:
            bysec[s].append(i)
    out = {}
    for s, items in bysec.items():
        pubs = {r["publisher"] for i in items for r in i.reports if r["role"] == "original"}
        days = {i.last_seen.date() for i in items if i.last_seen}
        if len(items) >= 3 and len(pubs) >= 3 and len(days) >= 2:
            out[s] = items
    return out


def snapshot_payload(ev: EvidenceSet) -> dict:
    """The compact record stored for next week's comparison: identities by report id (incident ids change as reports join), not copies of articles.
    ``restoration_status`` is stored as one of ed.RESTORATION_STATUSES (older snapshots hold only ongoing / restored / unknown)."""
    return {"date": ev.generated_at.date().isoformat(), "kind": "weekly_evidence_incidents", "method_version": ev.method_version,
            "incidents": [{"incident_id": i.incident_id, "report_ids": i.report_ids, "headline": i.headline, "priority": i.priority,
                           "materiality": i.materiality, "evidence_status": i.evidence_status,
                           "restoration_status": i.record["restoration_status"]} for i in ev.incidents if i.priority in _ACTIONABLE],
            "patterns": sorted(_patterns(ev))}


def compare_snapshots(prev: dict, ev: EvidenceSet) -> dict:
    """New / continuing / materially changed / resolved / no-longer-reported incidents and newly emerging patterns, matched by report-id overlap.
    RESOLVED only when the incident is now 'restored' (and was not before): 'partially_restored' is still a current disruption and
    'unknown' is not a resolution."""
    prev_by_report = {rid: p for p in prev["incidents"] for rid in p["report_ids"]}
    cur = [i for i in ev.incidents if i.priority in _ACTIONABLE]
    out = {"new": [], "continuing": [], "changed": [], "resolved": [], "no_longer_reported": [], "emerging_patterns": []}
    seen_prev = set()
    for i in cur:
        hits = {prev_by_report[r]["incident_id"]: prev_by_report[r] for r in i.report_ids if r in prev_by_report}
        if not hits:
            out["new"].append(i)
            continue
        p = next(iter(hits.values()))
        seen_prev.update(hits)
        diffs = [f"{label}: {p[key]} → {now}" for label, key, now in (("priority", "priority", i.priority), ("materiality", "materiality", i.materiality),
                                                                       ("evidence", "evidence_status", i.evidence_status)) if p.get(key) != now]
        if i.record["restoration_status"] == "restored" and p["restoration_status"] != "restored":
            out["resolved"].append((i, p))
        elif diffs:
            out["changed"].append((i, p, diffs))
        else:
            out["continuing"].append((i, p))
    cur_reports = {r for i in ev.incidents for r in i.report_ids}
    for p in prev["incidents"]:
        if p["incident_id"] not in seen_prev and not (set(p["report_ids"]) & cur_reports):
            out["no_longer_reported"].append(p)
    out["emerging_patterns"] = [s for s in _patterns(ev) if s not in prev.get("patterns", [])]
    return out


def load_previous_snapshot(path: str | None, before: datetime) -> dict | None:
    """The latest stored snapshot dated before this week's, from the existing SnapshotStore (append-only JSONL). None when unavailable."""
    if not path:
        return None
    rows = [r for r in we.SnapshotStore(path).load() if r.get("kind") == "weekly_evidence_incidents" and r.get("date", "") < before.date().isoformat()]
    return rows[-1] if rows else None


def record_snapshot(path: str | None, ev: EvidenceSet) -> bool:
    if not path:
        return False
    we.SnapshotStore(path).append(snapshot_payload(ev))
    return True


# ── Weekly Intelligence & Decision Brief view ────────────────────────────────────────────────────────

def weekly_view(ev: EvidenceSet, previous: dict | None = None) -> list[str]:
    acts = [i for i in ev.incidents if i.priority in _ACTIONABLE]
    cnt = Counter(i.priority for i in ev.incidents)
    lines = ["📊 EVIDENCE-BASED WEEK (V1)",
             f"{len(ev.incidents)} incidents from {ev.n_events} reports: {cnt['ESCALATE']} escalate, {cnt['VERIFY']} verify, {cnt['WATCH']} watch; method {ev.method_version}.", ""]
    lines.append("What changed since the previous snapshot")
    if previous is None:
        lines.append("- Change cannot be assessed: no prior snapshot is available. Showing this week's actionable incidents only.")
    else:
        cmp_ = compare_snapshots(previous, ev)
        lines.append(f"- Compared with the snapshot of {previous['date']}: {len(cmp_['new'])} new, {len(cmp_['continuing'])} continuing, "
                     f"{len(cmp_['changed'])} materially changed, {len(cmp_['resolved'])} resolved, {len(cmp_['no_longer_reported'])} no longer reported.")
        lines += [f"  NEW {_line(i)[2:]}" for i in cmp_["new"][:5]]
        lines += [f"  CHANGED {i.headline} ({'; '.join(d)}) {_cite(i)}" for i, _p, d in cmp_["changed"][:5]]
        lines += [f"  CONTINUING {i.headline} {_cite(i)}" for i, _p in cmp_["continuing"][:3]]
        lines += [f"  RESOLVED {i.headline} (restoration reported) {_cite(i)}" for i, _p in cmp_["resolved"][:4]]
        lines += [f"  NO LONGER REPORTED {p['headline']} (resolution not assessed)" for p in cmp_["no_longer_reported"][:3]]
        lines.append("  Emerging recurring patterns: " + (", ".join(cmp_["emerging_patterns"]) or "none new"))
    lines += ["", "Major incidents"]
    lines += [_line(i, True) for i in ev.by_priority("ESCALATE")[:6]] or ["- No incident met the escalation rule this week."]
    pats = _patterns(ev)
    lines += ["", "Recurring patterns (threshold: ≥3 incidents, ≥3 publishers, ≥2 days)"]
    lines += [f"- {s}: {len(items)} incidents [{', '.join(i.incident_id for i in items[:4])}]" for s, items in sorted(pats.items(), key=lambda kv: -len(kv[1]))] \
        or ["- No pattern met the threshold."]
    ents: dict[str, list[IncidentView]] = defaultdict(list)
    for i in acts:
        r = i.reports[0]
        for o in sorted(ed.detect_candidate({"id": r["report_id"], "title": r["title"], "source": r["source_name"]}).orgs):
            if o in {"microsoft", "azure", "aws", "google cloud", "cloudflare", "crowdstrike", "oracle", "salesforce", "github", "telstra", "optus", "nbn"}:
                ents[o].append(i)
    deps = [f"- {o}: shared by {len(v)} incidents [{', '.join(i.incident_id for i in v[:3])}]" for o, v in ents.items() if len(v) >= 2]
    lines += ["", "Systemic dependencies (named providers appearing in ≥2 incidents; no causal link asserted)"] + (deps or ["- None repeated."])
    lines += ["", "Evidence-supported implications (each cites its incident)"]
    imps = [f"- {i.headline}: {_facts(i)}; evidence {STATUS_LABEL[i.evidence_status]}; dependencies "
            f"{', '.join(i.record['critical_service_dependencies']) or 'none recognised'} {_cite(i)}" for i in ev.by_priority("ESCALATE")[:4]]
    lines += imps or ["- No implication is supported at escalation level this week."]
    lines += ["", "Decisions and emerging risks to monitor"]
    dec = [f"- DECIDE: confirm or stand down provisional escalation — {i.headline} ({i.record['next_verification_action']})"
           for i in ev.by_priority("ESCALATE") if i.provisional][:4]
    dec += [f"- MONITOR: {i.headline} — unresolved: {i.record['next_verification_action']}" for i in ev.by_priority("VERIFY")[:4]]
    dec += [f"- WATCH FORWARD: {i.headline} ({i.impact_status}) {_cite(i)}" for i in ev.by_priority("WATCH") if i.impact_status in ("warning", "forecast")][:3]
    lines += dec or ["- No open decision."]
    return lines


# ── Communications & Presence Brief view ──────────────────────────────────────────────────────────────

_AUDIENCE = {
    "Operational Resilience": "operational-resilience and technology-risk leaders in regulated entities",
    "Business Continuity": "business-continuity and crisis-management practitioners",
    "AI-Augmented Leadership": "technology executives governing AI and automation",
    "Decision Quality & Governance": "senior leaders accountable for risk decisions",
    "Future of Work": "workforce and technology-strategy leaders",
}
_CONTRIBUTION = {
    "Operational Resilience": "your practitioner view of impact tolerances, dependency mapping and what you would test before the next incident (the brief cannot supply experience)",
    "Business Continuity": "how you would run the first 24 hours and the decisions you would take (practitioner judgement the brief cannot supply)",
    "AI-Augmented Leadership": "how you would govern the technology involved and where human accountability sits (your judgement, not news)",
}


def _entity(i: IncidentView) -> str:
    r = i.reports[0]
    orgs = [o for o in ed.detect_candidate({"id": r["report_id"], "title": r["title"], "source": r["source_name"]}).orgs if ed._ORG_LEX.search(o)]
    return orgs[0].title() if orgs else ""


def _argument(i: IncidentView, entity: str) -> tuple[str, bool]:
    """(one-sentence central argument, supported?). Supported only when the evidence status is officially confirmed or corroborated and the
    headline states an impact; otherwise the sentence is a labelled hypothesis and the topic cannot be publication-ready."""
    deps = ", ".join(d.replace("_", " ") for d in i.record["critical_service_dependencies"]) or "a shared dependency"
    who = entity or "a single provider"
    if i.event_type == "outage":
        text = f"When {who} fails, the exposure sits in {deps} concentration, so test dependency and exit plans before the next outage rather than after it."
    elif i.event_type in ("cyber_incident", "data_breach"):
        text = f"The incident at {who} shows that resilience depends on knowing which third-party and {deps} dependencies can disrupt service, not only on preventing intrusion."
    elif i.event_type in ("supply_shortfall", "hazard"):
        text = "Forecast and warning notices are the earliest usable resilience signal, so operating plans should be triggered by them and not by the outage."
    else:
        text = f"This event is a prompt to check {'the ' + deps if deps != 'a shared dependency' else deps} against impact tolerances."
    supported = i.evidence_status in ("officially_confirmed", "corroborated") and i.impact_status == "stated"
    return (text if supported else "Hypothesis (unsupported until verified): " + text), supported


def _deps_phrase(i: IncidentView) -> str:
    deps = [d.replace('_', ' ') for d in i.record['critical_service_dependencies']]
    return (', '.join(deps) + ' affected') if deps else 'dependencies not identified'


def _headline(i: IncidentView, entity: str) -> str:
    who = entity or "one critical provider"
    t = i.event_type
    if t == "outage":
        return f"What the {who} outage tells resilience owners about dependency risk"
    if t in ("cyber_incident", "data_breach"):
        return f"Beyond the breach at {who}: mapping the dependencies that actually carry the risk"
    if t in ("supply_shortfall", "hazard"):
        return "Why forecast notices, not outages, should trigger your operating plans"
    return f"What {who} teaches about operating through disruption"


def comms_view(ev: EvidenceSet, *, existing_titles: list[str] | None = None, pillar_fn=None, similarity_fn=None, research_fn=None) -> list[str]:
    """What is worth contributing publicly. pillar_fn(text) -> pillar label or None, similarity_fn(title, titles) -> 0..1 and research_fn(headline) ->
    list of related research references are injected by the comms hook (they live in platform-runtime). Recommendation only: publication needs the
    Captain's approval, and an unsupported argument is never marked ready."""
    existing_titles = existing_titles or []
    rows = []
    for i in ev.incidents:
        if i.priority not in _ACTIONABLE or i.impact_status in ("potential", "retrospective"):
            continue
        pillar = pillar_fn(i.headline) if pillar_fn else None
        if pillar_fn and not pillar:
            continue                                             # no alignment with the Captain's pillars: not worth contributing
        sim = similarity_fn(i.headline, existing_titles) if (similarity_fn and existing_titles) else 0.0
        entity = _entity(i)
        if not entity and not i.record["critical_service_dependencies"]:
            continue                                             # nothing specific to argue from: not a topic
        argument, supported = _argument(i, entity)
        if sim >= 0.7:
            ready = "hold — duplicates existing content"
        elif not supported:
            ready = "hold — argument unsupported until a second or primary source confirms the facts"
        else:
            ready = "ready to draft (argument supported; Captain approval still required to publish)"
        rows.append((i, pillar, sim, entity, argument, supported, ready))
    rows.sort(key=lambda r: (not r[5], r[2] >= 0.7, -r[0].evidence_confidence))
    lines = ["📡 EVIDENCE-BASED CONTRIBUTION CANDIDATES (V1) — recommendation only; publication is approval-only and nothing is published automatically", ""]
    for n, (i, pillar, sim, entity, argument, supported, ready) in enumerate(rows[:5], 1):
        refs = research_fn(i.headline) if research_fn else []
        orig = ("not assessed (no published-content titles supplied)" if not existing_titles
                else f"duplicate of existing content (similarity {sim:.2f})" if sim >= 0.7
                else f"no duplicate found against {len(existing_titles)} existing titles (similarity {sim:.2f})")
        lines += [f"{n}. Proposed headline: {_headline(i, entity)}",
                  f"    audience: {_AUDIENCE.get(pillar or '', 'senior operational-risk and technology leaders')}",
                  f"    central argument: {argument}",
                  f"    why now: first reported {i.first_seen.strftime('%d %b') if i.first_seen else 'recently'}; {_facts(i)}; {_deps_phrase(i)}",
                  f"    evidence and provenance: {STATUS_LABEL[i.evidence_status]} — {', '.join(i.evidence_basis[:3]) or 'no original report'} {_cite(i)}",
                  f"    what only you can add: {_CONTRIBUTION.get(pillar or '', 'your own practitioner judgement and decisions, which the brief cannot supply')}",
                  f"    originality: {orig}" + (f"; related research: {'; '.join(refs[:2])}" if refs else "; related research: none found"),
                  f"    relevance: {pillar or 'unclassified'}",
                  f"    publication readiness: {ready}",
                  f"    evidence gaps: {i.record['next_verification_action']}"]
    if not rows:
        lines.append("- No incident this period is both evidenced and aligned with a content pillar.")
    return lines
