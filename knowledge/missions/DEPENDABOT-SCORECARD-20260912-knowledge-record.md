# Knowledge Record — Dependabot config and OpenSSF Scorecard workflow added, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0365 (Stream E) |
| Title | Dependabot wired across all 10 requirements.txt directories (not 9, as originally briefed) plus lcars-portal npm and github-actions; Scorecard added from OpenSSF's live template |
| Date | 2026-09-12 |
| Lesson | LL-153 |

## Outcome

Neither `.github/dependabot.yml` nor `.github/workflows/scorecard.yml`
existed before this — confirmed greenfield. PR #119
(https://github.com/timjardenross/TJRHQ/pull/119, merged) added both.

**Directory-count correction:** the mission brief stated nine
`requirements.txt` directories needing a `pip` Dependabot entry each. A
real `find . -name requirements.txt` turned up **ten**:
`core/infrastructure/mac-collector`, `core/infrastructure/vm-processing`,
`core/infrastructure/vm-transfer`, `platform-runtime`,
`scripts/self_improvement`, `services/revs-content-agents`,
`telegram-bots/capacitybot`, `telegram-bots/revs`, `telegram-bots/xo`,
`tools/supabase`. Re-verified independently by the implementing agent
before finalizing — same ten, none missing, no eleventh found. The final
`dependabot.yml` has 12 `updates` entries: the 10 `pip` directories above,
one `npm` entry for `lcars-portal/` (has its own `package.json`), one
`github-actions` entry for `/`.

**Scorecard workflow provenance:** fetched live from
`ossf/scorecard/.github/workflows/scorecard-analysis.yml` on `main` (the
canonical template OpenSSF's own README points to) rather than
reconstructed from memory, so the pinned action versions/SHAs
(`actions/checkout@v7.0.1`, `ossf/scorecard-action@v2.4.4`,
`actions/upload-artifact@v7.0.1`,
`github/codeql-action/upload-sarif@v4.37.7`) and the `permissions:` /
`publish_results: true` shape are exactly what OpenSSF currently
recommends, not an approximation.

**Evidence:** `actionlint` wasn't preinstalled — downloaded the official
v1.7.7 Linux binary from GitHub releases and ran it for real.
`scorecard.yml`: 0 findings, exit 0 (also re-ran across all
`.github/workflows/*.yml` present at the time to confirm no regressions
elsewhere — exit 0). `dependabot.yml` is not an Actions workflow, so
actionlint has no schema for it (only validates `on:`/`jobs:` syntax) —
that's a tool-scope mismatch, not a file defect, called out explicitly in
the PR; validated instead via `python3 -c "import yaml;
yaml.safe_load(...)"` (parsed cleanly, 12 entries) plus a manual check of
every key against the current Dependabot v2 schema.

## Lesson

A mission brief's stated counts (here, "nine" requirements.txt files) are a
starting hypothesis, not ground truth — re-verifying against the actual
repo state before finalizing a config caught a real discrepancy that would
otherwise have silently under-covered the platform's dependency surface by
one directory.

## Future Guidance

Dependabot's first PR and Scorecard's first score should appear in the
repo's Security tab within 24h of this merge — that needs to be checked on
GitHub directly; it isn't verifiable from a build sandbox. If a new
directory ever gains its own `requirements.txt`, `dependabot.yml` needs a
matching new `pip` entry by hand — nothing here auto-discovers new
directories.
