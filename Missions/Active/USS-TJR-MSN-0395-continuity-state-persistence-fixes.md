# USS-TJR-MSN-0395 — Continuity & State-Persistence Fixes (Mission 7 Phase 16 follow-up)

## Mission Header

- **Mission ID:** USS-TJR-MSN-0395 (minted via `python3 tools/mint_id.py MSN`, 2026-09-20 —
  see Pre-flight item 1 below for a real collision this mint avoided)
- **Priority:** P1 — functional correctness bugs in the Captain's actual task-execution flow
  (Ready Room, Capture, Content, Knowledge Workbench), not a visual/cosmetic issue. Distinct
  from, and not blocking, USS-TJR-MSN-0394 (Endeavour 27) — that mission stays gated on this
  repo's Mission 7 branch finishing, per its own doc; this mission is a direct, narrow
  continuation of Mission 7's own findings, not new scope.
- **Source:** Mission 7 (USS-TJR-MSN-0393) Phase 16 — the full per-workbench PURPOSE/ENTRY/
  EXIT/PRIMARY ACTION/NOISE/DUPLICATION/CONTEXT/CONTINUITY/MOBILE write-up (item 1,
  CLOSED-WITH-EVIDENCE) surfaced two real CONTINUITY defects during live interaction testing,
  plus a third related one found by this session's own code-level follow-up read. See §3.16 of
  that mission's doc for the full original evidence (timing trials, screenshots, DOM checks).

## Pre-flight

1. **Existing-entry check.** This mission doesn't add a row to an existing source/ADR/
   scheduler/specialist list (AGENTS.md sense) — it's a new mission doc. The one check that
   matters is the mission ID itself, and it caught a real collision:
   ```
   $ python3 tools/mint_id.py MSN   # run from a checkout of origin/main
   id_registry: counter drift detected for MSN -- stored=390 true_max=393 (source=repo scan,
   MSN-0393). Auto-bumping counter before minting.
   USS-TJR-MSN-0394
   ```
   **That result is wrong to use** — `USS-TJR-MSN-0394` is already reserved (Endeavour 27,
   PR #292), but only on an unmerged branch (`claude/endeavour-27-mission-brief`), so the
   tool's repo-scan (working-directory grep, not cross-branch, not the `missions` Supabase
   table either since this was never a real mission-table row) couldn't see it. Manually
   corrected `.id-counters.json` to `394` before re-minting, which then correctly returned
   `USS-TJR-MSN-0395`:
   ```
   $ python3 tools/mint_id.py MSN   # after manually setting stored=394
   USS-TJR-MSN-0395
   ```
   Worth a note for whoever eventually consolidates the mission-ID registry (AGENTS.md's own
   "this list will go stale" caveat): `mint_id.py`'s repo scan is single-checkout, so two
   sessions minting from two different unmerged branches at once can still collide. Not fixed
   here — out of scope, flagged for the next registry-tooling pass.

