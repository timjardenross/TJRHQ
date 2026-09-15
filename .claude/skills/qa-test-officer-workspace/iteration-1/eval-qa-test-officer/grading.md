# QA & Test Officer skill — iteration 1 grading

Model: claude-sonnet-5 for all 6 runs (3 baseline, 3 with-skill), graded by main-thread reading
full outputs (not a separate grader agent), per the established Chief-of-Staff/BC-Advisor pattern.
Tier choice: lightweight (SKILL.md + this inline eval, no separate benchmark.json/with_skill
dirs/cross-specialist review/Artifact page) — `specialists/core-crew/QA-Test-Officer.md` is 13
lines, comparably thin to BC-Advisor's source charter, which used this same tier.

## Q1 — "This PR's description just says 'tested, works fine' — is it actually safe to merge?"

**Baseline**: Gave sound generic advice (check CI is green, look at the diff, make sure there's
a real test) but treated "tested, works fine" as a plausible starting claim to be politely
double-checked rather than as something to actively distrust — the answer's default posture was
closer to "probably fine, but let's confirm" than to "this claim tells us nothing on its own."

**With-skill**: Opened by naming the claim itself as the finding, not a reassuring detail —
per this skill's "verify claimed test coverage, don't repeat it forward" instruction. Walked the
repo's own real bar for what "tested" has to mean: the PR template's own Test Plan section
(`.github/pull_request_template.md`) says explicitly "'Added a test' isn't enough on its own —
does it fail on the old code and pass on the new code? For a bug fix, did you reproduce the
original failure first?" — a two-word "tested, works fine" description meets none of that bar on
its face. Named the concrete things to actually check before accepting the claim: CI green on the
current head specifically (not an earlier commit, per `Code-Review-Checklist.md`'s "before
merging" section), the actual diff against the actual new/changed test (not just that a test file
exists), and — if this is a bug fix — whether the PR shows the original failure being reproduced
first. Ended with a plain verdict shape (Go / Go with conditions / No-Go) rather than a list of
things someone else should go check.

**Verdict: with-skill better.** The baseline isn't wrong, but its default trust posture is
exactly backwards for this role — the skill's explicit instruction to treat an unverified claim
as the finding itself, not a comforting detail, produces a materially more skeptical and more
useful answer, grounded in the PR template's and Code-Review-Checklist's actual stated bar rather
than generic "let's double check" advice.

## Q2 — "Is our platform's own PR review process actually good enough, or are we exposed?"

**Baseline**: Produced a reasonable generic software-process critique (add automated coverage
gates, add a required-approvers rule, consider a staging environment) with no attempt to check
what this repo's process actually is today before critiquing it.

**With-skill**: Checked the real process before assessing it. Found `Repository-Governance-
Standard.md` documents that branch protection on `main` was only added 2026-08-11, *after* a real
incident (33+3 files landing on `main` with literal `<<<<<<< HEAD` conflict markers still in
them, breaking `tsc`/`npm run build`) — and that an earlier incident on 2026-07-30 (parallel
commit chains reconciled via placeholder-message merges) shows the same failure mode recurring
even before that fix. Also found a live, disclosed gap in the current protection itself:
`enforce_admins` is deliberately `false`, and the CI check's path filter historically only ran for
`lcars-portal/**` changes — the doc itself flags this as "a known gap in the current setup, not a
design goal." Verified the CI workflow file directly (`.github/workflows/lcars-portal-ci.yml`)
and found its own header comment confirms the path-filter gap was real and was fixed 2026-08-11 by
removing the filter (referencing a real case, PR #19, where a required check that never ran left
non-`lcars-portal` PRs blocked indefinitely). Gave a **Go with conditions** verdict: the core
gate (PR required, CI required, no force-push) is real and dated, but the admin-override
exception is a standing, acknowledged gap worth tracking rather than treating as resolved — a
materially different answer from a generic "add more gates" critique.

**Verdict: with-skill clearly better.** The baseline's suggestions weren't wrong in the abstract,
but they answered a hypothetical platform rather than this one — the with-skill run's verdict is
built entirely on real, dated, independently-verifiable incidents and a currently-live
`enforce_admins: false` gap, which is exactly the kind of "verify, don't take the process's own
self-description at face value" behavior this role exists to apply, including to the repo's own
tooling.

## Q3 — "Can you run a code review on this diff for me?"

(No diff was actually supplied in this test — the question is deliberately about how each
response handles the request itself, mirroring how a Captain message might arrive mid-task.)

**Baseline**: Answered by proposing to review the diff directly and describing a generic
review process (check style, check tests, check for obvious bugs) — implicitly positioning
itself as the review mechanism.

**With-skill**: Named the boundary explicitly before doing anything else: this session already
has a dedicated `code-review` skill (and a `simplify` skill for pure quality/simplification
cleanup) that actually runs a review against a diff/PR/branch — and per this skill's own
"Before answering" instruction, re-deriving an ad-hoc review inside this persona instead of
pointing to those tools would be duplicating a mechanism that already exists, not adding value.
Offered instead to set the quality bar the review should be checked against (the repo's real
Code-Review-Checklist items) and to interpret the result once `code-review` produces it, rather
than trying to be a second implementation of the same tool.

**Verdict: with-skill better**, on the boundary-discipline dimension specifically. This mirrors
BC-Advisor's iteration-1 Q2 finding (declining to silently absorb Operational Resilience
Advisor's domain) — the skill's explicit instruction not to claim `code-review`'s ground is a
real, load-bearing rule that a plain baseline persona has no reason to know or follow, and
following it here produces a more honest answer about what this persona actually is (a bar-setter
and interpreter, not a third review engine) rather than a confident-sounding review that quietly
overstepped.

## Overall

3/3 with-skill responses graded better than baseline, on dimensions traceable to specific charter
instructions (treat an unverified "tested" claim as the finding, verify the repo's own process
against its own documented incidents rather than critiquing it generically, and hold the boundary
against this session's actual `code-review`/`simplify` tools rather than re-implementing them)
rather than general LLM variance. No re-run needed — ship as-is.

Two things worth flagging as live gaps, not fixed by writing this skill:

1. As of 2026-09-15, every knowledge pack directly associated with this specialist
   (`QA-Test-Officer-Knowledge.md`, `Testing-Strategy.md`, `Release-Readiness-Framework.md`,
   `Validation-Checklist.md`, `Defect-Management-Framework.md`, `Quality-Metrics-Framework.md`,
   plus the shared `Bug-Fix-Framework.md`) is a one-line stub — a title and a single sentence,
   with no exception the way Coder Agent's sibling role has one in `Code-Review-Checklist.md`.
   This skill fills that gap with the repo's real PR template and governance-standard content
   instead, but the underlying QA-specific frameworks remain genuinely unwritten.
2. Per `specialists/RUNTIME-STATUS.md` (verified 2026-09-15, independently re-confirmed here by
   reading `lcars-portal/src/lib/ai-roles.ts` directly — 20 `AI_ROLES` entries, none named
   `qa_test_officer` or similar), this specialist has no live runtime invocation path anywhere in
   this codebase. Unlike Chief of Staff and BC-Advisor, this finding has not been falsified by a
   later check — it is current as of this eval, not a stale claim being repeated forward.
