# Content Workbench — Review Findings Fixed

USS TJR · Chief Engineer persona · 2026-08-09
Source: `.claude/skills/workbench-reviews/content/chief-engineer-review.md` + `xo-gate-review.md`

All 4 findings addressed. 3 fixed and verified live; 1 investigated and reported (deliberately not touched).

---

## 1. RLS gap on `comms_content_revisions` — FIXED, verified live

**Problem**: RLS enabled, zero SELECT policies. The GET revisions route uses the session-scoped
(anon-key) client, so "Show Revision History" silently returned `[]` for every item despite 10 real
rows across 5 content items existing.

**Fix**: Added an `authenticated`-only SELECT policy (`auth_read`, `qual: true`), matching the exact
pattern already live on `comms_content` / `intelligence_events` / `intelligence_briefs` /
`intelligence_source_registry`.

- Applied live via Supabase MCP `apply_migration` against project `cjvrpjwewsrumnbdydgg`.
- Local archive file: `core/infrastructure/supabase/migrations/0109_comms_content_revisions_auth_read_policy.sql`
  (numbered 0109, not 0105/0106/0107/0108 — those were taken in real time by a concurrent session
  also doing RLS-tightening work tonight; had to bump the number three times to avoid re-creating the
  exact kind of collision finding #4 is about).
- **Verified**: `pg_policies` now shows exactly one row for `comms_content_revisions` (`auth_read`,
  SELECT, `{authenticated}`, `qual: true`). `SET ROLE authenticated; SELECT COUNT(*)...` now returns
  10 rows / 5 distinct items — was 0 before the policy existed.

Commit: `a2e728d` — pushed to `main`.

---

## 2. QA gate was UI-only — FIXED, verified live

**Problem**: `POST /api/comms/[id]/advance` never read `qa_status`. The `review → approved` transition
(`captain_approved` trigger) succeeded unconditionally; only `ContentBoard.tsx` hid the Approve button
client-side when `qa_status !== 'qa_passed'`. A direct API call could skip QA entirely.

**Fix**: Read `qa/route.ts` first to get the real enum (`qa_status: 'pending' | 'qa_passed' |
'qa_failed'`, defaulting to `null` before any QA pass) rather than guessing. Added a server-side check
in `advance/route.ts`: when `status === 'review'` and `trigger === 'captain_approved'`, reject with a
clear `400` (`"QA has not passed (qa_status: 'x') — complete the Proofing checklist before approving"`)
unless `qa_status === 'qa_passed'`. Scoped narrowly to the one transition QA actually gates (`qa/route.ts`
only accepts status `review`/`approved`) — doesn't touch any other trigger in the `TRANSITIONS` map.

- `ContentBoard.tsx`'s existing `approve()` handler already does `if (!res.ok) throw new
  Error(d.error)` and surfaces it via `setMsg(...)` with `aria-live="polite"` — no UI change needed,
  the clear error surfaces automatically.
- **Verified**: `tsc --noEmit` and `eslint` clean on the changed file. Production build (`npm run
  build`) succeeded. Live service (manually run on port 3200 — see open item below) killed and
  restarted from the fresh build; confirmed the compiled `.next/server/app/api/comms/[id]/advance/route.js`
  contains the string `"QA has not passed"`. Traced the logic against 3 live items currently sitting
  in `status = 'review'` with `qa_status = null` — all 3 would now be correctly rejected by a
  `captain_approved` call instead of silently succeeding.
- Did not get a real authenticated browser session to fire an actual end-to-end HTTP request (no test
  login credentials available in this environment) — verification is via compiled-bundle inspection +
  direct logic trace against live DB state, not a live HTTP round-trip. Flagging this gap rather than
  overclaiming full E2E coverage.

Commit: `af0a40b` — pushed to `main`.

---

## 3. "CONTENT REVIEW" alert vs. "Proofing" column naming mismatch — FIXED, verified live; mobile bug also found and fixed

**Problem**: The Telegram EOD/morning brief's `CONTENT REVIEW` section
(`intelligence/captains_brief.py::_get_content_review_queue`) prints `comms_content.status` verbatim
— e.g. `[review · pillar]` — for items with status `draft`/`review`/`ready_to_publish`. The Content
Workbench board has no column called "Review"; that stage is labelled "Proofing"
(`shared.ts::STAGE_LABEL`, single source of truth for every place the label renders — column header,
card label, mobile picker chip, ARIA labels).

**Fix**: Renamed the `proofing` stage's `STAGE_LABEL` to `"Proofing / Review"` — keeps both names
visible together, stays short, consistent with the other 3 labels (Capture, Research, Content Prep).
One-line change in the single shared constant, no behavior change.

- **Verified**: `tsc`/`eslint` clean. Production build succeeded; confirmed `"Proofing / Review"`
  present in the compiled client bundle
  (`.next/static/chunks/app/content-workbench/page-*.js` and `.next/server/app/content-workbench/page.js`).

**Mobile "opens on empty Capture column" — checked, was real, fixed (simple default-tab bug):**
`ContentBoard.tsx`'s below-`sm` single-column view hardcoded `activeMobileStage` to `'capture'` on
every load, regardless of where items actually sit — since most live work sits in later stages, the
common case was opening the mobile board on an empty column. Fixed by auto-selecting the first
non-empty stage on initial load, tracked via a `userPickedMobileStage` ref so it stops auto-switching
once the Captain has tapped a stage themselves (doesn't yank them back on a later refresh/poll).

- **Verified**: `tsc`/`eslint` clean, build succeeded, deployed. Not verified via an actual narrow
  viewport browser session (same auth-credential constraint as #2) — verified by code trace + compiled
  presence in the same bundle that already confirmed the label change landed.

Commits: `2c9512c` (label rename), `c53f280` (mobile default fix) — both pushed to `main`.

---

## 4. Duplicate migration numbers (`0095` × 2) — INVESTIGATED, NOT renumbered (reported only)

**Files**: `core/infrastructure/supabase/migrations/0095_content_workflow_extensions.sql` and
`core/infrastructure/supabase/migrations/0095_technical_osint_workbench_gaps.sql`, both dated
2026-08-08, about an hour apart.

**Does it actually cause a problem?** No — checked, not just assumed:

- `mcp__supabase__list_migrations` shows the platform's real migration tracking is keyed by a full
  timestamp `version` (e.g. `20260808034258` / `20260808015152`), independent of the local filename's
  leading `00NN` number. Both `0095` files have distinct, correctly-ordered timestamp versions in the
  live tracking table — no collision at the level that actually matters to Supabase.
- There is no `supabase/config.toml`, no CI workflow, and no runner script anywhere in the repo that
  reads `core/infrastructure/supabase/migrations/` by filename order and applies them — grepped for
  this specifically. Migrations here are applied ad hoc via the MCP `apply_migration` tool (which
  mints its own timestamp); the local `.sql` files are an archival mirror for humans, not a
  machine-consumed ordered queue.
- The one existing prose reference to `"migration 0095"` (in `0101_backfill_affected_cves.sql`'s
  header comment) unambiguously means the OSINT one (`affected_cves` is an OSINT/`intelligence_events`
  column) — not the content-workflow one — so there's no live ambiguity in practice either.

**Why I didn't renumber anyway**: While checking, I found this is not an isolated pair — the
directory has **8 groups of duplicate leading numbers** in total: `0006`, `0007`, `0014`, `0020`,
`0028`, `0030` (×3), `0031` (×3), `0095`, `0096`. (`0096` duplicates too:
`0096_content_workflow_captain_focus.sql` vs `0096_osint_confidence_level_column.sql` — the same
COMMS-002/OSINT pair that produced the `0095` collision, one number later.) Renumbering just the one
pair named in this task while leaving 7 other duplicate groups untouched would be a partial,
inconsistent fix that could read as "the numbering is clean now" when it isn't — and per the Chief
Engineer's Advisory-authority discipline, a systemic/platform-wide convention issue like this is the
kind of thing to flag clearly rather than spot-fix unilaterally mid-task. Conservative action taken:
report exact filenames and the full scope of the pattern, make no changes to the migrations directory
for this finding.

**Recommendation**: A dedicated, scoped pass (own mission) to renumber all 8 duplicate groups at once,
verifying every prose cross-reference (like `0101`'s) is updated consistently — not a one-off fix
buried inside an unrelated task.

**Also worth flagging**: while doing this investigation, a second, live session was actively
minting new migrations in `core/infrastructure/supabase/migrations/` in real time (`0105` through
`0108`, RLS-tightening work, unrelated to Content Workbench) — I had to bump my own new file's number
three times (0105→0107→0108→0109) to stay clear of it. This is a live illustration of exactly the
race-condition risk finding #4 is about, worth folding into scope if/when the renumbering pass above
happens.

---

## Open items / not done

- **Server restart used the existing manual-port workaround, not systemd.** `lcars-portal.service` is
  `inactive/dead`; the live process is a manually-started `next start -p 3200` (systemd is configured
  for port 3100). This is a pre-existing, previously-flagged drift (see memory:
  `health-osint-workbench-built-2026-08-08.md`), not something introduced or fixed by this task — I
  restarted the same way the process was already running (killed the old PID, started a fresh
  `next start -p 3200` from the new build) to get the fixes live without changing that underlying
  deploy posture, which is out of this task's scope.
- **Fix #2 and #3's mobile change were verified by build/bundle inspection and direct logic trace
  against live DB rows, not a real authenticated browser session** — no test login credentials were
  available in this environment. If tighter E2E confidence is wanted, that needs either test
  credentials or a session-cookie-minting helper added to the environment.
- **Fix #4 intentionally left the migrations directory untouched** — see reasoning above. Exact
  filenames reported; recommend a dedicated renumbering mission covering all 8 duplicate groups.
- The review's other findings (P3 stale "Decide" comments in `page.tsx` /
  `api/content-workbench/route.ts`, P4 test coverage, P4 comment cleanup on the
  `generate/route.ts` status-writer exception) were **not in this task's scope of 4 findings** and
  were not touched.
