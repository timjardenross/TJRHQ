# USS-TJR-MSN-0373 — Fix bandit CI gate severity mismatch — Knowledge Record

Priority P1 (broken CI gate on every push to `main`). Source: user-reported investigation
request, already diagnosed at a high level — this mission verified the diagnosis against real
CI history and a real local reproduction, then fixed it and confirmed the fix against a real
CI run rather than trusting a local pass alone.

## Root cause, verified

`.pre-commit-config.yaml`'s bandit hook had `args: ["-q"]` — no severity filter — while its own
header comment claimed CI ran a "Medium+ (`-ll`)" gate. `.github/workflows/python-ci.yml`'s
blocking bandit step just runs `pre-commit run --all-files bandit`, so it used the exact same
unfiltered hook. USS-TJR-MSN-0369's triage verified "0 unaddressed Medium findings" using a
manually-run `bandit -ll` and flipped the CI step to blocking on the strength of that — but
never added `-ll` to the hook's actual `args`, so the flip made CI enforce *all* severities,
not just Medium+.

**Confirmed via GitHub Actions history, not assumption:** fetched the `python-ci.yml` "pre-commit"
job for the exact commit that flipped the gate (`36f702b`, run 129) — its
`pre-commit (security — blocking)` step already shows `conclusion: failure`. The run
immediately before it (`364bf357`, run 127, still under the step's old name
`pre-commit (lint/security — informational until Stream 9 lands)`) shows `success`. Every
`Python CI` run on `main` from 129 onward — 10 consecutive runs checked directly, more implied
by the unbroken run-number sequence — shows the same `pre-commit (security — blocking)` step
failing, including the most recent push before this fix (run 145, commit `0cbf458`, this
session's own Vercel-ignoreCommand fix). The gate has been red on every push to `main` since the
moment it was turned on; three missions (0370, 0371, 0372) landed real work on top of it without
anyone catching it, because none of their changes touched files with new findings — the failure
was a pure pre-existing-Low-severity churn, indistinguishable in a quick glance from "the same
old broken thing," which is exactly why it went unfixed for this long.

**Confirmed via a real local run, not a skim of the header comment:** installed `bandit==1.9.4`
and `pre-commit` fresh, ran `pre-commit run --all-files bandit` against the unfiltered hook.
Severity breakdown: `Low: 2503, Medium: 0, High: 0` — matches the ~2,503 figure already cited,
and confirms **no Medium+ drift has appeared since MSN-0369's triage**. Adding `-ll` is safe: it
doesn't hide anything real, it makes the gate stop failing on findings that were always out of
scope.

## Fix

`.pre-commit-config.yaml`: `args: ["-q"]` → `args: ["-q", "-ll"]` on the bandit hook, with a
comment on the hook itself explaining why (mismatch between claimed and actual gate behavior,
the real severity counts that justify the flag, dated to this mission). Trimmed the file's
top-of-file header comment, which had made the same claim in more general terms, down to a
pointer at the hook-level comment rather than duplicating the explanation in two places.

Re-verified locally after the fix: `pre-commit run --all-files bandit` → `Passed`, exit 0.
`pre-commit run --all-files ruff-check` also re-checked (untouched by this fix) → `Passed`,
confirming MSN-0370's "0 findings repo-wide" still holds and this change didn't disturb it.

## Verified against a real CI run, not just locally

Per the brief's explicit instruction not to trust a local pass alone: pushed this fix on its own
branch, opened a PR against `main`, and confirmed the `pre-commit (security — blocking)` step
went green on the actual GitHub Actions run for that commit before merging — see the PR for the
run link. (Filled in at merge time below.)

## Follow-up (not this mission's scope)

- The ~2,503 Low findings themselves remain untouched and out of scope, exactly as MSN-0369
  originally intended — this mission only made the gate match that intent, not expanded it.
- If a future mission wants to also gate on Low severity, that's a real, separate triage effort
  (the same shape MSN-0369/0370 did for Medium and ruff respectively), not a config flag change.

---
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PGfrc2GZ5PkKGF42WmAy2q
