---
status: "proposed"
date: 2026-10-03
decision-makers: Captain TJR (final), Chief Engineer (advisory)
consulted: XO (gatekeeper review of auto-generated PRs), Chief of Staff (cost/priority)
informed: all officers; owners of core/engineering/, scripts/self_improvement/, core/security/
---

# Agent-loop coder for engineering handoffs: gated pilot, not a replacement

## Context and Problem Statement

The self-improvement → HQ Evolution → `ENG-HANDOFF-*` → draft-PR pipeline
writes code with a **single-shot** model call:
`core/engineering/batch_coding.py` sends each handoff, plus context from
`core/engineering/context_enricher.py`, to the Mistral Batch API
(`codestral-latest`). It gets back either a unified diff (PATCH) or whole
files (FULL_FILE). The model cannot search the code, open a file it wasn't
given, run a test, or retry. It sees only what the enricher put in the
prompt:

- the mission body;
- the top 3 keyword-matched files;
- cortex_suite structural context;
- since PR #332 (branch `claude/brave-keller-jh0fzo`), the files that import
  those 3 files and the tests that cover them.

A review of the MIT-licensed ECC agent pack (github.com/affaan-m/ECC) raised
a question. Modern coding agents work in a loop: look, edit, test, retry.
Should larger handoffs go to a loop like that (Claude Code headless or the
Claude Agent SDK) instead of one batch call?

This is more than a provider swap. An agent loop **modifies files and runs
commands itself**. ADR-030 says cloud backends do plan and review work and
are never trusted to modify files directly. Today's batch coder satisfies
that because the model only returns text, and our own code (`github_pr`, in
a throwaway worktree) decides what gets written. So the question is whether,
and under what controls, a cloud model may take actions inside the platform
rather than only return text.

## Decision Drivers

* **Quality of AI-authored changes.** Single-shot output misses callers,
  invents APIs and can't check itself against tests. A loop can.
* **ADR-030's trust boundary.** Any change to who may modify files needs an
  explicit decision. It can't happen as an implementation detail.
* **Prompt injection becoming code execution (OWASP LLM01).** Handoff
  content can come from HQ Evolution's *external* discovery
  (`scripts/self_improvement/external_discovery.py`: GitHub, Hacker News,
  arXiv). A text-only coder that receives injected text produces bad text,
  which the `_is_fenced_path` fence and XO review then check. An agent with
  shell and write tools that receives the same text can *act* on it on the
  VM.
* **ADR-032's guardrails coverage.** Every external cloud call is meant to
  pass through `core/security/llm_guardrails.py`
  (`secure_outbound_prompt`). An agent loop sends file contents back to the
  model on every turn, which a single redaction before the first call does
  not cover.
* **Cost and duration.** Mistral batch is cheap and asynchronous. An agent
  loop costs several times more per handoff, and the actual figure is not
  measured. `config/self_improvement_policy.json` already sets bounds on the
  overnight run (`run_duration_budget_minutes`, batch sizes), and those must
  continue to hold.
* **The new-files-only policy.** `batch_coding._open_files_pr` holds back
  edits to *existing* files from the PR. Only version bumps, or the
  `AUTO_ENGINEER_ALLOW_EXISTING_EDITS` override, get through; everything
  else becomes a manual-apply artifact. This policy limits the pipeline's
  value more than coder quality does, and relaxing it is a separate Captain
  decision.
* **ADR-020, capability reuse before creation.** Reuse the existing
  pipeline: worktree-based `github_pr`, XO review, the fence, the
  batch/collect timer. Add no new scheduler instance; the MSN-0368 Stream 6
  consolidation is still in progress.
* **Concurrent-session git safety (AGENTS.md).** Any new git-writing actor
  works in a worktree whose path and branch include the mission ID.

## Considered Options

1. **Status quo plus grounding.** Keep the single-shot Mistral coder, with
   PR #332's dependents/tests grounding and diff-scoped XO checklists.
2. **Full replacement.** Every handoff goes to an agent loop.
3. **Gated pilot.** An agent loop as an opt-in provider for a narrow class
   of handoffs, sandboxed and side by side with Mistral, and only after a
   baseline exists.
