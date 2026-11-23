"""One bounded V1 evaluation of the shared evidence foundation against the Captain's 75% targets. Run ONCE on a frozen model; do not tune on it.

Evidence used: (1) 437 events with rubric-v2.1 labels from two AI reviewers (PROVISIONAL, not independent ground truth), evaluated at the INCIDENT level,
in two label variants ('either' recall-conservative, 'both' precision-conservative); (2) the curated historical sentinel incidents whose sources were
re-opened and verified, each tested on its contemporary headlines as a single live report; (3) the verified non-incidents as a false-alarm check."""
import json
import math
import sys
from itertools import combinations
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "scripts")]
import eval_weekly_evidence as ev

from intelligence import event_detection as ed

F = _REPO / "tests" / "fixtures"
SETS = ("dev150", "hist127", "h2_160")


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    a = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - a) / d, 3), round((c + a) / d, 3)]


def rate(k, n):
    return {"k": k, "n": n, "value": None if n == 0 else round(k / n, 3), "ci95": wilson(k, n)}


def one_set(path):
    doc = json.loads(Path(path).read_text())
    rows = ev.load(path)
    decs = ed.run(ev.to_events(rows), now=ev.NOW)
    inc_of = {m.event_id: d for d in decs for m in d.group.members}
    cand = {m.event_id: m for d in decs for m in d.group.members}
    lab = {r["id"]: r for r in rows}
    groups = doc["_meta"].get("gold_incident_groups", {})
    unit = {i: i for i in lab}
    for name, ids in groups.items():
        for i in ids:
            if i in unit:
                unit[i] = name
    units = {}
    for i, u in unit.items():
        units.setdefault(u, []).append(i)
    gold_high = {u for u, ids in units.items() if any(lab[i]["label_materiality"] == "H" for i in ids)}
    model_high = {u for u, ids in units.items() if any(inc_of[i].materiality == "high" and not cand[i].commentary for i in ids)}
    gold_esc = {u for u, ids in units.items() if any(lab[i]["label_priority"] == "E" for i in ids)}
    model_esc = {u for u, ids in units.items() if any(inc_of[i].priority == "ESCALATE" and not cand[i].commentary for i in ids)}
    gold_pairs = {frozenset(p) for ids in groups.values() for p in combinations([i for i in ids if i in lab], 2)}
    model_pairs, false_merge, comm = set(), 0, 0
    for d in decs:
        for a, b in combinations([m.event_id for m in d.group.members], 2):
            model_pairs.add(frozenset((a, b)))
            if frozenset((a, b)) not in gold_pairs:
                if cand[a].commentary or cand[b].commentary:
                    comm += 1
                else:
                    false_merge += 1
    return {"n_events": len(rows), "n_incidents_model": len(decs),
            "high": (len(gold_high & model_high), len(model_high), len(gold_high)),
            "esc": (len(gold_esc & model_esc), len(model_esc), len(gold_esc)),
            "grp": (len(gold_pairs & model_pairs), len(gold_pairs), len(model_pairs & gold_pairs) + false_merge),
            "false_merge": false_merge, "commentary_attached": comm,
            "priorities": {p: sum(1 for d in decs if d.priority == p) for p in ("ESCALATE", "VERIFY", "WATCH", "REFERENCE")}}


def labelled(variant):
    per = {s: one_set(F / f"weekly_evidence_v2_{s}_{variant}.json") for s in SETS}
    tot = lambda key, i: sum(v[key][i] for v in per.values())
    return {"variant": variant, "per_set": per,
            "high_materiality_recall": rate(tot("high", 0), tot("high", 2)),
            "high_materiality_precision": rate(tot("high", 0), tot("high", 1)),
            "escalation_recall": rate(tot("esc", 0), tot("esc", 2)),
            "escalation_precision": rate(tot("esc", 0), tot("esc", 1)),
            "grouping_recall": rate(tot("grp", 0), tot("grp", 1)),
            "grouping_precision": rate(tot("grp", 0), tot("grp", 2)),
            "false_merges": sum(v["false_merge"] for v in per.values())}


def sentinel():
    ver = json.loads((F / "historical_challenge_verification.json").read_text())["entries"]
    inc = json.loads((F / "historical_challenge_au.json").read_text())["entries"] + json.loads((F / "historical_challenge_intl.json").read_text())["entries"]
    neg = json.loads((F / "historical_challenge_negatives.json").read_text())["entries"]

    def heads(entry, only_contemporary=True):
        v = ver.get(entry["id"], {})
        by_url = {s["url"]: s for s in v.get("sources", [])}
        out = []
        for s in entry["sources"]:
            vs = by_url.get(s["url"], {})
            if only_contemporary and vs.get("evidence_type") != "contemporary":
                continue
            h = vs.get("rendered_headline") if vs.get("headline_matches_input") in ("exact", "minor_difference") and vs.get("rendered_headline") else s["headline_verbatim"]
            out.append((h, s["publisher"], vs.get("headline_matches_input")))
        return out

    def classify(h, pub):
        d = ed.run([{"id": "s", "title": h, "source": pub, "geography": "AU", "collected_at": "2026-11-20T00:00:00Z"}], now=ev.NOW)[0]
        return d.priority

    res, miss = [], []
    for e in inc:
        if ver.get(e["id"], {}).get("entry_verification", {}).get("status") != "verified":
            continue
        hs = heads(e)
        if not hs:
            res.append({"id": e["id"], "tested": 0})
            continue
        pr = [classify(h, p) for h, p, _ in hs]
        best = min(pr, key=["ESCALATE", "VERIFY", "WATCH", "REFERENCE"].index)
        res.append({"id": e["id"], "tested": len(hs), "priorities": pr, "best": best, "first": pr[0]})
        if best not in ("ESCALATE", "VERIFY"):
            miss.append((e["id"], hs[0][0][:80], pr))
    tested = [r for r in res if r["tested"]]
    strict = sum(1 for r in tested if r["best"] in ("ESCALATE", "VERIFY"))
    lenient = sum(1 for r in tested if r["best"] != "REFERENCE")
    firstok = sum(1 for r in tested if r["first"] in ("ESCALATE", "VERIFY"))
    negs = []
    for e in neg:
        for h, p, _ in heads(e, only_contemporary=False)[:1]:
            negs.append((e["id"], classify(h, p)))
    return {"verified_incidents": len(res), "with_contemporary_headline": len(tested),
            "detected_or_retained_ESCALATE_or_VERIFY_best_headline": rate(strict, len(tested)),
            "detected_or_retained_first_headline": rate(firstok, len(tested)),
            "not_REFERENCE_best_headline": rate(lenient, len(tested)),
            "missed": miss, "negatives_tested": len(negs),
            "negatives_escalated": [i for i, p in negs if p == "ESCALATE"], "negatives_verify": [i for i, p in negs if p == "VERIFY"]}


if __name__ == "__main__":
    out = {"model": ed.METHOD_VERSION, "labelled_either": labelled("either"), "labelled_both": labelled("both"), "sentinels": sentinel()}
    print(json.dumps(out, indent=1, ensure_ascii=False))
