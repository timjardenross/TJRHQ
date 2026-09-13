# USS-TJR-MSN-0374 — OSS Capability Search Closures (Storybook a11y, pip-audit, deepteam, log4brains, garak handoff) — Closing Record

Mission source: `knowledge/OSS-Capability-Search-2026-09-12.md`, §8 "Recommended Sequence → Now" — five items flagged as near-zero-risk, independently-landable closures from a same-day 9-agent GitHub OSINT capability search. Pre-flight found the source doc's own framing already stale on two items (Storybook a11y addon already installed — the real gap was CI enforcement, not the addon; gitleaks already present, nothing to do there) and one item genuinely inexecutable from a sandbox as originally assumed (garak against the live router) — see below, that assumption turned out to be wrong mid-mission.

## Stream 1 — Storybook a11y CI enforcement

PR #201. `@storybook/addon-a11y`/axe-core/vitest-axe were already installed; the gap was that nothing ran a11y checks across all stories in CI. `@storybook/test-runner` and `@storybook/addon-vitest` were both tried and found incompatible with Storybook 10.5.0 — landed a hand-rolled Playwright + axe-core script (`lcars-portal/scripts/storybook-a11y-check.mjs`) instead, added as a report-only `test-storybook` CI job. **Real captured result:** 28 stories checked, 8 color-contrast violations (all `serious`), 145 passing axe checks. Fixing the 8 violations is explicitly out of scope — tracked as follow-up.

## Stream 2 — pip-audit pre-commit + CI gate

PR #202. Added as a local `.pre-commit-config.yaml` hook plus a CI job, both report-only, scoped to all 15 tracked `requirements*.txt` files. **Real captured result:** 17 distinct findings across 12 package@version pins in 5 of 15 files (`services/revs-content-agents`: 8, `core/security/requirements-llmsec.txt`: 3, `core/quality/requirements-ragas.txt`: 3, `core/quality/requirements-garak.txt`: 2, `platform-runtime/requirements.txt`: 1); 9 files clean; `telegram-bots/revs/requirements.txt` failed to resolve at all (pre-existing `httpx<0.29` conflict, unrelated to CVEs, flagged not fixed). Triaging the 17 findings is out of scope — tracked as follow-up.

## Stream 3 — deepteam alongside deepeval

PR #204. Added `core/quality/deepteam_scan.py` in its own isolated venv (`platform-runtime/.venv-deepteam`, `core/quality/requirements-deepteam.txt`), reusing the existing `_ModelRouterJudge` backend as deepteam's simulator/evaluator/target — no second judge model stood up, `build_learning_loop.py`'s existing `deepeval` caller untouched. **Surprising fact, verified independently during integration:** the Model Router (`127.0.0.1:8891`) was actually reachable this whole mission — contrary to the mission pre-flight's "VM-only, unreachable from sandbox" premise (which was true for a prior session/sandbox but not this one). So this ran as a genuine production scan, not a stub. **Real captured result:** Bias × 4 subtypes + PIILeakage × 4 subtypes, Base64/ROT13 attacks, 8/8 passing, CVSS 0.0, 0 errored. Report at `reports/deepteam/20260913T004113Z.md` (+ native JSON). Real limitation disclosed, not hidden: deepteam's *generative* attack methods ask the simulator to draft jailbreak content, and the aligned `glm-5.3:cloud` model refuses that meta-prompt, surfacing as an evaluation error rather than a clean pass/fail — only deterministic-transform attacks (Base64, ROT13) were exercised by default.

## Stream 4 — log4brains ADR browsable site

PR #200. Confirmed `core/governance/architecture-decision-records/` as canonical (per the SUOC Platform Registry's own citation of its `ADR-NAMESPACE-MAPPING.md`, since the literal mapping file no longer exists standalone in the tree). Added repo-root `package.json` (none existed before) with `npm run adr:build`, `.log4brains.yml` pointing at the canonical directory, no ADR content changes. **Real captured result:** `log4brains build` actually run, produced `.log4brains/out/` with all 10 canonical ADRs present and correctly titled (verified by grep against generated output, e.g. ADR-027 "Whole-of-system principle...", ADR-020 "Capability reuse before capability creation"). No hosting/auto-deploy decision made — manual build script only, per scope.

## Stream 5 — garak_gate.py handoff, then a real run + a real bug found

