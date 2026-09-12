---
status: "accepted"
date: 2026-09-12
decision-makers: {unknown — reconstructed from code, not from a governance-log entry}
consulted: {unknown}
informed: {unknown}
---

# Advisory-Only Automation: A Recommendation Is Not a Decision (Gate 1/Gate 2 stay human)

## Context and Problem Statement

Multiple automation modules in the mission-lifecycle pipeline (`core/coordination/`)
generate triage packages, review packages, classification reports, and stage
recommendations for missions. Left unconstrained, an automated "recommender"
module can drift into silently making the decision itself (writing status,
approving, or advancing a mission) rather than just informing the human who is
supposed to decide. ADR-013 is the governance rule that draws this line, and it
is cited, verbatim in spirit, at every one of the coordination pipeline's
recommendation-producing modules.

## Decision Drivers

* Automated agents ("Number One") are trusted to gather evidence, classify,
  and draft recommendations — but not to hold assignment/approval authority.
* Gate 1 (Capture → Triage Ready) and Gate 2 (mission closure) are the
  points where the pipeline has historically needed a human accountable for
  the call.
* Reuse-first design (ADR-020) already established that these modules should
  not duplicate `delivery_reconciler`/source-gathering; ADR-013 is the
  parallel rule for the *write/approval* side of the same pipeline.

## Considered Options

* Let recommendation modules also write status/approval when confidence is high.
* Recommendation modules are strictly read-only/advisory; a human (XO/Captain)
  makes every status transition and approval.

## Decision Outcome

Chosen option: "Recommendation modules are strictly read-only/advisory", because
it keeps a single, auditable human accountable for every status transition and
approval in the mission lifecycle, while still letting automation do the
evidence-gathering and drafting work that is safe to automate.

Concretely, as implemented:

* `core/coordination/lifecycle_reconciler.py`: "GOVERNANCE (ADR-013): a
  recommendation is NOT a transition. This module writes no status, performs
  no approval, runs no code. It is read-only and advisory."
* `core/coordination/triage_package.py`: "a triage package is a
  RECOMMENDATION, not a decision. It assigns no status, makes no assignment,
  performs no approval. Gate 1 stays human: Number One recommends, the XO
  decides."
* `core/coordination/review_package.py`: "a review package is preparation,
  not a decision. ... performs no closure, no approval, no merge, and runs no
  code. The human still decides at Gate 2."
* `core/coordination/lifecycle_advancer.py`: the one module that *does* write
  (a gate-safe, reversible ledger move to "Triage Ready") is explicitly scoped
  to a single pre-gate stage and still requires the human call downstream —
  "Approval stays 100% human (ADR-013: Number One recommends, XO decides)."
* `core/coordination/lifecycle_coverage.py` and `core/coordination/engineering_prep.py`
  repeat the same constraint for classification and engineering-prep
  advisory output respectively.

### Consequences

* Good, because every status transition in the mission lifecycle has a single,
  identifiable human decision point — no automation can silently move a
  mission through a gate.
* Good, because it lets six-plus coordination modules share one governance
  rule instead of each re-deriving its own approval boundary, keeping the
  boundary consistent and easy to audit.
* Bad, because it means genuinely low-risk, high-confidence recommendations
  still require a human click before anything happens — no fast-path for
  cases where the human would obviously agree.

### Confirmation

Grep for `ADR-013` across `core/coordination/*.py`: every module that appears
should either (a) perform no writes at all, or (b) perform only the single
narrow, reversible, pre-gate ledger write that `lifecycle_advancer.py`
performs, with approval/closure left to a human-driven call. A new module in
this pipeline that writes status or approval without this citation and
without an accompanying human-approval step should be treated as a
regression against this decision.

## Pros and Cons of the Options

### Read-only/advisory recommendation modules

* Good, because it matches how the rest of the pipeline already works
  (ADR-020 reuse-first: no new write paths).
* Good, because it is cheap to verify (grep for writes in a module that
  claims to be advisory).
* Bad, because it adds a manual step even when automation is confident.

### Let high-confidence recommendations auto-apply

* Good, because it would reduce human toil for the "obvious" cases.
* Bad, because it removes the single accountable decision point and was
  never adopted anywhere in the current pipeline.

## More Information

Evidence gathered by grepping `ADR-013` across the live repository
(USS-TJR-MSN-0369 Stream 3, 2026-09-12): 6 real, load-bearing citations in
`core/coordination/lifecycle_reconciler.py`, `engineering_prep.py`,
`lifecycle_advancer.py`, `lifecycle_coverage.py`, `triage_package.py`, and
`review_package.py`. Additional citations exist only in non-authoritative
material: a hand-maintained/known-stale UI mock (`ArchitectureIndex.tsx` /
`captainReview.ts`, explicitly commented as "not guaranteed complete or
current"), a `docs/runbooks/graphify-query-templates.md` example query
("ADR-013 number one orchestrator"), a defunct/ghost `temporal_entities`
table dump referencing a never-committed file
`ADR-013-Number-One-as-Operational-Orchestrator.md`, and several
`data/self-improvement/runs/*/evidence.json` retrieval-fixture file lists
(candidate paths, several of which never existed on disk). These
non-authoritative sources are consistent with the code-derived title
("Number One as operational orchestrator/recommender, not decision-maker")
but were not used as the basis for this document's content — the `core/coordination/*`
docstrings were.

Related: ADR-020 (Capability Reuse Before Capability Creation) — the reuse
half of the same pipeline's design discipline.
