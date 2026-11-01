# Mission Brief

## Mission Header

- **Mission ID:** USS-TJR-MSN-0374
- **Priority:** P1 — five independently-landable, low-risk items; no reason to hold any of them
- **Source:** `knowledge/OSS-Capability-Search-2026-09-12.md`, §8 "Recommended Sequence → Now" (five items identified as near-zero-risk in a same-day, 9-agent GitHub OSINT capability search)

## Pre-flight

1. **Existing-entry check.**
   ```
   grep -n "addon" lcars-portal/.storybook/main.ts
   → "@storybook/addon-a11y", "@storybook/addon-docs", "@storybook/addon-mcp" — ALREADY installed,
     plus axe-core, vitest-axe, eslint-plugin-jsx-a11y already in lcars-portal/package.json.

   grep -n "pip-audit\|pip_audit" .pre-commit-config.yaml
   → not found. Real gap.

   grep -rn "deepteam" platform-runtime/requirements.txt core/quality/
   → not found. Real gap.

   grep -rln "log4brains" . --include="*.md" --include="*.json" --include="*.yaml"
   → only the search-report doc itself. Real gap.

   ls reports/garak/
   → missing/empty. core/quality/garak_gate.py exists (12KB, executable, has a working
     --router-url CLI defaulting to http://127.0.0.1:8891) but has never produced a report.
   ```

2. **Premise verification.**
   ```
   Source doc's item 1 claim: "Storybook a11y addon" is a quick win to ADD.
   -> ACTUALLY TRUE: "@storybook/addon-a11y" ^10.5.0 is already in package.json and
      .storybook/main.ts (confirmed by direct grep, not assumed from the search report).
      The Registry's WCAG-contrast debt is real despite this — because .github/workflows/
      lcars-portal-ci.yml only runs `npm run typecheck / lint / test` (vitest); there is no
      `test-storybook`/axe-CI step, so a11y coverage only exists on the specific component
      tests that happen to import vitest-axe themselves, not systematically across every
      story. Stream 1 below is corrected to "wire systematic enforcement," not "install
      the addon" — the source doc's framing of this item was already stale.

   Source doc's item 5 claim: run garak_gate.py against the live Model Router.
   -> VERIFIED NOT POSSIBLE FROM A SANDBOXED/REMOTE DEV SESSION: `curl 127.0.0.1:8891/health`
      from this session times out — the Model Router only runs on the production VM. This
      stream is an operational task for whoever has VM/systemd access, not something a
      remote coding session can close out itself. Scoped accordingly below.

   Source doc's claim: gitleaks needs adding.
   -> ALREADY FALSE at doc-write time, and confirmed again now: gitleaks is already a
      `.pre-commit-config.yaml` hook. Not included in this mission (nothing to do).
   ```

3. **Explicitly not in scope.** (see below)

## Explicitly Not In Scope

- **Full search consolidation, memory wiring, scheduling pilots, or any "Next"/"Later" item** from the same source doc (`pgqueuer`/`procrastinate`, `promptfoo`, `crawl4ai`, `FlashRank`, `whisper.cpp`, Radix/shadcn re-theme, GPT-Researcher, mini-swe-agent/PR-Agent). Each is a separate, larger mission with its own pre-flight.
- **Retroactive a11y remediation of every existing LCARS component.** This mission wires the *enforcement mechanism* (Stream 1); fixing every violation it then surfaces is follow-up work, tracked separately once the first CI run produces a real punch list.
- **Wiring `garak_gate.py` as a blocking pre-activation/deploy gate.** Stream 5 only gets a first real pass/fail verdict from the live router; whether it becomes blocking is the Registry's own "Next Planned Evolution" decision for Observability, not this mission's call.
- **Adding gitleaks.** Already present; nothing to do.
- **Any change to `deepeval`'s existing shadow-mode caller in `build_learning_loop.py`.** `deepteam` (Stream 3) is additive/parallel, not a replacement for that integration.

## Scope / Streams

