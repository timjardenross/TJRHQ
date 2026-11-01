# Knowledge Record — pre-commit gate wired (Ruff/Bandit/gitleaks/detect-secrets); found a live-looking leaked credential, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0365 (Stream D) |
| Title | Pre-commit config added; detect-secrets and an independent gitleaks scan both flagged the same real-looking Supabase service_role key, left deliberately unbaselined |
| Date | 2026-09-12 |
| Lesson | LL-152 |

## Outcome

Repo root had no `.pre-commit-config.yaml`, `.secrets.baseline`,
`pyproject.toml`, `ruff.toml`, or `.bandit` before this — confirmed
greenfield. PR #173 (https://github.com/timjardenross/TJRHQ/pull/173,
merged) added:

- `.pre-commit-config.yaml`: Ruff (`ruff-check` only — lint, no
  autofix/format, to avoid a mass reformat side effect across this
  930-Python-file monorepo), Bandit, gitleaks (`gitleaks git --pre-commit
  --staged` — gitleaks v8 removed the `protect` subcommand the mission
  brief named; this is its direct successor, same purpose), and
  `detect-secrets-hook` against a generated `.secrets.baseline`.
- `.gitleaks.toml`: a small path-based allowlist. Without it, gitleaks
  flagged every SHA1 hash *inside* `.secrets.baseline` itself as a fake
  `generic-api-key` finding — 1,346 false positives purely from combining
  the two tools, plus lockfile-hash noise. Excludes `.secrets.baseline`,
  `package-lock.json`, `yarn.lock`, `*.lock` by path, not by content.
- Hook versions pinned to real current tags, verified via `git ls-remote`:
  `astral-sh/ruff-pre-commit` v0.16.7, `PyCQA/bandit` 1.9.4,
  `gitleaks/gitleaks` v8.30.1, `Yelp/detect-secrets` v1.5.0.

**Real `pre-commit run --all-files` output** (930 Python files, 173,409
lines scanned by Bandit; gitleaks built from source via Go, matching a
contributor's first run):

| Hook | Result | Findings |
|---|---|---|
| ruff (lint only) | Failed | 6,861 errors (3,420 `--fix`-able, not applied) |
| bandit | Failed | 2,795 issues — 2,616 Low, 179 Medium, 0 High |
| gitleaks (staged-diff) | Passed | 0 leaks in this PR's own staged diff |
| detect-secrets | Failed | 1 unbaselined finding (below); ~1,410 other findings triaged and baselined as false positives (commit SHAs, generated cache/manifest hashes, docstring examples, test fixtures, env-var *names* not values) |

Per the mission brief, fixing Ruff/Bandit findings is out of scope for this
stream — it wires the gate, it doesn't clean up 9,656 pre-existing findings.

### ⚠️ Security finding — not resolved by this record, needs a human with Supabase access

`detect-secrets scan` and an independent full-repo `gitleaks dir .` scan
both flagged the same thing: **`lcars-portal/deploy-phase-1b.js:13`**
hardcodes a Supabase project URL and what decodes to a `service_role` JWT
(Supabase's most privileged key — bypasses row-level security). The
decoded payload's `ref` claim matches the hardcoded URL's project ref, and
the role is `service_role`, not `anon`; it is not a placeholder (no
`YOUR_...` pattern, no obviously fake value). This repo is public on
GitHub, so if this key is live it is currently exposed.

**This finding was deliberately left out of `.secrets.baseline`** rather
than silently baselined away. Direct, visible consequence:
`pre-commit run --all-files` will keep failing on this one detect-secrets
hit for every future contributor until it is resolved — that failure is
intentional and should stay red on purpose. This is not this stream's (or
this mission's) call to resolve unilaterally: rotating a Supabase key is an
ops/human decision, not a code change an automated pass should make.

**Reported directly to the Captain during this mission, not held for a
final summary.** As of this record, still open.

## Lesson

A pre-commit gate's first real run against an existing 930-file monorepo
will surface a large, mostly-noise finding count (9,656 combined here) —
that volume is exactly why triage discipline matters: burying one real
credential inside thousands of false positives, or baselining everything to
get a clean run, would have been strictly worse than shipping a config that
fails on purpose until a human acts.

## Future Guidance

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
