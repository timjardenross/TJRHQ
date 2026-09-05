# MSN-0364 — Captain's Chair Redesign: Command & Synthesis Surface

**Mission ID is provisional** — same minting-drift caveat as MSN-0363 (memory `mission-id-minting-drift`); no canonical counter found in-repo. Confirm before citing elsewhere.

**Status:** Scoped, not started.
**Owner:** Chief Engineer.
**Requested by:** Captain (TJR), via mission brief, 2026-09-05.

---

## 1. Objective

Redesign `/captains-chair-workbench` from a stack of dashboard widgets into a synthesis surface: one interpreted Command Status, a real decision queue (Needs You), domain-level Situation, a merged Ahead (Calendar+Reminders), an elevated Captain's Brief, and a simplified Captain's Log capture. Target hierarchy: **Posture → Attention → Situation → Ahead → Brief → Capture**.

## 2. Non-Overlap Boundary (hard constraint)

Same live boundary as MSN-0363: `adaptive-themes-workbench-redesign` owns AppShell/sidebar/themes and already merged once today (`73743aaa` — added `Sidebar.tsx`/`ThemeSelector.tsx`/`theme.ts`, rewrote `WorkbenchShell.tsx` internals). **Do not touch** `WorkbenchShell.tsx`, `DomainToggle.tsx`, or any theme file. Captain's Chair's own `page.tsx` already consumes `WorkbenchShell` via its unchanged external prop contract (`title/eyebrow/tagline/right/tabs/back/wide/children`) — confirmed compatible post-merge, same pattern as Content Workbench, no action needed there beyond normal usage.

