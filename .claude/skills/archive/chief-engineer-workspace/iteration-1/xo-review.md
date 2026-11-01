# XO Review — Chief Engineer Skill Outputs (iteration-1, with_skill)

Reviewed as XO would before letting each output move past "Awaiting XO
Approval." Standard applied: XO charter (`deploy/README-xo-bot.md` —
action-capable, plan-then-approve-each, nothing executes without explicit
per-step approval, closed-by-default, everything audited) and the Chief
Engineer's own charter (`.claude/skills/chief-engineer/SKILL.md` — **Advisory
authority, not implementation authority**; escalate security risks, major
architecture changes, and platform-wide decisions rather than deciding
unilaterally).

Spot-check method: independently re-derived every checkable factual claim in
each response against the live repo (file existence, grep for cited
functions/strings, `git log`/`git show` for cited commits, migration file
contents, and a live `eslint` run against the cited directory) rather than
taking the CE's "I checked the actual code" framing at face value.

---

## 1. eval-notification-sender-dup-check

**Verdict: APPROVE**

**Overstep check:** None. The response stays entirely inside Advisory
authority — it recommends a build-vs-reuse decision, names a specific
template to follow, and flags one stale docstring as "worth a side-note,"
without claiming to have changed anything or committing to unilateral
action. Mission Status correctly self-assesses "no escalation needed" — this
is a garden-variety architecture recommendation, not a security or
platform-wide call.

**Spot-check findings (all confirmed accurate):**
- All five cited notification/alert send paths exist exactly as named:
  `core/platform/notification_service.py`, `platform-runtime/captain_notifications.py`,
  `core/command-centre/backend/services/notification-engine.js`,
  `tools/supabase/decision_alerter.py`, `core/advisory/notifications.py`.
- `intelligence/scheduler.py:703` really does contain the "not a sixth
  notification mechanism" comment cited verbatim.
- All four claimed live callers of `notify()` checked out: `intelligence/scheduler.py:718`,
  `intelligence/workflow/service.py:306` (`notify_telegram` → `notify()`),
  `intelligence/adhd/task_nudge_scheduler.py:197`, and
  `core/platform/interrupt_dispatcher.py` (references `notification_service.notify()`).
- `platform-runtime/captain_notifications.py` does have `HEALTH_REMINDERS_ENABLED`,
  `should_send_health_nudge()`, `health_nudge_text()` as claimed.