### Stream 1 — Enforce Storybook a11y systematically (lcars-portal)
The addon and axe-core are already installed; the gap is that nothing runs it across all stories in CI. Add a `test-storybook` step (Storybook 10's test-runner + `@storybook/addon-a11y`'s CI mode, or `axe-playwright` against `build-storybook` output — pick whichever fits the existing Vite/Vitest setup with least new tooling) as a new job in `.github/workflows/lcars-portal-ci.yml`. Non-blocking on first landing (report-only) so the initial violation count doesn't gate an unrelated PR; flip to blocking in a fast follow-up once the backlog it surfaces is triaged.

### Stream 2 — `pip-audit` pre-commit + CI gate
Add `pip-audit` as a `.pre-commit-config.yaml` hook (mirror the existing `bandit`/`ruff-check` local-repo pattern) scanning `platform-runtime/requirements.txt` and any other tracked `requirements*.txt`. Non-blocking (report-only) on first landing, same reasoning as Stream 1 — an unknown existing CVE backlog shouldn't gate this mission's own merge.

### Stream 3 — `deepteam` alongside the existing `deepeval` integration
Add `deepteam` to `core/quality`'s isolated eval venv (same pattern as the existing `requirements-garak.txt`/`requirements-ragas.txt` isolation — do not put it in the main `platform-runtime/requirements.txt`). Point it at the existing `_ModelRouterJudge` backend already built for `deepeval`'s `HallucinationMetric` — do not stand up a second judge model. Land it as a standalone script (`core/quality/deepteam_scan.py` or similar), run manually first; do not wire it as a caller of anything live yet.

### Stream 4 — `log4brains` over the canonical ADR directory
Point `log4brains` at `core/governance/architecture-decision-records/` (the canonical directory per its own `ADR-NAMESPACE-MAPPING.md`) using the existing MADR format already in use — no ADR content changes. Produce a browsable static site build; wire a manual `npm run adr:build`-style script, not an auto-deploy, since this mission doesn't own hosting decisions.

### Stream 5 — Run `garak_gate.py` against the live Model Router (operational, VM-side)
This cannot be executed inside a remote/sandboxed dev session — the Model Router (`:8891`) only runs on the production host. Handoff: whoever has VM/systemd access runs `python3 core/quality/garak_gate.py --router-url http://127.0.0.1:8891`, saves the output under `reports/garak/`, and files the resulting knowledge record. This mission's deliverable for this stream is the handoff instruction itself (already usable as-is — the script needs no code changes) plus a placeholder tracking entry so it doesn't silently drop.

## Acceptance

- Stream 1: a `test-storybook`/axe CI job exists, runs on every `lcars-portal` PR, and its first real output (pass count / violation count) is captured in the knowledge record — not just "job exists."
- Stream 2: `pip-audit` runs via pre-commit and in CI; first real finding count (0 or N) captured in the knowledge record.
- Stream 3: `deepteam` runs at least once against the Model Router in this dev/build sandbox (does not require the production host, unlike Stream 5) and produces a real report artifact.
- Stream 4: a `log4brains` build completes locally and produces a real browsable HTML output from the actual ADR directory — not a config-only "should work" claim.
- Stream 5: the exact command is documented and handed off; if VM access is available within this mission's execution, the real pass/fail verdict and report path are captured instead of just the handoff.
- All five streams: SUOC Platform Registry's `Observability` and `CI/CD & Supply-Chain Hygiene` records updated to reflect new tooling states (Registry update required — engineering-tooling missions that add or run a canonical implementation for a capability are exactly the case that requires it).

## Reporting

One knowledge record per stream (five total, `knowledge/missions/USS-TJR-MSN-0374-stream{1..5}-*-knowledge-record.md`), following the existing MSN-0369/0370 multi-stream pattern, plus a closing summary record. Registry update: yes — `Observability` (Stream 3, 5) and `CI/CD & Supply-Chain Hygiene` (Stream 1, 2) both get technical-debt/next-evolution fields touched; `Governance` (Stream 4) gets a new "browsable ADR site" note under its Next Planned Evolution.
