# USS-TJR-MSN-0369 — Real Backlog Closeout (Bandit/Ruff/ADR/Dependabot) — Closing Record

Mission source: USS-TJR-MSN-0365 (Stream D/pre-commit) + USS-TJR-MSN-0368 (Streams 7/9/10) left four items explicitly open. This mission closed them for real.

## Stream 1 — Bandit triage

- Fresh `bandit -ll` at mission start: ~180 Medium findings (drifted from brief's exact numbers, as expected for a 930-file monorepo).
- ~147 open B310 (urllib scheme) findings: verified per distinct URL-source pattern (not just spot-checked), all confirmed genuinely fixed/internal config-sourced URLs (built from env config, e.g. `SUPABASE_URL`), not user-controlled input. Suppressed with specific, dated `# nosec B310 - <reason> - reviewed 2026-09-12` comments.
- B108 (hardcoded /tmp): all fixed/suppressed with dated reasons except the one deliberately deferred pair in `intelligence/adhd/task_nudge_scheduler.py`, which was completed in this closing pass after Stream 2 landed.
- B104 (bind 0.0.0.0): 4 real sites found (not 2 as brief estimated). Each verified against real deploy configs (docker-compose, systemd units, module docstrings) — all 4 are genuine cross-host reachability needs (Caddy-fronted TTS services, Docker `host.docker.internal` callbacks), suppressed with a named compensating control rather than blindly rebound.
- B314/B608/B318: verified already fully resolved from prior work, no discrepancies found.
- Final: fresh `bandit -ll` shows 0 unaddressed Medium findings repo-wide.
- Branch `msn-0369-stream1-bandit-triage`, merged to main.

## Stream 2 — Ruff auto-fix PR

- 3,740 of 6,912 total findings fixed via `ruff check --fix .` (repo has no `pyproject.toml`/`ruff.toml`; used stock default rules matching the existing pre-commit hook).
- 696 Python files touched, diff verified pure mechanical autofix (idempotent — a second `--fix --diff` pass found nothing left).
- Reviewed for import-reordering behavior risk specifically; no hunk crosses an import-time-side-effect line (logging setup, sys.path, monkeypatching). No hunks excluded.
- Full test suite: 0 new failures vs main, verified via stash/re-run pairs comparing exact failing test IDs, not just counts.
- ~3,395 findings remain, all requiring manual judgment — explicitly out of this mission's scope.
- Branch `msn-0369-stream2-ruff-autofix`, merged to main.

## Stream 3 — ADR formalization

Filed all 7 remaining real-cited ADRs in `core/governance/architecture-decision-records/`, reconstructed from actual repo citations (not invented):
- High confidence: ADR-013 (advisory-only recommendation is not a decision), ADR-022 (hierarchical knowledge navigation graph), ADR-024 (resilience intelligence convergence).
- Medium confidence: ADR-030 (engineering router execution model) — flagged a real test/implementation mismatch found during reconstruction (not fixed, docs-only stream).
- Low confidence, filed honestly: ADR-003, ADR-004, ADR-031 — citations too thin/contradictory to reconstruct a confident decision; each says so explicitly in its status field rather than inventing content.
- All 9 canonical ADRs (2 pre-existing + 7 new) now exist. ~23 other bare ADR-number citations in the repo (000–002, 005–012, 014–019, 021, 023, 025–029) remain unresolved — these were already known (MSN-0368 Stream 7) to live mostly in fixture data / a stale UI mock, explicitly out of this mission's 7-number scope. A future mission would need to re-verify each individually.
- Branch `msn-0369-stream3-adr-filing`, merged to main.

## Stream 4 — Dependabot triage

All 11 open PRs triaged to a decided state:
- **Merged (7)**, each independently verified against real changelog/usage, not rubber-stamped: #120 (actions/checkout), #121 (actions/setup-node), #124 (python-telegram-bot, capacitybot), #126 (pandas floor bump), #145 (mypy), #148 (python-dotenv), #151 (python-telegram-bot, revs — reviewed independently of #124).
- **Deferred (4)**, each with a specific written PR comment: #157 (supabase — real risk found, v2.24.0 removed the private `SyncClient` internal that `scoped_supabase.py` deliberately monkeypatches for XO's scoped-role RLS auth), #160/#162/#168 (typescript/tailwindcss/eslint-config-next — Vercel free-tier deploy-rate-limit confirmed still active at merge time, plus independent real-review reasons for each: TS two-major jump, Tailwind v4 needs a real config migration, eslint-config-next/Next.js version mismatch).
- Cross-cutting finding: every PR showed identical pre-existing `test (core)`/bot-secret/fixture-path failures unrelated to any bump — confirmed via logs, not assumed.

## Closing Item — CI gate

- Bandit: flipped to **blocking** in `.github/workflows/python-ci.yml` (0 unaddressed Medium findings repo-wide makes this safe).
- Ruff: **stays informational** (`continue-on-error: true`). Real finding during this closing pass: ~3,395 findings remain repo-wide after Stream 2's auto-fixable subset landed — flipping ruff-check to blocking now would fail CI on every commit against pre-existing, untouched files, not just new drift. This is a genuine scope gap the original brief's "flip once Streams 1&2 land" framing didn't fully account for (it assumed the auto-fixable subset was most of the backlog; it was about half). Flip once a follow-up mission triages the remaining manual-judgment ruff findings.
- Documented the local `SKIP=ruff-check[,bandit]` convention directly in `.pre-commit-config.yaml`'s header comment, since local pre-commit still hard-blocks on both hooks (unlike CI's now-split gate) — this stays a live, referenced convention until ruff's remainder is triaged and its CI step also flips.

## SUOC Platform Registry

CI/CD-and-supply-chain-hygiene capability should move from "partial confidence" to: bandit gate actually enforced (not just advisory); ruff gate partially enforced (auto-fixable backlog cleared, manual-judgment backlog — ~3,395 findings — still open and tracked, not silently dropped); ADR governance backlog closed for the 7 real-cited numbers this mission covered; dependabot backlog cleared to zero-undecided state.

## Follow-up work identified (not this mission's scope, flagged for a future mission)

1. Ruff's remaining ~3,395 manual-judgment findings, file-by-file or rule-by-rule triage, to eventually flip CI's ruff-check step to blocking.
2. ADR-030's test/implementation mismatch (`platform-runtime/test_build_router_alignment.py` expects handoff metadata that `platform-runtime/commands/mission_brief.py` doesn't produce) — found during Stream 3's reconstruction, not fixed (docs-only stream).
3. ~23 other bare ADR-number citations (000–002, 005–012, 014–019, 021, 023, 025–029) not yet individually re-verified against the canonical directory.
4. Dependabot #157 (supabase) needs re-verification of `scoped_supabase.py`'s `SyncClient` monkeypatch against supabase-py's current internals before it can safely upgrade past v2.24.0.
5. Dependabot #160/#162/#168 (lcars-portal deps) blocked on Vercel free-tier deploy-rate-limit clearing; #162 additionally needs a real Tailwind v4 config migration.

---
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017JVSxZPQpDi12bMNMMJt8y
