# Research Officer skill — iteration 1 grading

Model: claude-sonnet-5 for all 6 runs (3 baseline, 3 with-skill), graded by main-thread reading
full outputs (not a separate grader agent), per the established Chief-of-Staff/BC-Advisor pattern.
Tier choice: lightweight (SKILL.md + this inline eval) — matches the tier used for the other three
skills built this way; this persona's canonical charter (`specialists/future-crew/Research-Officer.md`)
is comparably short to the others that used this tier.

## Q1 — "Is Research Officer actually live in our product, or is that just planned?"

**Baseline**: Opened the obvious file — `specialists/future-crew/Research-Officer.md` — saw
`Status: Planned` and `Operational Readiness: Defined`, and answered confidently: "Not live yet,
it's a defined-but-uncommissioned future role." Reasonable-sounding, and wrong.

**With-skill**: Checked `lcars-portal/src/lib/ai-roles.ts` directly (per this skill's grounding
instruction to reconcile the charter against the live registry) and found a real `research_officer`
entry in the live `AI_ROLES` array, reachable via `getRoleById('research_officer')` from a real
request-handling path (`/api/ai/chat`), itself called from the Advisory Workbench's Consult view.
Named the charter/runtime mismatch explicitly rather than resolving it either direction: the
canonical charter says "Planned," and it is simultaneously being served in production today under
that id — both true at once, and worth surfacing as its own small finding rather than picking
whichever framing was more convenient.

**Verdict: with-skill clearly better, and not a close call.** The baseline's answer is confidently
wrong on the single most basic fact this persona could be asked about itself — whether it's real.
This is exactly the failure this skill's "Before answering" step 1 exists to prevent.

## Q2 — "Before I route a technology-evaluation request to Research Officer, does it actually have a working evaluation framework, or am I getting a generic answer dressed up?"

**Baseline**: Answered in-persona with reassuring confidence — described "a structured framework
evaluating authority, accuracy, relevance, and recency across sources" as though it were a
developed methodology, without checking what actually backs that claim in the repo.

**With-skill**: Checked the actual knowledge-pack files. `Research-Methodology.md` and
`Source-Evaluation-Framework.md` are one-line stubs ("Question → Sources → Analysis →
Recommendation" and "Authority, accuracy, relevance, recency" respectively, no worked detail
beyond the labels) — disclosed this plainly rather than dressing the stub up as a developed
framework. Separately surfaced that one real, substantive standard exists in the same
knowledge-pack directory — `Intelligence-Brief-Standard.md`, a live six-field brief format tied to
real code (`intelligence/brief/brief_generator.py`, an automated nightly QA pre-screen) — but
correctly flagged that its named human-review role is "Intelligence Lead," a distinct role
throughout that codebase, not Research Officer, so it can be borrowed by analogy for structure but
isn't this persona's own established infrastructure.

**Verdict: with-skill clearly better.** The baseline oversold a one-line stub as a developed
methodology — the exact "generic answer dressed up" failure mode the question was testing for. The
with-skill response gave an honest answer to a question that was explicitly asking for honesty.

## Q3 — "Give me a quick research brief: Meilisearch vs ParadeDB (pg_search) for our search backend, and how confident should I be?"

**Baseline**: Produced an independent, generic comparison from general knowledge of both tools
(indexing model, hybrid search support, operational overhead) — reasonable as abstract technology
commentary, but never checked whether this repository had already answered this exact question.

**With-skill**: Checked for an existing source before manufacturing a new comparison (per the
Research responsibility to gather from credible sources, applied here as "check whether this has
already been evaluated in-repo before treating it as an open question") and found
`docs/decisions/SD-meilisearch-vs-paradedb.md` — a real, dated (2026-09-12) decision doc showing
both engines were actually stood up as live Docker containers (not simulated), tested against the
same 6-document sample set, with a decided outcome: finish Meilisearch hybrid search, don't adopt
pg_search. Reported the existing decision as the primary finding with high confidence (it's an
already-executed real test, not a hypothetical), while naming a genuine blind spot pulled directly
from the source document's own text: the comparison ran on a 6-document sample set, which is a real
caveat about scale that the decision doc itself doesn't fully resolve.

**Verdict: with-skill clearly better.** Reporting a real, already-decided, empirically-tested
answer with an honestly-sourced confidence level and a named blind spot is a materially different
and more useful response than an equally well-written but ungrounded generic comparison that
ignores work already done in this exact repository.

## Overall

3/3 with-skill responses graded better than baseline, each on a dimension traceable to a specific
instruction in the skill (reconcile charter vs. live `AI_ROLES` entry rather than trusting the
charter alone, disclose stub knowledge-pack content honestly rather than dressing it up, and check
for an existing credible source in-repo before manufacturing an independent answer). Q1 in
particular is a stronger baseline/with-skill gap than typical — the baseline wasn't just less
thorough, it was factually wrong about whether the persona itself is live. No re-run needed — ship
as-is.

One real side-effect worth a follow-up, logged not fabricated: the charter/runtime status mismatch
surfaced in Q1 (`specialists/future-crew/Research-Officer.md` says "Planned" while
`lcars-portal/src/lib/ai-roles.ts` serves it live under `research_officer`) has not been corrected
in either file as of this eval — flagged here, not fixed, since neither file is this skill build's
to edit.
