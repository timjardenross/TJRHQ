# Chief Engineer Architecture Review — Content Workbench

USS TJR · Registry USS-TJR-003 · Engineering Division · Advisory authority
Reviewer: Chief Engineer persona · Date: 2026-08-09

## Mission Summary

Real architecture review of the Content Workbench (`/content-workbench`), live on the platform and listed in the canonical workbench registry (`lcars-portal/src/lib/workbenches.ts`) as: "Capture, research, draft, proof, and publish comms content end-to-end, plus a Portfolio of everything published — one QA-gated pipeline." Specifically tasked with checking whether the description still matches the live pipeline, given the registry's own comment flags a prior instance of this exact tile drifting (it kept describing a "Captain approval … in Decide" step for weeks after that step was removed).

## Assessment

### What the workbench actually is

Confirmed by reading `lcars-portal/src/app/content-workbench/page.tsx`, `_components/{ContentBoard,CaptureBox,PortfolioTab,shared}.tsx`, and every route under `lcars-portal/src/app/api/content-workbench/` plus `api/comms/[id]/advance` and `api/comms/route.ts`.

Pipeline (COMMS-002, additive to the existing `comms_content` table from migration 0027/0036): **Capture → Research → Content Prep → Proofing**, with a separate **Portfolio** tab for published items. Stage is computed at read time from `status` + `research_completed_at` (`stageOf()` in `api/content-workbench/route.ts`), not stored as a new status value — the pre-existing `comms_content_status_chk` constraint and the canonical `TRANSITIONS` map in `advance/route.ts` are unchanged.

- **Capture**: `CaptureBox.tsx` → `POST /api/content-workbench/capture` → real scoring via `lib/contentScoring.ts`, a TypeScript port of the Python pillar classifier/ranker (8 pillars, keyword-matched, has its own unit test `lib/__tests__/contentScoring.test.ts`, 98 lines). Not mock — every capture gets a real `pillar`, `rank_score`, `captain_focus`.
- **Research**: `PATCH /api/content-workbench/[id]/research` — human-authored brief (angle/notes/sources); `research_completed_at` is the real server-side gate on generating a draft.
- **Content Prep**: `POST /api/content-workbench/[id]/generate` calls a real LLM (Ollama Cloud, `glm-5.2`) with a genuine fallback to a labelled `[DRAFT SCAFFOLD]` template if the LLM call fails — the UI surfaces which mode fired (`d.mode === 'llm'`). Edits go through `PATCH …/draft`, which appends to a real `comms_content_revisions` table (migration 0095).
- **Proofing**: 4-item QA checklist (`PATCH …/qa`), an AI-assisted first pass (`POST …/ai-review`, advisory-only, never writes `qa_status` itself), an AI-assisted revision proposal (`POST …/ai-polish`, human must click Apply), then Approve → Publish, all firing the single canonical `POST /api/comms/[id]/advance` state machine.
- **Portfolio**: reads `GET /api/comms?status=published` — same `comms_content` table, no separate store.

Every API route in this set — capture, research, generate, draft, qa, revisions, ai-review, ai-polish, advance, and the board's own `GET /api/content-workbench` — calls `requireSession()` and returns 401 if there's no session. Page access is additionally gated by `middleware.ts`'s global auth redirect (`/content-workbench` is not in `PUBLIC_ROUTE_ALLOWLIST`). This matches the pattern the 2026-07-18 WORKBENCH-REVIEW fixed platform-wide after finding 9 routes reachable with no auth check.

### Registry description vs. reality: the *tile* is accurate now — but the drift recurred inside the code itself

The task asked specifically whether the "Captain approval in Decide" drift is still present. **The registry tile itself is correct** — its current wording ("one QA-gated pipeline") makes no claim about a Decide step, and `workbenches.ts`'s own comment documents that this was deliberately fixed there.

But the same claim — now false — is still live in two source comments that were *not* touched when the behavior changed:

- `lcars-portal/src/app/content-workbench/page.tsx:17-18`: *"mark_published still only queues a governed proposal — the Captain approves the actual publish in Decide, same as always."*
- `lcars-portal/src/app/api/content-workbench/route.ts:8-11,18-22`: *"the Captain still makes the final call in Decide"* / *"awaiting the Captain's sign-off in Decide via the same governed publish_content proposal."*

