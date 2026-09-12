# Lessons Learned

Generated from the structured knowledge records under `knowledge/missions/*-knowledge-record.md` — each mission's own `## Lesson` / `## Future Guidance` sections, indexed by the `LL-NNN` ID it was minted with. Parsed by `core/knowledge/lessons_analyser.py`.

**Note:** the following lessons were independently minted with the same `LL-149` ID (no shared counter across missions — the same class of ID-minting drift already flagged for mission IDs in `knowledge/missions/MSN-0363-content-workbench-comms-002-uplift.md`). Kept the first as `LL-149`; reassigned the rest to the next free IDs:
- `BROWSER-USE-OSINT-ADAPTER-20260912-knowledge-record.md`: `LL-149` → `LL-155`
- `FND-001-MODEL-ROUTER-ESCALATION-HARDENING-20260912-knowledge-record.md`: `LL-149` → `LL-156`

---
## LL-136
### Title
A grep for one variable name undercounts real adoption of a pattern
### Date
2026-09-08
### Lesson
A single-string grep for a specific variable name is not evidence of absence — it only proves that name is absent, not that the underlying capability is. Before proposing a multi-file fix based on a grep, read the actual components; the grep undercounted 6 of 7 "gaps" as already correctly handled under different names (error, apiError, loadFailed).
### Future Guidance
When a mission asks "does every page do X", verify by reading the code, not by grepping for the one name you expect X to use — naming drift across a codebase this size is the norm, not the exception. Confirmed dominant convention going forward: loadError (string | null) for page/component-level load state; per-signal xError names are fine when a component genuinely combines multiple independent data sources.
---
## LL-137
### Title
A PR template alone does not reach auto-generated PRs
### Date
2026-09-08
### Lesson
Adding a PR template is necessary but not sufficient for "used as part of every PR" — any code path that opens a PR via the API with an explicit body bypasses it silently, with no error or warning. Auto-generated/bot PRs are exactly the kind most likely to need review scrutiny and least likely to get it if the checklist only lives in a template nobody's code path reads.
### Future Guidance
When wiring a process doc into "every PR", grep for every code path that calls a PR-creation API with an explicit body — a repo-level template is a good default but is invisible to anything that doesn't go through GitHub's own no-body-specified path.
---
## LL-138
### Title
A shared-vocabulary grouping can hide a real one-sided opportunity behind a fake three-way conflict
### Date
2026-09-08
### Lesson
Grouping technical debt by shared vocabulary ("these all have Task/Queue in the name") rather than verified function produces a false N-way-conflict framing that obscures the real, much smaller finding: one file was genuinely obsolete (safe to delete, zero risk), and one file was a completely different, working, tested capability that nobody had ever wired up — a missed-opportunity bug, not consolidation debt. The "3 variants, low urgency, not worth it" framing nearly caused a live, valuable capability to keep sitting unused indefinitely under the "not urgent" label a genuinely dead file deserved.
### Future Guidance
When technical debt is framed as "N variants of the same thing," verify each one's actual data model and real callers before accepting the grouping — a pattern match on class/field names is not evidence of functional overlap. Treat "well-built, tested, zero callers" as a wiring bug to fix, not consolidation debt to defer — the fix is usually cheaper than the discovery that found it.
---
## LL-139
### Title
Removing a dead integration surfaces its own orphaned dependents, and app.py's removal doesn't imply theirs
### Date
2026-09-08
### Lesson
Deleting platform-runtime/app.py (the Slack Bolt process) as directed left a whole cluster of modules with zero live callers: the Commander brain stack (commander_runtime.py etc.), the entire ~20-module platform-runtime/commands/ slash-command surface, and captains_inbox_capture.py's pipeline. All were only ever reachable through app.py's dispatch table. The instinct to also delete these because 'nothing calls them now' would have been wrong twice over: (1) most were never Slack-specific themselves, just Slack-dispatched — deleting them would destroy working, reusable logic over a removed transport, not removed functionality; (2) they were already unreachable in production before this change, since the Captain had already disabled Slack — the code cleanup just made that existing reality visible in the repo rather than creating it.
### Future Guidance
When removing a transport/integration's entry point, distinguish 'coupled to the transport itself' (imports the SDK, calls its API directly — delete or rewire) from 'only ever invoked through that transport's dispatch table' (generic logic that happens to have had one caller — keep, and flag the now-orphaned capability for a deliberate revive-or-retire decision rather than silently deleting or silently leaving it undocumented). Verify each file's actual imports and callers before batch-deleting anything that merely mentions the removed system's name.
---
## LL-140
### Title
A "simple" scoped item can still surface a real, unrelated bug in the very tests meant to prove it safe
### Date
2026-09-08
### Lesson
Both candidates A and B were deliberately picked as "easy" — small, unblocked, reusing already-tested functions rather than new logic. Re-running the full test suite before pushing (not just the new tests) caught a real, unrelated failure anyway: Missions/Engineering-Handoffs/ had gained real content on main via a concurrent session's PR while this work was in progress, and several pre-existing tests in test_number_one_brief.py were not actually hermetic against that — they patched _load_missions but not load_engineering_handoffs, so real handoff files with real PR URLs started leaking into supposedly-isolated unit tests and making live GitHub API calls. "Small and safe" work is not a reason to skip the full local test run before pushing — the size of a change and the size of what a full test run can catch are unrelated.
### Future Guidance
Always run the FULL relevant test suite before pushing, not just tests for the lines you touched — real repo state (file corpus, concurrent sessions' work landing on main) can silently invalidate a test's isolation assumptions between one run and the next, and the cheapest time to catch that is your own pre-push check, not CI or a future session.
---
## LL-135
### Title
A metric's denominator must be discovered with the same scope as its numerator
### Date
2026-09-08
### Lesson
Two counts meant to be compared (or where one is meant to be a subset of the other) must be discovered with matching scope and matching directory-exclusion rules, or they silently drift apart and any consumer trusting both numbers together draws a wrong conclusion. Same defect class as the vendored-directory exclusion bug already fixed for _count_python_files()/_find_todos() (2026-08) — the fix pattern (shared prune-args helper) existed but was never applied to _find_test_files().
### Future Guidance
When a self-improvement/audit collector adds a new file-discovery method, default it to the same shared prune/scope helper the rest of the collector already uses rather than a fresh ad hoc glob() — and pair any two counts meant to be compared with a reconciliation assertion in tests, not just a non-emptiness check.
---
## LL-134
### Title
Retire duplicate config formats immediately, not just fix the loader bug
### Date
2026-09-08
### Lesson
A loader bug caused by "which of two config files wins" is a symptom; leaving both files in place after fixing the loader just re-arms the same class of bug for the next person who edits the wrong one.
### Future Guidance
When investigating a "which file is actually read" bug, check for a duplicate/shadow config file as part of the fix, not just the code path that reads it — and require the fix to name a single canonical source.
---
## LL-143
### Title
"Quarantined, not deleted" needs an expiry, or the quarantine never ends
### Date
2026-09-10
### Lesson
Self-improvement's dead-code check flagged `telegram-bot.DEPRECATED-2026-07-12/` (2 months stale) and its own auto-remediation explicitly declined to delete it ("code deletions require manual review") — correctly conservative, but nothing then routed that manual-review request to a human or follow-up mission. It sat flagged-but-untouched for at least two more cycles. `self-improving-loop.DEPRECATED-2026-07-29/` was never flagged at all despite matching the identical pattern (quarantined directory, past its own stated recovery window, zero live references) — the dead-code check evidently isn't re-scanning directories it has no memory of having quarantined, only ones matching its live detection heuristics on that run.
### Future Guidance
A directory renamed to `*.DEPRECATED-<date>/` as a deliberate "recovery window, not permanent" convention needs either an actual expiry (a follow-up mission auto-created N weeks out) or a periodic sweep that lists every `*.DEPRECATED-*` directory in the tree and checks it against today's date — otherwise the convention silently degrades into permanent dead weight, discovered only by chance during an unrelated audit. When auto-remediation declines a finding as "needs manual review," that decline should itself be visible somewhere a human will actually see it (a handoff, a digest, a recurring reminder) rather than only living in `remediation_results.jsonl`.
---
## LL-141
### Title
A fallback guard added to one task type must be audited across every sibling task type
### Date
2026-09-10
### Lesson
PR #87 (merged 2026-09-08) bumped `MODEL_CLOUD` to `glm-5.3:cloud` and added an availability-fallback guard for `escalate` and `engineering-review` — but not `fallback-complex`, a third task type routed to the same unverified model, live in the same file, in the same function. PR #87's own description flagged the model tag as unverified. The gap sat for two days and two self-improvement cycles (both correctly classified `needs_signoff`, so auto-remediation never touched it) before a human-driven fix closed it.
### Future Guidance
When adding an availability/fallback guard because a model tag is unverified or newly introduced, grep the same file for every other task type routed to that model tag and guard all of them in the same PR — not just the one task type that prompted the change. A partial fix for a shared-risk config value is a latent recurrence, not a closed finding; self-improvement will keep re-flagging it every cycle until every sibling is covered.
---
## LL-142
### Title
A system that writes to its own working tree outside of commits will eventually block its own deploy pipeline
### Date
2026-09-10
### Lesson
None of the three auto-generated handoffs for this finding (SD-FND-003 and its two MSN-1788922470456 duplicates) resulted in a batch-coded PR being opened — all three logged "no PR opened (GitHub not configured or no new files to add)". The fix that actually landed was authored independently, outside the auto-dispatch pipeline, days after the findings were first raised. The auto-dispatch path silently produced nothing actionable three times over for the same real, conclusive-evidence finding, and nothing surfaced that failure loudly enough to prompt a human or a differently-routed fix sooner.
### Future Guidance
A live-mutated state file living inside a git-tracked directory is a recurring category, not a one-off: any new per-cycle counter, lock, or live-decision file a background process writes should be `.gitignore`d at the moment it's introduced, not discovered after it blocks a deploy. Separately, when an auto-dispatch handoff's batch result says "no PR opened," that is itself a signal worth escalating (or re-attempting via a different path) rather than leaving the handoff sitting at `DELIVERED` indefinitely — three consecutive dispatches producing no PR for the same finding should have triggered a fallback, not a fourth identical dispatch.
---
## LL-149
### Title
LL-146's diagnosed-but-unfixed root cause is fixed: git_commit() fails closed on branch mismatch and pushes on success
### Date
2026-09-12
### Lesson
Diagnosing a bug and writing it up (LL-146) is not the same as it being
fixed — a knowledge record that says "not fixed here" needs a tracked
follow-up or it can sit indefinitely while the underlying automation keeps
producing the exact failure mode already documented. This record closes
that loop explicitly rather than leaving LL-146 as a dangling diagnosis.
### Future Guidance
Before any daily/scheduled write-job's commit method ships, ask two
questions LL-146 and this fix both had to answer the hard way: (1) does it
verify *which* branch it's about to commit to, or does it trust whatever
happens to be checked out at fire time; (2) does it push, or does it leave a
local-only commit that `origin` never sees. A scheduled job sharing a
working tree with interactive/human use is the specific shape of risk here
— isolating its target branch (as done here) is one fix; giving it a
dedicated worktree/clone it owns exclusively (LL-146's other suggested
direction) is the other, not yet taken.
---
## LL-155
### Title
A hard-pinned dependency required isolating a whole venv, and the recommended PoC source turned out unreachable from this host
### Date
2026-09-12
### Lesson
A library that wraps another tool (browser-use wraps Playwright/CDP) can
still bring its own hard dependency graph, and that graph is invisible
until you actually run `pip install` — the task's own instruction to
"confirm which Chromium build it needs... before installing a second one"
correctly anticipated the *browser binary* question but not the *Python
package* question, which turned out to be the actually dangerous one here.
Anything installed into a shared venv should be assumed to have this risk
until checked, especially late in a multi-task session where earlier tasks
already made that venv load-bearing for something new.

Separately: an audit or task-brief's specific example ("use this source as
your PoC") is a suggestion informed by evidence gathered at some earlier
point, not a guarantee the example still holds — network reachability from
a specific host is exactly the kind of fact that can change (or never have
been true from *this* host) without anyone noticing until someone actually
tries it.
### Future Guidance
Before installing any new pip package into `platform-runtime/.venv`
specifically (the platform's one shared, load-bearing venv), check its
declared dependencies for pinned (`==`) versions of anything already used
elsewhere in the platform (`anthropic`, `google-genai`, `openai`,
`mistralai` are the ones that matter most here, per today's session alone)
before running the install — a `pip download --no-deps` or reading the
package's own metadata first is cheap; reverting a silent platform-wide
downgrade after the fact is not guaranteed to be caught immediately by
whoever hits it next.
---
## LL-150
### Title
context-service's own code acknowledged it was running the dev server in production; now runs gunicorn
### Date
2026-09-12
### Lesson
A code comment admitting "this isn't a production server" is a known-debt
marker that's easy to walk past once a service is live and stable — nothing
forces revisiting it until load actually breaks it. This capability sat on
the dev server in production for long enough that a specific concurrency
concern (`/brief/evolved`'s long-running LLM calls) had already been solved
around the dev server's own limitation (`threaded=True`) rather than by
fixing the underlying gap.
### Future Guidance
**Required VM step, not automatic:** `pip install -r
platform-runtime/requirements.txt` in the service's venv (installs
gunicorn), `systemctl daemon-reload` (picks up the new `ExecStart`),
`systemctl restart context-service`, then `systemctl status
context-service` — confirm it shows a gunicorn master + `gthread` worker
process tree, not a bare `python3 ... context_service.py serve` process,
and that `/health` (direct and through Caddy) still returns 200. This
cannot be verified from a build sandbox; it is real production risk until
someone with VM access runs it.
---
## LL-148
### Title
The audit's P1 ("quality scoring dead") was half-solved and silently broken the other half
### Date
2026-09-12
### Lesson
"No LLM output is scored in production" and "the scoring code has no
caller" are different claims, and a fix aimed at the wrong one can look
complete while changing nothing observable. The audit's stated symptom
(`quality_scoring_service=None` default) was real but pointed at
`outcome_capture_service.py`'s optional-injection contract, not at
`score_output()`'s actual, more specific problem: a real function with a
default judge-model configuration that silently produces `None` on every
call, forever, with no distinguishing signal from "not called yet."
### Future Guidance
Any `except Exception: return None` (or equivalent silent-degrade) path
around an external judge/LLM call is invisible to normal testing unless a
test specifically asserts the *configuration* reaches the external call
correctly — not just that the function doesn't crash. `test_score_output_wires_model_router_judge_not_default`
exists specifically to catch a regression class that would otherwise
reintroduce this exact bug (someone removing the explicit `model=` kwarg
in a future refactor) without any test going red until someone notices the
scores are suspiciously always identical or always `None` in production.
---
## LL-153
### Title
Dependabot wired across all 10 requirements.txt directories (not 9, as originally briefed) plus lcars-portal npm and github-actions; Scorecard added from OpenSSF's live template
### Date
2026-09-12
### Lesson
A mission brief's stated counts (here, "nine" requirements.txt files) are a
starting hypothesis, not ground truth — re-verifying against the actual
repo state before finalizing a config caught a real discrepancy that would
otherwise have silently under-covered the platform's dependency surface by
one directory.
### Future Guidance
Dependabot's first PR and Scorecard's first score should appear in the
repo's Security tab within 24h of this merge — that needs to be checked on
GitHub directly; it isn't verifiable from a build sandbox. If a new
directory ever gains its own `requirements.txt`, `dependabot.yml` needs a
matching new `pip` entry by hand — nothing here auto-discovers new
directories.
---
## LL-156
### Title
Cloud-unavailability guard existed and worked correctly; its only fallback was itself unsafe on this host
### Date
2026-09-12
### Lesson
**A working availability guard and a safe fallback destination are two
different things, and detecting the first does not prove the second.** This
guard never failed at its actual job — it correctly identified unavailability
on every single call for four days straight. The bug was a design gap one
layer past the guard: nothing evaluated whether the fallback it reached for
was itself appropriate for automatic, unattended use. A model can be
completely legitimate as a *deliberate* capability (scheduled, cost-budgeted,
someone accepted its latency explicitly) while being categorically wrong as
an *automatic* one (silently substituted, no one budgeted for its cost, and
the caller has no idea a degrade even happened until it times out).
### Future Guidance
Whenever a routing/fallback chain has exactly one degrade step, treat that
as a design smell, not a design decision — ask explicitly whether the
fallback destination is safe to select *automatically*, independent of
whether the primary-unavailability detection itself is correct. A resource-
constrained host (no GPU, few cores, no request parallelism) makes this
sharper: a model choice that's fine for a human-approved, scheduled job can
be actively dangerous as something a health check reaches for on its own.
Make the degrade path multi-tier (cheap/fast options before anything heavy),
make the tier that actually served a request observable in logs and
responses (not just the model name), and write the regression test as an
invariant over *every* availability state, not just the one state that
happened to be observed failing — that's what catches a future variant of
this same class of bug in a different task type before it needs its own
incident.

Also: self-improvement detected this finding correctly, twice, and both
times it was rediscovered on a later cycle without ever becoming a fixed
issue — see the separate follow-up finding on the missing
DETECTED→...→CLOSED lifecycle for repeated HIGH findings
([[fnd001-self-improvement-remediation-lifecycle-gap-20260912]]).
---
## LL-151
### Title
garak wired as a pre-activation vulnerability gate; GAP 1's other half (deepeval) already merged via PR #114
### Date
2026-09-12
### Lesson
A gate that has only ever been exercised against a target it can't reach
proves its own wiring is correct but says nothing about what it will
actually find on the real system. That gap is real here and is called out
explicitly rather than implied by "tests pass."
### Future Guidance
**Required VM step, not automatic:** run `python3 core/quality/garak_gate.py`
(no flags) against the actually-running Model Router at `127.0.0.1:8891` to
get a first true pass/fail verdict. Nothing currently wires this gate into
any activation/deploy flow — it is a standalone script today, not an
enforced check (see the new Observability capability record in the SUOC
Platform Registry, added this pass, for the broader tracking of this gap).
Also gitignore `reports/garak/` (added this pass, PR #172) — both this gate
and the pre-existing `tools/garak_sweep.sh` write timestamped reports there,
and neither path had ever been excluded from git.
---
## LL-144
### Title
Opportunities can go stale or duplicate in the gap between classification and human review
### Date
2026-09-12
### Lesson
A finding or candidate's evidence is a snapshot taken at classification time.
Nothing re-checks that snapshot against reality again until either an
overnight re-run happens to notice, or (until this fix) never at all for a
brand-new candidate about to be minted. The gap between "HQ observed X" and
"a human looks at the resulting card" is where staleness and duplication both
live — not in the observation itself, which was usually correct at the time.
### Future Guidance
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
---
## LL-146
### Title
hq-evolution.timer's cycle-artifact commit never pushes, so it silently pollutes any branch checked out at 03:00
### Date
2026-09-12
### Lesson
A scheduled job that commits to a shared, interactively-used working tree
without also pushing creates commits that are invisible to `origin` but
still fully "real" to any local branch built from that tree afterward. The
bug doesn't announce itself at commit time — `git status` after the timer
fires looks clean, because the commit succeeded. It only surfaces much
later, on a completely unrelated PR, as a confusing diff that looks like the
PR's author changed files they never touched.
### Future Guidance
Before cutting any new branch on a VM that also runs scheduled write-jobs
against the live working tree, run `git fetch origin` and branch from
`origin/main`, never from local `main` directly — local `main` can be
silently ahead of `origin/main` with commits a background job made and never
pushed. `git log --oneline origin/main..main` is the fast way to check
whether local main carries any such orphan commits before trusting it as a
base. If a PR's diff shows files nobody touched, especially files owned by
another automated process (self-improvement artifacts, generated reports,
timer output), suspect this pattern first rather than assuming a merge
mistake in the PR's own history — rebasing/cherry-picking the real commit(s)
onto a branch cut from `origin/main` is the fix, not manually reverting the
unrelated files forward.
---
## LL-147
### Title
The audit's "unexecuted" item was already executed — the real gap was one caller short
### Date
2026-09-12
### Lesson
A gap-closure audit document is a snapshot, not a live index. Three weeks
is enough time for the two items an audit called "unexecuted" to become
fully executed and merged, while a third fact the same audit relied on
(the temporal tables existing at all) becomes false in the other
direction. Re-deriving a plan from an audit doc without first grepping for
whether its premises still hold risks either redoing already-shipped work
or building toward a target that no longer exists.
### Future Guidance
Before executing any "wire X into Y" instruction sourced from a dated audit
or backlog document, grep for X's actual current caller count and check
recent migration/commit history for whatever Y names as its target — both
took under an hour here and changed the scope of the task from "build two
integrations" to "add one caller and two docstring fixes." The cost of
checking is small relative to the cost of either duplicating merged work or
writing against a schema that's already gone.
---
## LL-145
### Title
The stated gap ("no systemd unit") was real but not the whole story
### Date
2026-09-12
### Lesson
A gap-solutions audit that names one visible symptom ("nothing is
listening on the collector's port") can be correct about that symptom
while still describing an incomplete fix — a second, silent failure one
layer upstream (every producer's own import of the tracing helper) meant
the collector could have been running for weeks with zero data ever
reaching it. Both failures shared the same shape: a `try/except Exception:
pass`/`return` guard with no log line on the failure path, which is
exactly the design that makes "confirm the write-up's own root cause
before implementing its fix" worth doing even when the write-up looks
complete and the constraints explicitly say not to touch the producers.
### Future Guidance
Any cross-cutting `try/except Exception` around an optional feature (here:
`configure_tracing()`'s import guard, repeated identically at all 7 call
sites) should log the swallowed exception at least once, even as a
one-line WARNING — "tracing unavailable: <reason>" would have surfaced
this exact `ModuleNotFoundError` for months instead of it being
indistinguishable from "packages intentionally absent." Silence on a
guarded failure path is cheap to add and is the only way to tell
"working as designed" apart from "broken since the last unrelated
directory rename."
---
## LL-152
### Title
Pre-commit config added; detect-secrets and an independent gitleaks scan both flagged the same real-looking Supabase service_role key, left deliberately unbaselined
### Date
2026-09-12
### Lesson
A pre-commit gate's first real run against an existing 930-file monorepo
will surface a large, mostly-noise finding count (9,656 combined here) —
that volume is exactly why triage discipline matters: burying one real
credential inside thousands of false positives, or baselining everything to
get a clean run, would have been strictly worse than shipping a config that
fails on purpose until a human acts.
### Future Guidance
**Required action, not automatic, and not something this pass can do:**
someone with Supabase project access must rotate the `service_role` key for
project `cjvrpjwewsrumnbdydgg`, then replace the hardcoded value in
`lcars-portal/deploy-phase-1b.js` with an environment variable or secret-manager
reference. Once done, either the line will no longer match detect-secrets'
pattern, or a follow-up can explicitly baseline the now-rotated, dead value.

**Required VM/contributor step, not automatic:** this config only takes
effect once each contributor runs `pip install pre-commit && pre-commit
install` in their own local checkout — nothing in CI enforces it yet. A
`pre-commit run --all-files` CI job (running once the credential above is
resolved and Ruff/Bandit findings are triaged) would be a reasonable
separate follow-up for server-side enforcement.

**Cross-worktree gotcha discovered while merging other streams this
mission:** `pre-commit install` writes to `.git/hooks/pre-commit`, which git
worktrees share via the common `.git` directory — installing it in one
worktree makes every other worktree of the same repo start requiring
`.pre-commit-config.yaml` on whatever branch they're checked out on, even
before this PR merges to `main`. `PRE_COMMIT_ALLOW_NO_CONFIG=1` is
pre-commit's own documented escape for exactly this situation (a branch
that genuinely doesn't have the config yet) and was used to complete
unrelated merge commits during this mission without disabling the hook.
---
## LL-154
### Title
First Python pytest/lint CI for this repo; also surfaced a pre-existing test file whose assertions can never fail
### Date
2026-09-12
### Lesson
A CI pipeline that runs `pytest` isn't automatically a gate — if the
underlying test file can't fail, the pipeline will report green forever
regardless of what breaks. Proving the new gate "gates" (the break-then-
revert exercise the mission brief required) is what caught this, not code
review of the workflow YAML itself.
### Future Guidance
`telegram-bots/xo/test_voice_capture.py`'s `check()` pattern should be
converted to real assertions before anyone relies on that specific test
file's pass/fail signal from this new CI pipeline — as written, it cannot
currently report a regression. More broadly: any test file using a
print-based "check" helper instead of `assert`/`self.assertX` anywhere else
in this repo carries the same risk and is worth a targeted audit now that
CI will actually run and report on all of them.
---
