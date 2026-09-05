# MSN-0363 — Content Workbench (COMMS-002) Single-Person AI Content Desk Uplift

**Mission ID is provisional** — minted as next-after-362 by scanning `.md`/`.ts`/`.py`/`.sql` for the highest existing `MSN-0xxx`, not via a canonical counter (none found in-repo; this is the same minting-drift gap tracked in memory `mission-id-minting-drift`). Confirm/reissue before this is treated as final.

**Status:** Scoped, not started.
**Owner:** Chief Engineer.
**Requested by:** Captain (TJR), via mission brief, 2026-09-05.

---

## 1. Objective

Evolve `/content-workbench` from a 4-column Kanban board into a single-person AI-assisted content desk: AI does preparation (research, drafting, QA advisory), TJR makes decisions (pursue, direction, quality, publish timing). No new multi-user/approval/agent-framework machinery.

Target user-facing model: **Capture → Develop → Review → Schedule/Publish → Learn**, with a "Today — what needs me?" default landing view replacing the current always-visible board.

## 2. Non-Overlap Boundary (hard constraint)

A separate, currently-active session — **`adaptive-themes-workbench-redesign`** (confirmed via `ListAgents`, status busy at scoping time) — is building a named theme system (Archive/Command/Midnight/Horizon/Sanctuary — none of these exist in code yet) and likely touching shared shell/nav components.

**Do not touch, fork, or duplicate:**
- `src/components/ui/WorkbenchShell.tsx` (135 lines, already consolidated 2026-07-18 from 6 forks — this is the de facto AppShell)
- `src/components/ui/DomainToggle.tsx`
- any theme/token file
- global nav, global routing

**This mission's touch surface stays inside:**
- `src/app/content-workbench/**`
- `src/app/api/content-workbench/**`
- `src/app/api/comms/**` (read-only reference; do not alter the canonical `advance` state machine)
- `src/lib/contentScoring.ts` (additive only)
- new: `src/lib/gmailSignalAdapter.ts`, `src/lib/contentSchedulingAdapter.ts` (thin, local)

If a shared component this mission needs is mid-change elsewhere: use its current interface as-is, don't fork it. If genuinely blocked, stub + document the dependency here rather than reimplementing.

## 3. Audit Findings (corrections against the original brief)

Verified by direct code read before scoping, not assumed:

| Brief claim | Verified reality |
|---|---|
| 4-stage Kanban exists (Capture→Research→Content Prep→Proofing) | **Confirmed.** `ContentBoard.tsx`, 848 lines, one file, wraps in `WorkbenchShell`. |
| Canonical `/api/comms/[id]/advance` state machine | **Confirmed**, 5 states (`opportunity→draft→review→approved→ready_to_publish→published`), `discard→archived` from any pre-published stage. Don't touch. |
| `rank_score`/pillar/`captain_focus`/suggested angle only, no fabricated sub-scores | **Confirmed** (`contentScoring.ts` `CaptureScore` interface). But real internal weights (`pillarFit`, `strategic`, `recency`, `cross`, `quality`) are computed and discarded, not returned — exposing them as plain-language "reasons" (brief §7) is grounded, not fabrication. Low-risk additive change. |
| Google Calendar API "already exists" | **Confirmed.** `lib/google-calendar.ts`, OAuth connect/callback routes, `getValidGoogleAccessToken()` already exported for reuse (see next row). |
| Gmail API "already exists" | **Initially found false in first pass — corrected by Captain.** `gmail.readonly` is already in `GOOGLE_OAUTH_SCOPES` (`google-calendar.ts`) under the same stored token as Calendar/Tasks; `getValidGoogleAccessToken()` is explicitly shared for this. No Gmail client module exists yet, but `google-tasks.ts` (122 lines) is the exact adapter pattern to follow: `googleXFetch()` wrapper + 401→`GoogleCalendarDisconnectedError`. A `gmailSignalAdapter.ts` is genuinely low-risk, not greenfield. |
| No git branch/component evidence of the parallel HQ redesign | **Confirmed no code yet** (no theme files, no named-theme strings), but the session is real and active per `ListAgents` — treat the constraint as live, not hypothetical. |

## 4. In Scope

