"""EDO — delivery analysis (pure): bottlenecks, metrics, reuse-check, lint.

Network-free reasoning over `mission_delivery`-shaped rows (or raw `missions`
rows — state/age are derived if absent). Powers /delivery and the dashboard.

  detect_bottlenecks()  MSN-EDO-002 QW5 — where work is stuck, ranked
  summarize_metrics()   MSN-EDO-008 ST3 — cycle/PR/outcome/rework roll-up
  reuse_check()         MSN-EDO-008 ST2 — reuse-first: find existing overlap
  lint()                MSN-EDO-002 QW2 — mission data-hygiene issues
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from . import lifecycle

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


@dataclass
class Finding:
    kind: str
    severity: str       # critical | high | medium | low | info
    title: str
    detail: str


# ── helpers ───────────────────────────────────────────────────────────────────

def _state(row: dict) -> str:
    s = row.get("delivery_state")
    return s if s else lifecycle.canonical_state(row.get("status"))


def _age(row: dict) -> int:
    if row.get("age_days") is not None:
        try:
            return int(row["age_days"])
        except (TypeError, ValueError):
            pass
    created = row.get("created_at")
    if not created:
        return 0
    try:
        d = datetime.fromisoformat(str(created).replace("Z", "+00:00")).date()
        return (date.today() - d).days
    except Exception:
        return 0


def _has_pr(row: dict) -> bool:
    return bool((row.get("pr_url") or "").strip())


def _title(row: dict) -> str:
    return str(row.get("title") or row.get("mission_id") or "untitled")


# ── WP: bottleneck detection ──────────────────────────────────────────────────

def detect_bottlenecks(rows: list[dict], *, stale_days: int = 3, review_days: int = 1) -> list[Finding]:
    """Find where missions are stuck, ranked by severity then age."""
    findings: list[Finding] = []
    for row in rows:
        st = _state(row)
        age = _age(row)
        title = _title(row)
        if st in lifecycle.TERMINAL_STATES:
            continue
        if st == "blocked":
            findings.append(Finding("blocked", "critical", title, f"Blocked for {age}d — needs an unblock decision."))
        elif st == "planned" and age > stale_days:
            sev = "high" if age > 7 else "medium"
            findings.append(Finding("stuck_planned", sev, title, f"Planned but not started for {age}d."))
        elif st == "in_progress" and age > stale_days * 2:
            findings.append(Finding("stuck_in_progress", "high", title, f"In progress for {age}d without reaching review."))
        elif st == "in_review" and age > review_days:
            findings.append(Finding("stuck_in_review", "medium", title, f"Awaiting review/validation for {age}d (review SLA {review_days}d)."))
        elif st == "validated" and age > review_days:
            findings.append(Finding("awaiting_closure", "medium", title, f"Validated but not closed for {age}d — awaiting XO closure."))
        # In-review without a PR is a quality-evidence gap.
        if st == "in_review" and not _has_pr(row):
            findings.append(Finding("review_no_pr", "high", title, "In review with no PR/evidence linked."))
    findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f.severity, 9)))
    return findings


# ── WP: metrics ───────────────────────────────────────────────────────────────

def summarize_metrics(rows: list[dict]) -> dict:
    """Delivery metrics roll-up from delivery rows."""
    total = len(rows)
    by_state: dict[str, int] = {}
    open_ages: list[int] = []
    cycle_days: list[float] = []
    pr = outcome = rework = 0
    for row in rows:
        st = _state(row)
        by_state[st] = by_state.get(st, 0) + 1
        if st in lifecycle.TERMINAL_STATES:
            cd = row.get("cycle_days")
            if cd is not None:
                try:
                    cycle_days.append(float(cd))
                except (TypeError, ValueError):
                    pass
        else:
            open_ages.append(_age(row))
        if _has_pr(row):
            pr += 1
        if row.get("outcome_rating") is not None:
            outcome += 1
        if row.get("rework_of"):
            rework += 1
    open_count = sum(v for k, v in by_state.items() if k in lifecycle.OPEN_STATES)
    closed_count = by_state.get("closed", 0) + by_state.get("archived", 0)
    return {
        "total": total,
        "open": open_count,
        "closed": closed_count,
        "by_state": by_state,
        "pr_rate": round(pr / total, 2) if total else 0.0,
        "outcome_rate": round(outcome / total, 2) if total else 0.0,
        "rework_rate": round(rework / total, 2) if total else 0.0,
        "avg_open_age_days": round(sum(open_ages) / len(open_ages), 1) if open_ages else 0.0,
        "avg_cycle_days": round(sum(cycle_days) / len(cycle_days), 1) if cycle_days else None,
        "oldest_open_age_days": max(open_ages) if open_ages else 0,
    }


# ── WP: reuse-first check ─────────────────────────────────────────────────────

_STOP = {"the", "a", "an", "to", "for", "of", "and", "or", "in", "on", "add",
         "build", "new", "improve", "create", "support", "with", "make"}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2 and t not in _STOP}


def reuse_check(query: str, capabilities: list[dict], missions: list[dict], *, limit: int = 5) -> list[dict]:
    """Reuse-first: surface existing capabilities/missions overlapping a request.

    Returns ranked matches [{kind, name, score, detail}] by token overlap, so the
    plan step can cite what to reuse before any new build is approved.
    """
    q = _tokens(query)
    if not q:
        return []
    scored: list[dict] = []
    for c in capabilities:
        name = c.get("name") or ""
        overlap = q & _tokens(f"{name} {c.get('purpose','')}")
        if overlap:
            scored.append({"kind": "capability", "name": name,
                           "score": len(overlap), "detail": c.get("purpose", "")})
    for m in missions:
        title = m.get("title") or ""
        overlap = q & _tokens(f"{title} {m.get('description','')}")
        if overlap:
            scored.append({"kind": "mission", "name": title,
                           "score": len(overlap), "detail": _state(m)})
    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]


# ── WP: mission lint (data hygiene) ───────────────────────────────────────────

def lint(rows: list[dict]) -> list[Finding]:
    """Surface mission data-hygiene issues that undermine routing/metrics."""
    findings: list[Finding] = []
    for row in rows:
        title = _title(row)
        st = _state(row)
        raw_tt = row.get("task_type")
        if raw_tt and raw_tt != str(raw_tt).strip().lower():
            findings.append(Finding("task_type_case", "low", title, f"task_type '{raw_tt}' is not normalised."))
        prio = lifecycle.normalize_priority(row.get("priority") or row.get("priority_norm"))
        if st in lifecycle.OPEN_STATES and prio == "unset":
            findings.append(Finding("missing_priority", "low", title, "Open mission has no priority set."))
        if st == "in_progress" and not (row.get("branch_name") or "").strip():
            findings.append(Finding("missing_branch", "medium", title, "In progress with no branch recorded."))
        if st in ("closed", "archived") and row.get("outcome_rating") is None:
            findings.append(Finding("missing_outcome", "low", title, "Closed without an outcome rating."))
    findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f.severity, 9)))
    return findings
