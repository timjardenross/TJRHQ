"""Human-review queue for the rubric-v2 labels: every event either AI reviewer marked ESCALATE, every priority disagreement, and a
deterministic stratified sample of events both reviewers called REFERENCE (to look for shared false negatives)."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
F, D = ROOT / "tests" / "fixtures", ROOT / "docs" / "review"
A = {x["id"]: x for x in json.loads((F / "labels_v2_reviewerA.json").read_text())["labels"]}
B = {x["id"]: x for x in json.loads((F / "labels_v2_reviewerB.json").read_text())["labels"]}
smap = json.loads((F / "rubric_v2_relabel_setmap.json").read_text())
info = {}
for f in ("dev150", "holdout127"):
    for r in csv.DictReader((D / f"{f}_review_sheet.csv").open()):
        info[r["id6"]] = (r["title"], r["publisher"], r["url"])
for name in ("weekly_evidence_holdout2_unlabelled.json",):
    d = json.loads((F / name).read_text())
    c = d["_meta"]["columns"]
    for r in d["rows"]:
        info[r[0]] = (r[c.index("title")], r[c.index("source")], r[c.index("url")])
ids = list(A)
esc = [i for i in ids if "E" in (A[i]["priority"], B[i]["priority"])]
dis = [i for i in ids if A[i]["priority"] != B[i]["priority"] and i not in esc]
both_r = [i for i in ids if A[i]["priority"] == B[i]["priority"] == "R"]


def md5key(i):
    return hashlib.md5(i.encode(), usedforsecurity=False).hexdigest()


def group_of(i):
    src = info[i][1].lower()
    return smap[i] + ("/aggregator" if "google news" in src else "/primary-advisory" if any(k in src for k in ("aemo", "cisa", "cisco", "apra", "acsc", "google cloud", "sans")) else "/other")


strata = {}
for i in both_r:
    strata.setdefault(group_of(i), []).append(i)
sample = []
for g, v in sorted(strata.items()):
    v.sort(key=md5key)
    k = max(2, round(60 * len(v) / len(both_r)))
    sample += v[:k]
rows = [(i, "E by at least one reviewer") for i in esc] + [(i, "priority disagreement") for i in dis] + [(i, "stratified REFERENCE sample") for i in sample]
with (D / "human_review_queue_v2.csv").open("w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["id", "set", "reason", "title", "publisher", "url", "A_priority", "A_note", "B_priority", "B_note", "human_priority", "human_materiality", "human_notes"])
    for i, why in rows:
        t, p, u = info[i]
        w.writerow([i, smap[i], why, t, p, u, A[i]["priority"], A[i]["note"], B[i]["priority"], B[i]["note"], "", "", ""])
print({"escalate": len(esc), "disputed_not_E": len(dis), "reference_sample": len(sample), "total": len(rows), "reference_pool": len(both_r)})
