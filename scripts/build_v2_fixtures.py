"""Build rubric-v2 labelled fixtures per set from the two blind reviewers: 'either' (positive if either reviewer says
high / ESCALATE: recall-conservative) and 'both' (positive only if both do: precision-conservative). Also writes the
transparent adjudication list for every ESCALATE disagreement. Originals (v1 labels) are not touched."""
import csv
import json
from pathlib import Path

F = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
D = Path(__file__).resolve().parents[1] / "docs" / "review"
A = {x["id"]: x for x in json.loads((F / "labels_v2_reviewerA.json").read_text())["labels"]}
B = {x["id"]: x for x in json.loads((F / "labels_v2_reviewerB.json").read_text())["labels"]}
smap = json.loads((F / "rubric_v2_relabel_setmap.json").read_text())
SRC = {"dev150": "weekly_evidence_eval_set.json", "hist127": "weekly_evidence_holdout_set.json",
       "h2_160": "weekly_evidence_holdout2_unlabelled.json"}
M = {"high": "H", "medium": "M", "low": "L"}
ORDER = {"R": 0, "W": 1, "V": 2, "E": 3}


def combine(i, mode):
    a, b = A[i], B[i]
    if mode == "either":
        mat = max((a["materiality"], b["materiality"]), key={"low": 0, "medium": 1, "high": 2}.get)
        pri = "E" if "E" in (a["priority"], b["priority"]) else max((a["priority"], b["priority"]), key=ORDER.get)
    else:
        mat = min((a["materiality"], b["materiality"]), key={"low": 0, "medium": 1, "high": 2}.get)
        non_e = [x for x in (a["priority"], b["priority"]) if x != "E"]
        pri = min(non_e, key=ORDER.get) if non_e else "E"      # E only when BOTH reviewers say E
    return M[mat], pri


def groups():
    g = {}
    for i, x in A.items():
        if x["group"]:
            g.setdefault(x["group"], []).append(i)
    return {k: v for k, v in g.items() if len(v) > 1}


for tag, name in SRC.items():
    d = json.loads((F / name).read_text())
    cols = d["_meta"]["columns"][:11]
    ids = {r[0] for r in d["rows"]}
    gg = {k: [i for i in v if i in ids] for k, v in groups().items()}
    gg = {k: v for k, v in gg.items() if len(v) > 1}
    for mode in ("either", "both"):
        rows = []
        for r in d["rows"]:
            m, p = combine(r[0], mode)
            rows.append(r[:11] + [m, p])
        meta = {"status": f"rubric 2.0 labels ({mode}); DEVELOPMENT EVIDENCE for model 0.5.0 (set seen during development)",
                "rubric_version": "2.0", "columns": cols + ["label_materiality", "label_priority"], "gold_incident_groups": gg}
        (F / f"weekly_evidence_v2_{tag}_{mode}.json").write_text(json.dumps({"_meta": meta, "rows": rows}, ensure_ascii=False))

titles = {}
for name in SRC.values():
    d = json.loads((F / name).read_text())
    c = d["_meta"]["columns"]
    for r in d["rows"]:
        titles[r[0]] = (r[c.index("title")], r[c.index("source")])
D.mkdir(exist_ok=True)
with (D / "adjudication_v2_escalate_disagreements.csv").open("w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["id", "set", "title", "source", "A_priority", "A_note", "B_priority", "B_note", "captain_decision", "captain_notes"])
    for i in A:
        if (A[i]["priority"] == "E") != (B[i]["priority"] == "E"):
            w.writerow([i, smap[i], titles[i][0], titles[i][1], A[i]["priority"], A[i]["note"], B[i]["priority"], B[i]["note"], "", ""])
print("ok")
