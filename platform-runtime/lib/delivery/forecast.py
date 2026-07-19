"""EDO Delivery Control Tower (MSN-EDO-003 WP2).

Forecasting, risk scoring, and capacity intelligence — pure functions over the
existing `mission_delivery` rows (no new telemetry store; reuses migration 0023
+ 0024 data). Answers: what's at risk, what's slowing delivery, what will miss
target, where to focus engineering effort.

  delivery_risk(row)          per-mission risk score + reasons
  risk_scored_missions(rows)  open missions ranked by risk
  throughput(rows, weeks)     closures per recent window (trend)
  cycle_time_stats(rows)      avg/median/p90 cycle for closed work
  bottleneck_forecast(rows)   which state is accumulating
  engineering_capacity(rows)  WIP vs a nominal limit (utilisation)
  control_tower(rows)         one roll-up for the dashboard / command
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from statistics import mean, median

from . import lifecycle

# Nominal concurrent-work limit for the capacity indicator (engineering WIP).
NOMINAL_WIP_LIMIT = 3
_SEV = {"high": 0, "medium": 1, "low": 2}


def _state(row: dict) -> str:
    return row.get("delivery_state") or lifecycle.canonical_state(row.get("status"))


def _age(row: dict) -> int:
    if row.get("age_days") is not None:
        try:
            return int(row["age_days"])
        except (TypeError, ValueError):
            pass
    c = row.get("created_at")
    if not c:
        return 0
    try:
        return (date.today() - datetime.fromisoformat(str(c).replace("Z", "+00:00")).date()).days
    except Exception:
        return 0


def _has_pr(row: dict) -> bool:
    return bool((row.get("pr_url") or "").strip())


def _is_eng(row: dict) -> bool:
    return "engineer" in str(row.get("task_type_norm") or "").lower()


def _priority(row: dict) -> str:
    return str(row.get("priority_norm") or row.get("priority") or "").lower()


# ── Risk scoring ──────────────────────────────────────────────────────────────

@dataclass
class RiskScore:
    title: str
    score: int            # 0–100
    level: str            # high | medium | low
    reasons: list[str] = field(default_factory=list)


_STATE_BASE = {"blocked": 80, "in_review": 50, "in_progress": 40,
               "planned": 30, "validated": 25, "proposed": 20}


def delivery_risk(row: dict) -> RiskScore:
    """Risk that an open mission stalls or misses target."""
    st = _state(row)
    age = _age(row)
    score = _STATE_BASE.get(st, 20)
    reasons: list[str] = [f"state {st}"]
    if age > 14:
        score += 30
        reasons.append(f"aged {age}d")
    elif age > 7:
        score += 20
        reasons.append(f"aged {age}d")
    if st in ("in_progress", "in_review") and not _has_pr(row):
        score += 15
        reasons.append("no PR/evidence")
    if _priority(row) in ("p0", "p1"):
        score += 10
        reasons.append("high priority")
    score = max(0, min(100, score))
    level = "high" if score >= 70 else "medium" if score >= 40 else "low"
    return RiskScore(title=str(row.get("title") or row.get("mission_id") or "untitled"),
                     score=score, level=level, reasons=reasons)


def risk_scored_missions(rows: list[dict]) -> list[RiskScore]:
    """Open missions ranked by risk (highest first)."""
    scored = [delivery_risk(r) for r in rows if _state(r) not in lifecycle.TERMINAL_STATES]
    scored.sort(key=lambda r: (-r.score))
    return scored


# ── Throughput + cycle-time trends ────────────────────────────────────────────

def _closed_date(row: dict):
    c = row.get("closed_at") or row.get("updated_at")
    if not c:
        return None
    try:
        return datetime.fromisoformat(str(c).replace("Z", "+00:00")).date()
    except Exception:
        return None


def throughput(rows: list[dict], weeks: int = 4) -> dict:
    """Closures within the last `weeks`, total + simple trend direction."""
    today = date.today()
    closed = [r for r in rows if _state(r) in lifecycle.TERMINAL_STATES]
    buckets = [0] * weeks
    for r in closed:
        d = _closed_date(r)
        if not d:
            continue
        wk = (today - d).days // 7
        if 0 <= wk < weeks:
            buckets[wk] += 1
    recent, older = buckets[0], (mean(buckets[1:]) if weeks > 1 and any(buckets[1:]) else 0)
    direction = "up" if recent > older else "down" if recent < older else "steady"
    return {"per_week_recent_first": buckets, "this_week": buckets[0],
            "avg_prior_weeks": round(older, 1), "direction": direction}


def cycle_time_stats(rows: list[dict]) -> dict:
    vals = [float(r["cycle_days"]) for r in rows
            if r.get("cycle_days") is not None]
    if not vals:
        return {"count": 0, "avg": None, "median": None, "p90": None}
    s = sorted(vals)
    p90 = s[min(len(s) - 1, int(round(0.9 * (len(s) - 1))))]
    return {"count": len(vals), "avg": round(mean(vals), 1),
            "median": round(median(vals), 1), "p90": round(p90, 1)}


# ── Bottleneck forecast + capacity ────────────────────────────────────────────

def bottleneck_forecast(rows: list[dict]) -> dict:
    """Which open state is accumulating, with its oldest item age."""
    by_state: dict[str, list[int]] = {}
    for r in rows:
        st = _state(r)
        if st in lifecycle.OPEN_STATES:
            by_state.setdefault(st, []).append(_age(r))
    if not by_state:
        return {"constraint": None, "counts": {}}
    counts = {k: len(v) for k, v in by_state.items()}
    # The constraint is the state with the most aged accumulation.
    constraint = max(by_state, key=lambda k: (len(by_state[k]), max(by_state[k])))
    return {"constraint": constraint, "constraint_count": counts[constraint],
            "constraint_oldest": max(by_state[constraint]), "counts": counts}


def engineering_capacity(rows: list[dict], wip_limit: int = NOMINAL_WIP_LIMIT) -> dict:
    """Engineering WIP vs a nominal limit → utilisation + headroom."""
    in_flight = [r for r in rows
                 if _is_eng(r) and _state(r) in ("in_progress", "in_review")]
    wip = len(in_flight)
    util = round(wip / wip_limit, 2) if wip_limit else 0.0
    status = "over" if wip > wip_limit else "at" if wip == wip_limit else "available"
    return {"wip": wip, "limit": wip_limit, "utilisation": util,
            "headroom": max(0, wip_limit - wip), "status": status}


# ── Control-tower roll-up ─────────────────────────────────────────────────────

def control_tower(rows: list[dict]) -> dict:
    risks = risk_scored_missions(rows)
    return {
        "throughput": throughput(rows),
        "cycle_time": cycle_time_stats(rows),
        "bottleneck": bottleneck_forecast(rows),
        "capacity": engineering_capacity(rows),
        "top_risks": risks[:5],
        "high_risk_count": sum(1 for r in risks if r.level == "high"),
        "open_count": sum(1 for r in rows if _state(r) in lifecycle.OPEN_STATES),
    }
