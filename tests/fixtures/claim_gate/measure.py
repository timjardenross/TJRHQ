"""Measure the legacy weekly_evidence.validate_claims and the claim gate on the adversarial corpus.

Run:  python tests/fixtures/claim_gate/measure.py [--json]
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import corpus

from intelligence import claim_gate as cg
from intelligence import weekly_evidence as we


def _flat_sentences(n: dict) -> list[str]:
    out = []
    for f in cg.STRING_FIELDS:
        if isinstance(n.get(f), str):
            out += cg._sentences(n[f])
    for f in cg.LIST_FIELDS:
        v = n.get(f)
        if isinstance(v, list):
            for x in v:
                if isinstance(x, str):
                    out += cg._sentences(x)
    return out


def legacy_rejects(case) -> bool:
    """Legacy validator, given the evidence ids the author intended each claim to rest on."""
    ev = {e["id"]: {"title": e["title"], "summary": e["summary"], "source": e["source"]} for e in corpus.EVIDENCE}
    sents = _flat_sentences(case["narrative"])
    if not sents:
        return True                       # nothing to validate: render_narrative treats `not claims` as fallback
    cites = case["cites"] or []
    claims = [we.Claim(s, cites) for s in sents]
    return not we.validate_claims(claims, ev).ok


def gate_result(case):
    return cg.validate_narrative(case["narrative"], corpus.EVIDENCE, mode="shadow", context=corpus.CONTEXT)


def run(cases):
    rows = []
    for c in cases:
        r = gate_result(c)
        rows.append({"id": c["id"], "category": c["category"], "expect": c["expect"],
                     "legacy_reject": legacy_rejects(c), "gate_reject": not r.passed,
                     "kinds": sorted({f.kind for f in r.failures}), "want": sorted(c["kinds"]),
                     "kind_hit": bool(c["kinds"] & {f.kind for f in r.failures}) if c["expect"] == "reject" else None})
    return rows


def table(rows):
    cat = defaultdict(lambda: [0, 0, 0, 0])
    for r in rows:
        k = cat[r["category"]]
        k[0] += 1
        k[1] += r["legacy_reject"]
        k[2] += r["gate_reject"]
        k[3] += bool(r["kind_hit"])
    return dict(cat)


def main():
    out = {}
    for name, cases in (("SET_A", corpus.SET_A), ("SET_B", corpus.SET_B), ("SET_C", corpus.SET_C), ("SET_D", corpus.SET_D)):
        rows = run(cases)
        out[name] = rows
        print(f"\n== {name}: n={len(rows)} ==")
        print(f"{'category':22} {'n':>3} {'legacy rejects':>15} {'gate rejects':>13} {'gate kind match':>16}")
        for cat, (n, lg, gt, kh) in table(rows).items():
            if cat == "clean":
                print(f"{cat + ' (false reject)':22} {n:>3} {lg:>15} {gt:>13} {'-':>16}")
            else:
                print(f"{cat:22} {n:>3} {lg:>15} {gt:>13} {kh:>16}")
        adv = [r for r in rows if r["expect"] == "reject"]
        cl = [r for r in rows if r["expect"] == "accept"]
        print(f"adversarial detected: legacy {sum(r['legacy_reject'] for r in adv)}/{len(adv)}, gate {sum(r['gate_reject'] for r in adv)}/{len(adv)}")
        print(f"clean falsely rejected: legacy {sum(r['legacy_reject'] for r in cl)}/{len(cl)}, gate {sum(r['gate_reject'] for r in cl)}/{len(cl)}")
        for r in rows:
            if (r["expect"] == "reject" and not r["gate_reject"]) or (r["expect"] == "accept" and r["gate_reject"]):
                print("  GATE MISS" if r["expect"] == "reject" else "  GATE FALSE REJECT", r["id"], r["kinds"])
            elif r["expect"] == "reject" and not r["kind_hit"]:
                print("  kind mismatch", r["id"], "got", r["kinds"], "want", r["want"])
    if "--json" in sys.argv:
        print(json.dumps(out))


if __name__ == "__main__":
    main()
