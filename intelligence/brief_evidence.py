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

from intelligence import event_detection as ed
from intelligence import weekly_evidence as we

MASTER_FLAG = "BRIEF_EVIDENCE_V1"
FLAGS = {"morning": "BRIEF_EVIDENCE_V1_MORNING", "weekly": "BRIEF_EVIDENCE_V1_WEEKLY", "comms": "BRIEF_EVIDENCE_V1_COMMS"}
SNAPSHOT_ENV = "BRIEF_EVIDENCE_SNAPSHOT_PATH"
_TRUE = ("1", "true", "yes", "on")
_ACTIONABLE = ("ESCALATE", "VERIFY", "WATCH")
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
            record=ed.escalation_record(d, now=now), reasons=list(d.reasons)))
    order = {"ESCALATE": 0, "VERIFY": 1, "WATCH": 2, "REFERENCE": 3}
    incidents.sort(key=lambda i: (order[i.priority], -(i.last_seen.timestamp() if i.last_seen else 0)))
    return EvidenceSet(ed.METHOD_VERSION, now, window_hours, len(events), incidents)


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
        out.append({"id": str(r.get("event_id")), "title": r.get("raw_title") or "", "summary": r.get("raw_summary") or "",
                    "source": reg.get("source_name") or "", "geography": r.get("geography") or "",
                    "collected_at": r.get("collected_at"), "published_at": r.get("published_at"), "url": r.get("canonical_url")})
    return out


# ── helpers shared by the views ───────────────────────────────────────────────────────────────────────

def _cite(i: IncidentView) -> str:
    pubs = sorted({r["source_name"] or r["publisher"] for r in i.reports if r["role"] != "commentary"})
    return f"[{i.incident_id}; {len(i.reports)} report(s); " + ", ".join(pubs[:3]) + (" …" if len(pubs) > 3 else "") + "]"


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
    if r.get("restoration_status") != "unknown":
        bits.append(r["restoration_status"])
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


def _line(i: IncidentView, with_action: bool = False) -> str:
    s = f"- [{_tag(i)}] {i.headline} — {_facts(i)}; confidence {i.evidence_confidence:.2f} {_cite(i)}"
    if with_action:
        s += f"\n    next: {i.record['next_verification_action']}"
    return s


_DATE_RX = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b")


def forward_dated_items(ev: EvidenceSet, *, hours: int = 72) -> list[tuple[IncidentView, datetime]]:
    """Notices whose headline names a date inside the next ``hours`` (e.g. 'LOR1 forecast … on 20/11/2026'). Dates are read, never inferred."""
    out = []
    for i in ev.incidents:
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


