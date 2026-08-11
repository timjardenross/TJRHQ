# Chief Engineer Architecture Review — Captain's Chair Workbench

USS TJR · Registry USS-TJR-003 · Engineering Division · Advisory authority
Reviewer: Chief Engineer persona · Date: 2026-08-09

## Mission Summary

Real architecture review of the Captain's Chair Workbench (`/captains-chair-workbench`), live on the platform and listed in the canonical workbench registry (`lcars-portal/src/lib/workbenches.ts:17-20`) as: "Operational dashboard — recovery posture, mission overview, alerts, and intelligence at a glance." This is the platform's default landing dashboard — the highest-traffic page in the app — so its trustworthiness matters more than any single-purpose workbench. Grounded entirely in the live code at `lcars-portal/src/app/captains-chair-workbench/page.tsx`, its embedded components, its data hooks, its API routes, and — because this session runs on the same VM that backs production — the actual running systemd service and Caddy config behind it.

## Assessment

### What the page actually renders, and whether the registry description matches

Confirmed via `page.tsx`: recovery posture (`ROSPanels`, `MobileOperatingPicture`), mission overview (Priority/Mission Status panels driven by `useLiveMissionStats`, `page.tsx:41-79`), alerts (`useAlerts` → Live Alerts panel), and intelligence (`CaptainIntelligencePanel`, Today's Briefing, Operational Picture). Structurally the tile description matches what ships. The problem isn't drift in what's *present* — it's that two of the "intelligence" pieces are currently non-functional or degraded in ways nothing on the page discloses, detailed below.

### Auth — solid, layered correctly

Global session gate (`middleware.ts:1-64`) redirects any unauthenticated request to `/login` for every route not in `PUBLIC_ROUTE_ALLOWLIST`, with a scoped bot-secret bypass limited to `/api/*` only (a prior over-broad version of this bypass covered the whole app surface — fixed, per that file's own comment). Every API route this page depends on (`/api/captain-brief`, `/api/proactive-signals`, `/api/captain-intelligence/{insights,generate}`, `/api/missions/[id]/{approve,reject}`) independently calls `requireSession()` (`lib/supabase-server.ts:29-33`) rather than trusting the middleware redirect alone — correct defense-in-depth, and the comment there explicitly documents *why* (WORKBENCH-REVIEW.md 2026-07-18 found 9 routes reachable by a direct API hit that bypassed the page-level redirect). The mission approve/reject routes go further: they derive the audit `owner` from the session, not the request body (`api/missions/[id]/approve/route.ts:23-33`), and use an exact `mission_id` match instead of the substring match that used to let `MSN-1` silently match `MSN-10`. This is genuinely good, documented remediation history — no findings here.

### Finding 1 (Critical, live now): the "Today's Briefing" and "Operational Picture" panels are running on an already-fixed bug that hasn't been deployed

`useTodaysBriefing` (`page.tsx:115-161`) is the sole source for both the Today's Briefing stat row (confidence/priorities/warnings/recommendations) and the Operational Picture list. It calls `GET /api/captain-brief`, which proxies to `core/context-assembly/context_service.py`'s `/brief/full` endpoint (`api/captain-brief/route.ts:38`). That endpoint calls `assemble_captain_brief_document(poll_events(limit=limit))` (`context_service.py:319-329`), and `assemble_captain_brief_document` does **"no I/O beyond `event_bus.poll_events()`"** by its own docstring (`core/platform/captain_brief_orchestrator.py:14,166-174`) — meaning the entire document (priorities, warnings, recommendations, operational_intelligence, confidence) is derived purely from whatever `poll_events()` returns.

`poll_events()` (`core/platform/event_bus.py:119-174`) has had a real bug since it was written: it called `.not_("recommended_action", "ilike", "CVE-%")` as a 3-arg method, but the installed `postgrest-py`'s `.not_` is a property, not a callable — every single invocation raised `'SyncSelectRequestBuilder' object is not callable`, caught by a broad `except`, logged as a quiet warning, and silently returned `[]`. This was fixed today in commit `5452a16e` ("Close morning intelligence gaps...", 2026-08-09 13:46:42) to `query.not_.ilike(...)` (`event_bus.py:167`) — the commit message itself states this ran every 10 minutes and "has never returned a real row" the whole time it's existed.

**The fix is committed but not live.** I confirmed this directly on the VM that backs production:
- `/etc/caddy/Caddyfile:58,124` reverse-proxies the public context-service route to `127.0.0.1:5001` — the exact port `context-service.service` listens on. This is not a side environment; it's the real backend `CONTEXT_SERVICE_URL` points at in production (per `deploy/MSN-0313-Context-Service-Runbook.md:17,64`).
- `systemctl show context-service -p ActiveEnterTimestamp` → `Fri 2026-07-31 06:40:26` — the process has been running continuously since a week before today's fix landed, so it's still executing the old, buggy bytecode from process start.
- `journalctl -u context-service --since "2026-08-09 13:40:00"` shows the exact same `'SyncSelectRequestBuilder' object is not callable` warning still firing at **13:57:56 — eleven minutes after the fix commit (13:46:42)**.
- The commit itself says "Local commit only - not pushed."

Net effect, right now: every Captain who opens Captain's Chair sees a Today's Briefing panel with confidence `—`, and 0 priorities/warnings/recommendations, and an Operational Picture panel reading "No active incidents or emerging risks" — not because there's nothing to report, but because the events feeding that assembly have been zero for as long as this job has run, and the just-written fix for that hasn't been rolled out. This is the single highest-value, lowest-effort fix available: `sudo systemctl restart context-service` (and pushing the commit) — not a design change, an operational one — but it's outside my authority to execute unilaterally on a live production service without the Captain's go-ahead, so it's called out here rather than actioned.

### Finding 2 (High, live now): "Generate New Insights" on the always-visible Captain Intelligence panel is broken on Vercel — it repeats a diagnosed-and-fixed anti-pattern

`CaptainIntelligencePanel` (`components/CaptainIntelligencePanel.tsx`) is one of the four always-visible panels on this page (`page.tsx:201-204`, outside the collapsible "Operational detail" section). Its `POST /api/captain-intelligence/generate` (`api/captain-intelligence/generate/route.ts:33-51`) runs:

```ts
execFileAsync('python3', ['-m', 'core.platform.captain_brief_cli', '--evolved', '--limit', '200'], { cwd: repoRoot(), timeout: 290000, ... })
```

This is the exact pattern the sibling `/api/captain-brief/route.ts` documents, in its own header comment (lines 4-25), as **already found broken and fixed on 2026-07-10**: "this route used to `execFile` a local python3 CLI directly ... this pattern is confirmed broken once deployed to Vercel's Node.js serverless runtime, which has no python3 available at all." That fix replaced the subprocess call with an HTTP call to the context-service. `generate/route.ts` was last touched **2026-07-30 21:12** (`git log`, commit `1e97f998`) — three weeks *after* that fix and its lesson were committed to the same repo — and still shells out to `python3` via `execFile`, with `repoRoot()` falling back to `path.resolve(process.cwd(), '..')` if `REPO_ROOT` isn't set, a VM-filesystem concept that doesn't resolve to anything meaningful inside a Vercel serverless function bundle.

Practical effect: clicking "Generate New Insights" on production almost certainly fails (`python3` unavailable in the Node.js serverless runtime), surfaced to the Captain as "Failed to generate Captain Intelligence insights" via the panel's own error state (`CaptainIntelligencePanel.tsx:56-68`) — not a silent failure, but a real, always-visible, currently-broken button on the platform's main dashboard, doing the identical thing a neighboring file's own commit history says doesn't work here. The read path (`GET /api/captain-intelligence/insights` → `insight_outcomes` table directly, no subprocess) is fine and unaffected — only generation is broken.

### Finding 3 (Medium): error handling is inconsistent across panels on the same page — one panel actively displays false reassurance on failure

The page itself shows awareness of one failure mode and fixed it in one place but not others. `useLiveMissionStats` (`page.tsx:41-79`) carries an explicit comment: "A failed request previously left stats null with no error state — panels silently rendered 0/'No data', indistinguishable from a real quiet day... this brings Captain's Chair in line" — and now surfaces failures through a shared `dataErrors` banner (`page.tsx:171,188-192`) alongside `useLiveEngineeringQueue` and `useTodaysBriefing`. That's the right pattern, applied to three of the page's data sources.

Two panels embedded on the same page don't follow it:

- **`CaptainApprovalQueue.tsx:50-64`** — `const { data } = await supabase.from('missions').select(...)` discards the `error` field entirely, and the whole call isn't wrapped in `try/catch` (only a `try/finally` around `setLoading`). A failed fetch — RLS denial, network blip — leaves `missions` at its previous (likely empty) state with zero indication anything went wrong. This is the exact same bug class `useLiveMissionStats` was just fixed for, in the same file's neighborhood, on the single highest-stakes panel on the page: approving or rejecting missions. A Captain has no way to distinguish "nothing is awaiting approval" from "the approval queue failed to load."
- **`ProactiveSignals.tsx:34-46`** — `.catch(() => setSignals([]))`, no error state tracked at all. The render logic (`ProactiveSignals.tsx:56-62`) then does: `if (signals.length === 0) return <p>All systems nominal</p>`. A failed `fetch('/api/proactive-signals')` renders the literal same "all clear" message as a genuine zero-signals day. This is the worst variant of the three — not a silent gap but an active false-positive: the panel affirmatively tells the Captain everything is fine when it actually couldn't check.

### Finding 4 (Low): dead imports and a dead fetch, both artifacts of an un-pruned migration from a "legacy" page

`page.tsx`'s own top-of-file comment says "All data hooks preserved from legacy `/captains-chair`" — consistent with what a word-boundary grep confirms: `DataSourceIndicator`, `DEPARTMENTS`, `toneClasses`, `stateToneClasses`, `AlertSeverity`, `RecoveryPostureBand`, `StateTone`, and `mockData`'s `departments` are all imported (`page.tsx:6-28`) but never referenced anywhere in the component body. None of this is user-visible risk — `DataSourceIndicator` specifically is redundant, not missing, since `ROSPanels` already renders its own live/mock badge internally (`components/ROSPanels.tsx:15,174-176`) — but it's real accumulated debris nobody caught, because neither the lint config nor `tsconfig.json` enforces unused-import detection here (`npx eslint page.tsx` returns clean/exit 0; `tsconfig.json` has no `noUnusedLocals`).

Separately: `summary` (`SinceLastSessionSummary`, `page.tsx:172,175-176`) is fetched via `loadSinceLastSession()` on every page load — a real Supabase query against `core_events` plus a `localStorage` write (`lib/sinceLastSession.ts:39-72`) — but the result is never rendered anywhere in the JSX (confirmed: `summary` appears nowhere in the render tree besides the state declaration; the only other `summary` matches in the file are the unrelated HTML `<details>/<summary>` disclosure element at line 262). This is a real, if cheap, wasted round-trip on the busiest page in the app, and it means the "Since Last Session" capability — which platform memory records as shipped (MSN-0345) — isn't actually surfaced on Captain's Chair specifically, despite being fetched there.

### Finding 5 (Low): the posture-based content gate fails open on fetch failure, with no visible tie-back to data confidence

The page hides the entire "Operational detail" section — mission overview, briefing, engineering queue, alerts, approvals — whenever `postureBand` is `FRAGILE` or `REST` (`page.tsx:260`), sourced from `useROSData().posture.posture` (`page.tsx:166,178`). If the live `get_recovery_posture` RPC fails, `useROSData` falls back to mock data (`lib/useROSData.ts:96-107`) whose hardcoded posture is `'STABLE'` (`lib/mockData.ts:659`) — so any RPC hiccup fails open toward showing *more* content, never toward the simplified "focus on recovery" view the mechanism exists to provide. Not dangerous on its own (fail-open is arguably the safer default direction here), but it means the one place this page makes a structural decision based on live health data has no visible connection to whether that data is actually live — the only signal a Captain has is `ROSPanels`' own internal Live/Mock badge, disconnected from the gating decision it happens to be feeding.

### Test coverage: none

No test file anywhere in the repo references `captains-chair-workbench` (confirmed by grep across the tree). None of the five embedded components (`ROSPanels`, `MobileOperatingPicture`, `CaptainApprovalQueue`, `CaptainIntelligencePanel`, `ProactiveSignals`) have unit tests, and the page's three bespoke hooks (`useLiveMissionStats`, `useLiveEngineeringQueue`, `useTodaysBriefing`) are defined inline in `page.tsx` rather than extracted to a testable module. For comparison, Content Workbench's scoring logic has its own unit test (`lib/__tests__/contentScoring.test.ts`). This is the platform's default landing page and has the thinnest test coverage of any workbench reviewed to date.

## Recommendations

1. **Restart `context-service.service` and push commit `5452a16e`** — highest priority, zero design risk, a fix that already exists and is already verified by its own author ("Verified live post-restart: '200 event(s) evaluated'"). This is an operational action, not an architecture change, but it directly determines whether two of this page's four always-visible panels show real data or empty placeholders. Flagging for Captain/on-call sign-off rather than executing it myself.
2. **Fix or remove the "Generate New Insights" button** — either point `generate/route.ts` at the context-service HTTP bridge the same way `captain-brief/route.ts` already does (reuse, don't reinvent — the pattern exists two files away), or disable the button in production until it does. Shipping a visibly-broken action on the main dashboard is worse than not having the feature yet.
3. **Bring `CaptainApprovalQueue` and `ProactiveSignals` in line with the error-handling fix already applied to `useLiveMissionStats`** — surface fetch failures explicitly rather than rendering an empty/"all clear" state indistinguishable from success. `ProactiveSignals` in particular should never render "All systems nominal" on a failed fetch.
4. **Prune the dead imports and the unused `summary` fetch** in `page.tsx` — small, safe, and worth doing precisely because nothing currently catches this class of drift (no `noUnusedLocals`, no lint rule). Low priority relative to 1–3.
5. **Consider a `noUnusedLocals`/`noUnusedParameters` pass or an eslint `no-unused-vars` rule** at the platform level, scoped carefully to avoid breaking intentionally-unused destructuring — this exact page shows that "legacy code carried forward" debris currently has no automated backstop anywhere in the toolchain.

## Next Actions

Immediate, concrete: restart `context-service.service` (Recommendation 1) — this alone fixes the two most user-visible panels on the page and requires no code change, just a Captain/ops decision to execute. Everything else in this review can follow at normal cadence.

## Mission Status

Advisory only. Findings 1 and 2 are live production issues on the platform's default landing page and are flagged for immediate Captain awareness; Finding 1's fix already exists and is one `systemctl restart` + `git push` away. No architecture-level design change is being recommended here — every finding is either a deployment gap (1), a documented anti-pattern that wasn't propagated (2), an inconsistency with a fix the page's own codebase already knows how to do correctly (3), or low-risk cleanup (4, 5).
