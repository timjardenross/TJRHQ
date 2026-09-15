# Skill Benchmark: chief-of-staff

**Model**: claude-sonnet-5
**Date**: 2026-09-15
**Evals**: priority-focus, weekly-review, authority-module-dup-check (1 run each per configuration)

This is a backfill benchmark. The original iteration-1 eval
(`eval-chief-of-staff/grading.md`) graded 3 prompts inline but skipped persisted response
transcripts and this aggregation — its source charter was thin at the time. This file re-runs the
same 3 prompts fresh against the current repo state, with full outputs persisted under
`eval-priority-focus/`, `eval-weekly-review/`, and `eval-authority-module-dup-check/`.

## Summary

| Metric | With Skill | Without Skill | Delta |
|--------|------------|---------------|-------|
| Pass Rate | 100% ± 0% | 78% ± 19% | +0.22 |
| Time | 178.7s ± 33.3s | 113.0s ± 17.5s | +65.7s |
| Tokens | 68117 ± 6157 | 51733 ± 5320 | +16383 |

## Notes

- Eval 1 (priority-focus) doesn't discriminate much: a capable baseline independently found the
  same registry Fix-Now items and the same Search/Scheduling TBD-ownership gap, and produced a
  reasoned ranking without the charter's formal leverage framework. With-skill's real edge here is
  evidentiary hygiene, not a new finding — it caught and disclosed that the original iteration-1
  eval's cited commit hashes (`ac9c3b95b`, `22fb55f68`, `8fe215074`) no longer exist anywhere in
  git history, rather than repeating that claim forward unchecked.
- Eval 2 (weekly-review) is the clearer differentiator on structure: baseline matched with-skill's
  raw grounding and even independently caught the same git-history staleness caveat (all 62
  commits in this repo are dated the same single calendar day), but its response ends in a
  "Bottom line" summary that never routes the open ownership gap to a named next step, where
  with-skill's Decisions Needed / Next Actions split names owners explicitly.
- Eval 3 (authority-module-dup-check) is the cleanest differentiator, matching the original
  grading.md's Q3 pattern almost exactly: both configs correctly find the existing
  `authority_validator.py`/`authority_enforcement.py` module and MSN-0326, and both correctly
  recommend against building a new one — but only with-skill explicitly declines to make the
  deeper engineering-scoping call itself and routes it to Chief Engineer, per its own Escalation
  section.
- **Material change since the original iteration-1 eval, disclosed rather than papered over:**
  this repo's entire git history (62 commits) is now dated a single calendar day (2026-09-15), so
  the specific commit hashes the original eval cited as possible evidence of registry staleness no
  longer resolve at all (`git show`/`git log --all` find nothing). The registry itself is
  genuinely fresh today (last reviewed 2026-09-12, 3 days before this run), so this doesn't change
  today's substantive answer on any of the 3 prompts — but today's runs did not and could not try
  to reproduce that specific old finding, and say so explicitly rather than forcing a match.
- With-skill runs took ~58% longer on average and used ~32% more tokens than baseline — consistent
  with the cost pattern already on file for chief-engineer and xo: the fuller persona,
  investigation depth, and response template cost more and win more often, not a red flag on its
  own given the pass-rate gain.
