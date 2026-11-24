"""Source effectiveness states: is a registered source actually delivering intelligence?

Registry presence is not coverage (ASIC returned 'no items' on every check for eleven weeks while marked active). Six states:
HEALTHY      checks succeeding and items collected recently
QUIET        checks succeeding, no recent items, and a live-feed probe confirmed nothing newer exists (recorded evidence)
UNVERIFIED   checks succeeding, no recent items, nobody has confirmed the source is genuinely quiet
DEGRADED     some checks failing, or checks stale
BROKEN       (nearly) every check failing, or an active source not checked at all
UNCOVERED    a sector/provider with no authoritative collection method (declared gap), or a priority source that is inactive
Pure functions over plain dicts so the same classification serves the CLI report and any delivery surface.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

HEALTHY, QUIET, UNVERIFIED, DEGRADED, BROKEN, UNCOVERED = "HEALTHY", "QUIET", "UNVERIFIED", "DEGRADED", "BROKEN", "UNCOVERED"
_CONFIG = Path(__file__).resolve().parents[1] / "config" / "source_effectiveness.json"

# one row per source; produced by SOURCE_ROWS_SQL
SOURCE_ROWS_SQL = """
with ev as (select source_id, count(*) filter (where collected_at > now()-interval '30 days') n30,
                   count(*) filter (where collected_at > now()-interval '7 days') n7, max(collected_at) last_event
            from intelligence_events group by 1),
h as (select source_id, count(*) filter (where checked_at > now()-interval '7 days') checks7,
             count(*) filter (where checked_at > now()-interval '7 days' and status <> 'ok') bad7, max(checked_at) last_check,
             max(checked_at) filter (where status = 'ok') last_ok
      from intelligence_source_health group by 1)
select s.source_name, s.source_type, s.active, coalesce(ev.n7,0) n7, coalesce(ev.n30,0) n30, ev.last_event,
       coalesce(h.checks7,0) checks7, coalesce(h.bad7,0) bad7, h.last_check, h.last_ok
from intelligence_source_registry s left join ev using (source_id) left join h using (source_id)
order by s.active desc, s.source_name
"""


def load_evidence(path: Path | None = None) -> dict:
    return json.loads((path or _CONFIG).read_text(encoding="utf-8"))


def _dt(v):
    if v is None or isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def classify_source(row: dict, evidence: dict | None = None, now: datetime | None = None) -> tuple[str, str]:
    """(state, reason) for one registry row."""
    evidence = evidence if evidence is not None else load_evidence()
    now = now or datetime.now(timezone.utc)
    if not row.get("active"):
        return UNCOVERED, "inactive: not collecting"
    checks, bad = int(row.get("checks7") or 0), int(row.get("bad7") or 0)
    last_check = _dt(row.get("last_check"))
    if checks == 0 or last_check is None:
        return BROKEN, "active but not checked in the last 7 days"
    if bad / checks >= 0.8:
        return BROKEN, f"{bad} of {checks} checks failed in 7 days"
    if bad / checks >= 0.2:
        return DEGRADED, f"{bad} of {checks} checks failed in 7 days"
    if now - last_check > timedelta(days=2):
        return DEGRADED, f"last check {last_check:%Y-%m-%d}, older than two days"
    if int(row.get("n30") or 0) > 0:
        return HEALTHY, f"{row.get('n30')} items in 30 days, {row.get('n7') or 0} in 7"
    for v in evidence.get("quiet_verifications", []):
        if v["source_name"] == row["source_name"]:
            return QUIET, f"live feed probe on {v['verified_on']}: newest item on source {v['newest_item_on_source']}"
    return UNVERIFIED, "checks succeed but no items in 30 days and no live-feed probe on record"


def classify_all(rows: list[dict], evidence: dict | None = None, now: datetime | None = None) -> list[dict]:
    evidence = evidence if evidence is not None else load_evidence()
    out = [{"source_name": r["source_name"], "state": (c := classify_source(r, evidence, now))[0], "reason": c[1]} for r in rows]
    out += [{"source_name": f"{g['provider']} ({g['sector']})", "state": UNCOVERED, "reason": g["reason"]}
            for g in evidence.get("coverage_gaps", [])]
    return out


def summarise(classified: list[dict]) -> dict[str, int]:
    counts = {s: 0 for s in (HEALTHY, QUIET, UNVERIFIED, DEGRADED, BROKEN, UNCOVERED)}
    for c in classified:
        counts[c["state"]] += 1
    return counts


if __name__ == "__main__":  # python -m intelligence.source_effectiveness rows.json  (rows = result of SOURCE_ROWS_SQL as JSON)
    import sys

    rows = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    res = classify_all(rows)
    print(summarise(res))
    for c in res:
        if c["state"] not in (HEALTHY,):
            print(f"{c['state']:<10} {c['source_name']}: {c['reason']}")


# ---- material exceptions and product-facing coverage limitations ----
MATERIAL_BROKEN_DAYS = 3


def is_priority(source_name: str, evidence: dict | None = None) -> bool:
    evidence = evidence if evidence is not None else load_evidence()
    return any(re.search(r"\b" + re.escape(p) + r"\b", source_name, re.IGNORECASE) for p in evidence.get("priority_sources", []))


def _broken_priority(rows, evidence, now):
    return [r for r in rows if is_priority(r["source_name"], evidence) and classify_source(r, evidence, now)[0] == BROKEN]


def material_exceptions(rows: list[dict], evidence: dict | None = None, now: datetime | None = None) -> list[dict]:
    """BROKEN priority sources with no successful check for 3+ days: the only source-health matter raised on Home."""
    evidence = evidence if evidence is not None else load_evidence()
    now = now or datetime.now(timezone.utc)
    out = []
    for r in _broken_priority(rows, evidence, now):
        last_ok = _dt(r.get("last_ok"))
        if last_ok is None or now - last_ok >= timedelta(days=MATERIAL_BROKEN_DAYS):
            out.append({"key": f"source-coverage:broken:{r['source_name']}", "source_name": r["source_name"],
                        "reason": classify_source(r, evidence, now)[1]})
    return out


def coverage_limitations(rows: list[dict], evidence: dict | None = None, now: datetime | None = None) -> list[dict]:
    """Short list for intelligence products: declared uncovered providers plus any BROKEN priority source."""
    evidence = evidence if evidence is not None else load_evidence()
    now = now or datetime.now(timezone.utc)
    out = [{"name": g["provider"], "kind": "uncovered", "reason": g["reason"]} for g in evidence.get("coverage_gaps", [])]
    out += [{"name": r["source_name"], "kind": "broken_priority", "reason": classify_source(r, evidence, now)[1]}
            for r in _broken_priority(rows, evidence, now)]
    return out


def limitations_line(limits: list[dict]) -> str:
    if not limits:
        return ""
    unc = [x["name"] for x in limits if x["kind"] == "uncovered"]
    brk = [x["name"] for x in limits if x["kind"] == "broken_priority"]
    parts = ([f"{', '.join(unc)} not covered by an authoritative feed"] if unc else []) + ([f"{', '.join(brk)} currently failing"] if brk else [])
    return "Coverage limitations: " + "; ".join(parts) + "."
