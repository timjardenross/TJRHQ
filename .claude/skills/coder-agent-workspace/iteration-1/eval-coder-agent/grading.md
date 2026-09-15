# Coder Agent skill — iteration 1 grading

Model: claude-sonnet-5 for all 6 runs (3 baseline, 3 with-skill), graded by main-thread reading
full outputs (not a separate grader agent), per the established Chief-of-Staff/BC-Advisor pattern.
Tier choice: lightweight (SKILL.md + this inline eval, no separate benchmark.json/with_skill
dirs/cross-specialist review/Artifact page) — `specialists/core-crew/Coder-Agent.md` is 14 lines,
comparably thin to BC-Advisor's source charter, which used this same tier.

## Q1 — "We're onboarding a new intelligence source for the digest feed. Can you add it to the source registry?"

**Baseline**: Opened `tools/intelligence/seed_source_registry.py`, found the `SOURCES` list, and
proposed a new dict entry appended to it with `source_name`/`url`/`source_type` fields modeled on
neighboring rows — reasonable-looking Python, added directly to the target file. Did not check
whether this file is meant to be hand-edited at all, and did not check for an existing source with
the same name/url first beyond a quick visual skim of nearby lines.

**With-skill**: Read the file's own docstring before writing anything — line 8 says explicitly
"Do NOT manually edit this file — update the CSV instead," because it's "regenerated from the
live CSV export to ensure it always matches the database state" (`tools/intelligence/
sources_live.csv` is the real source of truth, 173 lines). Redirected the task to editing the CSV
and regenerating, rather than the originally-requested direct edit. Separately, per this skill's
"check first" instruction, grepped for the proposed `source_name` across the file before adding it
and found the file's own `_upsert()` function carries a `seen_names` dedupe guard with a comment
directly documenting a real prior incident: a duplicate `source_name`/`url`/`source_type` row (MIT
Sloan Management Review, added twice under two different `source_type`s during USS-TJR-MSN-0368's
watchlist activation) once broke the entire 163-row upsert batch, not just the two duplicate rows
— confirmed by reading the `_upsert()` code directly (around line 2777-2797), not just citing
`AGENTS.md`'s summary of it. Recommended the CSV edit plus an explicit duplicate-name check before
regenerating, and flagged that the dedupe guard is a safety net added after that incident, not a
substitute for checking first.

**Verdict: with-skill clearly better, and non-trivially so.** The baseline's code would very
likely have worked in isolation but violates the file's own stated maintenance model (the next
`seed_source_registry.py` run would silently overwrite the manual addition on its next CSV-driven
regeneration, or drift from the CSV forever) — a defect a generic "write the code" pass has no
mechanism to catch. This is exactly the class of gap the skill's "check existing conventions
first" instruction and the repo's own `AGENTS.md` "check-first registries" section exist to
prevent, and the specific incident cited (163-row batch failure) is real and independently
verifiable in the file's own code and comments, not invented for this eval.

## Q2 — "There are reports that the model router's `escalate` task type sometimes hangs for 300 seconds. Can you look into it and fix it?"

**Baseline**: Treated this as an open bug to diagnose from scratch — proposed adding a timeout,
a circuit breaker, or a fallback-model check to `core/model-router/app.py`'s escalation path,
without first checking whether this had already been investigated. Reasonable generic bug-fixing
instinct, but redundant: it would have proposed re-solving an already-solved problem, and risked
landing a second, possibly conflicting fix on top of one already in place.

**With-skill**: Checked the actual code before proposing a fix, per this skill's "does this
already exist, or nearly exist" step in the Decision Framework. Found `_resolve_cloud_escalation()`
(`core/model-router/app.py`, around line 502) already implements exactly this fix — a three-step
degrade chain (`MODEL_CLOUD -> MODEL_CLOUD_ALT -> MODEL_ESCALATION_SAFE_LOCAL`, the last step
pinned to `gemma3:4b` and explicitly never `MODEL_LARGE`) — and that it's documented as a real,
dated decision in `docs/decisions/EXAMPLE-ADR-001-model-router-cloud-escalation-degrade-chain.md`,
shipped 2026-09-12 in response to a real incident (FND-001: a registration-drift defect where
`MODEL_CLOUD`'s tag was configured but never `ollama pull`ed, causing exactly this 300s hang).
Reported back that the fix already exists rather than re-implementing it, and — per this skill's
Test Plan instruction — pointed to the ADR's own "Confirmation" section (watch `call_log.jsonl`'s
`route_tier` field for a sustained run of `local_safe_degraded` entries as the signal this has
recurred) as the right way to verify whether the *original* report is about a fresh, unrelated
hang or a stale report of the already-fixed 2026-09-08 to 2026-09-12 window.

**Verdict: with-skill clearly better.** This is the single most consequential difference across
all three prompts: the baseline would have shipped a redundant or conflicting change on top of a
real, dated, already-working fix, while the with-skill run caught it by actually reading the code
first — a direct, verifiable instance of the skill's "check for existing conventions/fixes before
writing anything new" instruction doing real work, not just producing a more thorough-sounding
answer.

## Q3 — "Can you write up an ADR for a decision using our template?"

**Baseline**: Answered as if `docs/decisions/TEMPLATE-madr.md` were a known, resolvable path —
referenced "the MADR template" confidently and produced a plausible ADR structure (status,
context, decision, consequences) without checking whether that specific file exists in this
checkout.

**With-skill**: Checked first and found `docs/decisions/TEMPLATE-madr.md` — the exact path named
in `AGENTS.md`'s "Writing a new decision record (ADR)" section — does not actually exist in this
repo; `docs/decisions/` contains only `EXAMPLE-ADR-001-model-router-cloud-escalation-degrade-
chain.md` (a real worked example, MADR 4.0.0 shape) and one unrelated file
(`SD-meilisearch-vs-paradedb.md`). Said so plainly rather than citing the missing path as if it
resolved, and used the worked example's actual shape (front matter with status/date/decision-
makers/consulted/informed, then Context and Problem Statement / Decision Drivers / Considered
Options / Decision Outcome / Consequences / Confirmation / More Information) as the template to
follow instead, noting explicitly that this is "the shape of the one real example, not a
template file that exists at the path the repo's own docs point to."

**Verdict: with-skill better**, on a smaller but genuine finding. `AGENTS.md` — a file this
skill's own "Before answering" section instructs grounding in — points to a template file that
was independently confirmed (via `Glob docs/decisions/*`) not to exist. A baseline response has no
reason to catch this: it read as confident and correct without ever being checked. The with-skill
run's disclosure is a direct instance of the skill's explicit instruction to say when a named path
"doesn't resolve" rather than presenting it with unearned confidence — this is a real, if narrow,
documentation gap in the repo itself (`AGENTS.md` and `TEMPLATE-madr.md` are out of sync), not a
skill defect, but the with-skill run is the one that actually surfaces it to whoever needs to
write the next ADR.

## Overall

3/3 with-skill responses graded better than baseline, and the margin is unusually large for Q1
and Q2 specifically: both are cases where the baseline response would have shipped something
actively wrong (a manual edit to a regenerated file; a redundant fix on top of an already-working
one) rather than merely being less thorough. All three findings are grounded in files read
directly during this eval, not summarized secondhand from `AGENTS.md` or the ADR doc's own
framing — the `seed_source_registry.py` docstring/dedupe-guard, the model-router's live
`_resolve_cloud_escalation()` code, and the actual `docs/decisions/` directory listing. No re-run
needed — ship as-is.

One thing worth flagging as a live gap, not fixed by writing this skill: as of 2026-09-15, all of
this specialist's directly-associated knowledge packs except `Code-Review-Checklist.md` are
one-line stubs (`specialists/knowledge-packs/Python-Coding-Standards.md`,
`Git-Workflow-Standard.md`, `Development-Lifecycle.md`, `Bug-Fix-Framework.md`,
`Refactoring-Framework.md`, `Coder-Agent-Knowledge.md` — each a title and a single sentence, no
worked content). This skill fills that gap with real repo conventions found elsewhere
(`Repository-Governance-Standard.md`, the PR template, `AGENTS.md`) rather than inventing a
standard from nothing, but the underlying knowledge packs themselves remain unwritten — a
follow-up for whoever owns that backlog, not something this skill build can close on its own.
