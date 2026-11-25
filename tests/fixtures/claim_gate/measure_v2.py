"""Measure the claim gate on the fix-logic corpus: python tests/fixtures/claim_gate/measure_v2.py [dev|sealed|both]."""
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..")))

import corpus_v2_common as common

from intelligence import claim_gate as cg


def run(cases):
    rows = []
    for c in cases:
        r = cg.validate_narrative(c["narrative"], common.EVIDENCE, mode="enforce", context=common.CONTEXT)
        rows.append({"id": c["id"], "category": c["category"], "expect": c["expect"], "gate_reject": not r.passed,
                     "kinds": sorted({f.kind for f in r.failures}), "details": [f.detail for f in r.failures][:2]})
    return rows


def summarise(name, rows, verbose=True):
    adv = [r for r in rows if r["expect"] == "reject"]
    ok = [r for r in rows if r["expect"] == "accept"]
    det = sum(r["gate_reject"] for r in adv)
    fr = sum(r["gate_reject"] for r in ok)
    print(f"== {name}: adversarial detected {det}/{len(adv)} ({100 * det / max(1, len(adv)):.0f}%); faithful falsely rejected {fr}/{len(ok)} ({100 * fr / max(1, len(ok)):.0f}%)")
    cat = defaultdict(lambda: [0, 0])
    for r in adv:
        cat[r["category"]][0] += 1
        cat[r["category"]][1] += r["gate_reject"]
    if verbose:
        for r in rows:
            if (r["expect"] == "reject" and not r["gate_reject"]) or (r["expect"] == "accept" and r["gate_reject"]):
                print("  MISS" if r["expect"] == "reject" else "  FALSE-REJECT", r["id"], r["category"], r["kinds"], r["details"])
    return det, len(adv), fr, len(ok)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("dev", "both"):
        import corpus_v2_dev
        summarise("DEV", run(corpus_v2_dev.DEV))
    if which in ("sealed", "both"):
        try:
            import corpus_v2_sealed
        except ImportError:
            print("SEALED: the sealed half of the author corpus is intentionally not distributed in this repository")
        else:
            summarise("SEALED", run(corpus_v2_sealed.SEALED))