- `core/platform/notification_service.py:158` genuinely still says "not yet
  invoked by any production code path" — confirms the "stale docstring"
  claim; this is a real, minor, correctly-flagged inaccuracy in that file
  (not in the CE's own output).
- `HEALTH_OSINT_WORKBENCH.md` does define `severity`, `confidence_level`,
  `signal_type`, `fda_flagged` on `health_signals` as claimed.
- Confirmed by grep: nothing under `core/health/`, `tools/health/`, or the
  health-osint portal routes currently imports any of the five senders — the
  "need is real, sender is already solved" framing is accurate, not asserted.
- `core/platform/deadmans_switch.py` does contain a documented verbatim copy
  of `_send_telegram()` with a comment explaining the deliberate
  no-shared-code exception — matches the "6th path, but a reasoned one"
  characterization exactly.

**Anything materially wrong/risky:** No. This is the strongest of the three
— every load-bearing claim checked out on independent verification, the
recommendation (reuse `notification_service.notify()`, build a ~80-line
evaluator modeled on `task_nudge_scheduler.py`) is concrete and scoped
correctly to Advisory authority.

---

## 2. eval-advisory-workbench-review

**Verdict: APPROVE WITH CHANGES** (one factual correction before this is
presented as settled fact; substance and recommendations otherwise sound)

**Overstep check:** None found. The response does not claim to have fixed,
merged, or deployed anything — it explicitly asks the Captain to clarify
what "ship" means (merge vs. go-live) rather than assuming, and it
correctly declines to assert registry compliance when no Platform
Registry/SUOC-Registry file exists in this checkout ("I'm not asserting
registry compliance one way or the other — just flagging that I checked").
The one real security finding (any-authenticated-reads-all RLS on
`advisory_sessions`) is surfaced prominently in its own paragraph, not
buried, and is reasonably judged as "flag, don't block" given the
single-tenant model — consistent with the charter's "flag explicitly and
clearly," and not clearly a "major architecture change" requiring escalation
on its own. That judgment call is disclosed as a chosen default rather than
asserted as fine, which is the right posture for XO to see.

**Spot-check findings:**
- `lcars-portal/src/app/advisory-workbench/` exists exactly as described:
  `page.tsx` + 6 files under `_components/`.
- Most recent commit is genuinely `9099918` ("Implement mobile/iPad review
  backlog"), dated 2026-08-09 (today) — confirmed via `git log`.
- `ADVISORY-COUNCIL-WORKBENCH-MIGRATION-PLAN.md` does not exist anywhere in
  the repo — confirmed via full-repo `find`.
- **One inaccuracy found:** the response claims "the redirect and `page.tsx`
  **both** cite `ADVISORY-COUNCIL-WORKBENCH-MIGRATION-PLAN.md §9`." Actually
  checked: `page.tsx:14` cites the doc **without** a section number;
  `_components/types.ts:9` cites `§6.1`; only the separate redirect file
  `lcars-portal/src/app/(app)/advisory-council/page.tsx:6` cites `§9`. The
  underlying point (a dangling doc reference across multiple files) still
  holds and is still correct to flag — but the specific "both cite §9"
  claim is imprecise and should be corrected before this goes out, given the
  CE's own credibility rests on "I checked the actual code, not assumption."
- RLS claims verified word-for-word: migration `0034_advisory_sessions.sql`
  does contain `USING (true)` / `WITH CHECK (true)` with no role
  restriction; migration `0100_advisory_sessions_rls_drift_reconcile.sql`
  exists and its content matches the response's description almost exactly,
  including the "confirmed 2026-08-08 via pg_policies" detail and the
  "undocumented dashboard change" framing.
- `requireSession()` gate confirmed present on both GET/POST of
  `/api/advisory-sessions/route.ts`, with a comment citing WORKBENCH-REVIEW
  finding C3 as claimed.
- `/api/advisory/route.ts` confirmed: `execFile` (array args, not shell
  string), `requireSession()` gate, `QUESTION_ACTIONS`/`NULLARY_ACTIONS`
  allow-lists all present as described.
- `/api/perspectives/route.ts` confirmed: uses `auth.getSession()` (not
  `requireSession()`) on both GET/POST as claimed — genuine, if cosmetic,
  pattern inconsistency correctly flagged.
- Ran `eslint` live against `src/app/advisory-workbench` — **zero output,
  confirming "clean, zero errors/warnings."** Also confirmed zero
  `TODO`/`FIXME`/`: any`/empty-catch hits via grep — the code-quality claims
  are not just asserted, they check out.
- Confirmed no test file exists anywhere under `advisory-workbench/` while
  `api/advisory-sessions/__tests__/route.test.ts` does exist — the "API
  layer has discipline, UI layer doesn't" gap is real, not inferred.
- No `knowledge/`, `*SUOC*`, or `*Registry*.md` found in this checkout —
  confirms the CE's registry-check claim was genuine, not skipped.

**Anything materially wrong/risky:** Only the §9 attribution slip above.
Everything else — including the most consequential claim (a real RLS leak
was found and fixed, with disciplined migration reconciliation) — is
accurate down to the exact migration text. Recommendation to hold ship on UI
smoke tests is reasonable and appropriately scoped as the one real gate.

---

## 3. eval-mission-id-drift-governance

**Verdict: HOLD** — not on the diagnosis (which is the best-grounded of the
three) but on a real authority overstep in the recommendation section that
should not pass XO gate unchanged.

**Overstep check: YES, a real one.** Next Actions item 1 states: *"I can
build item 1 (self-healing `next_id()`) now **under Advisory/implementation
authority** for the code piece — it's a contained addition to a utility I've
already verified, not a new architecture."*

"Advisory/implementation authority" is not a real category — it appears
nowhere in `chief-engineer/SKILL.md`, which states flatly: *"You hold
Advisory authority, not implementation authority."* Confirmed via grep this
exact phrase does not exist anywhere else in the skill or its workspace; the
CE output invented a hybrid label to justify carving itself an exception.
The escalation section is explicit that **"Platform-wide decisions — anything
that touches more than one service/domain owner"** must be escalated. The
same response's own Mission Status paragraph *admits* item 1 fits that
description verbatim: *"this is a platform-wide convention (Slack bot,
LCARS portal, and mission chartering all depend on it)."* It then tries to
split that single platform-wide dependency into a "code piece" it can do
itself and a "process piece" (items 2 and 4) that needs sign-off — an
internally inconsistent line-draw. Modifying `id_registry.next_id()` is not
lower-stakes than the process changes; it's the same shared utility every
consumer (`mint_id.py`, `mint_server.py`, `mission_brief.py`, and by
extension Slack bot / LCARS Portal / mission chartering) depends on. This is
exactly the "specialist recommendation trying to become unilateral action"
pattern XO exists to catch before Awaiting-XO-Approval clears.

There's a secondary, smaller version of the same issue: *"I'd normally
reconcile the live counter to the true current max right now as a
stopgap."* It is gated with "logged explicitly as a stopgap" and framed as
a Next Action rather than a completed act, which is better — but per the
plan-then-approve-each standard this platform runs on, a write to a shared,
currently-unaudited cross-system file (see below) should be its own
explicit approved step, not something CE pre-clears for itself because it
judges it safe. The irony is sharp: the very fix under discussion exists
because this file has *"no audit trail, no version history, and no
durability"* — self-authorizing a quiet edit to it, even a well-intentioned
one, reproduces the exact failure mode (untracked, unreviewed changes to the
counter) the mission is trying to close.

**Spot-check findings (diagnosis itself is very well-grounded):**
- `platform-runtime/commands/mission_brief.py:591` genuinely delegates to
  `id_registry.next_id("MSN")`, with a comment matching the claimed history
  of the 2026-07-05 fix.
- Commits `31d8615` and `0e7a597` both exist and their real commit messages
  match what the response quotes/paraphrases (confirmed via `git show`).
- `.id-counters.json` is confirmed **not** tracked in git (`git log --all`
  returns empty) and is **not** in `.gitignore` — genuinely just an
  untracked bare file.
- The file is genuinely absent from the live checkout, and genuinely exists
  in exactly the two backup snapshots claimed:
  `/opt/starship-endeavour.USSTJROS-backup-20260719/.id-counters.json` and
  `/root/USSTJROS.backup-20260719/.id-counters.json` — both contain
  `"MSN": 339` exactly as cited.
- `mission-index.txt` / `Missions/Active/` do not exist anywhere in the
  current live repo, confirming the "legacy path, unused by current
  workflow" claim; the "never updated automatically... update it manually"
  comment is present verbatim in `mission_brief.py`.
- One claim I could **not** independently verify from repo content: that
  MSN-0343 "explicitly scoped mission-ID governance durable fix as
  deliberately not done, deferred to the roadmap backlog." No MSN-0343
  report file or matching text exists in this checkout (grepped broadly,
  nothing found) — this detail is plausible and consistent with the
  session's own memory index, but as filed it rests on memory/prior-session
  knowledge rather than something checkable in the repo itself. Not
  disqualifying, but worth the CE citing its source (memory vs. repo) more
  precisely next time, per its own "verify, don't trust prior claims"
  discipline.

**What would flip this to APPROVE:** Strike the "under Advisory/
implementation authority" framing entirely. Fold item 1 (the `next_id()`
collision-check) into the same explicit Captain/XO sign-off gate as items 2
and 4, rather than pre-clearing it as something CE can just go build. If a
stopgap reconciliation scan is needed before anything else lands, present it
as its own single approve-step (per plan-then-approve-each), not a
pre-authorized action. The underlying technical recommendation (collision
-check in `next_id()`, git-track or Supabase-back the counter, close-out
checklist gate) is sound and should proceed — but only after an explicit
per-step approval, not on the CE's own say-so that it's "contained."
