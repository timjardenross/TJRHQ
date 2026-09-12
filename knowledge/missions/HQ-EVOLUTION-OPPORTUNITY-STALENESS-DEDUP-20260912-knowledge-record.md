# Knowledge Record — HQ Evolution opportunity review, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | none (ad-hoc review, not an auto-dispatched finding) |
| Title | Opportunities can go stale or duplicate in the gap between classification and human review |
| Date | 2026-09-12 |
| Lesson | LL-144 |

## Outcome

A manual review of 8 "Proposed" HQ Evolution opportunities found 6 that were
already stale (their underlying condition was fixed by a later, unrelated PR
or was never real to begin with) and 3 of those 6 were also duplicates of
each other. Rejected via `POST /api/opportunity/decide`
(EVO-0010, EVO-0011, EVO-0012, EVO-0013, EVO-0014, EVO-0035), reworded the
one glm-5.3:cloud opportunity kept open (EVO-0009) to reflect that the
engineering fix already shipped and the remaining ask is ops-only, and left
one genuine open gap (EVO-0036) as-is.

Fixed two root causes rather than just closing the individual records:

1. `opportunity_store.new_fingerprint()` hashes `discovery_source:source:title`
   verbatim (whitespace/case-normalized only) — no fuzzy matching. Three
   internal-discovery cycles independently re-derived three differently-worded
   titles for the exact same finding (glm-5.3:cloud unavailable in the model
   router: EVO-0009/EVO-0012/EVO-0035), so all three hashed differently and
   none of them ever collapsed. Added `OpportunityStore.find_near_duplicate()`,
   reusing `evolution_memory.py`'s existing deterministic keyword-overlap +
   near-duplicate-title-prefix approach (no embeddings, no LLM — the same
   pattern already proven for investigation-time "related experience" recall,
   now also serving dedup), wired in as a fallback in `relevance.py`'s
   `check_duplicate()` when the exact-hash lookup misses. Regression test uses
   the three real titles from this incident as its fixture.

2. `internal_discovery.py`'s `finding_to_candidate()` mapped a classified
   finding into an opportunity 1:1 with no re-check of current repo state —
   `staleness_check.py` already existed and did exactly this kind of
   deterministic re-check (path exists/absent, git dirty), but was only ever
   applied to findings already sitting undecided in the dashboard
   (`evolution_orchestrator.py`'s `_check_finding_staleness`, logging to
   `finding_staleness.jsonl` for a human to read) — never before a finding
   became a brand-new opportunity in the first place. Wired
   `staleness_check.check_finding_staleness()` into `internal_discovery.discover()`
   (new optional `repo_root` param, default `None` preserves prior behavior):
   a finding it can positively confirm `resolved` is skipped and logged; a
   finding it can only call `confirmed` or `unclear` still proceeds
   unchanged — same never-guess-resolved honesty contract as
   `staleness_check.py`'s other caller.

## Lesson

A finding or candidate's evidence is a snapshot taken at classification time.
Nothing re-checks that snapshot against reality again until either an
overnight re-run happens to notice, or (until this fix) never at all for a
brand-new candidate about to be minted. The gap between "HQ observed X" and
"a human looks at the resulting card" is where staleness and duplication both
live — not in the observation itself, which was usually correct at the time.

## Future Guidance

Any pipeline stage that turns an observation into a persisted, human-facing
record (a finding → candidate → opportunity, or equivalent in a future
surface) should ask two questions immediately before persisting, not just at
creation: (1) does an existing record already represent this same
underlying thing, even if worded differently — exact-match dedup alone is
not enough once an LLM is doing the wording; (2) is the original evidence
still true right now, not just at the moment it was collected. Both checks
already exist as reusable, deterministic, LLM-free primitives in this
codebase (`evolution_memory.py`'s keyword-overlap matcher,
`staleness_check.py`'s re-check) — the fix in both cases was wiring an
existing primitive into an earlier point in the pipeline, not inventing a
new one.
