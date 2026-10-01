# Lessons Learned

Generated from the structured knowledge records under `knowledge/missions/*-knowledge-record.md` — each mission's own `## Lesson` / `## Future Guidance` sections, indexed by the `LL-NNN` ID it was minted with. Parsed by `core/knowledge/lessons_analyser.py`.

**Note:** the following lessons were independently minted with the same `LL-149` ID (no shared counter across missions — the same class of ID-minting drift already flagged for mission IDs in `knowledge/missions/MSN-0363-content-workbench-comms-002-uplift.md`). Kept the first as `LL-149`; reassigned the rest to the next free IDs:
- `BROWSER-USE-OSINT-ADAPTER-20260912-knowledge-record.md`: `LL-149` → `LL-155`
- `FND-001-MODEL-ROUTER-ESCALATION-HARDENING-20260912-knowledge-record.md`: `LL-149` → `LL-156`

**Backfill (2026-10-01):** the register stopped being updated after 2026-09-12. `LL-157`–`LL-164` were already minted in their knowledge records but never added here; they are now, verbatim from each record's `## Lesson` / `## Future Guidance`. `LL-165`–`LL-200` were distilled from 38 knowledge records that never minted an ID (MSN-0368 → MSN-0394, Mission 3, Mission 5, CI performance); each source record now carries its `Lesson` ID. Where several records teach one lesson they share an ID, and a record can cite more than one. MSN-0372 and MSN-0373 carry no date of their own; 2026-09-12 is inferred from their neighbouring missions.

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
## LL-157
### Title
The "814-document backlog" was real but described a different pipeline than the mission brief implied, and Docling's own "CPU-only" pitch turned out to still assume unrestricted internet egress
### Date
2026-09-12
### Lesson
Two things, both only found by actually running the tool against real
files in the real target environment, not by reading its docs:

1. **A task brief's cited number can be real and still describe something
   different from what the plain-English framing implies.** The
   "814-document backlog" is a genuine figure from a genuine audit
   document — but investigating where it actually came from (not just
   trusting the framing) showed it was about this repo's own markdown
   knowledge base, not a queue of raw files waiting on extraction. Building
   against an assumed-but-unverified backlog location would have either
   silently done nothing (no such folder exists) or, worse, been pointed
   at the wrong thing entirely. The mission brief itself anticipated this
   exact possibility and named the honest fallback — worth noting that it
   did, because the investigation step it asked for is what surfaced the
   gap between "described" and "reachable."

2. **"CPU-only" and "no unrestricted internet access needed" are different
   claims, and a library can satisfy the first while quietly assuming the
   second.** Docling's PDF pipeline (`StandardPdfPipeline`)
   unconditionally initialises a HuggingFace-hosted layout-detection
   model in `_init_models()` — regardless of whether OCR or table-
   structure extraction are even enabled — so *every* PDF conversion
   needs a working path to `huggingface.co` on first use, confirmed live
   as a hard `403`/`ProxyError` in this network-restricted sandbox. DOCX
   and HTML needed no such thing (both backends parse the file's own
   structure directly, confirmed working fully offline with real table
   extraction). The fix — retrying a failed PDF conversion with docling's
   own `NativePdfPipeline` (text-layer extraction via pypdfium2, no ML
   model, no network) — recovers real text but not table structure for
   PDFs specifically, a real, disclosed trade-off (`layout_fallback: true`
   in the metadata) rather than a silently-degraded result nobody would
   notice. A tool's "runs on CPU" pitch is about compute, not about
   whether its first run needs a network call to a specific host — those
   are separate facts and only the second one bit here.
