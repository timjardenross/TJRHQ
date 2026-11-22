"""Evaluate the staged detector (intelligence/event_detection.py) against a labelled fixture.

Separately reports: candidate recall, materiality (high) precision/recall, escalation recall/precision at incident
level, and incident-grouping precision/recall with false merges listed. Wilson 95% intervals and denominators
everywhere. The frozen b92c1b39 model and the legacy fields are reported alongside for comparison.

Usage: eval_staged_detection.py FIXTURE [--list]   (fixture rows need label_materiality/label_priority;
`_meta.gold_incident_groups` {name: [ids]} is used for grouping; ids absent from every group are singletons)."""
from __future__ import annotations

import json
import math
import sys
from itertools import combinations
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "scripts")]
import eval_weekly_evidence as ev

from intelligence import event_detection as ed


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    a = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - a) / d, 3), round((c + a) / d, 3)]


def rate(k, n):
    return {"k": k, "n": n, "value": None if n == 0 else round(k / n, 3), "ci95": wilson(k, n)}


def evaluate(path, *, with_lists=False):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = ev.load(path)
    events = ev.to_events(rows)
    decisions = ed.run(events, now=ev.NOW)
    inc_of = {m.event_id: d for d in decisions for m in d.group.members}
    cand_of = {m.event_id: m for d in decisions for m in d.group.members}
    lab = {r["id"]: r for r in rows}

    # 1. candidate recall: gold candidates are events a reviewer judged high-materiality or VERIFY/ESCALATE
    gold_cand = [i for i, r in lab.items() if r["label_materiality"] == "H" or r["label_priority"] in ("E", "V")]
    cand_hit = [i for i in gold_cand if cand_of[i].is_candidate]
    out = {"n": len(rows), "candidate_recall": rate(len(cand_hit), len(gold_cand)),
           "candidate_pool_share": rate(sum(1 for c in cand_of.values() if c.is_candidate), len(rows))}

    # 2. materiality (event level, headline impact of the event itself)
    def ev_high(i):
        return ed._impact(cand_of[i]) == "actual_major"
    tp = sum(1 for i, r in lab.items() if ev_high(i) and r["label_materiality"] == "H")
    fp = sum(1 for i, r in lab.items() if ev_high(i) and r["label_materiality"] != "H")
    fn = sum(1 for i, r in lab.items() if not ev_high(i) and r["label_materiality"] == "H")
    out["materiality_high"] = {"precision": rate(tp, tp + fp), "recall": rate(tp, tp + fn), "tp": tp, "fp": fp, "fn": fn}

    # 3. escalation at incident level. Unit = gold group (or singleton).
    gold_groups = doc["_meta"].get("gold_incident_groups") or (
        ev.GOLD_INCIDENT_GROUPS if "eval_set" in str(path) else {})
    unit_of = {i: i for i in lab}
    for name, ids in gold_groups.items():
        for i in ids:
            if i in unit_of:
                unit_of[i] = name
    units: dict[str, list[str]] = {}
    for i, u in unit_of.items():
        units.setdefault(u, []).append(i)
    gold_e = {u for u, ids in units.items() if any(lab[i]["label_priority"] == "E" for i in ids)}
    model_e = {u for u, ids in units.items() if any(inc_of[i].priority == "ESCALATE" for i in ids)}
    out["escalation"] = {"recall": rate(len(gold_e & model_e), len(gold_e)),
                         "precision": rate(len(gold_e & model_e), len(model_e)),
                         "missed": sorted(gold_e - model_e), "false_alarms": sorted(model_e - gold_e)}

    # 4. grouping. Commentary attached to an incident is reported separately, not counted as a false merge.
    gold_pairs = {frozenset(p) for ids in gold_groups.values() for p in combinations([i for i in ids if i in lab], 2)}
    model_pairs, false_merge, attached_commentary = set(), [], []
    for d in decisions:
        for a, b in combinations([m.event_id for m in d.group.members], 2):
            model_pairs.add(frozenset((a, b)))
            if frozenset((a, b)) not in gold_pairs:
                if cand_of[a].commentary or cand_of[b].commentary:
                    attached_commentary.append((a, b))
                else:
                    false_merge.append((a, b))
    out["grouping"] = {"recall": rate(len(gold_pairs & model_pairs), len(gold_pairs)),
                       "precision_excl_commentary": rate(len(model_pairs & gold_pairs),
                                                         len(model_pairs & gold_pairs) + len(false_merge)),
                       "false_merges": false_merge, "commentary_attached": attached_commentary,
                       "gold_groups_split": [n for n, ids in gold_groups.items()
                                             if len({inc_of[i].group.incident_id for i in ids if i in inc_of}) > 1]}
    # frozen model comparison
    old = ev.evaluate(rows)
    old.pop("_inc_of", None)
    out["frozen_b92c1b39_materiality_high"] = old["materiality_high"]["proposed method"]
    out["legacy_confidence_high"] = old["materiality_high"]["legacy 'high' (osint confidence = HIGH)"]
    out["priority_counts"] = {p: sum(1 for d in decisions if d.priority == p) for p in ("ESCALATE", "VERIFY", "WATCH", "REFERENCE")}
    if with_lists:
        out["escalated"] = [(d.headline.event_id, d.headline.title[:80], d.provisional) for d in decisions if d.priority == "ESCALATE"]
        out["missed_candidates"] = [(i, lab[i]["title"][:80]) for i in gold_cand if i not in cand_hit]
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    print(json.dumps(evaluate(args[0], with_lists="--list" in sys.argv), indent=1, ensure_ascii=False))
