"""Inter-reviewer agreement for the fresh holdout: Cohen's kappa per field, group-pair agreement, and the
disagreement list (ids only; the Captain adjudicates)."""
import json
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

F = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def kappa(a, b):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3), round(po, 3)


def load(p):
    return {x["id"]: x for x in json.loads(Path(p).read_text())["labels"]}


def main(a_path=F / "labels_holdout2_reviewerA.json", b_path=F / "labels_holdout2_reviewerB.json"):
    A, B = load(a_path), load(b_path)
    ids = list(A)
    assert list(B) == ids
    out = {"n": len(ids)}
    for f in ("materiality", "priority", "role"):
        k, po = kappa([A[i][f] for i in ids], [B[i][f] for i in ids])
        out[f] = {"kappa": k, "raw_agreement": po}
    # binary: materiality high; priority escalate
    for name, fn in (("materiality_high", lambda x: x["materiality"] == "H"), ("escalate", lambda x: x["priority"] == "E")):
        k, po = kappa([fn(A[i]) for i in ids], [fn(B[i]) for i in ids])
        out[name] = {"kappa": k, "raw_agreement": po}

    def pairs(L):
        g = {}
        for i in ids:
            if L[i]["group"]:
                g.setdefault(L[i]["group"], []).append(i)
        return {frozenset(p) for v in g.values() for p in combinations(v, 2)}
    pa, pb = pairs(A), pairs(B)
    out["group_pairs"] = {"A": len(pa), "B": len(pb), "both": len(pa & pb), "only_A": len(pa - pb), "only_B": len(pb - pa)}
    out["disagree"] = {f: [i for i in ids if A[i][f] != B[i][f]] for f in ("materiality", "priority", "role")}
    out["disagree_escalate"] = [i for i in ids if (A[i]["priority"] == "E") != (B[i]["priority"] == "E")]
    out["disagree_high"] = [i for i in ids if (A[i]["materiality"] == "H") != (B[i]["materiality"] == "H")]
    return out


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
