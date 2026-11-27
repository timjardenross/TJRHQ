"""Incident clustering v2 (offline, default OFF): consolidate reports of one disruption and classify each report.

``event_detection.correlate`` joins reports by shared headline terms. A long, widely reported disruption (a global Microsoft 365
outage, 50+ headlines over four days) still leaves stragglers that share no rare term with the core: a pure restoration headline
("Microsoft 365 recovers with Outlook back online"), a cost-of-outage story, a phishing follow-up, a regulator reaction. Each
becomes its own one-report "incident" with its own priority, so the same disruption is represented several times and its
restoration is detached from it.

This module consolidates those groups and labels every report relative to its incident:

  NEW                  the earliest factual report of the disruption
  SUBSEQUENT           a later factual report (scale, cause, progress)
  RESTORATION_UPDATE   service is back / being restored (never a hedged, forecast or negated restoration)
  RELATED              commentary, cost, aftermath, regulator or phishing follow-up about the same disruption
  HISTORICAL_REFERENCE refers back to an earlier event (named older date, "after the July outage", complaints after a past outage)

Consolidation rules (deliberately conservative; a wrong merge hides an incident, a missed merge only costs a duplicate):
  * subject = a canonical operator/platform key read from headlines (Microsoft family, AWS, Telstra, ...)
  * a PLATFORM subject (global cloud/SaaS) is one incident per platform while reports chain within the class window
  * any other subject merges only an UNANCHORED group (restoration/follow-up/commentary with no live event of its own) and only
    when exactly one other incident of that subject is active in the window. Two Telstra incidents (a local copper-theft outage and
    a network-wide one) are never merged just because both say "Telstra outage".

Flag: ``INCIDENT_CLUSTERING_V2`` (read at call time, default OFF). Nothing here is wired into a production path.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from intelligence import event_detection as ed
from intelligence import weekly_evidence as we

FLAG = "INCIDENT_CLUSTERING_V2"
_TRUE = ("1", "true", "yes", "on")

NEW = "NEW"
SUBSEQUENT = "SUBSEQUENT"
RESTORATION_UPDATE = "RESTORATION_UPDATE"
RELATED = "RELATED"
HISTORICAL_REFERENCE = "HISTORICAL_REFERENCE"
RELATIONS = (NEW, SUBSEQUENT, RESTORATION_UPDATE, RELATED, HISTORICAL_REFERENCE)


def enabled() -> bool:
    """True only on an explicit opt-in; read at call time so a test or an operator can flip it without a reimport."""
    return os.getenv(FLAG, "").strip().lower() in _TRUE


# ── subjects ──────────────────────────────────────────────────────────────────────────────────────────────
_DISRUPT = r"outages?|disruptions?|down|offline|restor\w+|recover\w*|back online|resolved|fixed|failures?|glitch|disrupted|disrupts"
_SUBJECTS: dict[str, re.Pattern] = {k: re.compile(v, re.IGNORECASE) for k, v in {
    "microsoft": r"\bmicrosoft\b|\bm365\b|\boffice 365\b|\bexchange online\b|\bazure\b|\boutlook\b(?=.*\b(?:" + _DISRUPT + r")\b)",
    "aws": r"\baws\b|\bamazon web services\b",
    "google_cloud": r"\bgoogle cloud\b|\bgcp\b",
    "cloudflare": r"\bcloudflare\b",
    "crowdstrike": r"\bcrowdstrike\b",
    "telstra": r"\btelstra\b",
    "optus": r"\boptus\b",
    "tpg_vodafone": r"\btpg\b|\bvodafone\b",
    "nbn": r"\bnbn\b",
    "coles": r"\bcoles\b",
    "woolworths": r"\bwoolworths\b",
    "qantas": r"\bqantas\b|\bjetstar\b",
}.items()}
PLATFORM_SUBJECTS = frozenset({"microsoft", "aws", "google_cloud", "cloudflare", "crowdstrike"})


def subjects(title: str) -> frozenset:
    t = ed.core_title(title)
    return frozenset(k for k, rx in _SUBJECTS.items() if rx.search(t))


# ── per-report signals ────────────────────────────────────────────────────────────────────────────────────
_RESTORE_RX = re.compile(r"\b(?:restores?|restored|restoring|recovers?|recovered|recovery|back online|resolved|fixed|resumed|resumes|service(?:s)? (?:is|are) back)\b", re.IGNORECASE)
_RESTORE_GUARD_RX = re.compile(
    r"\b(?:races?|racing|works?|working|attempts?|attempting|tries|trying|aims?|aiming|expected|hopes?|set|yet|struggl\w+|pursuing|seeks?|"
    r"will|would|could|may|might|should)\b[^.]{0,30}?\b(?:to )?(?:restor\w+|resolv\w+|fix\w*|recover\w*)"
    r"|\bnot\b[^.]{0,25}\b(?:progress\w+|working|restored|resolved|fixed|as expected)\b|\bnot as expected\b|\bwhen will it be fixed\b|\bhow to (?:restore|recover)\b",
    re.IGNORECASE)
_HIST_REF_RX = re.compile(
    r"\b(?:after|since|following|from|of)\s+(?:the\s+|last\s+)?(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+(?:outage|incident|attack|breach|disruption)"
    r"|\blast (?:week|month|year)'?s?\b|\bearlier (?:this year|outage|incident)\b|\bprevious (?:outage|incident)\b|\bone year (?:on|since)\b|\banniversary\b",
    re.IGNORECASE)
_AFTERMATH_RX = re.compile(
    r"\b(?:complaints?|compensation|claims?|credits?|refunds?|share (?:repurchase|buyback)|scrutiny|reliance|exposes?|lessons?|prepare|"
    r"phish\w*|fraud|insurance|near miss|billions?|billion-dollar|cost(?:s|ing)?|losses|layoffs|review|inquiry|hidden risk|warnings? (?:over|of|about)|risks?|"
    r"what (?:we know|happened)|explained|opinion|analysis|growing trend|more disruption|backup plans?|workaround|celebrat\w+|laugh\w*|"
    r"surge in|spike|jump in|questions? (?:over|about)|raises? question|calls? for)\b", re.IGNORECASE)


@dataclass
class ClassifiedReport:
    candidate: ed.Candidate
    relation: str
    reason: str
    restoration: str | None = None            # RESTORATION_UPDATE only: "full" or "partial"

    @property
    def event_id(self) -> str:
        return self.candidate.event_id


@dataclass
class Incident:
    incident_id: str
    group: ed.Group
    reports: list[ClassifiedReport]
    subject: str | None
    merged_from: list[str]                    # baseline group ids consolidated into this incident (len 1 = unchanged)
    consolidation_reasons: list[str] = field(default_factory=list)
    decision: ed.Decision | None = None
    restoration_status: str = "unknown"

    @property
    def n_reports(self) -> int:
        return len(self.reports)

    def by_relation(self, relation: str) -> list[ClassifiedReport]:
        return [r for r in self.reports if r.relation == relation]

    @property
    def first_report_time(self):
        times = [r.candidate.published for r in self.reports if r.candidate.published]
        return min(times) if times else None


def restoration_signal(m: ed.Candidate, now: datetime | None = None) -> bool:
    """True when the headline affirms (full or partial) restoration. A race/work/aim to restore, a negation, a forecast or a
    hedge is never a restoration."""
    t = ed.core_title(m.title)
    if _RESTORE_GUARD_RX.search(t) or ed._ongoing_cue(t) and not ed._affirmative_restored(t):
        return False
    state = ed._report_state(m, now)
    if state in ("restored", "partially_restored"):
        return True
    return bool(_RESTORE_RX.search(t)) and not ed._HEDGED_RESTORE_RX.search(t) and state != "ongoing"


_PARTIAL_RX = re.compile(r"\bbroad recovery\b|\bbeing restored\b|\brecovering\b|\bgradually\b|\bslowly\b", re.IGNORECASE)


# An explicit statement that a disruption has come back. Requires the disruption itself to be the subject ('outage returns', 'down
# again'): 'service returns' and 'power returns' are restorations.
_RECURRENCE_RX = re.compile(r"\b(?:outage|blackout|disruption|fault)s?\s+(?:has\s+|have\s+)?(?:returns|returned|recurs|recurred|resumes|resumed)\b"
                            r"|\b(?:down|offline|without(?:\s+\w+){0,3}?\s+(?:service|power|water|internet|coverage))\s+again\b", re.IGNORECASE)


def resolve_restoration(reports: list[ClassifiedReport], base: str, now: datetime | None = None) -> str:
    """Incident restoration state from report ROLES in time order (``reports`` is chronological): a RESTORATION_UPDATE sets restored
    (full) or partially_restored; a factual report with an unresolved cue reopens to ongoing; a cause or scale update after a
    restoration changes nothing. ``event_detection`` only recognises the verb form "restored", so "restores" / "recovers" headlines
    were read as ongoing. Live states need a verified report within CUE_MAX_AGE_HOURS of ``now``, else "unknown" (never a stale 'ongoing')."""
    state = None
    for r in reports:
        if r.relation == RESTORATION_UPDATE:
            state = "restored" if r.restoration == "full" else "partially_restored"
        else:
            reported = r.relation in (NEW, SUBSEQUENT) and (state is None or ed._report_state(r.candidate, now) == "ongoing")
            recurred = state == "restored" and bool(_RECURRENCE_RX.search(r.candidate.title)) and ed._live(r.candidate, now)
            if reported or recurred:
                state = "ongoing"
    if state is None:
        return base
    if state in ed.CURRENT_DISRUPTION and now is not None:
        recent = [r.candidate for r in reports if r.relation in (NEW, SUBSEQUENT, RESTORATION_UPDATE)
                  and r.candidate.time_verified and r.candidate.published and now - r.candidate.published <= timedelta(hours=ed.CUE_MAX_AGE_HOURS)]
        if not recent:
            return "unknown"
    return state


def _is_aftermath(m: ed.Candidate) -> bool:
    return bool(m.commentary or m.status in ("potential", "retrospective") or _AFTERMATH_RX.search(ed.core_title(m.title)))


def classify(members: list[ed.Candidate], now: datetime | None = None) -> list[ClassifiedReport]:
    """Label every report relative to its incident. Exactly one NEW at most: the earliest factual report."""
    ordered = sorted(members, key=lambda m: (m.published or datetime.max.replace(tzinfo=timezone.utc), m.event_id))
    out: list[ClassifiedReport] = []
    have_new = False
    for m in ordered:
        t = ed.core_title(m.title)
        if ed._historic(m) or _HIST_REF_RX.search(t):
            out.append(ClassifiedReport(m, HISTORICAL_REFERENCE, "refers back to an earlier dated event"))
        elif restoration_signal(m, now):
            partial = bool(ed._PARTIAL_RESTORE_RX.search(t) or _PARTIAL_RX.search(t))
            out.append(ClassifiedReport(m, RESTORATION_UPDATE, "affirms service restoration (unhedged, not a forecast or negation)",
                                        "partial" if partial else "full"))
        elif _is_aftermath(m):
            out.append(ClassifiedReport(m, RELATED, "commentary / cost / aftermath / follow-up about the disruption"))
        elif not have_new:
            have_new = True
            out.append(ClassifiedReport(m, NEW, "earliest factual report"))
        else:
            out.append(ClassifiedReport(m, SUBSEQUENT, "later factual report"))
    return out


# ── consolidation ─────────────────────────────────────────────────────────────────────────────────────────
def _span(g: ed.Group):
    ts = [m.published for m in g.members if m.published]
    return (min(ts), max(ts)) if ts else (None, None)


def _gap(a: ed.Group, b: ed.Group) -> timedelta | None:
    (a0, a1), (b0, b1) = _span(a), _span(b)
    if None in (a0, a1, b0, b1):
        return None
    if a0 <= b1 and b0 <= a1:
        return timedelta(0)
    return min(abs(a0 - b1), abs(b0 - a1))


def _group_subjects(g: ed.Group) -> frozenset:
    s: set = set()
    for m in g.members:
        s |= subjects(m.title)
    return frozenset(s)


def _class(g: ed.Group) -> str | None:
    for cls in ("outage", "cyber_incident"):
        if any(cls in m.types for m in g.members):
            return cls
    if any(restoration_signal(m) for m in g.members):
        return "outage"                       # a bare restoration headline belongs to an outage
    return None


def _anchored(g: ed.Group) -> bool:
    """A group is anchored when it carries a live factual event of its own (not only restoration/commentary/retrospective)."""
    return any(m.is_candidate and not m.commentary and m.status in ("stated", "unconfirmed") and not restoration_signal(m)
               and not _HIST_REF_RX.search(ed.core_title(m.title)) and not ed._historic(m) for m in g.members)


def _rebuild(parts: list[ed.Group], reason: str) -> ed.Group:
    members = [m for g in parts for m in g.members]
    pairs = [p for g in parts for p in g.pairs]
    anchor = parts[0].members[0].event_id
    pairs += [(g.members[0].event_id, anchor, 0.5, reason) for g in parts[1:]]
    synd = sorted({s for g in parts for s in g.syndicated_ids})
    original = [m for m in members if not m.commentary and m.event_id not in synd]
    fams = {m.family for m in original if m.kind != we.AGGREGATOR}
    gid = "inc-" + "-".join(sorted(m.event_id for m in members))[:40]
    return ed.Group(gid, members, pairs, round(min((p[2] for p in pairs), default=1.0), 2), len(fams), synd,
                    [m.event_id for m in members if m.commentary])


def consolidate(groups: list[ed.Group]) -> list[tuple[ed.Group, list[str], list[str], str | None]]:
    """Merge baseline groups that are one disruption. Returns (group, merged_from_ids, reasons, subject)."""
    n = len(groups)
    parent = list(range(n))
    why: dict[int, list[str]] = {i: [] for i in range(n)}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    subs = [_group_subjects(g) for g in groups]
    cls = [_class(g) for g in groups]
    anch = [_anchored(g) for g in groups]
    for s in sorted({x for ss in subs for x in ss}):
        idx = [i for i in range(n) if s in subs[i] and cls[i]]
        if s in PLATFORM_SUBJECTS:
            # one incident per platform while reports chain within the class window (single-linkage over group spans)
            idx.sort(key=lambda i: _span(groups[i])[0] or datetime.max.replace(tzinfo=timezone.utc))
            for x in idx:
                for y in idx:
                    if x >= y or find(x) == find(y) or cls[x] != cls[y]:
                        continue
                    gap = _gap(groups[x], groups[y])
                    if gap is None or gap > ed._WINDOW.get(cls[x], ed._WINDOW["other"]):
                        continue
                    if not (anch[x] or anch[y]):
                        continue                  # two unanchored fragments never form an incident by themselves
                    parent[find(y)] = find(x)
                    why[find(x)].append(f"platform subject '{s}': chained within {gap} of a related group")
        else:
            for u in idx:
                if anch[u]:
                    continue
                window = ed._WINDOW.get(cls[u], ed._WINDOW["other"])
                active = [i for i in idx if i != u and anch[i] and cls[i] == cls[u]
                          and (g := _gap(groups[i], groups[u])) is not None and g <= window]
                roots = {find(i) for i in active}
                if len(roots) == 1:               # unique active incident for this operator: attach the follow-up
                    parent[find(u)] = roots.pop()
                    why[find(u)].append(f"unanchored follow-up attached to the only active '{s}' incident")
    buckets: dict[int, list[int]] = {}
    for i in range(n):
        buckets.setdefault(find(i), []).append(i)
    out = []
    for root, ids in buckets.items():
        parts = [groups[i] for i in sorted(ids)]
        reasons = sorted({r for i in ids for r in why.get(i, [])} | {r for r in why.get(root, [])})
        sset = [x for i in ids for x in subs[i]]
        # most frequent subject; ties go to a platform (the cause of a joint "Telstra ... AWS outage" headline), then alphabetical: deterministic
        subject = max(sorted(set(sset)), key=lambda x: (sset.count(x), x in PLATFORM_SUBJECTS)) if sset else None
        out.append((parts[0] if len(parts) == 1 else _rebuild(parts, "v2 consolidation: " + (reasons[0] if reasons else "same disruption")),
                    [g.incident_id for g in parts], reasons, subject))
    return sorted(out, key=lambda t: min((m.published for m in t[0].members if m.published), default=datetime.max.replace(tzinfo=timezone.utc)))


def cluster_incidents(events: list[dict], *, now: datetime | None = None, force: bool | None = None) -> list[Incident]:
    """Cluster raw event dicts (keys as event_detection.detect_candidate reads them: id, title, source, published_at, collected_at).
    With the flag OFF (and no ``force``) no consolidation is applied: one Incident per baseline group (report relations are still
    computed so callers can compare before/after)."""
    on = enabled() if force is None else force
    cands = [ed.detect_candidate(e) for e in events]
    groups = ed.correlate(cands)
    merged = consolidate(groups) if on else [(g, [g.incident_id], [], None) for g in groups]
    incidents: list[Incident] = []
    for g, from_ids, reasons, subject in merged:
        d = ed.decide(g, now=now)
        rec = ed.escalation_record(d, now=now)
        reports = classify(g.members, now)
        incidents.append(Incident(g.incident_id, g, reports, subject, from_ids, reasons, d, resolve_restoration(reports, rec["restoration_status"], now)))
    return incidents


def representation(incidents: list[Incident], subject_rx: re.Pattern, *, actionable_only: bool = False) -> dict:
    """How many separate incidents carry reports matching ``subject_rx`` (the duplicate-representation measure).
    ``actionable_only`` counts only incidents the decision rules rate ESCALATE/VERIFY/WATCH."""
    hit = [i for i in incidents if any(subject_rx.search(r.candidate.title) for r in i.reports)
           and (not actionable_only or (i.decision and i.decision.priority in ("ESCALATE", "VERIFY", "WATCH")))]
    return {"incidents": len(hit), "reports": sum(sum(1 for r in i.reports if subject_rx.search(r.candidate.title)) for i in hit),
            "ids": [i.incident_id for i in hit]}
