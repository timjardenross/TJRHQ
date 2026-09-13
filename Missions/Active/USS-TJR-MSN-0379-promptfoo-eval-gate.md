# Mission Brief

## Mission Header

- **Mission ID:** USS-TJR-MSN-0379
- **Priority:** P2 — extends existing eval investment, no external deadline
- **Source:** `knowledge/OSS-Capability-Search-2026-09-12.md` — highest-priority untouched item after MSN-0374's five "Now" items landed.

## Pre-flight

1. **Existing-entry check.**
   ```
   grep -rli "promptfoo" .
   → only this session's own report/mission docs. Not adopted anywhere. Real gap.

   grep -n "score_output\|shadow" platform-runtime/lib/build_learning_loop.py
   → confirmed still shadow-mode only: deepeval's HallucinationMetric via
     _ModelRouterJudge has exactly one caller, and it doesn't block anything.
   ```
   So the real gap this mission closes: garak (fixed, MSN-0374/live-VM follow-up), deepteam
   (added, MSN-0374 Stream 3), and deepeval (shadow-mode) all exist, but **nothing currently
   blocks a merge or a deploy on any of them.**

2. **Premise verification** — the repo's own established pattern for landing a new advisory
   tool is: report-only first (`continue-on-error: true` at both job and step level), earn
   trust, flip to blocking later. Confirmed directly in `.github/workflows/python-ci.yml`
   for `vulture`, `pip-audit`, and `semgrep` (all landed this way, per their own comments).
   This mission follows that same convention — it does **not** ship as a blocking gate on
   first landing.

## Explicitly Not In Scope

- **Flipping garak/deepteam/deepeval from shadow-mode/manual to blocking.** Separate,
  larger decisions each capability's own Registry entry already flags as its own
  "Next Planned Evolution" — not bundled into this mission.
- **Replacing deepeval or deepteam.** promptfoo is additive — a CI-runnable eval/red-team
  layer, not a replacement for the judge-model work already done.
- **Wiring promptfoo into the live Model Router as a pre-activation gate** (that's
  `garak_gate.py`'s job, already built). This mission's scope is CI-time evals against
  test prompts, not production traffic gating.

## Scope

1. Add `promptfoo` as a CI job in `.github/workflows/python-ci.yml`, mirroring the
   `pip-audit`/`vulture` advisory pattern exactly (report-only, `continue-on-error` at
   job and step level).
2. Write a small, real `promptfooconfig.yaml` covering the Model Router's actual
   OWASP-LLM-Top-10-relevant surface (prompt injection, PII leakage) — reuse existing
   test prompts/fixtures already used by garak/deepteam where they overlap, don't
   invent a parallel fixture set.
3. Run it for real against the live Model Router at least once (same bar MSN-0374's
   deepteam stream held itself to) and capture the actual pass/fail output — not a
   claim that the config "should work."

## Acceptance

- CI job exists, runs on every PR, report-only on first landing.
- At least one real run against the live Model Router with captured output.
- Knowledge record states plainly whether promptfoo found anything garak/deepteam
  didn't — that comparison is the actual value case for adding a third eval tool.

## Reporting

One knowledge record (`knowledge/missions/USS-TJR-MSN-0379-knowledge-record.md`).