Both are wrong as of commit `9fb2640` (2026-08-08, *"Fix Content Workbench publish flow: mark_published stalled forever, no page ever drained the queue it fed"*), which reverted `mark_published` to a direct status flip precisely because no `/decide` page was ever built to drain the approval queue it fed — confirmed by that commit's own message and by `advance/route.ts`'s current header comment, and independently confirmed there is no `/decide` route in the app (`find lcars-portal/src/app -iname "*decide*"` returns nothing under `app/`; only unrelated `api/self-improvement/decide` and `api/knowledge-library/…/decide` routes exist). The fix commit touched `advance/route.ts` and `ContentBoard.tsx` (which now correctly says *"mark_published is a direct flip again now"*) but not `page.tsx` or `api/content-workbench/route.ts`, leaving their header comments stale. This is the identical failure mode the registry already learned from — a description outliving the behavior it described — just relocated from the tile into two file headers. Low runtime risk (comments don't execute), but exactly the kind of stale doc that leads a future engineer to reintroduce the now-known-broken gate.

### Real, verified bug: revision history is unreadable due to a client/RLS mismatch

`GET /api/content-workbench/[id]/revisions/route.ts` reads `comms_content_revisions` using `createSupabaseServerClient()` — the anon-key, session-cookie client, subject to RLS. Every *write* to that table (`generate/route.ts`, `draft/route.ts`) uses the service-role client, which bypasses RLS.

Checked live against the production Supabase project (`cjvrpjwewsrumnbdydgg`):
```
comms_content            relrowsecurity=true, policy "auth_read" (SELECT, role authenticated, qual: true)
comms_content_revisions  relrowsecurity=true, NO policies at all
```
Migration 0095's own comment even documents the intent: *"No anon policy: mirrors comms_content's own write pattern (service-role client only, from session-gated API routes …)"* — but the GET route was never written that way; it uses the session client instead of the service client the comment assumes. With RLS enabled and zero policies, `authenticated`-role reads return an empty result set silently (no error). Confirmed there is real data being hidden: **10 revision rows across 5 distinct content items** currently in the live table, and 4 items currently sitting in `review`/`ready_to_publish` today. So "Show Revision History" in the Content Prep stage modal will render "No revisions yet." for every item, always, regardless of actual history — a silent failure, not a crash, so it's easy to miss in manual testing. This is the same dual-client (anon vs. service/session-aware) mismatch pattern flagged before in `ros-data.ts` (memory: `ros-data-401-regression-2026-07-18.md`) — worth treating as a recurring class of bug, not a one-off.

Fix is small and low-risk: switch `revisions/route.ts` to `serviceClient()` (consistent with every other route in this API surface) or add an `authenticated` SELECT policy on `comms_content_revisions` mirroring `comms_content`'s `auth_read`.

### "QA-gated pipeline" is enforced in the UI, not at the data layer

The registry description's central claim is "one QA-gated pipeline." In practice the QA gate is client-side only: `ProofingStageBody` only renders the "Approve →" button when `qaStatus === 'qa_passed'`, but `POST /api/comms/[id]/advance` with `trigger: 'captain_approved'` on a `review`-status item succeeds unconditionally — the route never reads or checks `qa_checklist`/`qa_status` (confirmed by reading `TRANSITIONS` and the full `POST` handler in `advance/route.ts`). There's no DB constraint tying `qa_status='qa_passed'` to the `review→approved` transition either — the `qa_status_chk` constraint only validates the enum's own values. Contrast this with the Research→Content-Prep gate (`research_completed_at`), which *is* enforced server-side in `generate/route.ts`. Given this is a single-tenant app where "any authenticated session is the Captain" (per `supabase-server.ts`'s own comment), the practical risk is low — there's no second party to route around the UI gate against — but it means the registry's "QA-gated" language describes a UI convention, not an invariant the system actually holds anywhere the UI could be bypassed (a direct `fetch` from devtools, a future automation, an LLM-driven action).