2. **Premise verification.** Every claim below was checked against the real repo state
   2026-09-20 (this session read the actual source files, not just Mission 7's write-up):
   - *Claimed (Phase 16, §3.16):* Ready Room/Capture Workbench/Content Workbench's tab/domain
     URL-sync is "flaky" under live interaction testing (4/4 fail at 1.5s wait on Ready Room,
     1/3 succeed at 2.5s; 3/3 fail on Capture; 1/1 fail on Content), not yet root-caused, and
     not yet confirmed as a real product bug vs. a Playwright/dev-mode artifact.
     *Verified and root-caused this session* by reading all three handlers directly:
     - `ready-room/page.tsx`'s `changeDomain` (line ~72-78)
     - `capture-workbench/page.tsx`'s `syncUrl` (line ~78-83, called by `changeDomain`/
       `changeFilter`/`filterToInbox`)
     - `content-workbench/page.tsx`'s `setTab` (line ~79-84)

     All three share the identical shape: `new URLSearchParams(Array.from(params.entries()))`
     — building the *next* URL from `useSearchParams()`'s current React-hook value, then
     `router.replace(...)`. Next.js's App Router `useSearchParams()` updates asynchronously
     after `router.replace()` (it's not a synchronous state setter) — so **two state-changing
     calls fired close together, before the first `router.replace()`'s navigation has
     re-rendered the component with fresh `params`, will race**: the second call builds its
     URL from the *stale* `params` snapshot (missing the first call's change) and overwrites
     it. This is a genuine, code-level, verifiable mechanism — not just "reported as flaky."
     It also matches Phase 16's own trial data precisely: a *single* deliberate click never
     races (nothing to race against), which is consistent with "not reproduced with a human
     clicking in a real browser this pass, only with Playwright" — Playwright's fast, close-
     together interactions are exactly the trigger condition, and a human double-tapping a
     toggle quickly could hit the same race. **This is a real, root-caused bug, not (only) a
     test-environment artifact** — see §1 below for the recommended fix shape.
   - *Claimed (Phase 16, §3.16):* Knowledge Workbench's Memory-view search box loses its
     query on any navigation away, "confirmed both live and in the source."
     *Verified* — `knowledge-workbench/_components/MemoryView.tsx` lines 62-63:
     `searchQuery`/`debouncedQuery` are plain `useState`, no `router.replace`/URL param, no
     `localStorage`/`sessionStorage` read or write anywhere in the file. `activeTab`
     (line 57) is the same — plain `useState`. Confirmed: this is a real, 100%-reproducible
     gap, exactly as Phase 16 reported.
   - *New finding this session (not in Phase 16's write-up, found while reading the same
     area for the above):* `content-workbench/page.tsx`'s `selectedContentId` (which item is
     open in the Studio) has the **same** gap as Knowledge Workbench's search box — Phase 16
     flagged this too (§3.16, `/content-workbench` entry) as "code-confirmed, not yet
     live-interaction-confirmed" (the test account had no content items to open). Verified
     directly: `setSelectedContentId` (line 76, `openStudio`/`closeStudio` functions) has no
     accompanying URL sync or storage write, unlike `setTab` which at least attempts one
     (Stream A's race notwithstanding). Folded into this mission's scope (§1, Stream C) since
     it's the same root problem (state not surviving navigation) on the same page Stream A's
     fix already touches.
   - *Claimed (Phase 16, §3.16, `/mission-workbench` entry):* 4 console 404 errors on page
     load, confirmed independently in both Phase 14 and Phase 16 (two separate sessions),
     never traced to a specific resource.
     *Verified as reported* — this session did not re-trace it (no live-environment access
     here), but two independent live sessions agreeing is real signal, not noise. Folded in
     as a lower-priority Stream (§1, Stream D) — investigate and fix if time allows, explicitly
     not blocking the mission's Acceptance criteria below.
   - *Claimed (implicit — worth checking before assuming URL-sync elsewhere is fine):*
     Phase 16 itself flagged Search (`/search`) and Timeline (`/timeline`) as untested for
     CONTEXT/CONTINUITY, explicitly noting "worth a fast follow-up given what was found" at
     Knowledge Workbench. *Not yet verified either way this session* (no live environment) —
     folded in as a verification-first Stream (§1, Stream E), not assumed broken or assumed
     fine.
   - *Precedent check:* is there an existing repo pattern for "state that should survive
     navigation but isn't a permanent record" (as distinct from `localStorage`'s existing use
     in `advisory-workbench`'s `ThinkView`/`PerspectivesView`/`ConsultView`, which persists a
     session *log* across visits, a different use case)? None found beyond the (currently
     racy) URL-sync pattern itself — Streams B/C below need to pick a shape (URL sync,
     `sessionStorage`, or both) rather than assume one exists to copy.

3. **Explicitly not in scope.** See dedicated section below.

## Explicitly Not In Scope

- **USS-TJR-MSN-0394 (Endeavour 27)** — the visual/design-system transformation. Unrelated
  surface area (styling/tokens vs. state-persistence logic) and explicitly sequenced to start
  only once Mission 7's branch work is fully done; this mission's fixes land on Mission 7's
  same branch lineage and should merge before Endeavour 27 starts, not block or be blocked by
  its own separate scoping.
- **Mission 7 item 15** (the Captain-flagged theme-palette complaint) — open, deferred to
  Visual-Design-Officer governance per Mission 7's own §5, unrelated to state-persistence.
- **The `/mission-workbench` 404s' root cause, if it turns out to be non-trivial** — Stream D
  is investigate-and-fix-if-tractable, not a blocking commitment; if the traced resource turns
  out to need real backend/infra work, stop at "here's what's 404ing and why" and hand off
  rather than absorbing new scope.
- **A general audit of every workbench's state-persistence behaviour** — Phase 16 already
  covered PURPOSE/ENTRY/EXIT/PRIMARY ACTION/NOISE/DUPLICATION/MOBILE for all 21; this mission
  only touches the specific CONTINUITY gaps Phase 16 found live-tested or code-confirmed
  (Ready Room, Capture, Content, Knowledge) plus the two explicitly-flagged follow-ups
  (Search, Timeline). Not a new full sweep.
- **Any change to the `?domain=unstick&task=` deep-link contract** (Mission 7 Phase 12, item
  2) or the Hub→Ready Room posture-default logic (Phase 2) — both must keep working exactly
  as-is; this mission's fix to `changeDomain` must preserve `captainHasChosen`'s "Captain's
  explicit choice always wins" invariant (`ready-room/page.tsx` lines 57-66), not just fix the
  URL-sync race in isolation.

## 1. Scope / Streams

**Stream A — Fix the URL-sync race (Ready Room, Capture Workbench, Content Workbench).**
Root cause per Pre-flight: building the next `URLSearchParams` from `useSearchParams()`'s
React-hook value races when two state-changing calls happen close together, because
`router.replace()` doesn't update that hook synchronously. Two fix shapes to weigh (pick one,
don't guess — verify against live rapid-interaction testing per Stream F before calling it
fixed):
  1. Track the "last URL this component itself wrote" in a `ref`, updated synchronously
     alongside every `router.replace()` call, and build each new URL from that ref instead of
     from `params` — this sidesteps the async-update race entirely since the ref is always
     current at the moment of the next call, regardless of whether React has re-rendered yet.
  2. Read `window.location.search` directly at call time instead of the hook's snapshot — also
     current, but only viable in a client-only handler (already true for all three: `'use
     client'`, called from `onClick`, never during render).
  Recommend option 1 (ref-based) as more idiomatic/testable, but this is a judgement call for
  whoever implements it with live verification in hand, not dictated here. Apply consistently
  across all three files — same bug, same fix shape, don't solve it three different ways.
  Preserve `ready-room/page.tsx`'s `captainHasChosen` ref logic exactly (§ Explicitly Not In
  Scope above) and `capture-workbench/page.tsx`'s multi-field `syncUrl({domain, filter})`
  batching (already a partial mitigation for the *within-one-call* case — don't regress it).

**Stream B — Knowledge Workbench Memory-view search persistence.** `MemoryView.tsx`'s
`searchQuery`/`activeTab` need to survive navigation away and back. Two shapes to weigh:
  - URL sync (`?q=<query>&view=<tab>` on `/knowledge-workbench`) — consistent with the
    pattern every other workbench in this repo already uses for this kind of state, but
    inherits Stream A's race if implemented naively; land Stream A first (or in the same
    pass) so this isn't built on a known-broken pattern.
  - `sessionStorage` (precedent: `advisory-workbench`'s `ThinkView`/`PerspectivesView`/
    `ConsultView` already use `localStorage` with the same repo's established `try { } catch
    { /* ignore */ }` guard pattern for browser-storage access — `sessionStorage` for a
    *search query specifically* arguably fits its per-visit, not-worth-bookmarking nature
    better than a URL param would, and sidesteps Stream A's race entirely since it doesn't
    involve `router.replace()` at all).
  Pick one deliberately (state the reasoning in this doc's phase record when implemented),
  don't default to copying the URL-sync pattern just because it's already used elsewhere.

**Stream C — Content Workbench `selectedContentId` persistence.** Same shape decision as
Stream B, same page Stream A already touches for `tab`. `openStudio`/`closeStudio`
(`content-workbench/page.tsx`) need the chosen persistence mechanism added. Verify live once
the test account has (or is seeded with) a real content item to open into the Studio — Phase
16 could not test this live for lack of data, only confirm the code gap.

**Stream D — `/mission-workbench` console 404s (lower priority, investigate-and-fix-if-
tractable).** Confirmed independently by two separate live sessions (Phase 14 and Phase 16),
never traced. Open the Network tab (or equivalent) against the live page, identify the exact
404ing resource/URL, and either fix it (if it's a stale reference in this repo) or report
exactly what it is and why it's out of this mission's reach (if it's backend/infra). Does not
block this mission's Acceptance.

**Stream E — Search/Timeline state-persistence check.** Phase 16 flagged both as untested,
explicitly worth checking given what Knowledge Workbench turned out to have. Read
`search/page.tsx` and `timeline/page.tsx` for any filter/query state, determine whether it's
already URL-synced, storage-synced, or not persisted at all, and apply the same fix pattern
Streams B/C land on if a real gap is found. If both turn out fine, say so plainly rather than
padding the mission with an unneeded fix.

**Stream F — Verification, matching Phase 16's own methodology.** Live-environment access
required (same wall every phase of Mission 7 has hit — if the implementing session doesn't
have it, say so and hand off rather than guessing). Re-run the same kind of repeated-trial
timing test Phase 16 used (switch tabs/domains at varying post-load delays, check whether the
URL and a hard refresh both land back on the expected state) for Streams A/B/C, not just a
single click each. Additionally, if feasible, get a human spot-check (a real person clicking
through, not just Playwright) per Phase 16's own recommendation — Playwright's fast clicking
is the most reliable way to trigger Stream A's race, but a human confirmation that the fix
holds under ordinary use closes the "is this a test artifact" question Phase 16 left open.

## 2. Acceptance

- Ready Room's Do/Unstick Me toggle: the URL's `domain` param reliably matches the visually
  active tab after a switch, verified across repeated trials at varying delays (not just one
  click), and a hard refresh lands back on the same tab that was active before the refresh.
- Capture Workbench's Capture/Inbox toggle and its `filter` param: same standard.
- Content Workbench's `tab` param and (once Stream C lands) `selectedContentId`: same standard
  for `tab`; for `selectedContentId`, opening a Studio item and refreshing lands back in that
  same item (or a graceful, deliberate fallback if that's the chosen design — not a silent
  drop back to the tab list).
- Knowledge Workbench's Memory-view search query survives a navigate-away-and-back (or a
  refresh, if URL-synced) — verified live, not just in code.
- `ready-room/page.tsx`'s `captainHasChosen` invariant and Mission 7 Phase 12's
  `?domain=unstick&task=` deep-link contract both still work exactly as before — regression-
  checked, not assumed unaffected.
- Search/Timeline's state-persistence status determined and, if a real gap was found, fixed to
  the same standard as Streams B/C; if no gap was found, stated as such.
- `/mission-workbench`'s console 404s either fixed or precisely characterised (Stream D is
  best-effort, not blocking).
- Full test suite green, `npx tsc --noEmit`/`npx eslint` clean, `npm run build` succeeds.
- Mission 7's own doc (`USS-TJR-MSN-0393-...md`) updated with this mission's findings/fixes as
  a cross-reference in its §5 deferred register or §3.x phase log — this mission fixes bugs
  Mission 7's own Phase 16 found, so Mission 7's record should point at where they got fixed,
  not leave them as a dangling "flagged, not fixed" note once they're resolved.

## 3. Reporting

### Phase 1 — Implementation + live verification (2026-09-20)

**Stream A — Fixed.** Added `src/lib/useUrlSync.ts`: a `writeParams` helper
that tracks the URL this component itself last wrote in a `ref`, updated
synchronously on every call, so the next call always builds from a current
snapshot regardless of whether `useSearchParams()` has caught up yet (option
1 from the mission's two fix shapes — the ref approach). Applied identically
to `ready-room/page.tsx`'s `changeDomain`, `capture-workbench/page.tsx`'s
`syncUrl`, and `content-workbench/page.tsx`'s `setTab`. `captainHasChosen`
and the `?domain=unstick&task=` deep-link contract preserved and regression-
checked live (see below).

*Live verification (Playwright against a local dev server, real Supabase,
dedicated test account — no MCP browser available in this container, root-
sandbox blocked, so driven directly via the project's own `playwright`
package per prior-session precedent):* repeated-trial rapid toggling at
50/150/400/1000ms delays on all three pages. At 400ms+ the URL always
matched the visually active tab, every trial. At 50-150ms the *visual*
state (`aria-selected`) always flipped correctly and instantly, but the URL
bar took longer to reflect it — confirmed by watching the URL after each
individual click rather than only at the end: it settled to the correct
final value (e.g. `?domain=do`) by ~2s, just slower than this test's
original fixed post-click wait. That is Next.js dev-mode's `router.replace()`
RSC round-trip latency (route-compile/fetch overhead specific to `next dev`,
not present the same way in production), not a surviving race — the ref-
based fix has no time-dependent mechanism once the click handler actually
runs, so a slow-to-settle-but-eventually-correct URL is consistent with
"fixed, but dev-mode is slow," not with the original bug (which produced a
*wrong* final URL, not a *delayed-correct* one). Hard refresh and the
`?domain=unstick&task=<id>` deep-link regression check both passed.

**Stream B — Fixed.** `MemoryView.tsx`'s `searchQuery`/`activeTab`: chose
`sessionStorage` over URL sync (per-visit, not worth bookmarking; sidesteps
Stream A's mechanism entirely). First implementation read `sessionStorage`
inside a `useState` lazy initializer — this hydration-mismatched (the
initializer also runs server-side during SSR, where `sessionStorage` doesn't
exist, so the server always rendered the empty/default state; React's
hydration reconciliation silently kept that empty state instead of the
client's restored one, confirmed via a `Warning: Prop aria-pressed did not
match` console warning caught mid-debug on the equivalent Timeline bug
below). Fixed to match the repo's own existing precedent
(`advisory-workbench`'s `ThinkView`/`PerspectivesView`/`ConsultView`, which
read `localStorage` inside a mount `useEffect`, never a lazy initializer) —
moved the restore into a `useEffect(() => {...}, [])`. Live-verified: search
query survives a full navigate-away-and-back, confirmed clean on a targeted
re-run after the fix.

**Stream C — Fixed (code only, not live-verified).** `selectedContentId`
URL-synced (`?item=<id>`) via the same `useUrlSync` hook as `tab` on the same
page — chose URL over `sessionStorage` since it's already the pattern `tab`
uses on this exact page and makes a Studio item shareable/bookmarkable.
`openStudio`/`closeStudio` updated to set/clear the param. Not live-verified
this pass — the test account has no content items to open into the Studio,
same limitation Phase 16 hit; `tsc`/build confirm it type-checks and the
mechanism is identical to Stream A/B's now-verified pattern.

**Stream D — 0 console 404s found this pass; explained, not just noted.**
Phase 14 and Phase 16 both independently found exactly 4 console 404s on
`/mission-workbench`. This pass found 0, live, on the current `main`
lineage. Traced rather than left as an unexplained contradiction:
`git log` on the page's own fetch-bearing files shows commit `b7e8e5c87`
("fix(lcars-portal): add AbortController cleanup to 41 fetch effects",
2026-09-15 — after both Phase 14 and Phase 16, which predate it) converted
exactly the two `fetch()` calls this page makes
(`NumberOneCoordination.tsx`'s `/api/health-adjusted-queue` and
`/api/number-one-brief`) from plain uncancelled `useEffect` fetches to
`useAbortEffect` (aborts the in-flight request on cleanup/re-run). Under
React 18 dev-mode `StrictMode`, effects mount-unmount-remount once on first
render — pre-fix, that meant each of these two fetches fired *twice*
uncancelled (2 routes × 2 = 4, matching the reported count exactly), with
the first request of each pair racing an unmount/remount in a way that could
surface as a failed/duplicate network entry. Post-fix, the first invocation's
fetch is aborted before the second starts, eliminating the duplicate
requests entirely. This reads as the real fix, landing as a side effect of
an unrelated adversarial-review pass, not a coincidence or a masking effect
— confirmed no other Stream D candidate in source (grepped this page and
its two component files for every `fetch`/`/api/`/image reference; these
were the only two). No other 404-prone fetch exists on this route today.
Nothing further to fix under this stream.

**Stream E — Real gaps found on both Search and Timeline; fixed to the same
standard as Streams B/C.** Per Phase 16's own hunch (flagged as worth
checking, not assumed broken or fine): both had the *identical* pattern to
Knowledge Workbench's original gap — plain `useState`, no URL/storage sync,
lost on navigate-away-and-back. Not a different failure mode, the same one,
found twice more. Fixed identically to Stream B: `sessionStorage` (same
per-visit reasoning), same hydration-mismatch pitfall hit and fixed the same
way (mount `useEffect`, not a lazy initializer) — `search/page.tsx`'s
`query` (re-runs the same search on restore) and `timeline/page.tsx`'s
`days`/`filter`. Live-verified clean after the hydration fix: both restore
correctly across a full navigate-away-and-back.

**Stream F — Live verification carried out this pass**, not handed off:
real Supabase, real Vercel-pattern local dev server (`.env.local` wired with
real anon/service-role keys supplied by the Captain this session, not the
checked-in placeholder `env.local`), the dedicated test account
(`timjardenross1986@gmail.com`), Playwright driven directly via the
project's own `playwright` package (Playwright MCP's Chromium launch is
blocked in this container — runs as root, refuses to launch without
`--no-sandbox`, and the MCP server config itself can't be edited to add it;
same wall a prior session hit and documented). Repeated-trial timing tests
per Phase 16's own methodology used throughout, not single clicks. No human
spot-check performed (no human available this session) — the Playwright-only
caveat Phase 16 itself left open stays open for a future pass, but every
mechanism above was verified against real live state, not just source
review.

`tsc --noEmit` clean. `npm run build`/full test suite/`eslint` not yet run
this pass — next step before closing the mission.



Phase-by-phase build record inside this same doc (same discipline as Mission 7's own —
§-numbered sections per phase, updated in place as work lands). On completion, add a short
cross-reference note to Mission 7's own doc (§5) pointing at this mission, per Acceptance
above. Knowledge record at `knowledge/missions/` once one exists for this mission, following
the established naming convention.
