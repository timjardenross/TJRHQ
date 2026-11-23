"""Combine the 150-event dev set, the 127-event historical holdout and holdout2 into ONE unlabelled, md5-ordered input for
rubric-v2 relabelling (labels, strata and legacy fields stripped so reviewers cannot anchor on them)."""
import hashlib
import json
from pathlib import Path

F = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
rows, seen = [], set()
for name, tag in (("weekly_evidence_eval_set.json", "dev150"), ("weekly_evidence_holdout_set.json", "hist127"),
                  ("weekly_evidence_holdout2_unlabelled.json", "h2_160")):
    d = json.loads((F / name).read_text())
    cols = d["_meta"]["columns"]
    for r in d["rows"]:
        x = dict(zip(cols, r))
        if x["id"] in seen:
            raise SystemExit(f"duplicate id {x['id']}")
        seen.add(x["id"])
        rows.append({"id": x["id"], "title": x["title"], "source": x["source"], "ts": x["ts"], "geo": x["geo"], "_set": tag})
rows.sort(key=lambda r: hashlib.md5(r["id"].encode(), usedforsecurity=False).hexdigest())
out = {"_meta": {"rubric": "docs/rubrics/weekly-evidence-rubric-v2.md (2.0)", "n": len(rows),
                 "note": "source-set tag removed from reviewer copy; ordering is md5(id)"},
       "rows": [[r["id"], r["title"], r["source"], r["ts"], r["geo"]] for r in rows]}
(F / "rubric_v2_relabel_input.json").write_text(json.dumps(out, ensure_ascii=False))
(F / "rubric_v2_relabel_setmap.json").write_text(json.dumps({r["id"]: r["_set"] for r in rows}))
print(len(rows))
