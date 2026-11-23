"""Merge the two blind reviewers' labels with the unlabelled fresh holdout into evaluation fixtures.
Variants: reviewerA, reviewerB, and 'either' (a positive if EITHER reviewer marks it H / E: recall-conservative)."""
import json
from pathlib import Path

F = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
base = json.loads((F / "weekly_evidence_holdout2_unlabelled.json").read_text())
cols = base["_meta"]["columns"][:11]
L = {k: {x["id"]: x for x in json.loads((F / f"labels_holdout2_reviewer{k}.json").read_text())["labels"]} for k in "AB"}
RANK_M, RANK_P = {"L": 0, "M": 1, "H": 2}, {"R": 0, "W": 1, "V": 2, "E": 3}


def groups(lab):
    g = {}
    for i, x in lab.items():
        if x["group"]:
            g.setdefault(x["group"], []).append(i)
    return {k: v for k, v in g.items() if len(v) > 1}


for name in ("A", "B", "either"):
    rows = []
    for r in base["rows"]:
        i = r[0]
        if name == "either":
            m = max((L["A"][i]["materiality"], L["B"][i]["materiality"]), key=RANK_M.get)
            esc = "E" in (L["A"][i]["priority"], L["B"][i]["priority"])
            p = "E" if esc else max((L["A"][i]["priority"], L["B"][i]["priority"]), key=lambda v: RANK_P[v] if v != "E" else -1)
        else:
            m, p = L[name][i]["materiality"], L[name][i]["priority"]
        rows.append(r[:11] + [m, p])
    meta = {"status": f"FRESH HOLDOUT, labels = {name}; frozen model run once; no tuning", "columns": cols + ["label_materiality", "label_priority"],
            "gold_incident_groups": groups(L["A" if name == "either" else name])}
    (F / f"weekly_evidence_holdout2_labelled_{name}.json").write_text(json.dumps({"_meta": meta, "rows": rows}, ensure_ascii=False))
print("ok")