def morning_view(ev: EvidenceSet) -> list[str]:
    recent = [i for i in ev.incidents if i.last_seen and i.last_seen >= ev.generated_at - timedelta(hours=24)]
    editorial = [i for i in recent if i.impact_status not in ("warning", "forecast") and _editorial_only(i)]
    active = [i for i in recent if i.impact_status not in ("warning", "forecast") and i not in editorial]
    firm = [i for i in active if i.priority in ("ESCALATE", "WATCH") and i.impact_status == "stated"
            and i.evidence_status in ("officially_confirmed", "corroborated")]
    single = [i for i in active if i.priority in ("ESCALATE", "WATCH") and i.impact_status == "stated" and i.evidence_status == "reported"]
    verify = [i for i in active if i.priority == "VERIFY" or (i.priority in ("ESCALATE", "WATCH") and i not in firm and i not in single)]
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
    # established, e.g. a historic outage still being written about) is listed but not counted.
    firm_n = [i for i in firm if i.record["restoration_status"] != "unknown"]
    single_n = [i for i in single if i.record["restoration_status"] != "unknown"]
    stale_n = len(firm) + len(single) - len(firm_n) - len(single_n)
    stale = (f" ({stale_n} more reported with current status unknown — not counted as current disruptions)" if stale_n else "")
    lines = []
    if not recent:
        lines.append("⚠️ EVIDENCE COVERAGE INSUFFICIENT: no reports collected in the last 24 hours; nothing below should be read as all quiet.")
    lines += ["🛰 EVIDENCE-BASED PICTURE (V1)", f"{len(recent)} incident(s) assessed from {ev.n_events} report(s); method {ev.method_version}.", ""]
    if not recent:
        lines.append("Operational situation: evidence coverage is insufficient (no recent reports), so no judgement about current disruption can be made.")
    elif firm_n or single_n:
        lines.append(f"Operational situation: {len(firm_n)} confirmed or corroborated and {len(single_n)} single-source reported disruption(s) in the last 24 hours.{stale}")
    else:
        lines.append(f"Operational situation: no confirmed, corroborated or single-source reported current disruption in the last 24 hours{stale}.")
    if notices or exposure:
        lines.append("Credible warnings and emerging exposures are listed separately below; they are not current disruptions and no operational consequence is inferred from them.")
    lines.append("")
    lines.append("What matters today — OFFICIALLY CONFIRMED or CORROBORATED incidents")
    lines += [_line(i, True) for i in firm[:6]] or ["- None officially confirmed or corroborated in the last 24 hours."]
    lines += ["", "REPORTED by one source (provisional until a second or primary source)"]
    lines += [_line(i, True) for i in single[:6]] or ["- None."]
    lines += ["", "IMPACT NOT YET ESTABLISHED (credible source; effect on service not yet shown)"]
    lines += [_line(i, True) for i in impact_open[:6]] or ["- None."]
    lines += ["", "RETROSPECTIVE REPORTS (about past events; not live disruptions)"]
    lines += [_line(i, True) for i in retro_open[:6]] or ["- None."]
    lines += ["", "SOURCE NOT YET VERIFIED (hedged, aggregator-only, low-quality source, editorial relevance only or weakly evidenced; not treated as fact)"]
    lines += [_line(i, True) for i in source_open[:6]] or ["- None."]
    lines += ["", "WARNINGS AND FORECASTS (not confirmed incidents)"]
    lines += [_line(i) for i in notices[:6]] or ["- No active warning or forecast notice."]
    lines += ["", "EMERGING EXPOSURE (credible advisories and risks; no confirmed current disruption; nothing here states an operational consequence)"]
    lines += [_line(i, True) for i in exposure[:6]] or ["- None."]
    lines += ["", "Operational implications (only what the cited reports state)"]
    imp = [f"- {'tier ' + str(i.sector_tier) if i.sector_tier else 'unclassified sector'}: "
           f"{', '.join(i.record['critical_service_dependencies']) or 'no recognised service'} — {_facts(i)} {_cite(i)}"
           for i in firm[:4] + single[:2]]
    lines += imp or ["- No operational implication is supported by corroborated reports today."]
    lines += ["", "Forward watch, next 24–72 hours"]
    fw = [f"- Ongoing: {i.headline} (restoration {i.record['restoration_status']}) {_cite(i)}"
          for i in active if i.record["restoration_status"] == "ongoing" and i.priority in ("ESCALATE", "WATCH") and _fw_credible(i)][:4]
    fw += [f"- Forecast/warning: {i.headline} {_cite(i)}" for i in notices[:4]]
    fw += [f"- Dated notice for {d.strftime('%d %b')}: {i.headline} {_cite(i)}" for i, d in forward_dated_items(ev) if i not in notices and _fw_credible(i)][:3]
    fw += [f"- Verify: {i.headline} → {i.record['next_verification_action']} {_cite(i)}" for i in [x for x in impact_open + exposure + source_open if _fw_credible(x)][:2]]
    lines += fw or ["- No ongoing incident, warning or dated notice to watch."]
    return lines


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
    """The compact record stored for next week's comparison: identities by report id (incident ids change as reports join), not copies of articles."""
    return {"date": ev.generated_at.date().isoformat(), "kind": "weekly_evidence_incidents", "method_version": ev.method_version,
            "incidents": [{"incident_id": i.incident_id, "report_ids": i.report_ids, "headline": i.headline, "priority": i.priority,
                           "materiality": i.materiality, "evidence_status": i.evidence_status,
                           "restoration_status": i.record["restoration_status"]} for i in ev.incidents if i.priority in _ACTIONABLE],
            "patterns": sorted(_patterns(ev))}


def compare_snapshots(prev: dict, ev: EvidenceSet) -> dict:
    """New / continuing / materially changed / resolved / no-longer-reported incidents and newly emerging patterns, matched by report-id overlap."""
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
