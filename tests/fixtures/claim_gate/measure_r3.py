"""Measure the claim gate on the round-3 dev corpus (and the earlier dev/sealed halves): python tests/fixtures/claim_gate/measure_r3.py [r3|v2|all]."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..")))

from intelligence import claim_gate as cg


def run(cases, evidence, context):
    rows = []
    for c in cases:
        r = cg.validate_narrative(c["narrative"], c.get("evidence") or evidence, mode="enforce", context=c.get("context") or context)
        rows.append({"id": c["id"], "category": c["category"], "expect": c["expect"], "gate_reject": not r.passed,
                     "kinds": sorted({f.kind for f in r.failures}), "details": [f.detail for f in r.failures][:2]})
    return rows


def summarise(name, rows, verbose=True):
    adv = [r for r in rows if r["expect"] in ("reject",)]
    ok = [r for r in rows if r["expect"] == "accept"]
    det = sum(r["gate_reject"] for r in adv)
    fr = sum(r["gate_reject"] for r in ok)
    print(f"== {name}: adversarial detected {det}/{len(adv)} ({100 * det / max(1, len(adv)):.0f}%); faithful falsely rejected {fr}/{len(ok)} ({100 * fr / max(1, len(ok)):.0f}%)")
    if verbose:
        for r in rows:
            if (r["expect"] == "reject" and not r["gate_reject"]) or (r["expect"] == "accept" and r["gate_reject"]):
                print("  MISS" if r["expect"] == "reject" else "  FALSE-REJECT", r["id"], r["category"], r["kinds"], r["details"])
    return det, len(adv), fr, len(ok)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("r3", "all"):
        import corpus_r3_dev as d
        summarise("R3-DEV", run(d.DEV, d.EVIDENCE, d.CTX))
    if which in ("v2", "all"):
        import corpus_v2_common as common
        import corpus_v2_dev
        try:
            import corpus_v2_sealed
        except ImportError:
            corpus_v2_sealed = None
        summarise("V2-DEV", run(corpus_v2_dev.DEV, common.EVIDENCE, common.CONTEXT))
        if corpus_v2_sealed is not None:
            summarise("V2-SEALED(seen)", run(corpus_v2_sealed.SEALED, common.EVIDENCE, common.CONTEXT))
