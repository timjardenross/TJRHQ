# Code Review Checklist

USS-TJR-MSN-0047 (lightweight code review process). Built after the platform had
gone 2026-06-27 to 2026-09-08 with real PRs and CI (`.github/workflows/lcars-portal-ci.yml`,
required per `Repository-Governance-Standard.md`) but no PR template and no written
review checklist — reviewers (human or Claude) were each reinventing what "reviewed"
means. This is deliberately short: a checklist nobody reads doesn't get used.

## Before opening the PR

- **Ran the repo's own fast checks locally** — typecheck, lint, the tests for
  whatever you touched. Don't rely on CI to tell you something you could have
  caught in 30 seconds.
- **Re-read your own diff adversarially.** What's the smallest input that breaks
  this? What would make CI reject it? `Repository-Governance-Standard.md`'s
  incident (33+3 files landing on `main` with literal `<<<<<<< HEAD` markers
  still in them) happened because nobody did this pass before pushing.
- **Kept the change minimal.** Does this PR do only what the issue/mission needs,
  or did unrelated cleanup sneak in? A wider diff is a harder review.
- **Commit messages say why, not just what.** A message like `"1"` or `"fix"` is
  a signal something got rushed past review — say what broke and why this fixes
  it.

## Reviewing someone else's PR (including your own, before merging)

- **Does the test plan actually prove the fix?** "Added a test" isn't enough —
  does the new test fail on the old code and pass on the new code? For a bug
  fix, was the original failure reproduced first?
- **Read the diff, not just the description.** A PR body can describe an
  intended change accurately while the diff does something slightly different
  — line-review is what catches that.
- **Conflict resolution gets extra scrutiny.** If a merge/rebase touched code
  you didn't author, verify with a diff against a known-good commit or a
  build/typecheck — don't trust a script-resolved conflict blindly (see the
  governance doc's incident where automated resolution silently deleted a
  function body).
- **Security-shaped changes get a slower pass:** anything touching auth,
  secrets, RLS policies, or user input handling — take the safer option over
  the faster one.
- **A bot/reviewer finding is a bug report, not a suggestion to argue with.**
  Verify it against the actual code before dismissing it; if it's wrong, say
  why in a reply rather than silently ignoring it.

## Before merging

- CI is green on the current head, not an earlier commit.
- No open thread you haven't either resolved or explicitly explained.
- If this PR was auto-generated (a `[Mistral]`/`ENG-HANDOFF-*` batch-coding
  draft), it still gets the same review as a human-authored PR — the diff
  applying cleanly is not the same as the diff being correct.

See `.github/pull_request_template.md` for the per-PR version of this
(test plan, scope, breaking changes) that GitHub populates automatically.