### Secondary observation: two code paths can flip `comms_content.status`

Several route comments (e.g. `research/route.ts`: *"advance() stays the only place status transitions happen"*) assert `advance/route.ts` is the sole status-writer. That's true for every route reviewed except `generate/route.ts` (both the Content Workbench's and the original `comms/generate/route.ts`), which writes `status: 'draft'` directly rather than going through `advance()`'s `TRANSITIONS` map. This is intentional (AI-drafting isn't one of `advance()`'s named triggers) and not currently harmful, but it means the "single canonical state machine" claim repeated across this codebase's comments has one quiet exception. Worth a one-line comment fix so the next engineer doesn't add a third.

### Test coverage

Only `lib/contentScoring.ts` (pure scoring function) has unit tests. None of the 9 API routes under `api/content-workbench/` or `api/comms/[id]/advance`, and none of the 4 React components (`ContentBoard`, `CaptureBox`, `PortfolioTab`, `page.tsx`), have any test coverage — confirmed via repo-wide search for test files referencing `content-workbench` or `contentScoring` (only the one scoring test file matched). The revision-history bug above is exactly the class of defect route-level tests would have caught (an empty-array 200 response looks identical to "no revisions exist").

### What's solid

- Real data throughout — no mock/stub data sources found anywhere in this workbench's read or write paths.
- Consistent auth gating (route-level `requireSession()` + global middleware) across all 9 API routes.
- Genuine LLM integration with honest degrade-to-scaffold behavior on `generate`/`ai-review`, and a hard-fail (502, no fake output) on `ai-polish` when the LLM is unavailable, which is the right call for a feature whose entire value is the LLM's output.
- `DomainToggle` (Pipeline/Portfolio tabs) is a real WAI-ARIA tablist (`role="tablist"`/`role="tab"`/`aria-selected` + arrow-key handling, confirmed in `components/ui/DomainToggle.tsx`, has its own test file) — the redesign comment's claim of fixing a prior accessibility gap checks out.
- Discard is soft (`archived`, not deleted) and reversible; published items are excluded from discard, matching the "reputation portfolio, permanent record" framing in the schema comments.

## Recommendations

1. **P2 — Fix the revision-history bug.** Switch `api/content-workbench/[id]/revisions/route.ts` to the service-role client (one-line change, matches every sibling route in this file set). Currently silent data loss in the UI for a feature that exists specifically to show editorial history.
2. **P3 — Fix the two stale "Decide" comments.** Update `content-workbench/page.tsx:14-18` and `api/content-workbench/route.ts:6-11,18-22` to match `advance/route.ts`'s and `ContentBoard.tsx`'s current, accurate description of the direct `mark_published` flip. Comment-only change, no behavior risk, closes off the exact failure mode the registry already had to learn from once.
3. **P3 — Decide whether "QA-gated" should become server-enforced.** Either add a server-side check in `advance/route.ts` (`captain_approved` requires `qa_status === 'qa_passed'`) so the registry's "QA-gated pipeline" claim is a real invariant, or soften the description to reflect that QA is currently a UI convention. Low urgency given single-tenant/single-actor risk profile, but worth a Captain decision on which is intended.
4. **P4 — Add route-level tests** for at minimum `advance/route.ts` (the shared state machine every workbench pipeline depends on) and the revisions route (would have caught #1 directly).
5. **P4 — Comment cleanup**: note the `generate/route.ts` exception to the "advance() is the only status-writer" claim repeated elsewhere, so it isn't rediscovered as a surprise later.

## Next Actions

Immediate, concrete: fix #1 (revision route client) and #2 (stale comments) together — both are small, low-risk, same-file-family changes and directly answer what this review was commissioned to check. I have not made any code changes; this is Advisory only per my authority.

## Mission Status

Advisory only. No security-severity finding here rises to the escalation bar (single-tenant app, only the Captain's own session can reach any of this) — flagging #1 and #3 clearly rather than burying them, per standing practice, but neither requires Captain sign-off before a small fix, just a go-ahead. Registry tile itself: confirmed accurate, no drift. Drift found instead in two source-file comments not covered by the registry's earlier fix.
