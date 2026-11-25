"""Offline replay of shadow PIR tagging over exported events (no DB, no network, no writes).

Input: JSON list of events (exported by SELECT elsewhere). Fields used: raw_title,
raw_summary, event_type, risk_rating, customer_impact, disposition,
operational_relevance. Optional labels: ``expect_any`` (list of acceptable PIR ids;
an empty list means "should match nothing"), ``material`` (reviewer judged material).
Labels are development examples written by the implementer, not independent evidence.

HONESTY NOTE: ``recall_on_labelled`` is measured on the author's own tuned development labels. It is NOT the PIR recall. The realistic
baseline is the independent reviewer's blind replay (config ``blind_replay_baseline``: 31% on title/summary only, 46% with classifier fields,
13 material items, 0 false matches on 15), emitted below as ``realistic_baseline`` with every replay. Event-type-only matches are WEAK;
``unmatched_material`` counts material items with no STRONG match, and such items must remain in the unmatched high-severity lane.

Usage: python tools/intelligence/pir_replay.py events.json [--json]
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from intelligence.requirements import load_pirs, tag_item

AMBIGUITY_THRESHOLD = 3  # an item matching this many PIRs or more is reported as ambiguous


def realistic_baseline() -> dict:
    """The independent reviewer's blind-replay result recorded in the PIR config (None-safe)."""
    try:
        from intelligence.requirements import _default_cfg
        return _default_cfg().get("blind_replay_baseline") or {}
    except Exception:  # noqa: BLE001
        return {}


def replay(events: list, pirs=None) -> dict:
    pirs = pirs or load_pirs()
    rows = []
    for ev in events:
        r = tag_item(ev, pirs)
        rows.append((ev, r, [m.pir_id for m in r.matches]))
    strong_of = lambda x: [m.pir_id for m in x[1].matches if m.strength == "strong"]
    labelled_pos = [x for x in rows if x[0].get("expect_any")]
    labelled_neg = [x for x in rows if x[0].get("expect_any") == []]
    hit = [x for x in labelled_pos if set(x[2]) & set(x[0]["expect_any"])]
    missed = [x for x in labelled_pos if not (set(x[2]) & set(x[0]["expect_any"]))]
    false_match = [x for x in labelled_neg if x[2]]
    extra = [x for x in labelled_pos if set(x[2]) - set(x[0]["expect_any"])]
    ambiguous = [x for x in rows if len(x[2]) >= AMBIGUITY_THRESHOLD]
    lane = [x for x in rows if x[1].unmatched_high_severity]
    unmatched_material = [x for x in rows if x[0].get("material") and not strong_of(x)]
    by_case = defaultdict(lambda: Counter())
    for ev, r, ids in rows:
        c = by_case[ev.get("case", "?")]
        c["n"] += 1
        c["tagged"] += bool(ids)
        if ev.get("expect_any"):
            c["expected"] += 1
            c["hit"] += bool(set(ids) & set(ev["expect_any"]))
        if ev.get("expect_any") == []:
            c["neg"] += 1
            c["false"] += bool(ids)
    def brief(x):
        return {"id": x[0].get("event_id"), "title": x[0].get("raw_title", "")[:80], "tags": x[2],
                "case": x[0].get("case")}
    return {
        "n": len(rows), "tagged": sum(1 for x in rows if x[2]),
        "labelled_positive": len(labelled_pos), "hit": len(hit),
        "recall_on_labelled": round(len(hit) / len(labelled_pos), 3) if labelled_pos else None,
        "labelled_negative": len(labelled_neg), "false_match": len(false_match),
        "false_match_rate": round(len(false_match) / len(labelled_neg), 3) if labelled_neg else None,
        "positives_with_extra_tags": len(extra),
        "weak_only_items": sum(1 for x in rows if x[2] and not strong_of(x)),
        "labelled_recall_is_dev_tuned": "recall_on_labelled is development-label recall, not PIR recall; see realistic_baseline",
        "realistic_baseline": realistic_baseline(),
        "ambiguous": len(ambiguous), "emerging": sum(1 for x in rows if x[1].emerging),
        "unmatched_high_severity_lane": len(lane),
        "unmatched_material": [brief(x) for x in unmatched_material],
        "unmatched_material_not_in_lane": [brief(x) for x in unmatched_material if not x[1].unmatched_high_severity],
        "missed_expected": [dict(brief(x), expected=x[0]["expect_any"]) for x in missed],
        "false_matches": [brief(x) for x in false_match],
        "ambiguous_items": [brief(x) for x in ambiguous],
        "lane_items": [brief(x) for x in lane],
        "by_pir": dict(Counter(i for x in rows for i in x[2])),
        "by_case": {k: dict(v) for k, v in by_case.items()},
    }


def main(argv) -> int:
    events = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    out = replay(events)
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