### Future Guidance
Before this pipeline is pointed at whatever actually holds the real
814-document backlog: (1) locate where those documents actually live —
this mission could not find a path to them from this repo/sandbox, so
that's still open; (2) decide deliberately, on the host that will
actually run this, whether PDF conversion should pre-warm docling's
HuggingFace model cache (real internet egress, or an internally-mirrored
copy under `artifacts_path`) to get full layout/table-structure detection,
or accept the `NativePdfPipeline` fallback's text-only trade-off for scanned/
complex PDFs — don't let the fallback happen silently by default the way
it would if nobody read this record; (3) wire an actual reviewer surface
for `metadata.review_status = "pending_review"` on `knowledge_documents` —
right now nothing in the LCARS Knowledge Library UI (or anywhere else)
queries for it, so Docling-extracted rows are marked as needing review but
nothing currently surfaces that queue to a human. Separately: any future
`pip install docling` on a fresh host should install the CPU-only torch
wheel first (`pip install torch --index-url https://download.pytorch.org/whl/cpu`)
before installing docling itself — full command in
`core/knowledge/requirements-docling.txt` — to skip the unnecessary ~6GB
CUDA download confirmed here.
---
## LL-158
### Title
"The RAG pipeline" turned out to be retrieval-only scaffolding with zero live callers, a real ragas/langchain-community version conflict blocked a vanilla install, and the eval sandbox itself had no reachable LLM at all
### Date
2026-09-12
### Lesson
A tool described as "the RAG pipeline" in a mission brief or registry is a claim
about intent, not architecture — confirm what actually combines retrieval with
generation (grep for real callers, don't infer from a module's docstring or
filename) before instrumenting it, and say plainly when a "pipeline" turns out to
be one stage of a pipeline with no second stage wired up yet. Separately: a
library's own PyPI metadata (`Requires-Dist: langchain-community`, unpinned) can
be fully satisfiable by pip's resolver while the library's actual code still hard
breaks against whatever version pip picks — declared dependency ranges and
hard-coded imports inside the package are two different (and here,
contradictory) sources of truth, and only actually running `import <package>`
after a fresh install catches the gap between them. And when a sandbox has zero
reachable LLM surface of any kind (no local model, no router, no API key, and
egress policy blocks the one remaining escape hatch), the honest move is to build
every real production code path anyway, prove the non-LLM-dependent parts (retrieval
fallback content, report generation, metric aggregation arithmetic) for real, and
be explicit and loud — in the code, the report, and here — about exactly which
piece had to use a deterministic non-LLM stand-in and why, rather than either
skipping the deliverable or quietly presenting a heuristic's output as if it were
a real judge's.
### Future Guidance
Before wiring `ragas_eval.py`'s judge or generation calls to a live Model Router
in a real deploy, re-run this harness there first (`retrieval_mode` and
`generation_mode` in the JSON report immediately show whether it actually reached
Supabase/the router, or silently fell back) — the fallback paths exist so the
harness never crashes when a dependency is down, which also means a misconfigured
`MODEL_ROUTER_URL` or missing `SUPABASE_URL` fails *quietly* into a fixture
answer rather than an error, so check the mode fields, don't just check the
scores. Before wiring an actual RAG caller (the still-missing second half of "the
RAG pipeline"), rerun `ragas_eval.py` against it directly rather than assuming
today's fallback-mode numbers transfer — `OfflineLexicalOverlapJudge`'s scores
are a proof of the scoring code path, not a quality baseline for real generated
answers. Any future `pip install ragas` into any venv (this one or a fresh one)
should keep `langchain-community<0.4` pinned alongside it until ragas's own
`ragas/llms/base.py` stops hard-importing `langchain_community.chat_models.
vertexai` — check `core/quality/requirements-ragas.txt`'s comment for how to
verify whether that's still true of whatever ragas version is current then.
---
## LL-159
### Title
Two real cloud-egress gaps got closed for real, but the platform's own model-name convention hides a third one from the exact code that would need to check for it
### Date
2026-09-12
### Lesson
A security control that gates "every real external-cloud-API dispatch
point" is only as complete as the assumption that every such dispatch
point looks different enough in code to be found and hooked. Two of this
platform's three cloud paths (Gemini, `mistralai`) do — they're separate
functions/modules with an obvious seam. The third
(`glm-*:cloud`) doesn't, by design: Ollama's whole value proposition for
`:cloud` tags is that they're a drop-in, same-endpoint, same-function
substitute for a local model, specifically so callers don't need to know
or care which one they're talking to. That transparency is a feature for
normal routing and a real blind spot for a security control that needs to
know, at the exact call site, "is this leaving the VM" — the two goals are
in direct tension, and this mission's own brief anticipated that tension
correctly ("they might not be [interceptable], since it's the same code
path as fully-local calls") rather than assuming a clean wrap was
guaranteed to be possible. Worth generalising: before promising "every
dispatch point" coverage for any cross-cutting concern (security,
observability, cost tracking), check whether every dispatch point is
actually *distinguishable* in code first — a provider that deliberately
erases the local/remote distinction for convenience will erase it for
your control too, and the fix at that point is a genuine design decision
(does the router learn to tell them apart?), not a wrapping exercise.
### Future Guidance
Before trusting this stream's semantic (model-backed) rail layer in
production, provision `platform-runtime/.venv-llmsec` on the real host
(`python3 -m venv platform-runtime/.venv-llmsec &&
platform-runtime/.venv-llmsec/bin/pip install -r
core/security/requirements-llmsec.txt`, then the `en_core_web_sm` step in
that file's own comment) and re-run `core/security/
test_llm_guardrails.py`/`tests/test_model_router_guardrails.py` WITHOUT
`fake_responses` against a real, reachable Ollama serving `gemma3:4b` —
this session's sandbox could not do that even once, so the deterministic
keyword/regex layer is the only half of either rail with real, live
verification behind it. If a real Ollama run surfaces the semantic layer
being slow, flaky, or wrong in ways the keyword layer alone would have
caught, that's exactly the kind of finding this platform already has a
home for (`call_log.jsonl`-style evidence, another FND-00N-style root
cause write-up in `app.py`'s own comments) — don't treat the semantic
layer as trustworthy just because the Colang wiring around it is now
proven correct in isolation.

Separately: if a future stream picks up the `:cloud` gap this one
disclosed, resist the urge to special-case it inside `_ollama_generate()`
itself blind — that function is the one code path every fully-local call
in this router also depends on being fast and simple, and MODEL_CLOUD's
own history in this file (FND-001: a real, previously-shipped defect where
a misconfigured cloud tag repeatedly fell through to a 24B local model no
one meant to reach automatically) shows this exact function has already
burned this platform once on a routing assumption that looked obviously
safe until it wasn't. Any change there earns the same live-verification
bar FND-001's own fix (`_resolve_cloud_escalation()`) was held to, not a
lighter one just because the change is "only" adding a security check.
---
## LL-160
### Title
The regulator/status-page candidates were all unreachable from this VM again, and the real blocker underneath most of this task was network policy, not the two OSS tools themselves
### Date
2026-09-12
### Lesson
The task's instinct — verify reachability with `curl` before assuming any
specific target works, the way the browser-use mission verified NEMA/CISC/
eSafety — was correct, but this time the honest finding one layer up is
more useful than the honest finding about any one site: **this VM's
network egress is allowlisted at a policy layer that applies uniformly to
every outbound host, including from inside Docker containers, not just
from the agent's own shell.** That reframes "is this specific regulator
site reachable" into "what is actually on the allowlist" — a much smaller,
faster question, and one where the two winning answers
(`pypi.org`/`registry.npmjs.org`) turned out to double as an unusually
good test target anyway (something that visibly changes on essentially
every poll, which most status pages don't).

A second, narrower lesson from actually wiring Uptime Kuma: its official
Python client library (`uptime-kuma-api` on PyPI) hangs indefinitely on
`api.info()` if called *before* `login()`/`setup()` — not a library bug,
but Uptime Kuma's own server deliberately omits the `version` field from
the `info` socket.io event it sends pre-login (`sendInfo(socket, true)` —
`hideVersion=true`), and the client library's own `_event_info()` handler
silently ignores any `info` payload missing that field, waiting
indefinitely for a second one that never arrives without a session.
Confirmed by raw `python-socketio` instrumentation (`logger=True,
engineio_logger=True`) showing the real payload
(`{'primaryBaseURL': None, 'serverTimezone': 'UTC', ...}`, no `version`
key) arriving correctly — the transport layer was never the problem,
call-ordering was. Separately: a freshly `docker run`-added Uptime Kuma
monitor with `active=true` in its own database record did not actually
start ticking until `resume_monitor()` was called explicitly through the
API — worth checking again on a from-scratch production deploy rather
than assuming `active=true` alone is sufficient.

Also encountered and fixed, unrelated to either OSS tool specifically:
this VM's `dockerd` was not running at task start and `/etc/init.d/docker
start` failed outright (`ulimit -Hn 524288`: "Operation not permitted" —
the init script's `set -e` aborts on that single line in this sandboxed
environment); running `dockerd` directly via `nohup` worked. And both
containers needed the VM's TLS-intercepting egress gateway's CA bundle
explicitly trusted to reach their allowlisted real targets at all —
changedetection.io via `REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE`/`CURL_CA_BUNDLE`
(its `requests`-based fetcher), Uptime Kuma via Node's own
`NODE_EXTRA_CA_CERTS` — both documented as sandbox-only in
`docker-compose.watchlist.yml`'s comments, since a real production host
without this gateway needs neither.
### Future Guidance
Before assuming a specific external site is or isn't reachable from a
given deployment host, check whether outbound network access is
allowlisted at a policy layer first (this session:
`curl -sS http://127.0.0.1:38001/__agentproxy/status` and
`/root/.ccr/README.md`) — it is a five-second check that, when true, turns
"which of these N candidate sites work" into "what's on the list", and
explains a rejection pattern (an explicit, identically-worded error across
every non-allowlisted host, from both the shell and from inside a
container) that would otherwise look like N separate site-specific
failures worth investigating one at a time.

For any future OSS tool wired into `intelligence/` the same way
(self-hosted, containerized, with its own webhook/notification system):
the push→pull queue bridge pattern here
(`intelligence/watchlist/webhook_queue.py`) generalizes — a webhook
receiver normalises and queues, the registered adapter's `collect()`
drains on the next cycle — without needing to change `collection_engine.py`
beyond one `_ADAPTER_MAP` entry, exactly as `downdetector_adapter.py`
proved for a synchronous-fetch adapter. Confirm the tool's actual
notification payload shape against its own real source (as done here for
both Apprise's `json://` scheme and Uptime Kuma's `webhook.js`) rather
than from memory or documentation, which can drift from what a specific
pulled image version actually sends.
---
## LL-161
### Title
Both pilot candidates fetch weights from a host this sandbox's egress policy blocks outright — the fix was a third-party ONNX port hosting the same weights on GitHub instead
### Date
2026-09-12
### Lesson
A pilot brief that frames two candidate *libraries* as the decision point
can have its real blocker sit one layer underneath both of them — here,
where the model weights are hosted, not which inference library wraps
them. Installing both packages cleanly (neither failed at `pip install`)
would have looked like a green light right up until the runtime call that
actually needs the weights; the mission's own acceptance bar ("do, for
real, no stubs" / "a real clip... not a claim") is what forced discovering
this before writing it up as done. Checking `pip install X` succeeding is
necessary but not sufficient evidence a CPU-sandbox pilot will actually
run — the first real inference call, hitting the network for weights, is
where a sandboxed egress policy shows up, and it can silently rule out
every package that shares that host regardless of which one looked
lighter-weight on paper.

Separately: an egress policy blocking an entire well-known host
(huggingface.co) is worth checking for *before* assuming it's the specific
model repo that's unreachable — this could easily have been misdiagnosed
as "this particular model's HF repo is having issues" (the same kind of
network-flakiness Chatterbox's own header already documents for its HF
download) rather than "this sandbox cannot reach huggingface.co at all,"
which would have wasted time retrying instead of looking for
weights hosted anywhere else.
### Future Guidance
When a pilot brief names a library by its ability to load a specific
open-weight model, check where that library actually fetches the weights
from (grep its source for `hf_hub_download`/`snapshot_download`/hard-coded
URLs) *before* spending install time on it, and test that one specific
host against the sandbox's egress policy directly
(`curl -sS -o /dev/null -w "%{http_code}" https://<host>`, checking for a
`403`/`connect_rejected` from `/__agentproxy/status` specifically) rather
than assuming a clean `pip install` means the package will actually run.
If the host is blocked, search for a third-party port of the *same*
open-weight model that hosts its files somewhere the sandbox can reach
(GitHub Releases is the load-bearing example found here) before falling
back to a different model entirely — the weights are usually
redistributable (Apache-2.0/MIT here), so a working alternative
distribution channel is often one search away, and preserves the actual
model the pilot brief was evaluating rather than substituting a different
one for infrastructure reasons alone.
---
## LL-162
### Title
Vulture would have caught one thread of the commander_runtime.py/router.py cluster, not the cluster — the manual grep investigation was still doing real work a symbol-level scanner can't
### Date
2026-09-12
### Lesson
"Would tool X have caught bug/dead-code Y" is answerable with evidence, not
just plausibility — extracting the actual historical tree at the commit
before the fix and re-running the tool against it is cheap (one
`git archive` call) and turns a hand-wavy "probably" into a real yes/no
with a line number attached. Here it turned what would have been a
too-generous claim ("Vulture would have caught this") into a more accurate
and more useful one ("Vulture would have pointed at the one thread worth
pulling, not rolled up the whole cluster for you").

The deeper, generalizable lesson: default-mode Vulture (and static
per-symbol dead-code scanners generally) cannot detect an island of
mutually-referencing code whose only problem is that nothing *outside* the
island calls in — it can only flag names unused *within whatever scope
you feed it*. Tools built with real entry-point/reachability knowledge of
their target framework (knip's Next.js plugin knowing every `page.tsx` is
a live route; a Python equivalent would need to know its own real entry
points — CLI `if __name__ == "__main__"` scripts, WSGI/ASGI app objects,
Slack/Telegram bot dispatch tables, systemd `ExecStart` targets) can catch
a whole orphaned cluster in one shot. Vulture cannot be configured into
having this, because it fundamentally doesn't model "entry point" as a
concept — this is a property of the tool, not a confidence-threshold or
whitelist setting to tune away.
### Future Guidance
- Treat Vulture as complementary to, not a replacement for,
  `tools/verify_dead_code.py`: Vulture is good at *fast, automatic, every-PR*
  detection of individual unused symbols (imports, dead parameters, an
  accidentally-disabled assertion) that nobody would think to manually grep
  for; `verify_dead_code.py` is good at *authoritative, on-demand*
  verification of "is this whole path actually dead" including non-Python
  signals (systemd units, crontab) that Vulture cannot see at all. Keep
  running both — don't retire the manual-investigation tooling because
  Vulture is now in CI.
- When Vulture flags a single unused top-level function in a file that
  looks like a dispatch/integration layer (a name like
  `execute_X_runtime`, `handle_X`, `dispatch_X`), treat that as a prompt to
  run `tools/verify_dead_code.py` on the whole containing module, not just
  delete the one function — that single flagged symbol is often the
  visible tip of exactly this kind of orphaned-island cluster.
- If dead-code coverage needs to catch orphaned Python module clusters
  automatically (not just via the on-demand script), the actual gap to
  close is a real-entry-point/reachability-aware checker for this repo's
  own entry points (Telegram bot dispatch tables, `platform-runtime`'s
  now-removed Slack dispatch, systemd `ExecStart` scripts) — not a Vulture
  confidence tweak. That is future work, not something this stream's scope
  covered; flagging it here so it isn't lost.
- Both `.vulture_whitelist.py` and `lcars-portal/knip.json` should stay
  small and evidence-backed — every entry in both files, as of this
  commit, was added only after reading the flagged code and confirming a
  real false positive (documented inline in each file and in
  `reports/vulture/README.md` / `reports/knip/README.md`). Resist the urge
  to pre-emptively widen either file to silence noise before someone has
  actually looked at what's being silenced.
---
## LL-163
### Title
The code path was proven with a genuinely real send — the one thing that turned out fake-able was the network path to get there
### Date
2026-09-12
### Lesson
**The one real limitation hit**: this deployment's network egress policy
blocks the public `ntfy.sh` host itself. Confirmed directly, not assumed —
`ns.notify(..., transport=Transport.APPRISE)` with `APPRISE_URLS`
pointed at the real `ntfy://ntfy.sh/<topic>` returned a real
`NotificationResult(ok=False, error="apprise notify() returned False …")`,
and a bare `curl https://ntfy.sh/` independently confirmed the same
block (`CONNECT tunnel failed, response 403`) — as did `api.telegram.org`,
`discord.com`, `webhook.site`, `google.com`, and even `example.com`; only
`api.anthropic.com`, `pypi.org`/`files.pythonhosted.org`, and
`github.com`/`api.github.com` (for repos this session attached) are
reachable from inside this sandboxed session. This is an environment/
network-policy fact, not a defect in `_send_apprise()` — the function
correctly attempted the send, correctly reported the real failure, and
would succeed unmodified in a deployment whose egress policy allows the
target host (exactly the "swap the config string" property Apprise
exists to provide).

Given that, the "real send, verified live" evidence above was produced
against a small local stand-in
(`/tmp/…/scratchpad/local_ntfy_stub.py`, not committed to the repo — a
throwaway test fixture, not a shipped module) implementing ntfy's real,
publicly-documented publish/subscribe wire protocol (POST with a JSON
`{"topic", "message"}` body; `GET /<topic>/json?poll=1` → newline-
delimited JSON) closely enough that Apprise's own unmodified `NotifyNtfy`
plugin, over a real HTTP connection, sent to it and got back a real
response it accepted. The only unreal part of this evidence chain is
*which* server received the request — the real `ntfy` self-hosted/private
mode's HTTP behavior (confirmed via Apprise's own DEBUG logging: `ntfy
POST URL: http://<host>` with a JSON body, not the plain-text-in-path
form the "cloud" mode without an explicit host uses) is what the stand-in
had to match, and did, on the first attempt only after fixing a topic-
extraction bug caught by actually running the real round trip (the
stand-in initially read the topic from the URL path, but apprise's
private-mode payload puts it inside the JSON body instead — an assumption
that would have shipped wrong without a real send actually being tried).

The broader lesson: "prove it with a real send" and "the destination is
internet-reachable from this environment" are two separate claims, and a
sandboxed session's egress allowlist can falsify the second while the
implementation under test remains completely correct. Don't let a blocked
network path get treated as "couldn't verify" — attempt the real target
first (to get a real, honest failure on record, not a guess), then verify
the actual code path with the most-real substitute available, and say
plainly which parts of the evidence are which.
### Future Guidance
Before claiming an Apprise (or any outbound-HTTP) integration is "verified
live" from inside a sandboxed agent session, check the egress policy
first with a plain `curl` to the intended host — `curl -sS
http://127.0.0.1:38001/__agentproxy/status` after a failed attempt names
the exact rejection reason and lists recent blocked hosts. If the real
target is blocked, do not silently substitute a local stand-in without
saying so: attempt the real send (record the real, honest failure), then
build the closest available real substitute (a real protocol
implementation on localhost, not a hand-waved "trust me"), and label
every piece of evidence with which claim it actually supports. In an
unrestricted deployment, re-run the exact same `notify(...,
transport=Transport.APPRISE)` call against `APPRISE_URLS="ntfy://ntfy.sh/
<topic>"` before relying on this integration for a real alert — nothing
in `_send_apprise()` needs to change for that, but nothing here has
proven the public ntfy.sh host specifically works from a
network-unrestricted context, only that the code that would talk to it
is correct.
---
## LL-164
### Title
Format-only adoption of the MADR (Markdown Architectural Decision Records) template, ahead of a later ADR-consolidation mission
### Date
2026-09-12
### Lesson
A "just adopt this format" task still needs a real usage check before the
template is written, not after: reading
`docs/self-improvement/DECISION-REMEDIATION-WORKFLOW.md` (a substantial
decision-flow document that turned out to have *no* ADR-shaped structure
at all — narrative and code-driven instead) and
`platform-runtime/adr_conflict_detector.py` (which does expect a specific
existing plain-text ADR shape, just not one used anywhere in the repo
yet — both its scanned directories are empty) established, before writing
a single line of template, that (a) the template needed to be genuinely
new infrastructure rather than a reformat of something existing, and (b)
the one existing piece of ADR-aware tooling had specific parsing
expectations (`ADR-\d{3}` filenames, `Title:`/`Status:` lines,
"supersedes ADR-NNN" / "conflicts with ADR-NNN" phrasing) worth mirroring
in the new template's naming convention even though the tool doesn't scan
the new directory yet — cheap forward-compatibility that costs nothing
now and saves the later consolidation mission from a naming mismatch it
would otherwise have to reconcile by hand.

Separately: "don't invent a fake decision, use a real one" produced a
noticeably better template example than a toy would have. Transcribing
FND-001's actual root-cause narrative into MADR's Decision
Drivers/Considered Options/Pros-and-Cons sections surfaced real friction
in the template itself worth knowing about going in — a real decision
rarely has neatly independent, mutually exclusive options the way a
textbook example does (the three "options" here are really "the old
behavior," "the new behavior," and "a stricter behavior nobody chose"),
and MADR's structure absorbed that fine, which is itself useful evidence
the format fits this repo's actual decisions before a large migration
commits to it.
### Future Guidance
When the later ADR-consolidation mission runs: it will need to decide (1)
whether `core/governance/architecture-decision-records/` and
`knowledge/architecture/` get retired in favor of `docs/decisions/` or
`adr_conflict_detector.py` gets pointed at `docs/decisions/` in addition
to (or instead of) them, and (2) whether the detector's regex-based
`Title:`/`Status:` parsing gets extended to also read MADR's YAML front
matter (`status:` field) so both shapes stay scannable during any
transition period, or whether every existing plain-shape ADR gets
reformatted to MADR up front instead. Both files this stream added
(`docs/decisions/TEMPLATE-madr.md`'s "USS TJR usage notes" footer and
`adr_conflict_detector.py`'s updated docstring) already name this
decision explicitly rather than leaving it implicit, so that mission can
start from a documented open question instead of rediscovering it.
---
## LL-165
### Title
Validation missions find as much as builds: re-checking "shipped" claims broke most streams, including this record's own garak PASS
### Date
2026-09-12
### Lesson
A mission to confirm shipped work was working was no lower-risk than a
build. Of five Priority-1 validation streams, three (2, 3, 5) found real,
unknown or mischaracterised problems once someone checked instead of
trusting the PR's self-report. The fourth (garak) was later found
(2026-09-13) to have made a false claim of its own. Its "real PASS, 0
hits" never happened. The cited run log shows garak crashed on a
nonexistent probe family (`probes.hallucination`) before sending a
request, and the gate had failed that way since it was written. Survey
premises failed too. "5 APScheduler instances with double-fire risk" was
2 live schedulers with no overlap, and "4 ADR registries" didn't exist.
Even the mint-drift bug report poisoned its own scan: the literal ID
string in the record's prose was the false repo-scan maximum.
### Future Guidance
Budget validation work like build work. Re-run every "done" or "PASS"
claim against its raw artifact (the run log, `.report.jsonl`,
`journalctl`) rather than the summary line. Never re-assert an earlier
claim; re-verify it. For "is it live", check each candidate with
`systemctl`, `ps` and `crontab`, not a grep count. `NRestarts=0` can hide
a restart counter that `journalctl -u` shows. Get fresh scan counts right
before triaging, since drift on this monorepo is constant. In prose, never
write a live ID prefix next to a sentinel number (`MSN` + `-9999`) in
files `id_registry.scan_repo_max()` scans. `next_id()` now refuses drift
above `_MAX_SANE_DRIFT = 100`.
Still open: `platform-runtime/commands/test_health_event.py` fails to
collect (missing `parse_event_modal_values`; contract unreconstructed).
The context-service 48h soak never started. The trigger for the 11:11-11:24
UTC `human_systems.recommendation_computed` burst was never found. Delete
dead `platform-runtime/recovery_scheduler.py`, and decide whether
`human_systems_scheduler.py`'s daemon mode should exist (do not merge the
two live schedulers). The garak verdict stayed ON HOLD because of host
contention. Decide between the `docs/decisions/` slug-named shape and the
numbered ADR registry.
---
## LL-166
### Title
"Flip the lint gate once the autofix lands" assumed autofixable was most of the backlog; it was about half, so ruff stayed advisory
### Date
2026-09-12
### Lesson
The brief planned to flip ruff-check to blocking in CI once Stream 2's
`ruff check --fix` landed. That plan assumed the auto-fixable subset was
most of the backlog. It was about half: 3,740 of 6,912 were fixed, and
about 3,395 manual-judgment findings remain. A blocking flip would then
fail every commit against untouched, pre-existing files, not just new
drift. Bandit could flip safely because Stream 1 took it to 0 unaddressed
Medium findings repo-wide. The gates diverged, and the local hook still
hard-blocks both, so the local `SKIP=` workaround became a documented,
standing convention instead of a one-off.
### Future Guidance
Before planning "flip gate X to blocking after cleanup Y", measure what
cleanup Y can actually remove. Run `ruff check . --statistics`, read the
fixable count, and plan the flip against the non-fixable remainder. A gate
goes blocking only when a fresh full-repo scan shows zero unaddressed
findings, as bandit did. When CI and local hooks differ in strictness,
document the local escape where contributors will see it (as in
`.pre-commit-config.yaml`'s header comment) and keep it tied to the
backlog that justifies it.
Still open: triage the ~3,395 manual-judgment ruff findings by file or
rule, then flip CI's `ruff-check` to blocking. The lcars-portal Dependabot
PRs #160, #162 and #168 are blocked on the Vercel free-tier deploy limit,
and #162 also needs a real Tailwind v4 config migration. Picked up by
MSN-0370 records (check those for current status): the ADR-030
test/implementation mismatch, the ~23 unverified bare ADR citations, and
#157's `scoped_supabase.py` re-verification.
---
## LL-167
### Title
Bandit findings were settled by reading each URL's source and each bind's deploy config, with the evidence written into the dated nosec
### Date
2026-09-12
### Lesson
Most Medium bandit findings here were real code patterns but not real
risks. About 147 B310 (urllib scheme) hits all built URLs from a fixed
constant, an internal env var (`SUPABASE_URL`, `OLLAMA_BASE`) or a
hardcoded API host. A runtime scheme check would have been dead code. The
B108 `/tmp` hits were synthetic paths in tests that mock the I/O, so
rewriting them to `tempfile` would have added real filesystem I/O. B104
(bind 0.0.0.0) was the one true decision, and the brief undercounted it
(2 vs 4). All four were confirmed by reading deploy configs: two
Caddy-fronted TTS services, and two webhooks that Docker containers reach
via `host.docker.internal`. Rebinding to loopback blindly would have broken
them. This session also picked up an interrupted agent's 92-file
uncommitted diff. It reviewed that diff and re-ran the scan over it rather
than discarding it or trusting it blind.
### Future Guidance
For each bandit finding, trace where the flagged value actually comes
from before choosing between a fix and a suppression. Suppress with a
specific, dated reason, e.g. `# nosec B310 - <URL source> - reviewed
<date>`, and never with a generic "trusted". For B104, read the
docker-compose file, systemd unit and module docstring, and name the
compensating control (secret header, Docker network need) in the comment.
Re-count from a fresh `bandit -r . -ll -x './node_modules,./.git'` rather
than the brief's numbers. On pickup, an uncommitted diff from an
interrupted agent is work to review and re-verify (bandit scans the
working tree, so re-run it), not to throw away. If no system bandit
exists and PEP 668 blocks a global install, use an isolated venv.
---
## LL-168
### Title
A 696-file autofix was proved behaviour-neutral by fixed-point, file-type and failing-test-ID checks, not by skimming the diff
### Date
2026-09-12
### Lesson
A repo-wide `ruff check --fix .` touching 696 files was shown to be pure
mechanical output through checks, not review volume. A second
`--fix --diff` pass found nothing to fix (fixed point), so no hand edits
were layered on top. Only `.py` files changed. Only Ruff's known-fixable
rule codes disappeared from the statistics. The feared risk, import
reordering crossing an import-time side effect, is structurally bounded.
Ruff's isort only reorders within a contiguous import block, so a
`sys.path.insert()` between blocks is never crossed. Test parity was
proved by stashing and comparing the exact failing test node IDs, not
pass/fail counts, which can hide one failure swapping for another.
### Future Guidance
For any bulk mechanical change, prove purity with three checks. Re-run the
tool and confirm it reports nothing left to do. Run
`git diff --name-only | grep -v '\.py$'` and confirm it's empty. Diff
`--statistics` before and after. Never pass `--unsafe-fixes` in the same
PR. Grep the diff for hunks that touch `sys.path.insert` or
`logging.basicConfig`, and hand-read the highest-churn files' sibling
imports for import-time side effects. Run tests per CI matrix entry (own
venv where CI uses one), then `git stash`, re-run, and diff the
`FAILED`/`ERROR` node IDs. Note: the repo has no `pyproject.toml` or
`ruff.toml`, so stock defaults match the pre-commit hook.
Still open: the ~3,396 non-autofixable findings. `telegram-bots/xo` and
`telegram-bots/revs` requirements hit pip `ResolutionImpossible`
(`supabase==2.3.4` + `gotrue==2.12.4` + python-telegram-bot `httpx`
conflict). The `platform-runtime` `test_health_event.py` collection error
also remains.
---
## LL-169
### Title
Grep hits for ADR numbers are mostly fixture noise; only 10 of 32 cited numbers had real backing, and confident-sounding titles misled
### Date
2026-09-12
### Lesson
`grep -rn "ADR-0[0-9][0-9]"` surfaces 32 distinct numbers, but per-number
verification found only 10 backed by live, load-bearing code or tests.
MSN-0369 filed 7, on top of 2 already filed, and MSN-0370 found 1 more
(ADR-006) in the other 23. The other 22 were noise: the `enrichment_poc/`
fixtures, a stale self-admittedly-incomplete UI mock
(`ArchitectureIndex.tsx`/`captainReview.ts`), template/example
boilerplate, test fixture literals, a dump of the orphaned
`temporal_entities_archived_2026` ghost table, and self-improvement
`evidence.json` snapshots of never-committed worktree files. The noise
sources give confident titles that contradict real code (ADR-003's two
sources disagreed with each other; ADR-024's were flatly wrong). Even
real numbers varied from deep multi-file evidence to nothing beyond a
title, so honest low-confidence filing was needed for 4 numbers.
### Future Guidance
Before citing or filing an ADR, check
`core/governance/architecture-decision-records/`. Then
`grep -rn "ADR-0NN\b"` for the number and read every hit. Count a
citation as real only in production code, its tests or migrations. Treat
these as known noise, never primary sources, and at most as weak title
corroboration: `core/context-assembly/enrichment_poc/`, the
`ArchitectureIndex.tsx`/`captainReview.ts` mock and its test,
`docs/decisions/TEMPLATE-madr.md` and `EXAMPLE-ADR-001`,
`core/infrastructure/supabase/backups/2026-09-01-dead-tables-pre-drop.json`,
and `data/self-improvement/runs/*/evidence.json`. When the drivers and
alternatives can't be recovered, file under a "Reconstructed — low
confidence" status that says so rather than inventing content. Note: a
reconstruction can surface code gaps. ADR-030's test/implementation
mismatch was found this way and handed to MSN-0370's ADR-030 fix record.
---
## LL-170
### Title
Dependabot triage needs a code-surface review, not a red/green read; a bot failing on Actions-only bumps proved the red was baseline
### Date
2026-09-12
### Lesson
All 11 PRs showed red CI, including #120 and #121, which bump GitHub
Actions and touch no Python. That proved the `test (core)`, missing
`TELEGRAM_BOT_TOKEN` and `sample_brief.md` failures were baseline, so CI
colour couldn't decide any merge. Decisions came from reading the
changelog against the repo's actual usage. Pandas 3.x's breaking changes
miss the parser's five calls. mypy runs in no CI step, so a stricter
default can't break CI. The one real danger hid in a minor-looking bump.
supabase-py v2.24.0 removed the private `SyncClient` that
`telegram-bots/xo/scoped_supabase.py` monkeypatches for XO's scoped-role
RLS auth. Merging blind risked a silent fallback to unscoped access.
### Future Guidance
Re-list open Dependabot PRs at the start; don't trust the brief's list.
When CI is red across the board, find a PR that touches none of the
failing code (an Actions bump) to prove the red is baseline. Then judge
each bump on the path-specific job and a grep of the package's real call
sites against its changelog. Before bumping any library, grep for private
attribute access or monkeypatching of it (`client._`, "pinned to"
docstrings). Those pins are re-verification tasks, not merge candidates.
For lcars-portal PRs, check live Vercel status before merging. Pair
`eslint-config-next` majors with a Next.js upgrade, and treat Tailwind
v3 to v4 as a config migration, not a bump.
Still open: rewrite and re-verify `scoped_supabase.py` before re-attempting
supabase 2.3.4 to 2.31.0 (#157). Run a scoped lcars-portal upgrade mission
(TS 5 to 7, Tailwind v4, Next.js plus eslint-config-next) once the Vercel
limit is confirmed cleared. Provision `TELEGRAM_BOT_TOKEN` for the bot test
jobs and fix the `examples/sample_brief.md` path in revs-content-agents.
---
## LL-171
### Title
The ADR-030 test asserted behaviour the code never had; `git log -S`, a caller grep and the docstring proved the test was stale
### Date
2026-09-12
### Lesson
When a test and its implementation disagree, "make the test pass" is not
the default fix. First establish which side is the source of truth.
MSN-0369 flagged one failing ADR-030 test without running it. Running the
whole file showed 12 of 23 failing from one root cause: the tests assumed
an Engineering Router design (`_parse_router_args`, router metadata, a
dict return) that `git log --all -S` showed never existed in
`commands/mission_brief.py`. The module had zero live callers and a
docstring documenting `-> str`. Implementing the feature would have built
new, unrequested behaviour into dead code. A sibling test of the same
abandoned integration was deleted on 2026-09-08 (commit `38e554352`), but
that pass missed this file.
### Future Guidance
Before resolving a test/implementation mismatch, run the whole test file,
not only the cited test. Then gather evidence: `git log --all -S
"<symbol>" -- <file>` shows whether the asserted function ever existed,
`grep -rn` outside tests finds live callers, and the module's own
docstring states its contract. If the feature never existed and nothing
calls it, fix the test and record the evidence inline and in the ADR's
"Resolution" section. When deleting test debt for a removed integration,
grep every test file that uses the same symbols so no sibling is missed.
System Python on this box has no working pytest, so use
`/opt/starship-endeavour/platform-runtime/.venv/bin/pytest`.
Still open: `commands/mission_brief.py` has zero live callers but was
deliberately not deleted. A revive-or-remove decision is still owed,
alongside `commands/health_appointment_prep.py` from the 2026-09-08 pass.
---
## LL-172
### Title
Four directory-split ruff streams each reached 0, yet the merged tree had 9 findings from unowned or mid-mission files
### Date
2026-09-12
### Lesson
Splitting a repo-wide triage by top-level directory kept parallel
workers' file ownership exclusive and took ~3,395 findings to 0. But
"0 findings" in every stream did not mean 0 in the merged tree. Merging
surfaced 9 more: a pre-existing `.vulture_whitelist.py` that none of the
four streams owned, and `platform-runtime/test_wp1_wp2_wp3.py`, which an
unrelated concurrent mission landed on `main` after the streams' scans.
Concurrent work collided in other ways too. Another mission fixed the
ADR-030 root cause on `main` first, which caused two conflicts. One ruff
stream had fixed lint in `recovery_scheduler.py`, a file a concurrent
mission had already deleted as dead code.
### Future Guidance
For any partitioned cleanup, run the gate (`ruff check .`) fresh on the
fully merged tree before declaring done or making the CI gate blocking.
Ownership partitions leave orphan files, such as root-level dotfiles,
and miss files that land mid-mission. Before merging, check `main` for
concurrent fixes of the same root cause. On a modify/delete conflict
against deliberately deleted dead code, take the deletion. Generated
files like `.secrets.baseline` conflict on line drift. Resolve them with
a full `detect-secrets` rescan and check for coverage loss, rather than
picking one side.
Open follow-ups from this mission:
- lcars-portal Dependabot PRs #160, #162 and #168 are still held,
  blocked on the Vercel free-tier deploy-rate-limit.
- 3 `KNOWN GAP` items from the triage are unfixed: the source-governance
  filter, the timezone-blind alert adapters, and the `tools/health-osint/`
  directory name.
- The `tg-xo.service` redeploy, the `telegram-bots/revs` monkeypatch and
  the PTB upgrade are covered in the supabase entry.
---
## LL-173
### Title
"Mechanical" ruff fixes broke code: scripted `check=False` insertion caused syntax errors in two streams, caught by a parse gate
### Date
2026-09-12
### Lesson
Even the most mechanical lint fixes need a verification gate. Two
MSN-0370 streams each scripted `check=False` into `subprocess.run()`
calls (PLW1510), and both broke multi-line calls. One hit "positional
argument follows keyword argument" and the other got 7 stray-comma
syntax errors. `ast.parse`/`py_compile` caught both before commit.
Fixes also cascade. RUF059 took 3 passes because ruff's dead-store check
is not flow-sensitive per binding. G201's `log.exception()` change then
correctly raised TRY401 and F841. Manual triage also turned up real bugs:
blocking calls inside `async def` in `telegram-bots/xo/app.py`
(`/restart_bots`) and `core/voice/tts_edge.py`, and an undefined `log`
in a function documented as "never raises".
### Future Guidance
After any scripted edit, run `python3 -m py_compile` (or `ast.parse`) on
every touched file before committing. Then re-run `ruff check <file>
--select <RULE>` to catch follow-on findings. For PLW1510, add explicit
`check=False`, which keeps current behaviour. `check=True` breaks callers
that inspect `returncode`. Insert by matching brackets, not by inserting
lines. Expect RUF059 and G201 fixes to need a second pass. Fix ASYNC
findings by hand with `asyncio.to_thread`/`create_subprocess_exec`. Note
that no test covers the `/restart_bots` subprocess path; it is verified
by construction only. Split big judgment buckets (BLE001) across
subagents by disjoint file sets. Intermediate commits may use the
documented `SKIP=ruff-check,bandit`. gitleaks and detect-secrets were
never skipped.
Left open:
- 192 low-severity bandit findings in the bots/scripts/services/tests
  scope, for a bandit follow-up.
- The cross-file `config` module-name collision that breaks a combined
  `pytest core/` run, which needs its own ticket.
---
## LL-174
### Title
Naive-datetime lint fixes change behaviour: core kept `date.today()` on local time while platform-runtime and bots moved it to UTC
### Date
2026-09-12
### Lesson
DTZ findings look mechanical but are not. Changing `datetime.utcnow()`
to `datetime.now(timezone.utc)` is always safe because it is the same
instant. `date.today()` is different. Core confirmed this host runs on
`Australia/Melbourne` time, so moving a calendar-day call to UTC changes
which day it returns for about 10-11 hours every day. Core kept the
local day with `datetime.now().astimezone().date()`. intelligence/tools
chose per site: AEST for business dates, UTC to match DB values.
platform-runtime and bots-misc both moved to UTC, and platform-runtime's
own record flags that it assumed the clock is effectively UTC. The
streams also found one recurring bug class: a timestamp's offset dropped
(git `%ai`/`%ci` cut to 19 characters), or a "Z" added to a naive string,
which labelled local time as UTC.
### Future Guidance
Classify each `date.today()` or `datetime.now()` call before fixing it.
A human calendar day should use `datetime.now().astimezone().date()` or
an explicit zone. A value compared against UTC database values, such as
Postgres `current_date`, should use UTC. Never truncate git `%ai`/`%ci`
output. Parse the full string with `%z`, then call
`.astimezone(timezone.utc)`. Never add "Z" to a naive isoformat. If a
source feed has no offset at all, flag it as `KNOWN GAP` rather than
guess. An emergency-alert adapter is the example: a wrong guess like
this once put a `bom_warnings.py` alert 10 hours off.
Follow-ups:
- Check platform-runtime's and bots-misc's `date.today()`-to-UTC
  replacements against core's confirmed Melbourne host timezone. The
  streams made opposite assumptions.
- Re-check the deliberate host-local-to-UTC "today" changes in
  `external_fetch_budget.py` and `llm_cost_governance.py`.
---
## LL-175
### Title
An "unused variable" finding often hides missing behaviour: three F841-class findings in intelligence/tools were real functional bugs
### Date
2026-09-12
### Lesson
F841 flags a dead store, and the dead store is often a sign of missing
logic rather than clutter. In `intelligence/` and `tools/`,
`correlation_synthesis.py` computed `r_value` and `sample_size` and then
dropped them. The Captain-facing brief showed correlations with no
supporting statistics. A test computed `initial_count` but never asserted
it, even though its comment said it should. And
`content_intelligence_service.score_and_persist()` loads the approved
sources (`terms_reviewed=true`) but never filters on them. As a result,
`content_signals` can be written from sources that have not passed terms
review. Deleting the "unused" variable would have removed the only
evidence of each gap.
### Future Guidance
Before deleting an F841 variable, read why it was computed. If it was
meant to be rendered, asserted or used as a filter, wire it up, as was
done for the correlation brief and the test assert. If the intended
behaviour needs a policy decision, keep the variable with a `KNOWN GAP`
comment and `# noqa: F841` instead of removing it. Also read the
neighbouring F821/B018 findings in context. One was a stray `PYEOF`
heredoc terminator in `tools/integrate_lessons.py`.
Still open:
- The source-governance filter in
  `intelligence/content_intelligence_service.py` is still not applied.
  This is a real governance gap and needs an owner decision on the
  intended filter logic.
- `tools/health-osint/` (hyphenated, N999) was not renamed because
  cron/systemd units reference it by path. A rename needs its own
  mission.
---
## LL-176
### Title
Git worktrees share one `refs/stash`, so a routine `git stash`/`pop` in one worktree grabbed a concurrent session's stash
### Date
2026-09-12
### Lesson
Separate worktrees isolate working directories but not every ref. All
worktrees of a repo share one stash stack. A routine `git stash &&
<baseline test> && git stash pop`, run to get a clean-HEAD pytest
baseline, collided with a stash the concurrent `msn-0368` session had
pushed from another worktree. The pop partially applied the other
session's stash and appeared to drop it. Nothing was lost, but only
because the dropped stash could still be reached as a dangling commit.
This is the same class as the shared-checkout collision lessons, now
confirmed for `git stash` as well as `git checkout`.
### Future Guidance
Never use `git stash` in this repo's shared-worktree setup. For a "compare
against clean HEAD" baseline, use `git diff > wip.patch` and
`git apply -R wip.patch`, run the baseline, then `git apply wip.patch`.
These commands touch only your own working tree, never a shared ref. If
a stash is lost, `git fsck --no-reflog` lists dangling commits. Find it
by its message and put it back with `git stash store <sha>`. Recover your
own WIP with `git diff <parent> <stash-sha>` plus `git apply` instead of
using the shared stash again. Note that the bots-misc stream in the same
mission also used `git stash`/`stash pop` for regression baselines, which
carries the same risk. The system `pytest` was broken, so use the venv at
`/opt/starship-endeavour/platform-runtime/.venv`.
---
## LL-177
### Title
A merged `requirements.txt` pin was never installable or deployed: tg-xo still ran pre-#132 gotrue 1.3.1 while the repo said 2.12.4
### Date
2026-09-12
### Lesson
A dependency bump that merges cleanly says nothing about the running
service. PR #132's `gotrue==2.12.4` pin could not be installed alongside
the existing `httpx<0.26` pin. The live `telegram-bots/xo/.venv` was
still on `gotrue==1.3.1`, so the reinstall was either skipped or failed
silently. The same investigation showed that PR #157 was deferred for the
wrong reason ("private API removed, no replacement"). A public
`ClientOptions` header route had existed since supabase-py 2.4.3. The
real blocker is the `httpx~=0.25.2` pin in `python-telegram-bot==20.7`,
a hard `ResolutionImpossible` against supabase 2.31.0's `httpx>=0.26`.
Both findings came from installing version combinations in throwaway
venvs, not from reading changelogs or docstrings.
### Future Guidance
For any pin change, run `pip install -r requirements.txt` into a fresh
venv before merging. After the merge, confirm the service's live
`.venv` actually changed (`pip show <pkg>`). When a bump is deferred
because an API was removed, bisect versions in throwaway venvs and test
the behaviour live before accepting that reason. Pin transitive deps
explicitly when needed: here `gotrue<2.9.0` kept the resolver off
versions that use the `proxy=` kwarg.
Required actions, not done:
1. Redeploy `tg-xo.service`: run `pip install -r requirements.txt` in its
   venv and restart it. This picks up supabase 2.7.4 with `gotrue<2.9.0`
   and the #132 change that was never deployed.
2. `telegram-bots/revs/scoped_supabase.py` still has the `_auth_token`
   monkeypatch and the same broken pins. It runs PTB 22.8, so it can go
   straight to supabase 2.31.0.
3. PR #157's 2.31.0 target first needs `telegram-bots/xo` upgraded past
   PTB 20.7. Then re-run the version bisection.
---
## LL-178
### Title
The secrets-migration brief listed 21 services from repo `deploy/*.service`; the live box had 38 units, drift, and an uncommitted cutover
### Date
2026-09-12
### Lesson
A brief built from the repo's copies of unit files describes what was
committed, not what is running. Auditing `/etc/systemd/system/*.service`
instead found 38 app-level units, not 21. Two services named in the brief
did not exist under those names; the real units are `tg-xo`/`tg-revs`,
plus an active `tg-capacitybot` the brief said had no unit.
`model-router`'s live `EnvironmentFile=` did not match the repo copy.
`intelligence-scheduler` had been moved to `run-with-infisical.sh` live a
week earlier but never committed, so no rollback commit existed. There
were at least 8 `.env` files, not 5, including a repo-root `.env` and one
outside the repo. An optional (`-`) `EnvironmentFile=` silently hid a
file that does not exist.
### Future Guidance
Before planning any host-level migration, take a live inventory first:
- `/etc/systemd/system/*.service`, not `deploy/`.
- `ps aux` for processes that bypass the units.
- pm2 for services outside systemd, such as `command-centre`.
- `diff` each live unit against its repo copy, and commit any live drift
  back before changing anything.
Check that every `-`-prefixed `EnvironmentFile=` path exists. Check each
unit's `User=` against the secret file's permissions (`sudo -u <user>
test -r ...`). If the audit invalidates the brief, stop and revise scope
with the Captain, as Stream 0 did. Still open from this audit: the
Infisical stack has no uptime monitoring, `command-centre`'s pm2 env was
never investigated, and the ~10 "(none found)" services were not checked
for code-level dotenv (see the Streams 2-6 entry). Separately,
`auto-deploy.service` was in a `failed` state that this mission did not
cause.
---
## LL-179
### Title
Infisical's flat prod namespace would have given all three Telegram bots XO's token; per-instance values need per-service folders
### Date
2026-09-12
### Lesson
A shared secret store with one value per key silently breaks services
that use the same key name with different values. `tg-xo`, `tg-revs` and
`tg-capacitybot` each need their own `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID`, confirmed different by SHA-256 hash rather than raw
values. The standard wrapper would have given all three bots XO's token,
and polling with a shared token fails outright with Telegram 409 errors.
The fix was a `/bots/<name>` folder per bot, plus
`run-with-infisical-bot.sh`, which loads the shared root secrets and then
the bot's folder as an override. Separately, the CLI's
`secrets set --file` and an ad hoc `printenv` printed 7 real secret
values into the session transcript. That command has no option to hide
values.
### Future Guidance
Before pointing several services at one secret environment, compare
their values for every shared key name by hash (`sha256sum`), never by
printing them. Put keys whose values differ in a per-service folder that
loads after root. Confirm each service receives its own value through
the wrapper before touching a live unit. Don't run secret-writing CLI
commands or `printenv` where the output lands in a transcript; assume
any value shown there needs rotating. `tools/check_no_raw_env_secrets.py`
(a pre-commit hook on `deploy/*.service`) now blocks re-enabling
`EnvironmentFile=`.
Required actions, not done:
- Rotate the 7 secret values exposed in the session transcript.
- Confirm `vm-processing.service`'s cutover on its next natural timer
  fire.
- Add uptime monitoring for the self-hosted Infisical stack.
- Fix `lcars-portal`'s `NEXT_PUBLIC_*` build-time env source, which is
  still `.env.local` at `next build`.
- Investigate `command-centre`'s pm2 env.
- Check the ~10 services with no `EnvironmentFile=` for code-level
  dotenv.
- Prove the 3 dead-reference services are clean.
Also open, unrelated to the migration: the REVS bot logs its
token-bearing request URL at INFO level in `journalctl`.
---
## LL-180
### Title
A "check first" rule written as prose got skipped twice; moving it into a mandatory Pre-flight caught the brief's own stale scheduler count
### Date
2026-09-12
### Lesson
AGENTS.md already said to check existing state first, and the rule was
still skipped twice: duplicate `SOURCES` rows broke a 163-row upsert batch,
and up to 4 ADR registries piled up. A rule that only exists as prose
gets skipped. It has to sit at the point where work starts, with
evidence required. Running this mission's own new Pre-flight showed the
same problem in the brief itself. The brief said there were "6 real
independent" APScheduler instances, but commits already on
`origin/main` had cut that to 2 live ones. The audit also found a dead,
unreferenced predecessor of the registry that had the original bug
(`seed_source_registry_old_64sources.py`). Nobody had checked whether
the old copy should be removed when the new one was built.
### Future Guidance
Start every new mission brief from `knowledge/MISSION-BRIEF-TEMPLATE.md`.
Its Pre-flight comes first and requires a cited grep command and its
result, a check of the brief's own premise against real repo state, and
an "Explicitly Not In Scope" section. Treat any number or location in
the brief as possibly out of date until you have re-checked it. Before
adding to a registry, use the "Check-first registries" list in AGENTS.md
and grep the exact key. When you build a replacement for a registry or
config file, delete or retire the old copy in the same change. Open
follow-ups the record flags:
(1) `specialists/SPECIALIST-INVENTORY.md` (prose) and `prompt_loader.py`'s
`SPECIALISTS` dict describe the same roster with no single source of
truth. This is a drift risk; raise a mission if the two are found to
disagree.
(2) Update the AGENTS.md registry list whenever this pattern turns up
again.
(3) Scheduler consolidation (USS-TJR-MSN-0368 Stream 6) is still open:
`human_systems_scheduler.py`'s unused daemon mode needs a keep-or-remove
decision, and the 8-event human_systems dispatch burst noted in commit
`9e768ff` is unexplained.
---
## LL-181
### Title
The bandit gate was made blocking after checking a hand-run `bandit -ll` that CI never ran, so main stayed red for 3 missions
### Date
2026-09-12
### Lesson
A comment in `.pre-commit-config.yaml` said CI ran a Medium+ (`-ll`)
bandit gate, but the hook's real `args` were just `["-q"]`. MSN-0369
checked "0 Medium findings" with a bandit command run by hand and then
made the CI step blocking. CI actually runs the unfiltered hook, so from
the moment it turned on (run 129) it failed on about 2,503 pre-existing
Low findings, on every push to `main`. Three missions (0370, 0371, 0372)
landed on top of it and nobody noticed. A gate that is always red looks
like the usual noise, which is why it went unfixed. A comment describing
a gate is not the gate. Only the exact command CI runs counts as proof.
### Future Guidance
Before making any check blocking, run the exact command the workflow
runs (here `pre-commit run --all-files bandit`), not a hand-run version
of the same tool. Then confirm the step goes green on a real GitHub
Actions run for that commit before merging. After making a gate
blocking, look at the Actions history for the next few pushes to `main`.
A step that has failed since the commit that turned it on is a config
mismatch, not new findings. Keep the explanation of a gate's flags in
one comment on the hook itself, not repeated in a header that can drift
from it. Open/deferred: the ~2,503 Low findings are deliberately left
alone. Gating on Low severity would need its own triage, like the
MSN-0369/0370 work, not a flag change.
---
## LL-182
### Title
The standard Storybook a11y-in-CI runner fails on Storybook 10's ESM loader; a hand-rolled Playwright + axe-core script did the job
### Date
2026-09-13
### Lesson
The source doc's framing was out of date. The a11y addon, axe-core and
vitest-axe were already installed. The real gap was that nothing ran a11y
checks across every story in CI. The textbook fix, `@storybook/test-runner`
(Jest + Playwright), failed outright against Storybook 10.5.0: 7/7 suites
threw `module.register() is not supported in Jest`, and 0 tests ran. The
"modern" alternative, `@storybook/addon-vitest`, had no release that
declared Storybook 10 support. Only running the tool showed this. Reading
docs would have shipped a broken job. A small script that reads
`storybook-static/index.json` and runs axe on each story iframe worked,
and it added only one new dependency (`playwright`).
### Future Guidance
When adopting a framework's "standard" CI integration, run it against the
real build output before wiring it in. Check that the major version it
supports matches yours. Remove any packages you tried and dropped (here
`@storybook/test-runner`, `axe-playwright`). To make a CI job report-only,
put `continue-on-error: true` on the step. Job-level alone still shows
the check-run as red (same pattern as the `deadcode`/knip job, PR #180).
Open follow-up: 8 pre-existing `serious` `color-contrast` violations in
the design-system Input, Navigation and Progress stories (28 stories
checked, 145 axe checks passing). They need triage and fixing. After
that, flip the `test-storybook` job in `lcars-portal-ci.yml` from
report-only to blocking.
---
## LL-183
### Title
A new pip-audit gate found 17 real findings, and a requirements file that won't resolve is unscanned, not clean
### Date
2026-09-13
### Lesson
The repo had no dependency-CVE scanning at all. Bandit and the secret
scanners don't cover pinned versions. Running the gate for real gave a
measured backlog of 17 distinct findings across 12 package@version pins
in 5 of 15 `requirements*.txt` files, not just "the gate exists". The
real run also exposed two traps. First, pip-audit's JSON listed each
finding twice, so the count was only right after deduplicating on
(package, version, advisory id). Second, one file
(`telegram-bots/revs/requirements.txt`) hit `ResolutionImpossible` and
was never vulnerability-matched at all. A naive summary could easily
have counted it among the clean files. pip-audit has no report-only flag,
so a gate added before the backlog is triaged needs a wrapper that always
exits 0. Otherwise it blocks every contributor's commits for reasons
unrelated to their change.
### Future Guidance
When adding a new scanner, report the real per-file numbers. Deduplicate
findings by advisory ID before counting. List files the tool could not
resolve or parse separately from files that scanned clean. The advisory
pieces are `tools/run_pip_audit_advisory.py` (pre-commit, always exits
0) and the `pip-audit` job in `python-ci.yml`, which uses step-level
`continue-on-error`. Open follow-ups:
(1) Triage the 17 findings to zero or documented-accepted, as was done
for bandit/ruff. Then make the gate blocking: have the wrapper return
pip-audit's real exit code, or drop the wrapper.
(2) Fix `telegram-bots/revs/requirements.txt`'s dependency conflict (its
pins vs. an implicit `httpx<0.29`) so the file can be scanned at all.
---
## LL-184
### Title
The "router unreachable from sandbox" pre-flight was stale; an aligned simulator model refusing to draft attacks shows up as "invalid JSON"
### Date
2026-09-13
### Lesson
The mission pre-flight said the Model Router was VM-only and unreachable.
A 5-second `curl` to `127.0.0.1:8891/health` showed it was live, so the
deepteam scan was a real run against production. A claim about the
environment describes one earlier sandbox, not a lasting property. Check
it, and say so explicitly whichever way it turns out. When an aligned
model (`glm-5.3:cloud`) is used as the red-teaming *simulator*, it
refuses deepteam's generative jailbreak-drafting meta-prompt. The refusal
surfaces as an opaque "Evaluation LLM outputted an invalid JSON" error,
not as "simulator declined". Separately, deepteam 1.0.9 imports
`sentry_sdk` unconditionally but doesn't declare it. A clean dependency
resolve doesn't prove a package works. Only a real `import` after a
fresh install does.
### Future Guidance
Re-probe `http://127.0.0.1:8891/health` before every run. Don't trust
either this record's "reachable" or the brief's "unreachable". After
installing any new library, run a real `import <package>` in a fresh
venv. When a harness throws a parse or JSON error from someone else's
library, instrument a single `generate()` call to see the raw exchange
first. `core/quality/deepteam_scan.py` defaults to the deterministic
attacks (Base64/ROT13/Leetspeak). Expect real errored cases with
`--allow-generative-attacks` against this model; that is not a bug.
Generative coverage needs a non-aligned or explicitly consenting
simulator model. Keep the scan in its own `.venv-deepteam`, because
deepteam's unpinned `deepeval` would bump the shared venv beside the live
`HallucinationMetric` caller. Re-verify the explicit `sentry-sdk` pin if
a later deepteam declares or drops it. Budget for wall-clock time: 8
cases took ~344s serially (`max_concurrent=1`). Open: whether
`deepteam_scan.py` should become a blocking pre-activation check is
undecided.
---
## LL-185
### Title
The registry's canonical-ADR claim cites a mapping file that no longer exists, so the authority pointer is dangling
### Date
2026-09-13
### Lesson
To point log4brains at the right ADR directory, this stream had to
confirm which of the repo's 4 parallel ADR registries is canonical.
`knowledge/SUOC-Platform-Registry.md` names
`core/governance/architecture-decision-records/` and cites that
directory's `ADR-NAMESPACE-MAPPING.md` as its authority, but that file no
longer exists anywhere in the tree. The conclusion still held, but only
because the registry's own text said so. A canonicity claim can outlive
the file that backs it, and the next person who follows the citation
finds nothing. The build was checked the same way: grepping real ADR
titles out of the generated HTML confirmed all 10 source ADRs mapped 1:1
to output pages. A "10 ADRs" count alone could hide dropped or duplicated
entries.
### Future Guidance
When a doc cites a file as the source of truth, open that file before
relying on the claim. If it's gone, flag the dangling citation; don't
silently trust or ignore it. Verify generated sites and reports by
grepping specific known content from the output, not just a count. Build
locally with `npm run adr:build`; `.log4brains/out/` is git-ignored. Open
follow-ups:
(1) Restore `ADR-NAMESPACE-MAPPING.md` or update the SUOC registry's
citation to it.
(2) Hosting/auto-publish for the ADR site is undecided. If it's wanted,
use log4brains' documented `publish-log4brains.yml` pattern; this is a
separate hosting decision.
(3) The other 3 ADR registries (`governance/ADR-*.md`,
`knowledge/Architectural-Decisions.md`, `architecture/decisions/`) are
still outside log4brains and need a fold-in or retire decision.
---
## LL-186
### Title
garak_gate.py printed PASS after garak ran zero probes because a default probe name doesn't exist in garak 0.17.0
### Date
2026-09-13
### Lesson
Stream 5 shipped as a documentation-only handoff because the router had
timed out from that agent's sandbox. During integration the router
answered, so the gate was run for real. That run found a bug nobody had
seen, because the gate had never produced a report. The default probe
`hallucination` doesn't exist in `garak==0.17.0` (only
`packagehallucination` does). garak errored with `Unknown run.spec`, ran
zero probes, exited 0, and the gate printed "PASS — 0 confirmed hit(s)".
A security gate that can't tell "clean run" from "nothing ran" gives a
false pass. A second run hit a 120s read timeout, because concurrent
sessions were scanning the same production router with garak and
deepteam at once. The gate correctly reported that as FAIL.
### Future Guidance
Any scan gate that passes on zero hits must also check that a nonzero
number of probes or tests actually ran. Treat a run with zero probes as
a failure. When a handoff exists only because the environment was
unreachable, re-probe before shipping it. Open follow-ups (the fix was
deliberately not applied):
(1) Change `DEFAULT_PROBES` in `core/quality/garak_gate.py` from
`"hallucination,promptinject"` to `"packagehallucination,promptinject"`,
and add the zero-probes-is-not-PASS check.
(2) Then re-run it against the live router to get a first clean
pass/fail verdict. Coordinate timing with other sessions so you don't
repeat the shared-load timeout.
(3) Before the first VM run, check that `platform-runtime/.venv-garak`
exists (install from `core/quality/requirements-garak.txt`).
(4) Deciding whether garak should be a blocking pre-activation gate is a
separate, deliberate decision (Observability's call), not a side effect
of one run.
---
## LL-187
### Title
The "migrate the scheduler daemon" premise was wrong: it had never been supervised, and its pgqueuer deps were never installed
### Date
2026-09-13
### Lesson
The pilot was framed as migrating `human_systems_scheduler.py`'s live
daemon. Stream 0 found no `deploy/*.service`, timer, crontab or tmux
entry that ever ran it. The real job was "stand up a supervised daemon
where none ran", not "migrate a live one". The commit that had blocked
migration (Slack `WebClient` coupling) no longer applied after Slack was
retired. During rollout, `pgqueuer`/`asyncpg` were already listed in
`requirements.txt` but had never been `pip install`ed in the VM's venv.
A listed dependency is not an installed one. The bar the mission held
itself to also carries over: the double-fire was reproduced on demand
(`run_count = 2`), and dedup was shown by one `successful` row in
`pgqueuer_log`. Neither was just asserted, and live rollout isn't called
verified until real rows land.
### Future Guidance
Before migrating any daemon, find what actually supervises it in
production (systemd unit, timer, crontab). If nothing does, re-scope.
After deploying, confirm the dependencies are installed in the target
venv, not just listed, and test a new credential with a real connect,
not "the secret exists". Open items:
(1) Live-day verification was IN PROGRESS. All 7 jobs were registered
in `pgqueuer_schedules` but zero dispatches had happened yet. `eod`,
`weekly` and `comms_weekly` can't fire before Monday 2026-09-14. Confirm
real rows in `pgqueuer_log` / `pgqueuer_schedules.last_run` for all 7
before calling it verified.
(2) Do not migrate `intelligence/scheduler.py` yet. It has the highest
blast radius, so wait until this pattern has a production track record,
and plan a rollback path.
(3) `telegram-bots/revs/scheduler.py` is lowest priority.
(4) `SUPABASE_DB_URL` is the repo's first raw Postgres DSN (everything
else uses supabase-py REST), so it must be available wherever
`run-with-infisical.sh` sources secrets.
---
## LL-188
### Title
LL-149's fail-closed branch check was correct, but the shared checkout was never on that branch, so it silently refused about 64 cycles
### Date
2026-09-13
### Lesson
LL-149 made `git_commit()` refuse to commit unless it was on the
`self-improvement` branch. But `self-improving-system.service` ran in
the shared `/opt/starship-endeavour` checkout, which interactive sessions
leave on whatever branch they last used, essentially never
`self-improvement` at 04:30. So the fix, correct on its own, meant the
job never committed at all. Cycle commits stopped the day LL-149 shipped,
and about 64 cycles of evidence piled up uncommitted until a human
noticed. The refusal was only a log line nobody read. A fail-closed guard
is only half a fix if the deployment doesn't guarantee its precondition
and nobody hears when it refuses. This is easy to confuse with
`hq-evolution.timer`, which never touches git. The finding rests on
git-history timestamps, not a live `journalctl` check.
### Future Guidance
When adding a precondition check to a scheduled job, also make the
deployment guarantee that precondition, and alert (not just log) when
the check refuses. Here that means the dedicated worktree at
`/opt/starship-endeavour-self-improvement` via
`scripts/self_improvement/run_daily_cycle.sh`, plus a `notify()`
WARNING. Measure success by commit cadence
(`git log --all --grep="self-improvement: cycle"`), not by whether the
check behaves correctly. Open items:
(1) Live acceptance is not yet observed. The VM's next 04:30
`self-improving-system.timer` fire (or a manual run on that host) must
produce a pushed cycle-artifact commit. The worktree creation itself was
never run.
(2) The one-off ~64-cycle backlog commit landed on
`msn-0368-stage-2b-existing-capability-fixes`, not `self-improvement`. A
human needs to decide how to reconcile it.
(3) No capability owns self-improvement's own operational health
(heartbeat staleness, cycle-commit success).
---
## LL-189
### Title
garak "covered" prompt injection on paper but every recorded run hit Connection refused; promptfoo's first live run found a 3/3 hijack
### Date
2026-09-13
### Lesson
A probe that is wired to a target is not evidence about that target
until a run has actually connected. Every `garak_gate.py` report in
`reports/garak/` ended in `ConnectionError ... Connection refused`, so
the platform had zero real evidence on whether `xo-response` falls for
instruction hijack — promptfoo's first live run showed it does, 3 for 3.
Assertions have the same trap: the PII session-leak test "passed"
because its literal-phrase checks didn't match what the model actually
did (confidently fabricate a fake prior conversation). Tool coverage
claims must be checked against captured output, not against which tool
is configured to run which probe.
### Future Guidance
Before citing any eval/red-team tool as coverage, open its latest report
and confirm it reached the target and produced results. Write assertions
against real captured responses, then re-check them offline against that
same text. For the local Model Router: it serialises model calls, so run
promptfoo with `--max-concurrency 1` and set `timeout` on the HTTP
provider itself (`defaultTest.options.provider` does not override it);
don't use Python-style `(?i)` in promptfoo regexes (JS `RegExp`).
**Open items:** (1) the `xo-response` literal-instruction-hijack
vulnerability needs its own remediation mission — not done here.
(2) The CI `promptfoo` job runs on `ubuntu-latest`, which cannot reach
`127.0.0.1:8891`, so it skips every PR until a self-hosted runner exists
or the router becomes reachable; it is report-only (`continue-on-error`).
(3) deepteam's design excludes generative attacks like `PromptInjection`
on `glm-5.3:cloud` — a structural blind spot to remember when reading
its reports.
---
## LL-190
### Title
Only 4 of 14 queued raw-<button> files needed a Radix primitive; the screen-reader check is blocked by environment, not code
### Date
2026-09-13
### Lesson
A follow-up queue built from a survey of "raw `<button>`" usage is a
candidate list, not a work list: reading each file in full showed 10 of
14 were plain action buttons (or already delegated to an accessible
`Modal`/native `<details>`) needing no change, and the one real overlay
needed Dialog, not the Collapsible the pilot used. Separately, a
verification step that's impossible in the current environment will be
deferred forever unless the deferral names the environmental fix:
re-attempting the AT pass from the same headless worktree would have
produced the same non-answer the pilot already got. All before→after
accessibility claims here are verified by static prop-trace and
`tsc`/`next build`, not by listening.
### Future Guidance
For primitive migrations, read the whole file and match its real
interaction shape (disclosure vs. overlay vs. segmented toggle vs.
navigation) before picking a primitive; "no change needed" is a valid
per-file outcome. Wrap existing styled elements with `asChild` so no
`wb-*`/className edits are needed. Radix Dialog unmounts on close by
default, which silently kills slide transitions — use `forceMount` and
keep the original open-state classing. One file per commit, with
`tsc --noEmit` and `next build` before each.
**Open follow-up (deferred twice):** from a machine with real assistive
tech, run `npm run dev` in `lcars-portal/` and do one VoiceOver/NVDA pass
over `ApprovalQueue.tsx`, `MobileAlertDrawer.tsx` (Dialog) and
`LCARSNav.tsx` (Collapsible). Until then, treat the pilot's and this
mission's accessibility claims as code-traced only.
---
## LL-191
### Title
A fix for one service's git collision didn't become a convention until written into AGENTS.md, where 74 concurrent sessions actually read it
### Date
2026-09-13
### Lesson
LL-146 diagnosed the shared-working-tree failure and LL-149 fixed one
caller, but that chain only protected one service — and MSN-0377 found
LL-149's fix never fired in practice because the service still ran in
the shared checkout. Meanwhile a peer session self-corrected to a
worktree "per past lesson" that existed nowhere as a citable rule;
`AGENTS.md` had nothing on worktrees or shared checkouts. A lesson
recorded against one incident is not a standing rule other sessions
will find. The risk was live while writing the rule: the shared checkout
was dirty and sitting on an unrelated stale branch, with ~60 untracked
`data/self-improvement/runs/*` dirs and another session's modified CI
workflow.
### Future Guidance
Follow `AGENTS.md`'s "Concurrent session git safety" section: never
`checkout`/`switch` on `/opt/starship-endeavour` for real work — run
`git worktree add <path> -b <branch>` off `origin/main`; put a session
or mission ID in both the path and branch name; run `git worktree list`
/ `git worktree prune` after merge; give systemd services their own
dedicated worktree (MSN-0377 precedent). When a per-caller fix reveals
a pattern that can hit any session, promote it to `AGENTS.md` (the file
agents actually read) rather than leaving it in an LL entry.
**Open follow-up:** no enforcement exists — a pre-flight check or lint
rule for shared-checkout use is flagged as a legitimate future mission,
not built.
---
## LL-192
### Title
The brief's commissioned Tremor adoption failed its own verification gate; a local primitive extraction fixed the same duplication
### Date
2026-09-13
### Lesson
A brief that says "introduce library X, but verify it fits first" should
treat the verification as a real decision point. Tremor was React-18
compatible, but its `Card`/`Metric`/`Grid` theme through a fixed internal
`tremor-*` palette rather than CSS custom properties, and none of the
real tiles' needs (focus rings, tone-conditional colour, chip
breakdowns, badge-as-value, loading/error states) existed in its
primitives — net value ≈ 0, with real risk of a second design-system
fork. The grep hit list also shrank 9 → 6 real files once read: one form
grid, two call sites, and a "KPI-sounding" `CommandStatus.tsx` that
wasn't a stat grid at all.
### Future Guidance
Before adopting a UI component library, check (1) how it themes —
arbitrary CSS variables vs. a fixed palette that needs a Tailwind
colour-key remap — and (2) whether the actual call sites' per-component
behaviours exist in its primitives, or would all be rebuilt inside its
wrappers anyway. If the answer is "rebuilt anyway", extract a shared
local primitive instead (here `src/components/ui/KpiStat.tsx`:
`KpiStat`/`KpiCard`, byte-identical extractions) and put the choice to
the Captain. Don't consolidate across design systems mid-migration.
**Next seam, not done:** `knowledge-workbench/_components/LibraryKpis.tsx`
uses the shared `@/components/StatTile` on legacy LCARS tokens, not
`wb-*` — it belongs to [[legacy-app-page-migration]], not this
consolidation.
---
## LL-193
### Title
unified_memory.py's "not yet adopted by any caller" docstring was false, and "shipped and live" still wasn't proven against a real chat
### Date
2026-09-14
### Lesson
A module docstring that states its own adoption status ("Standalone
module. Not yet adopted by any existing caller") is a dated claim, not a
fact. Pre-flight grep found `daily_operations_cycle.py` importing
`unified_memory` at line 126 — a real live caller the docstring denied.
Anyone scoping a change from that docstring would have treated a live
dependency as safe to reshape. Separately, a feature can be deployed,
restarted and `active (running)` while its actual behaviour is still
unverified: `conversation_turns` held 0 rows at record time because no
real multi-turn exchange had happened yet, so "live" and "works" were
still two different claims.
### Future Guidance
Before relying on any docstring that describes who uses a module, grep
for the real importers (`grep -rln "<module>" --include=*.py .`) and fix
the docstring in its own commit if it has drifted, as `fe46d86f8` did.
When shipping a conversational feature from a session that can't act as
the Captain, record the end-to-end check as an explicit pending item.
**Open follow-up, not yet done:** next time the Captain sends XO two or
more messages in one sitting, confirm (a) both turns land in
`conversation_turns`, and (b) XO's reply references earlier-turn content,
not just live DB state. Best-effort writers like
`_log_conversation_turn()` never raise into the reply path, so a silent
write failure will look exactly like "no messages yet" — check the row
count, don't infer it.
---
## LL-194
### Title
unified_memory's RELATIONSHIPS write and COMMAND recall were silent no-ops the mission brief assumed already worked
### Date
2026-09-14
### Lesson
The brief told Stream 5 to write distilled facts into Graphiti "via
unified_memory.py's remember()" — but `remember()` only ever wrote to
mem0; `remember(RELATIONSHIPS, ...)` silently did nothing. The Stream 6
benchmark then exposed a second one: the existing COMMAND recall route
scored 0/8 because `_recall_table()` only supports exact-match `.eq()`
filters and `"query"` isn't a column on `decisions`, so natural-language
recall on that path never existed. A typed memory API can accept every
memory type in its signature while doing nothing for some of them, and
only an end-to-end measurement (not reading the call site) reveals it.
Measuring the pre-existing path as a baseline is what turned "62.5%"
into an honest result instead of an unanchored number.
### Future Guidance
When a brief says "write/read via existing function X", trace X down to
the store it actually touches for the specific type/route you need
before building on it. Always benchmark the old path alongside the new
one. When an in-place `ALTER COLUMN TYPE` on a live table is blocked,
the additive-column-plus-new-RPC route (as done for `research_memory`)
avoids the migration risk entirely. **Open items carried forward:**
(1) mem0 SEMANTIC/FACTUAL backend repoint to Supabase/mistral-embed is
deliberately not done — blocked by mem0's `vecs` raw-Postgres connection
requirement and lack of a native mistral embedder; filed as Technical
Debt in the SUOC Platform Registry. (2) `decisions` has no
`consolidated_at`-style marker, so the nightly job re-reads a trailing
24h window and may re-process. (3) Re-run
`scripts/memory/benchmark_locomo.py` after the nightly job has fired
several times on organically grown history (the 62.5% came from a
hand-seeded graph, n=8, token-overlap scoring). (4) Stream 2's real
Telegram multi-turn verification is still pending.
---
## LL-195
### Title
Critical-slowing-down warning killed at Stream 0: 31 readings is noise, and limits fit to a strained baseline would silence alerts
### Date
2026-09-14
### Lesson
A cheap Stream 0 kill-gate earned its keep: rolling lag-1 AR(1) on 31
capacity readings had the wrong sign at every window, standard errors
1.8–2.5x the effect size, and a range inside a shuffled-data null — no
signal to wire. The less obvious finding killed Stream 1 too: personal
SPC/CUSUM limits need an in-control baseline, and the Captain's own
history is 71% orange/red, above two of three population thresholds.
Limits fitted to it would have centred "normal" on strain and silenced
`accumulating_strain`/`sustained_high_strain` — worse alerting dressed
as personalisation. The binding constraint was history length, not
method choice, so no alternative statistic rescues it.
### Future Guidance
Before personalising any threshold from a person's own history, check
whether that history contains an in-control period at all; compare its
baseline against the population constants it would replace. For any
time-series early-warning method, compare series length against the
method's literature (hundreds+ points) and test against a permutation
null before building on it. Don't commission CAP-1 wiring into
`capacity_gate.py`; re-run `python3 -m
core.health.stability_statistic_validation` after ~6 months of
sustained check-ins and revisit only if AR(1) turns positive and clears
the null band. CAP-2 (contextual bandit) needs its own data-sufficiency
gate first. Stream 3 also had no ground truth (`burnout_profile` empty,
no crash/flare table).
**Open, not fixed:** `tools/mint_id.py MSN` minted a colliding ID
(0377) because literal `MSN-9999` placeholders in two test files and the
MSN-0368 record push `scanned` past `_MAX_SANE_DRIFT`, so the auto-bump
is refused. Fix: make `true_max_for_prefix()` ignore test files and
placeholder sentinels. Until then, check minted IDs against
`knowledge/missions/` before use.
---
## LL-196
### Title
A 24-minute merge wait was one advisory step serialised ahead of blocking gates, scanning 563MB its pre-commit-only exclude never hid
### Date
2026-09-19
### Lesson
Merge latency was 24m42s, but every blocking check took under a minute.
The cause was job shape: advisory `detect-secrets` (23m24s,
`continue-on-error`) ran as a serial step ahead of bandit and ruff-check
in one `pre-commit` job, so the real gates waited on a check that gated
nothing. Its own slowness had a second, hidden cause. The 2026-09-15
`exclude:` for `data/self-improvement/runs/` lived in
`.pre-commit-config.yaml`, which pre-commit applies only when it runs the
hook. CI called the bare `detect-secrets scan` CLI directly, so the
exclude never applied and every run rescanned 611 files (563MB). Splitting
the job into parallel jobs and passing the exclude to the CLI cut it to
about 2 minutes. Branch protection also required only `check`, so the
wait the team saw was a team-practice trust gate, not a GitHub-enforced one.
### Future Guidance
Profile CI per step from a real run before optimising, and never place an
advisory step in the same job ahead of a blocking one. Give advisory
checks their own job, kept out of the merge gate's `needs`. Any `exclude:`
or file filter in `.pre-commit-config.yaml` is pre-commit's, not the
tool's. When CI calls a hook's tool directly, mirror it with the tool's
own flag (`detect-secrets scan --exclude-files ...`), and add `--no-verify`
when only new-vs-baselined matters. An aggregate gate (`merge-gate`,
`if: always()`) must treat `failure`, `cancelled` and `skipped` as
failures. It may accept a skipped conditional job only after re-checking
the upstream matrix output was really empty. Prove each fail-closed path
before making the gate required. Compare what branch protection actually
requires (`gh api repos/.../branches/main/protection`) with what the team
waits on. Patch only `required_status_checks`, then read protection back.
Still open: the `changes` job's `core` path filter appears to over-match
(a `python-ci.yml`-only change set `core = true`). Also open:
detect-secrets flakiness on two IBM Cloud IAM Key fixtures (#189).
The record also notes 16 of 18 cited `ADR-NNN` numbers lack a backing file.
---
## LL-197
### Title
A second capture channel writing straight to the task table hid the real gap: captures never became tasks, and capacity vocab had forked
### Date
2026-09-19
### Lesson
The confirmed gap was that capture never became a task. Portal and voice
wrote `captured_items`, but Telegram wrote `personal_tasks` directly,
skipping classification, provenance and routing. Each surface also
interpreted capacity in its own dialect. `follow_through_engine.py` had
reimplemented raw `"orange"`/`"red"` strings rather than calling the
canonical Green/Amber/Red/Unknown mapper. The fix added no new
architecture. It sent every channel to one intake, made actionability a
judgement independent of classification, enforced idempotency with a
database unique index (not app logic), and moved the drifted consumer
onto `capacity_zone_from_checkin()`. Behaviour was proven identical by
existing tests. Remember became a filtered view of the same adapter, not
a new domain.
### Future Guidance
Before adding a capture or task feature, list every writer to the target
table (`grep -rn "personal_tasks"` across Python and TS). A channel that
inserts downstream directly is a competing truth, not a shortcut. Enforce
"exactly once" with a partial unique index (as `0217` did for
`personal_tasks.source_capture_id`) and handle the unique violation as
"already routed": no second row, no repeat confirmation. Write data
before sending notifications, and wrap `notify()` so a send failure can't
look like a routing failure. When one domain concept appears in several
modules, grep for raw vocabulary (`"orange"`, `"red"`) and migrate
consumers onto the canonical mapper rather than adding another. In a git
worktree, failures in tests that read gitignored runtime data (e.g.
`logs/decisions/*.json`) are environment gaps. Confirm them on unmodified
main before calling them regressions.
Still open: `npm run typecheck` in `lcars-portal/` was never run (no
`node_modules`). `google-tasks/sync/route.ts` is a third, unaudited
direct-insert path into `personal_tasks`. Also open: web voice capture,
TS-side natural-language date parsing for Ready Room, and the dead
`intelligence/adhd/task_nudge_scheduler.py` (flagged for a dead-code sweep).
---
## LL-198
### Title
The retired /medical dashboard was still the link target for the four highest-severity wellness alerts
### Date
2026-09-19
### Lesson
Retiring a page is not done until every inbound link has moved. The
legacy `/medical` dashboard, with dead check-in/pulse tabs, was still the
`href` for the red-flag, emotional-load, pain-critical and pain-elevated
alerts in `lcars-portal/src/lib/alerts.ts` — a dead end on exactly the
path that matters most when something urgent fires, while the adjacent
recovery-debt alert had already been repointed. The broader map showed
the same shape at the surface level: 6/9 Captain intents had a single
clean owner, and the 3 splits ("I'm stuck", "Still can't start", "Too
much") all fell along the XO-bot/capacitybot boundary, where capacitybot
runs its own ranking engine Number One and XO can't see.
### Future Guidance
When retiring a route, grep for its path in alert/notification hrefs,
nav sources and deep links, not just page imports, and repoint
siblings together. Separate safe one-line fixes from decision-sized
findings and record the latter rather than half-fixing them. **Open
6B/redesign inputs, not done:** Hub (PWA front door) has no link to Ready
Room, Capture or capacity check-in; the Command Centre JS Telegram
sender is still an unreconciled duplicate (flagged by
`tools/check_notification_senders.py`) and its in-app notification store
is decorative; capacity-gated delivery covers only follow-through
nudges; web-push and Telegram have no shared dismissal ledger; three
unrelated "Captain's Log" surfaces collide on name; draft state is lost
in capture/quick-add/pause-note fields; no web voice capture; no
`/remember` read in XO bot. The deterministic experience test matrix is
deferred until "I'm stuck"/"Too much" routing converges with Mission 5.
---
## LL-199
### Title
Mission 5's evidence engine already existed in capacitybot; the real defects were dead file reads and write-only tables
### Date
2026-09-19
### Lesson
Six discovery streams found the canonical evidence model already built
and proven in capacitybot (`evidence_engine.py`, `intervention_engine.py`,
`capacity_interventions`/`_events`), so the job became "generalise one
model, close Ready Room's missing feedback loop" — not a second engine.
The defects discovery did find were all silent: `mission_knowledge_store
.py` read two `.jsonl` files that don't exist, returning empty/None while
live-wired into mission ranking; `insight_outcomes` was write-only (its
reader had zero call sites); and CI's path filter had never run all of
`telegram-bots/capacitybot/`, hiding import-time `os.environ[...]` and
unmocked `_get_supabase()` isolation gaps until this PR touched enough
files.
### Future Guidance
Before building an engine, search for an existing one on bypass surfaces
(separate bots, side tables). For any function that reads a file or
table, confirm the source exists and has a live reader — a silent empty
return is indistinguishable from "no evidence". Use the real six-state
posture vocabulary (`ENGAGE/STEADY/PROTECT/RECOVER/RESET/UNKNOWN`), not
the brief's three-state wording. For bots that read env vars at import,
use a `conftest.py` with `os.environ.setdefault` plus an autouse fake-db
fixture, and verify in a fresh venv with the vars unset. **Open
residuals:** A — no mission_id → mission_type mapping exists, so the
mission-ranking blend stays a no-op until something records type at
write time; B — `PickUpBanner.tsx` has no evidence-writing hook (6B
input); C — `get_decision_quality_stats()` reads real data but has zero
callers (the live G008 gate is `core/intelligence/decision_effectiveness
.py`); D — the 50-item accommodation list is classified, not
auto-backlogged. Merge SHA was left as "recorded post-merge" in the
record.
---
## LL-200
### Title
Switching to one fixed dark surface exposed latent bugs and an accepted contrast trade-off the old 5-theme system had hidden
### Date
2026-09-20
### Lesson
Changing the default context a UI renders in surfaces defects that were
invisible under the old one. Tailwind `/NN` opacity modifiers (e.g.
`bg-wb-bg/80`) silently no-op on plain-hex CSS variables — found and
fixed 6 separate times; text without an explicit colour inherited the
parent's computed dark ink and vanished on the Read surface; the Number
One button collided with the now-taller Sidebar. The same applies to
decisions: the `*-on` text contrast trade-off (1.33–2.9:1 on dark) was
accepted when dark was one optional theme, and is now the permanent
default. A mission doc's "last consumer" claim for `LCARSPanel` was also
stale — a fresh importer check found another.
### Future Guidance
When a change alters the default theme, surface or layout height,
re-check previously accepted trade-offs and grep for patterns that only
looked right under the old default. Use live screenshots where possible;
the mode-scoping bug was caught that way, not by inspection. Re-check
importers before deleting a "last-consumer" component. **Open residual
debt:** (1) fresh Captain decision on the `*-on` contrast trade-off at
its new exposure; (2) repo-wide sweep for `/NN` opacity modifiers on
plain-hex tokens (`WatchingView.tsx`, `InboxView.tsx`, `ThinkView.tsx`,
`ContentStudio.tsx`, `JobsView.tsx`, `LibraryView.tsx`, `ConsultView.tsx`
and more); (3) retire `(app)/stage-progression/page.tsx` onto
`WorkbenchPanel` to unlock deleting `LCARSPanel.tsx`; (4) four mockup
elements never verified or built (What Helps ratio, Watch For list,
background photography licensing, Ready Room Context counts); (5)
Sidebar motto and "More" sheet not Captain-confirmed; (6) typography and
spacing/radius tokens never formalised; (7) `focus-visible` gaps in
`intelligence-workbench` sub-pages; (8) most phases verified only by
code review/tests — production user testing is the real check;
SUOC registry entry undecided; branch not yet promoted to `main`.
---