4. **Adopt an external harness wholesale.** Install a third-party
   agent-harness plugin (e.g. ECC's `ecc@ecc`) and its hooks on the VM.

## Decision Outcome

Proposed option: **"3. Gated pilot"**. It is the only option that tests
whether a loop actually improves outcomes without first widening ADR-030's
trust boundary platform-wide or opening a path from injected text to code
execution. Option 1 stays the default and the fallback throughout.

The pilot proceeds only if **all** of these hold:

1. **A baseline exists first.** At least 2–3 weeks of overnight cycles run
   with PR #332 merged. The acceptance rate of batch-coded PRs and
   artifacts is recorded from `outcome_evaluation` / `opportunity_store`:
   merged or applied, against declined or needing rework. If the rate is
   already acceptable, close this ADR as **rejected**.
2. **Provenance gate.** Only handoffs that come from *internal* findings
   (the self-improvement `EvidenceCollector` / `internal_discovery.py`) are
   eligible. No handoff whose content came from external discovery goes to
   the agent loop, whatever the risk level or approval.
3. **Sandbox.**
   - The loop runs in a fresh worktree created from the committed tree,
     with the path and branch named for the mission ID.
   - It gets no credentials: no `GITHUB_TOKEN` and no provider keys other
     than the model API's own.
   - Its only outbound network is the model API.
   - Its tool allowlist is read, search, edit, and one fixed test command
     scoped to the changed paths. There is no general shell.
   - Our own code, not the agent, then runs the `_is_fenced_path` fence,
     opens the draft PR through `github_pr`, and runs `xo_review`, exactly
     as today.
4. **Guardrails.** The outbound prompt goes through
   `llm_guardrails.secure_outbound_prompt`. Per-turn exposure is limited by
   what the worktree can read: the fenced paths must be absent from it or
   unreadable. Before the pilot, the fence itself needs one fix: its `.env`
   pattern does not match the tracked file `lcars-portal/env.local`.
5. **Budget.** A per-handoff cap on turns and spend, and a per-cycle cap on
   the number of handoffs, both in `config/self_improvement_policy.json`. A
   handoff that hits its cap fails closed: it is left as an artifact and
   never pushed partially.
6. **Provider switch.** The coder is selected by a field on the handoff
   (e.g. `Coder: mistral | agent`), defaulting to `mistral`, so turning the
   pilot off is a config change, not a code change.
7. **Existing-file policy is unchanged.** The pilot does **not** relax the
   new-files-only policy. Agent-loop edits to existing files go into the
   same deferred artifact and XO review as Mistral's. Whether those edits
   may reach a PR is a separate decision for a later ADR, made with the
   pilot's data.

### Consequences

* Good, because the trust boundary widens only for one narrow, sandboxed,
  internally sourced class of work, with a one-setting rollback.
* Good, because a side-by-side comparison on the same handoffs gives real
  evidence for or against a wider rollout.
* Good, because it reuses the existing PR path, fence, XO gate and timer.
  Nothing parallel is built (ADR-020).
* Bad, because it adds a second coder provider to maintain, and a sandbox
  definition that has to be kept tight.
* Bad, because handoffs from external discovery, which may be the ones that
  would benefit most, are excluded by design.
* Bad, because cost per handoff goes up, by an amount not yet measured.
* Neutral, because if the baseline shows step 1 was enough, this ADR is
  rejected and nothing beyond PR #332 is built.

### Confirmation

* Pilot handoffs carry `Coder: agent` in their `ENG-HANDOFF-*` file, and
  every resulting PR or artifact names its coder, so the comparison can be
  queried.
* A test asserts that a handoff of external-discovery origin is never sent
  to the agent provider.
* A test asserts that the agent subprocess environment contains no
  `GITHUB_TOKEN` and no other credential variables.
* A test asserts that `_is_fenced_path("lcars-portal/env.local")` is
  `True`.
* The go/no-go review for a wider rollout compares acceptance rate, rework
  rate, XO `hold` rate and cost per accepted change between the two
  providers over the same window.

## Pros and Cons of the Options

### 1. Status quo plus grounding

* Good, because it costs nothing more and has no new attack surface.
* Good, because PR #332 already closes the main known gap: callers and
  tests the coder couldn't see.
* Bad, because a single shot still can't run tests or recover from its own
  mistakes.

### 2. Full replacement

* Good, because every handoff gets the strongest coder.
* Bad, because it widens ADR-030 for all handoffs at once, including ones
  that come from external discovery. That makes LLM01 a code-execution risk
  everywhere at once.
* Bad, because the overnight cost and run time are unknown and probably
  break the existing time budget.
* Bad, because there's no baseline to show it's better.

### 3. Gated pilot

* Good, because it produces evidence before commitment and the risk is
  contained by the provenance gate and the sandbox.
* Bad, because it is more machinery (a provider switch, a sandbox, budgets)
  than option 1.

### 4. Adopt an external harness wholesale

* Good, because the pre-built material is extensive.
* Bad, because it installs third-party hooks that run on every tool call on
  a shared VM with many concurrent sessions: a supply-chain and performance
  risk.
* Bad, because it brings its own ADR and learning registries, the
  duplication ADR-020 and AGENTS.md's check-first rules exist to prevent.
* Bad, because our headless coder doesn't run Claude Code today, so most of
  it wouldn't even load.

## More Information

* Amends ADR-030 (Engineering Router execution model). This conflicts with
  ADR-030 as currently worded until accepted. On acceptance, ADR-030's "no
  cloud backend modifies files" rule gains one named exception: the
  sandboxed pilot provider defined above.
* Extends ADR-032 (LLM application security baseline). The agent loop is a
  new external-cloud dispatch point and must be added to that ADR's
  coverage list.
* Applies ADR-020 (capability reuse before capability creation).
* Origin: an ECC review followed by a Chief Engineer review, both in the
  same session as PR #332. Step 1 of that review, the dependents/tests
  grounding in `context_enricher.py` and the diff-scoped defect checklists
  in `xo_review.py`, is PR #332 and is independent of this ADR.
* Unverified here: the actual per-handoff cost and duration of an agent
  loop, and the current acceptance rate of batch-coded PRs. Both are inputs
  to condition 1, not assumptions this ADR relies on.