Touch surface for this mission:
- `src/app/captains-chair-workbench/**` (page.tsx, notebook/, alerts/, `__tests__/`)
- `src/lib/captainsChairData.ts`, `src/lib/useROSData.ts`, `src/lib/useAlerts.ts`, `src/lib/departments.ts` (read/extend, don't fork)
- `src/components/TodaysBriefPanel.tsx`, `src/components/SituationBadge.tsx`
- New: a Captain's Chair synthesis module (naming TBD in Phase 2) and any narrowly-scoped new API route for combining existing sources — not a new database.

## 3. Audit Findings (corrections against the brief)

Verified by direct code read before scoping:

| Brief assumption | Verified reality |
|---|---|
| 5 equal-weight KPI cards | **Confirmed.** `SituationBadge.tsx` (40 lines) renders 5: Recovery Posture, Operational Risk, Interrupt Now, Emergency Alerts, Background Systems. No cross-interpretation logic exists — genuinely new synthesis work, not a restyle. |
| Signal Snapshot exposes source systems | **Confirmed.** 3 raw cards (Capacity Today, Top OSINT Signal, Top Health Signal) in `page.tsx`, no synthesis. |
| Captain's Brief needs elevating/building | **Partially wrong — it already exists and is more real than the brief assumes.** `TodaysBriefPanel.tsx` reads `captains_daily_briefs`, populated by `intelligence/captains_brief.py`'s LLM chain (Gemini→Mistral→Ollama fallback, real synthesis, not templated). Runs daily 07:00 AEST. Already has Read Aloud. This needs **repositioning/prominence**, not building from scratch. |
| "184 recommendations" / diagnostic stats overexposed | **Confirmed as a real, separate, more fragile data source.** A second "Today's Briefing" stat tile reads `/api/captain-brief` → `core/context-assembly/context_service.py`, which depends on an external always-running Python process (`CONTEXT_SERVICE_URL`) — its own code comments document a prior silent-breakage incident on Vercel's serverless runtime. This is exactly what brief §11 wants demoted, and it's also the shakier of the two brief-like sources — treat as detail-view only, not a load-bearing Command Status input. |
| Captain's Notebook is underused / simple capture | **Undersells what exists.** `notebook/page.tsx` (604 lines) backs a real workflow (`CAPTURED→OFFICER_REVIEW→NUMBER_ONE_REVIEW→READY_FOR_ROUTING→ROUTED→ARCHIVED` on `intelligence_notes`, with officer findings + confidence/strategic-alignment scores). A `recommended_route` column exists but **no code path currently populates it via a live model call** — needs verification whether anything else sets it before Phase 7 assumes it's wired. Captain's Log should simplify the *entry* UX without discarding this triage backend. |
| Canonical posture states "reuse where possible" | **Exists, one caveat.** `useROSData.ts`'s `fetchRecoveryPostureWithStatus()` gives a real, live-derived `RecoveryPostureBand` (`STRONG\|STABLE\|FRAGILE\|REST\|UNKNOWN`) — reuse this directly. But its `guidance` field is **hardcoded `mockGuidance`** (comment: "Phase 2: replace with health_insights fetch") — not currently rendered since the page only destructures `posture`, but Command Status's synthesis logic must not accidentally surface `guidance` as if real. |
| Google Calendar "already exists" | **Confirmed, already wired.** `useCalendarToday()` reads `/api/calendar/today`. Plus this session's own MSN-0363 work added write scope (`calendar.events`) if Ahead ever needs to create/edit events — unlikely needed here since Ahead only reads. |
| Redundant Read Aloud controls | **Confirmed, 2 independent buttons today** — `SituationBadge`'s `speakAlertsAloud()` and `TodaysBriefPanel`'s `speakBriefAloud()`. Consolidation opportunity, not fabrication. |
| Honest degraded-state handling ("unavailable ≠ clear") | **Already partially built**, reuse don't rebuild: `useAlerts.ts` exposes `failedSources`/`totalSources`; `useCalendarToday` exposes a `calendarStatus: 'disconnected'\|'error'\|'ok'` tri-state; a 2026-08-29 fix already applied the "curated, not raw counts" instinct brief §7 asks for. |

## 4. In Scope

1. **Command Status** — new synthesis: combine `useROSData` (posture), `useOperationalRisk`, interrupt count, `useEmergencyAlerts`, `useAgentHealth` (systems) into one interpreted headline + supporting-signal strip, replacing `SituationBadge`'s 5 equal cards. Must explicitly distinguish PERSONAL vs EXTERNAL vs COMMAND POSTURE per brief §6, with a real "why" line, not a template string with blanks filled in.
2. **Needs You** — decision-queue replacing the 3 CountTiles + Live Alerts list: real human-gate items only (content awaiting publish — now available via MSN-0363's Content Workbench `scheduled_for`/`ready_to_publish` state, capture triage backlog, Human Systems review, unresolved alerts, mission exceptions). Priority-ordered (urgency ≠ severity per brief). Real empty state, not manufactured.
3. **Situation** — replace the 3 raw Signal Snapshot cards with domain-grouped read-only summaries (Personal/Environment/Systems) routing to source workbenches, not duplicating them. Only render domains with material content (brief's own "don't force a fixed card count" rule).
4. **Ahead** — merge `useCalendarToday` + `useReminders` into one adaptive component, default 24-48h horizon, compact when empty. Read-only against Calendar (no write needed for this surface).
5. **Captain's Brief** — reposition `TodaysBriefPanel` to the elevated slot brief wants (full-width, prominent, near top of the meaningful content, not buried under Signal Snapshot/Calendar/Reminders). Consolidate to one Read Aloud control for the whole page's narrative content, removing the `SituationBadge` alerts-only one if it becomes redundant post-Command-Status-redesign (evaluate in Phase 6 — don't remove blind).
6. **Demote diagnostics** — move the `/api/captain-brief` stat tile (confidence/priorities/warnings/recommendation counts) behind a "Brief Details" disclosure, not a headline. Given its own fragility (external service dependency), also surface a clear "unavailable" state distinct from "0" when `CONTEXT_SERVICE_URL` is unreachable.
7. **Captain's Log** — simplify `notebook/page.tsx`'s entry UX into a compact capture box on the main Chair page (matching Content Workbench's `QuickCaptureModal` pattern from MSN-0363 — reuse that interaction shape, not its code, since it's Content-Workbench-local by design). Suggested-destination routing: verify first whether `recommended_route` is populated anywhere live; if not, this is new classification logic (simple LLM call via the existing model-router, per brief's "no agent framework" constraint), gated behind human confirmation before it changes any downstream state, per brief §12.
8. **Layout/responsive** — brief §13/§14 order, no horizontal scroll on mobile, tablet as specified.
9. **Regression** — existing 4-test `__tests__/page.test.tsx` baseline must still pass (situation-strip defaults, alert tier display, failed-job display, curated-not-raw-counts) — these tests encode exactly the behaviours this redesign must preserve, not just avoid breaking incidentally.

## 5. Explicitly Out of Scope

Per brief §20 and MSN-0363's own precedent: no new AppShell/nav/theme engine, no agent framework, no second calendar system, no duplicated workbench functionality, no roles/permissions/collaboration, no configurable dashboard builder, no drag/drop.

## 6. Data / API Approach (brief §17)

No new Captain's Chair database. Preferred shape — a client-side (or thin route) synthesis layer over existing hooks in `captainsChairData.ts`/`useROSData.ts`/`useAlerts.ts`, producing an in-memory view model (`commandStatus`, `needsYou[]`, `situation[]`, `ahead`, `captainsBrief`, `captainsLog`) without a new persisted table. A server-side synthesis endpoint is only justified if the "why" narration for Command Status needs an LLM call (likely yes, for the interpretation sentence) — route that through the existing model-router (`core/model-router`, already the canonical LLM gateway per SUOC registry), not a new inference path.

## 7. Sequencing

Matches brief §21 phases 1-9. Phase 1 (audit) is this document. Suggested adjustment: fold Phase 2 (synthesis model) and Phase 3 (Command Status) together, since the view-model's first real consumer is Command Status anyway — building the model in the abstract first risks over-designing before Needs You/Situation reveal what it actually needs to hold.

## 8. Acceptance Criteria

Per brief §22, unchanged, plus: existing `__tests__/page.test.tsx` assertions still pass or are deliberately superseded with an equal-or-stronger replacement test (not silently dropped); no edits to `WorkbenchShell.tsx`/`DomainToggle.tsx`/theme files.

## 9. Open Decisions for Captain

- Confirm mission ID (provisional MSN-0364).
- Command Status's interpretation sentence: template-based (fast, deterministic, matches existing `departments.ts` tone-mapping style) or LLM-generated (richer, matches Captain's Brief's own synthesis approach, adds a model-router dependency)? Recommend template-based for Command Status (needs to be instant/always-available) and reserve LLM synthesis for Captain's Brief, which already works that way.
- `recommended_route` on `intelligence_notes`: needs a quick check (Phase 1 follow-up, cheap) whether any existing Python job populates it before Phase 7 assumes new classification logic is needed from scratch.
- Should the `SituationBadge` alerts-only Read Aloud button be removed once Command Status ships, or kept as a narrower "just the alerts" option alongside a new page-level one? Brief says avoid redundant controls but doesn't mandate exactly one.