PR #199 shipped the documentation-only handoff (`reports/garak/README.md`, exact command, no code changes) as originally scoped, since the mission pre-flight's premise — the Model Router is VM-only, unreachable from a sandbox — held for that agent's sandbox. **During integration, the same premise was re-tested and found false for this session** (the router answered `curl 127.0.0.1:8891/health` directly), so `garak_gate.py` was actually run for real:

- First run (default probes `hallucination,promptinject`): garak errored immediately with `Unknown run.spec: probes.hallucination` — that probe name doesn't exist in the installed `garak==0.17.0` (only `packagehallucination` does) — garak ran **zero** probes and exited 0, and `garak_gate.py` still printed **"PASS — 0 confirmed hit(s)"**. This is a real, reproducible bug: a probe-name/version mismatch produces a false PASS with no actual scan having occurred, and the gate has no check that distinguishes "clean run, zero hits" from "no probes ran at all."
- Second run, corrected to `packagehallucination,promptinject`: hit a genuine 120-second read-timeout against the router. Traced to real contention — a separate concurrent peer session was independently running `garak_gate.py` against the same production router at the same time this mission's Stream 3 was also hammering it with `deepteam`. The gate correctly reported **FAIL** on this occasion (non-zero garak exit), which is the correct behavior for an execution failure — the bug is specifically in the silent-zero-probes-still-PASSES case above, not in this path.
- Per user direction mid-mission, further garak retries were deprioritized rather than chased to a clean pass/fail verdict — the router was under real, shared load from multiple sessions and forcing another attempt would have added to that contention rather than resolved it.

**Net for Stream 5:** the handoff doc shipped as scoped; a real execution attempt happened (not scoped, but the premise justifying "handoff only" turned out to be false, so it was the honest thing to do once discovered); it surfaced one real, unfixed bug (`DEFAULT_PROBES` typo → false PASS) and one real, transient operational condition (router contention under concurrent multi-session scanning), both recorded in the Observability capability's Technical Debt rather than silently dropped. **The `DEFAULT_PROBES` bug fix itself was not applied** (a one-line change, deliberately left for a follow-up pass rather than expanding this mission's diff after the fact) — see Registry Next Planned Evolution.

## SUOC Platform Registry (updated this pass)

- **Observability:** rewritten to reflect two real live-router runs (garak's bug + contention finding; deepteam's first real 8/8-passing scan), Engineering Confidence raised 60%→65%, Technical Debt and Next Planned Evolution both updated with the specific, actionable follow-ups.
- **CI/CD & Supply-Chain Hygiene:** Dashboard row updated to note the two new report-only gates (pip-audit: 17 findings; Storybook a11y: 8 violations) and their untriaged-backlog status; Engineering Confidence adjusted 85%→82% to reflect the two new open backlogs (not a regression — new visibility into pre-existing risk that was previously undetected).
- **Governance:** Next Planned Evolution gained a note that a browsable ADR site now exists via log4brains, without touching the still-open ~16-ADR formalization backlog itself.

## Follow-up work identified (not this mission's scope, flagged for a future mission)

1. Triage the 17 pip-audit findings (12 package@version pins across 5 files); fix the `telegram-bots/revs/requirements.txt` resolution failure (pre-existing `httpx<0.29` conflict).
2. Triage the 8 Storybook color-contrast violations (Input/Navigation/Progress design-system stories); flip `test-storybook` from report-only to blocking once clear.
3. Flip `pip-audit`'s CI/pre-commit gate from report-only to blocking once its findings are triaged.
4. Fix `garak_gate.py`'s `DEFAULT_PROBES` default (`"hallucination,promptinject"` → `"packagehallucination,promptinject"`) — a one-line change; also consider adding a check that a zero-probes-ran garak exit doesn't silently count as PASS.
5. Once the probe fix lands, re-run `garak_gate.py` against the live router for a first clean pass/fail verdict — coordinate timing with other sessions to avoid the contention/timeout seen during this mission.
6. Decide whether either the garak gate or `deepteam_scan.py` should become a blocking pre-activation/deploy check (explicitly this mission's non-decision, per scope — Observability's own call).
7. If deepteam's generative-attack coverage (PromptInjection, Roleplay, ...) is wanted, it needs a non-aligned or explicitly-consenting simulator model — `glm-5.3:cloud` refuses the jailbreak-drafting meta-prompt by design.
8. Decide on hosting/publishing for the log4brains ADR site (currently local-build-only, `.log4brains/out/` git-ignored) — not this mission's call.

---
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015kBLmXs4TVKDnVy7TPihkz
