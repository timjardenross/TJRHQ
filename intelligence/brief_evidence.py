"""Shared evidence foundation for the three briefs (V1) — one event identity, one materiality assessment, one provenance trail.

Morning Command Brief, Weekly Intelligence & Decision Brief and Communications & Presence Brief all read the SAME ``EvidenceSet`` built
once from validated reports by the staged detector (``intelligence.event_detection``, method wk-detect/0.5.0-tiered-v2). The three
``*_view`` functions only SELECT and ARRANGE incidents; none of them scores, classifies severity or invents a claim. Every statement a
view emits carries the incident id and its report ids so it can be traced back to publisher, URL and timestamp.

Feature flags (all default OFF; nothing changes in a live brief unless one is set):
    BRIEF_EVIDENCE_V1            enable all three
    BRIEF_EVIDENCE_V1_MORNING / _WEEKLY / _COMMS   enable one
Publication is never automatic: the comms view only recommends and always states ``approval-only``.
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
_TRUE = ("1", "true", "yes", "on")
_ACTIONABLE = ("ESCALATE", "VERIFY", "WATCH")


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
    impact_status: str              # confirmed | unconfirmed | retrospective | potential
    evidence_confidence: float
    independent_publishers: int
    provisional: bool
    grouping_confidence: float
    reports: list[dict]             # provenance: report_id, publisher, source_kind, title, url, collected_at, role
    first_seen: datetime | None
    last_seen: datetime | None
    record: dict                    # ed.escalation_record(): confirmed vs reported, customers, restoration, dependencies, next action
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
    """events: dicts with id, title, source, geography, collected_at, optional url/summary. Pure; no I/O."""
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
                            "title": m.title, "url": e.get("url"), "collected_at": m.published.isoformat() if m.published else None,
                            "role": role})
        times = [m.published for m in members if m.published]
        incidents.append(IncidentView(
            incident_id=_incident_id([m.event_id for m in members]), headline=d.headline.title, priority=d.priority,
            materiality=d.materiality, sector_tier=d.sector_tier, event_type=d.event_type, impact_status=d.impact_status,
            evidence_confidence=d.evidence_confidence, independent_publishers=d.group.independent_publishers,
            provisional=d.provisional, grouping_confidence=d.group.grouping_confidence, reports=reports,
            first_seen=min(times) if times else None, last_seen=max(times) if times else None,
            record=ed.escalation_record(d), reasons=list(d.reasons)))
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
                      "&select=event_id,raw_title,raw_summary,geography,collected_at,canonical_url,intelligence_source_registry(source_name)")
    except Exception:  # noqa: BLE001 - evidence layer is additive; the legacy brief must still render
        return []
    out = []
    for r in rows or []:
        reg = r.get("intelligence_source_registry") or {}
        out.append({"id": str(r.get("event_id")), "title": r.get("raw_title") or "", "summary": r.get("raw_summary") or "",
                    "source": reg.get("source_name") or "", "geography": r.get("geography") or "",
                    "collected_at": r.get("collected_at"), "url": r.get("canonical_url")})
    return out


# ── helpers shared by the views ───────────────────────────────────────────────────────────────────────

def _cite(i: IncidentView) -> str:
    pubs = sorted({r["source_name"] or r["publisher"] for r in i.reports if r["role"] != "commentary"})
    return f"[{i.incident_id}; {len(i.reports)} report(s); " + ", ".join(pubs[:3]) + (" …" if len(pubs) > 3 else "") + "]"


def _facts(i: IncidentView) -> str:
    r = i.record
    bits = [r["impact"]]
    if r.get("affected_customers"):
        bits.append(f"{r['affected_customers']:,} customers")
    if r.get("restoration_status") != "unknown":
        bits.append(r["restoration_status"])
    if r.get("duration"):
        bits.append(r["duration"])
    return ", ".join(bits)


def _line(i: IncidentView, with_action: bool = False) -> str:
    kinds = {r["source_kind"] for r in i.reports if r["role"] != "commentary"}
    tag = "provisional" if i.provisional else "corroborated" + (" via aggregator feeds only" if kinds <= {we.AGGREGATOR} else "")
    s = f"- [{i.priority}{' ' + tag if i.priority == 'ESCALATE' else ''}] {i.headline} — {_facts(i)}; confidence {i.evidence_confidence:.2f} {_cite(i)}"
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
            if ev.generated_at <= d <= ev.generated_at + timedelta(hours=hours):
                out.append((i, d))
    return out


# ── Morning Command Brief view ────────────────────────────────────────────────────────────────────────

def morning_view(ev: EvidenceSet) -> list[str]:
    recent = [i for i in ev.incidents if i.last_seen and i.last_seen >= ev.generated_at - timedelta(hours=24)]
    confirmed = [i for i in recent if i.priority in ("ESCALATE", "WATCH") and i.impact_status == "confirmed"]
    verify = [i for i in recent if i.priority == "VERIFY" or (i.priority == "ESCALATE" and i.impact_status != "confirmed")]
    lines = ["🛰 EVIDENCE-BASED PICTURE (V1)", f"{len(recent)} incident(s) assessed from {ev.n_events} report(s); method {ev.method_version}.", ""]
    lines.append("What matters today — CONFIRMED incidents")
    lines += [_line(i, True) for i in confirmed[:6]] or ["- None confirmed in the last 24 hours."]
    lines += ["", "REQUIRES VERIFICATION (unconfirmed or weakly evidenced; not treated as fact)"]
    lines += [_line(i, True) for i in verify[:6]] or ["- Nothing awaiting verification."]
    lines += ["", "Operational implications (only what the cited reports state)"]
    imp = [f"- {'tier ' + str(i.sector_tier) if i.sector_tier else 'unclassified sector'}: "
           f"{', '.join(i.record['critical_service_dependencies']) or 'no recognised service'} — {_facts(i)} {_cite(i)}"
           for i in confirmed[:4]]
    lines += imp or ["- No operational implication is supported by confirmed reports today."]
    lines += ["", "Forward watch, next 24–72 hours"]
    fw = [f"- Ongoing: {i.headline} (restoration {i.record['restoration_status']}) {_cite(i)}"
          for i in recent if i.record["restoration_status"] == "ongoing" and i.priority in ("ESCALATE", "WATCH")][:4]
    fw += [f"- Dated notice for {d.strftime('%d %b')}: {i.headline} {_cite(i)}" for i, d in forward_dated_items(ev)[:4]]
    fw += [f"- Verify: {i.headline} → {i.record['next_verification_action']}" for i in verify[:2]]
    lines += fw or ["- No ongoing incident or dated notice to watch."]
    return lines


# ── Weekly Intelligence & Decision Brief view ────────────────────────────────────────────────────────

def weekly_view(ev: EvidenceSet, previous_ids: set[str] | None = None) -> list[str]:
    acts = [i for i in ev.incidents if i.priority in _ACTIONABLE]
    cnt = Counter(i.priority for i in ev.incidents)
    new = [i for i in acts if previous_ids is not None and i.incident_id not in previous_ids]
    lines = ["📊 EVIDENCE-BASED WEEK (V1)",
             f"{len(ev.incidents)} incidents from {ev.n_events} reports: {cnt['ESCALATE']} escalate, {cnt['VERIFY']} verify, {cnt['WATCH']} watch; method {ev.method_version}.", ""]
    lines.append("What changed this week")
    if previous_ids is None:
        lines.append("- No prior-week snapshot to compare; showing the week's actionable incidents only.")
    else:
        lines += [_line(i) for i in new[:6]] or ["- No new actionable incidents since the previous snapshot."]
    lines += ["", "Major incidents"]
    lines += [_line(i, True) for i in ev.by_priority("ESCALATE")[:6]] or ["- No incident met the escalation rule this week."]
    # recurring patterns: >=3 distinct incidents, >=3 evidence-bearing publishers, >=2 days (same thresholds as the shared foundation)
    bysec: dict[str, list[IncidentView]] = defaultdict(list)
    for i in acts:
        for s in i.record["critical_service_dependencies"]:
            bysec[s].append(i)
    patterns = []
    for s, items in sorted(bysec.items(), key=lambda kv: -len(kv[1])):
        pubs = {r["publisher"] for i in items for r in i.reports if r["role"] == "original"}
        days = {i.last_seen.date() for i in items if i.last_seen}
        if len(items) >= 3 and len(pubs) >= 3 and len(days) >= 2:
            patterns.append(f"- {s}: {len(items)} incidents, {len(pubs)} publishers, {len(days)} days "
                            f"[{', '.join(i.incident_id for i in items[:4])}]")
    lines += ["", "Recurring patterns (threshold: ≥3 incidents, ≥3 publishers, ≥2 days)"] + (patterns or ["- No pattern met the threshold."])
    # systemic dependencies: platform entities shared by >=2 actionable incidents
    ents: dict[str, list[IncidentView]] = defaultdict(list)
    for i in acts:
        for r in i.reports[:1]:
            for o in sorted(ed.detect_candidate({"id": r["report_id"], "title": r["title"], "source": r["source_name"]}).orgs):
                if o in {"microsoft", "azure", "aws", "google cloud", "cloudflare", "crowdstrike", "oracle", "salesforce", "github", "telstra", "optus", "nbn"}:
                    ents[o].append(i)
    deps = [f"- {o}: shared by {len(v)} incidents [{', '.join(i.incident_id for i in v[:3])}]" for o, v in ents.items() if len(v) >= 2]
    lines += ["", "Systemic dependencies (named providers appearing in ≥2 incidents; no causal link asserted)"] + (deps or ["- None repeated."])
    lines += ["", "Evidence-supported implications (each cites its incident)"]
    imps = [f"- {i.headline}: {_facts(i)}; dependencies {', '.join(i.record['critical_service_dependencies']) or 'none recognised'} {_cite(i)}"
            for i in ev.by_priority("ESCALATE")[:4]]
    lines += imps or ["- No implication is supported at escalation level this week."]
    lines += ["", "Decisions and emerging risks to monitor"]
    dec = [f"- DECIDE: confirm or stand down provisional escalation — {i.headline} ({i.record['next_verification_action']})"
           for i in ev.by_priority("ESCALATE") if i.provisional][:4]
    dec += [f"- MONITOR: {i.headline} — unresolved: {i.record['next_verification_action']}" for i in ev.by_priority("VERIFY")[:4]]
    lines += dec or ["- No open decision."]
    return lines


# ── Communications & Presence Brief view ──────────────────────────────────────────────────────────────

def comms_view(ev: EvidenceSet, *, existing_titles: list[str] | None = None, pillar_fn=None, similarity_fn=None) -> list[str]:
    """What is worth contributing publicly. pillar_fn(text) -> pillar label or None and similarity_fn(title, titles) -> 0..1 are injected by
    the comms hook (they live in platform-runtime); without them the view still ranks by evidence and readiness. Recommendation only."""
    existing_titles = existing_titles or []
    rows = []
    for i in ev.incidents:
        if i.priority not in _ACTIONABLE or i.impact_status in ("potential",):
            continue
        pillar = pillar_fn(i.headline) if pillar_fn else None
        if pillar_fn and not pillar:
            continue                                             # no alignment with the Captain's pillars: not worth contributing
        sim = similarity_fn(i.headline, existing_titles) if (similarity_fn and existing_titles) else 0.0
        kinds = sorted({r["source_kind"] for r in i.reports if r["role"] != "commentary"})
        corroborated = we.PRIMARY in kinds or (i.independent_publishers >= 2 and any(k != we.AGGREGATOR for k in kinds))   # aggregator feeds alone never make a draft 'ready'
        if i.priority == "VERIFY" or i.impact_status != "confirmed":
            ready = "hold — facts unresolved"
        elif corroborated:
            ready = "ready to draft (corroborated)"
        else:
            ready = "needs a second or primary source before drafting"
        rows.append((i, pillar, sim, kinds, ready))
    rows.sort(key=lambda r: (r[4].startswith("hold"), r[2] >= 0.7, -r[0].evidence_confidence))
    lines = ["📡 EVIDENCE-BASED CONTRIBUTION CANDIDATES (V1) — recommendation only; publication is approval-only", ""]
    for i, pillar, sim, kinds, ready in rows[:5]:
        lines.append(f"- {i.headline} {_cite(i)}")
        orig = ("not assessed (no existing-content titles supplied)" if not existing_titles
                else f"duplicate of existing content (similarity {sim:.2f})" if sim >= 0.7 else f"new angle (similarity {sim:.2f})")
        lines.append(f"    relevance: {pillar or 'unclassified'} · originality: {orig}")
        lines.append(f"    evidence: confidence {i.evidence_confidence:.2f}, sources {', '.join(kinds)}, {i.independent_publishers} independent publisher(s)")
        lines.append(f"    publication readiness: {ready}")
        lines.append(f"    research gap: {i.record['next_verification_action']}")
    if not rows:
        lines.append("- No incident this period is both evidenced and aligned with a content pillar.")
    return lines
