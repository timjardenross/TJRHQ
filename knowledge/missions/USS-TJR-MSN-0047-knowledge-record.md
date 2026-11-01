# Knowledge Record — USS-TJR-MSN-0047

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0047 |
| Title | A PR template alone does not reach auto-generated PRs |
| Date | 2026-09-08 |
| Lesson | LL-137 |

## Outcome

Built specialists/knowledge-packs/Code-Review-Checklist.md (real content) and .github/pull_request_template.md. Folded a short checklist reminder directly into both of batch_coding.py's PR body templates so Mistral/ENG-HANDOFF-* auto-generated PRs carry it too. Added tests/test_batch_coding_review_checklist.py (4 tests).

## Lesson

Adding a PR template is necessary but not sufficient for "used as part of every PR" — any code path that opens a PR via the API with an explicit body bypasses it silently, with no error or warning. Auto-generated/bot PRs are exactly the kind most likely to need review scrutiny and least likely to get it if the checklist only lives in a template nobody's code path reads.

## Future Guidance

When wiring a process doc into "every PR", grep for every code path that calls a PR-creation API with an explicit body — a repo-level template is a good default but is invisible to anything that doesn't go through GitHub's own no-body-specified path.
