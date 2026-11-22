"""Offline evaluation of intelligence/weekly_evidence.py against a labelled set.

Read-only and offline: loads the fixture, runs the prototype, prints metrics. Labels in
the shipped fixture are PROPOSED and unreviewed; treat every figure as provisional until
the Captain has reviewed them.

    python3 scripts/eval_weekly_evidence.py [fixture.json] [--json]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

import intelligence.weekly_evidence as we

DEFAULT_FIXTURE = _REPO / "tests" / "fixtures" / "weekly_evidence_eval_set.json"
NOW = datetime(2026, 11, 23, 13, 0, tzinfo=timezone.utc)
LEGACY_RANK_FLOOR = 18.6          # lowest rank in the legacy weekly sample (top 1,000 of 2,376)
_PRIO = {"E": "ESCALATE", "W": "WATCH", "V": "VERIFY", "R": "REFERENCE"}
_MAT = {"H": "high", "M": "medium", "L": "low"}


def load(path=DEFAULT_FIXTURE):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    cols = doc["_meta"]["columns"]
    return [dict(zip(cols, r)) for r in doc["rows"]]


def to_events(rows):
    return [{"id": r["id"], "title": r["title"], "source": r["source"],
             "collected_at": "2026-" + r["ts"] + ":00Z", "geography": r["geo"],
             "legacy": {"rank": r["legacy_rank"], "rel": r["legacy_rel"], "conf": r["legacy_conf"],
                        "disp": r["legacy_disp"], "risk": r["legacy_risk"]}} for r in rows]


def prf(pred, gold):
    """pred, gold: parallel booleans. Returns precision/recall/F1 and FP/FN/TP/TN."""
    tp = sum(1 for p, g in zip(pred, gold) if p and g)
    fp = sum(1 for p, g in zip(pred, gold) if p and not g)
    fn = sum(1 for p, g in zip(pred, gold) if not p and g)
    tn = sum(1 for p, g in zip(pred, gold) if not p and not g)
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = (2 * prec * rec / (prec + rec)) if prec and rec else (0.0 if tp + fp + fn else None)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": None if prec is None else round(prec, 3),
            "recall": None if rec is None else round(rec, 3),
            "f1": None if f1 is None else round(f1, 3)}


# Real incidents reported by several outlets, as judged by the assistant (proposed, unreviewed).
# Used to measure how often reports of ONE incident end up in the same incident group.
GOLD_INCIDENT_GROUPS = {
    "retailer cyber incident": ["ef9960", "4e3568", "1fba2d"],
    "telco outage complaints": ["42e7c7", "457b35"],
    "transmission towers power outage": ["735f41", "75657c", "4893fe"],
    "global Microsoft outage": ["5faa0a", "f48aad", "55d3fe", "1d9cd2"],
}


def grouping_recall(inc_of, groups=GOLD_INCIDENT_GROUPS):
    """Pairwise: of all pairs of reports that belong to one real incident, the share the
    prototype put in the same incident group. Also returns the groups left split."""
    from itertools import combinations
    res, tot_pairs, tot_hit = {}, 0, 0
    for name, ids in groups.items():
        ids = [i for i in ids if i in inc_of]
        pairs = list(combinations(ids, 2))
        hit = sum(1 for a, b in pairs if inc_of[a] == inc_of[b])
        res[name] = {"reports": len(ids), "pairs": len(pairs), "grouped_pairs": hit,
                     "incident_groups_used": len({inc_of[i] for i in ids})}
        tot_pairs += len(pairs)
        tot_hit += hit
    res["_overall_pairwise_recall"] = round(tot_hit / tot_pairs, 3) if tot_pairs else None
    return res


def evaluate(rows):
    events = to_events(rows)
    incidents = we.correlate_incidents(events, now=NOW)
    assess = {a.event_id: a for i in incidents for a in i.members}
    inc_of = {a.event_id: i for i in incidents for a in i.members}
    order = [assess[r["id"]] for r in rows]
    gold_h = [r["label_materiality"] == "H" for r in rows]
    gold_surface = [r["label_priority"] in ("E", "W", "V") for r in rows]
    gold_esc = [r["label_priority"] == "E" for r in rows]

    new_h = [a.materiality_level == "high" for a in order]
    new_surface = [a.priority in ("ESCALATE", "WATCH", "VERIFY") for a in order]
    # Escalation means "needs attention now": judge each event at its own detection time (one hour
    # after collection), not at the weekly report time, when a Wednesday event is never fresh.
    from datetime import timedelta
    new_esc = []
    for e in events:
        t0 = we._parse_ts(e["collected_at"]) + timedelta(hours=1)
        solo = we.correlate_incidents([e], now=t0)[0].headline
        new_esc.append(solo.priority == "ESCALATE")
    legacy = {
        "legacy 'high' (osint confidence = HIGH)": [r["legacy_conf"] == "H" for r in rows],
        "legacy risk_rating = HIGH": [r["legacy_risk"] == "H" for r in rows],
        "legacy disposition ESCALATE/WATCH": [r["legacy_disp"] in ("E", "W") for r in rows],
        "legacy relevance >= 0.85": [r["legacy_rel"] >= 0.85 for r in rows],
        f"legacy weekly sample (rank >= {LEGACY_RANK_FLOOR})": [r["legacy_rank"] >= LEGACY_RANK_FLOOR for r in rows],
    }
    out = {
        "n": len(rows), "gold_high": sum(gold_h), "gold_surface": sum(gold_surface),
        "materiality_high": {"proposed method": prf(new_h, gold_h),
                             **{k: prf(v, gold_h) for k, v in legacy.items()}},
        "surface (ESCALATE/WATCH/VERIFY)": {"proposed method": prf(new_surface, gold_surface)},
        "escalate": prf(new_esc, gold_esc),
    }
    mat_conf = Counter((_MAT[r["label_materiality"]], a.materiality_level) for r, a in zip(rows, order))
    out["materiality_confusion"] = {f"{g}->{p}": n for (g, p), n in sorted(mat_conf.items())}
    pr_conf = Counter((_PRIO[r["label_priority"]], a.priority) for r, a in zip(rows, order))
    out["priority_confusion"] = {f"{g}->{p}": n for (g, p), n in sorted(pr_conf.items())}
    out["priority_exact_match"] = round(sum(1 for r, a in zip(rows, order) if _PRIO[r["label_priority"]] == a.priority) / len(rows), 3)
    by_stratum = {}
    for s in sorted({r["stratum"] for r in rows}):
        idx = [i for i, r in enumerate(rows) if r["stratum"] == s]
        by_stratum[s] = {"n": len(idx), "gold_high": sum(gold_h[i] for i in idx),
                         **{k: v for k, v in prf([new_h[i] for i in idx], [gold_h[i] for i in idx]).items() if k in ("tp", "fp", "fn")}}
    out["materiality_by_stratum"] = by_stratum
    out["false_negatives"] = [(r["id"], r["title"][:70], r["source"][:24], assess[r["id"]].materiality_level)
                              for r, g, p in zip(rows, gold_h, new_h) if g and not p]
    out["false_positives"] = [(r["id"], r["title"][:70], r["source"][:24], r["label_materiality"])
                              for r, g, p in zip(rows, gold_h, new_h) if p and not g]
    # incident-correlation check: known multi-report incidents that stayed split
    out["incident_groups"] = {"events": len(rows), "incidents": len(incidents),
                              "multi_report": sum(1 for i in incidents if len(i.members) > 1)}
    out["_inc_of"] = {k: v.incident_id for k, v in inc_of.items()}
    out["incident_grouping_recall"] = grouping_recall(out["_inc_of"])
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    rows = load(args[0] if args else DEFAULT_FIXTURE)
    res = evaluate(rows)
    res.pop("_inc_of")
    print(json.dumps(res, indent=1, ensure_ascii=False))