1. **Today/Queue landing** — new default view: "what needs me" surfacing (blocked-on-TJR items, review decisions, high-score opportunities awaiting pursue/ignore, ready-to-publish, upcoming scheduled), pipeline snapshot, compact `+ Capture Idea` trigger (modal/drawer/inline — not a permanently-dominant box).
2. **Content Studio** — single-item focused workspace: editor + research/sources panel + governance (4-point QA) + AI actions + revision history, replacing in-board stage editing. Consumes existing `draft`/`research`/`qa`/`generate`/`ai-review`/`ai-polish`/`revisions` endpoints unchanged.
3. **Pipeline (Queue default, Board secondary)** — reuses `ContentBoard.tsx` logic/data, changes default presentation to a priority-sorted queue; Board view retained but demoted.
4. **Library** — evolve `PortfolioTab.tsx` (139 lines): search, pillar filter, export (existing), + "Reuse Idea" (creates new opportunity row, never mutates the published source record).
5. **Opportunity scoring reasons** — additive change to `contentScoring.ts` return type + capture-result UI, using real existing weights only.
6. **Calendar adapter** — `contentSchedulingAdapter.ts`, thin wrapper over `google-calendar.ts`, for "Coming Up" + suggested publish time. No new calendar system.
7. **Gmail signal adapter** — `gmailSignalAdapter.ts` following `google-tasks.ts`'s pattern. Bounded: explicit label/query only (e.g. a manually-applied Gmail label), never full-inbox scraping. Feeds `scoreCapture()`, same path as manual capture. New local endpoint only.
8. **AI interaction language pass** — consistent "AI proposes, TJR decides" labelling across all AI actions (Generate/Review/Suggest Improvements/Reframe/Shorten/Strengthen Opening); no autonomous-sounding language (no "Auto Approve"/"Auto Publish").
9. **AI Polish diff view** — show current-vs-proposed before apply; apply still goes through the tracked draft-save endpoint, still creates a revision, still resets QA.
10. **Responsive pass** — no horizontal Kanban scroll on mobile/tablet; Studio panels stack vertically.
11. **Regression pass** — capture, scoring, research gate, generation, revisions, QA reset-on-substantive-change, approval, publish, archive/undo, Library/export, RLS, build/lint/existing tests (393 passing per Registry as of last check — reverify).

## 5. Explicitly Out of Scope

Per brief §21/22, unchanged: no client/team approvals, no roles/permissions system, no agent orchestration framework, no reviewer queues, no comment collaboration, no task assignment, no second theme/design system, no global AppShell/nav changes, no new editorial-calendar database, no large editor-framework dependency swap unless proven necessary.

## 6. Schema Changes

None anticipated for Phases 1–6/8–11. If Phase 7 (Gmail) needs a dedup/seen-message marker, prefer a new nullable column on `comms_content` or a small local table over touching `comms_content_revisions`/`content_signals` shape — confirm necessity before writing a migration.

## 7. Sequencing

Phase 1 Today/Queue → Phase 2 Content Studio → Phase 3 Pipeline resequence → Phase 4 Library → Phase 5 Scoring reasons → Phase 6 Calendar adapter → Phase 7 Gmail adapter → Phase 8 AI language/diff pass → Phase 9 Responsive polish → Phase 10 Regression. Each phase mergeable independently; Studio (Phase 2) is the highest-value, highest-effort item and can start once Phase 1's data-priority logic exists (Studio needs "what's blocking" logic anyway).

## 8. Acceptance Criteria

Per original brief §26, unchanged, plus: no edits landed in `WorkbenchShell.tsx`/`DomainToggle.tsx`/theme files; `adaptive-themes-workbench-redesign`'s eventual merge requires no revert/restructure of this mission's work.

## 9. Open Decisions for Captain

- Confirm mission ID (provisional MSN-0363) against canonical registry before this is cited elsewhere.
- Gmail signal adapter (§17): deferred by Captain 2026-09-05 — skipped this pass, revisit once a bounding label/query is chosen.
- Calendar write scope (§16): Captain confirmed 2026-09-05 — `GOOGLE_OAUTH_SCOPES` widened from `calendar.readonly` to `calendar.events`, `createCalendarEvent`/`updateCalendarEventTime`/`deleteCalendarEvent` added to `lib/google-calendar.ts`, schedule endpoint now creates/updates/deletes a real event per scheduled item. **Requires a one-time reconnect** at `/api/auth/google-calendar/connect` for the new scope to take effect on the already-stored token — until then scheduling still works (DB-only) with a surfaced warning, per the route's own fallback.
