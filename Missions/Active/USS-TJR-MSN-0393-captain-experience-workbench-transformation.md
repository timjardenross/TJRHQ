# USS-TJR-MSN-0393 — Captain Experience & Workbench Transformation (Mission 7)

**Type:** UI + UX + navigation + interaction design. Not a backend architecture programme —
Missions 1–6 own the canonical machinery; this mission consumes and exposes it.
**Status:** Active — Phase 1 shipped 2026-09-19. This is a large, multi-phase mission; this
record is honest about what Phase 1 actually closed versus what remains open (see §5/§6).
**Branch:** `claude/tjr-hq-mission-7-az63cy`.

## 0. Mission question

Does TJR HQ now actually feel like an intelligent personal operating environment and Chief
of Staff — or does the Captain still have to operate the machinery manually?

## 1. Baseline (verified against the live repo, not the mission brief's screenshot alone)

The mission brief's "before" description (RESPOND TODAY / NEXT / NEEDS YOU / WORLD, links
into Captain's Chair, Workbench selector, Workbenches/Capture/Readiness bottom nav) is close
to — but not identical to — what's live in `main` today. Missions 6/6B already did real
Hub-uplift work (`app/hub/page.tsx`'s own header comment documents a "Command-Experience
vNext" pass, 2026-09-06/09-19) that moved the Hub past a pure dashboard: it already derives
one posture headline, a curated 0–3-item Needs You list shared verbatim with Captain's
Chair, a single World/Intelligence line, and a "pick up where you left off" card. That
baseline is stronger than the brief assumes — but the mission's underlying diagnosis (HQ
tells the Captain something, then the Captain has to go find and operate the right
Workbench) was still true, for reasons the audit below is specific about.

### 1.1 The core finding: a fully-built canonical capability with zero ambient UI

Mission 6B built exactly what Mission 7 §9 asks for — a deterministic, canonical Number One
intent dispatcher (`lib/number-one/intent-router.ts`, `lib/number-one/context-store.ts`):
9 recognised intents (remember / what matters / what am I forgetting / stuck / still can't
start / too much / not now / where was I / done), cross-turn continuity via
`number_one_context`, wired into `/api/ai/chat`'s `role: 'number_one'` branch. Verified
**zero `.tsx` files anywhere in the repo referenced it** before this mission — its only
Captain-facing entry point was Advisory Workbench's full `ConsultView.tsx` (Workbenches →
Advisory → Consult → pick Number One from a 7-persona advisor list built for long-form
sessions). That is the mission's own §5 anti-pattern verbatim: "HQ tells me something → I
identify the right Workbench → navigate there → find the function → act." The backend
answer to "does HQ behave like connective tissue or another workbench" was already yes; nothing
in the product let the Captain reach it that way.

### 1.2 Confirmed navigation/IA inconsistency

- Root `/` redirects to `/hub` (2026-09-05, `app/page.tsx`'s own comment). Desktop
  `Sidebar`'s "Home" entry also points at `/hub`.
- `MobileCommandBar` — **the only nav rendered below the `xl` breakpoint, i.e. on every
  phone** — had its first tab labelled "Home" with a home glyph (⌂) pointing at
  `/workbenches` (the tile directory), not `/hub`. Two different pages both called
  themselves Home depending on device width.
- `workbenches/page.tsx`'s own header comment still asserted "WORKBENCHES IS THE HOME
  PAGE" — stale documentation left over from before the 2026-09-05 redirect moved, the same
  doc/code drift class this codebase's own comments elsewhere call out (the Content
  Workbench description example cited in `lib/workbenches.ts`).

### 1.3 Confirmed dead affordance

`app/hub/page.tsx` passed `WorkbenchShell` a tagline reading `"USS TJR · LifeOS Hub ·
Workbenches →"`. `WorkbenchShell` renders `tagline` as plain text — the trailing arrow
promised a link that did not exist anywhere on the page.

### 1.4 Confirmed backend gate bug blocking a canonical capability

`/api/ai/chat` checked `OLLAMA_CLOUD_ENABLED` **before** the Number One deterministic
dispatch branch. The 9 canonical intents never call the LLM (regex classification + direct
DB reads/writes) — but were unreachable in any environment where the optional LLM persona
chat happened to be switched off, even though nothing about them needs it.

### 1.5 Confirmed mobile collision

`QuickCapture`'s floating action button used `bottom: max(1.25rem, env(safe-area-inset-bottom))`.
`MobileCommandBar` is a *separate* fixed element covering the bottom ~4.5rem of the
viewport at `z-50` (vs. the button's `z-40`) on every viewport below `xl`. The floating
capture button rendered partly behind/under the bottom nav bar on every real phone.

### 1.6 Confirmed unstructured directory

`/workbenches` renders `LIVE_WORKBENCHES` (19 live entries) as one flat, unlabelled grid —
one long single-column scroll on mobile, no way to scan by domain, no search.

## 2. Workbench responsibility matrix (condensed — see `lib/workbenches.ts` for the
   canonical, always-current source; this table adds the grouping introduced in Phase 1)

| Group | Workbench | Primary job |
|---|---|---|
| Start here | LifeOS Hub (`/hub`) | Ambient orientation — posture, next, needs-you, world, in ~5s |
| Start here | Capture Workbench | Inbox triage for everything captured |
| Start here | Captain's Chair | Executive perspective — attention, decisions, material change |
| Start here | Ready Room | Execution — start/continue/unstick/regulate/complete |
| Plan & review | Mission Workbench | Every active/completed mission, capacity-aware |
| Plan & review | Weekly Review | One calm weekly pass across everything |
| Intelligence & alerts | Technical OSINT | Cyber/infra/regulatory signal intelligence |
| Intelligence & alerts | Health OSINT | Clinical/performance-research intelligence |
| Intelligence & alerts | Emergency Alerts | Official AU emergency information |
| Intelligence & alerts | Briefs | Canonical daily brief archive + cross-domain Domains view |
| Personal systems | Human Systems | Personal capacity intelligence + support |
| Personal systems | Physical Readiness | Exercise library/history (read-only record) |
| Personal systems | Shopping List | Everything worth buying, prioritised |
| Work & decisions | Content Workbench | Capture → draft → proof → publish comms pipeline |
| Work & decisions | Advisory | Decision support / multi-persona consult (incl. Number One's full-session mode) |
| Work & decisions | Knowledge Workbench | Command memory — decisions + reasoning, searchable |
| Platform | HQ Status | Is HQ itself working properly |
| Platform | HQ Evolution | Continuous improvement, overnight discovery |
| Platform | Engineering Handoffs | Approved handoffs awaiting triage/delivery/review |

No two workbenches were found to own the same job closely enough to justify consolidation
in this pass — the overlap that existed (Hub vs. Captain's Chair both deriving Needs You)
was already resolved by Mission 6B sharing one builder (`commandState.ts`'s
`buildNeedsYouItems`) between them, which this mission preserved and extended rather than
duplicating.

## 3. What shipped (Phase 1 — this branch)

All changes are additive/corrective to the existing canonical architecture; no new
attention/task/evidence/capacity/notification/recommendation engine was created, per
mission §4's constraint.

1. **Ambient Number One** (`components/ui/NumberOne.tsx`, new) — a floating entry point
   mounted globally (`WorkbenchShell`, plus `/workbenches` directly) consuming the existing
   `/api/ai/chat` `role: 'number_one'` dispatcher: 8 one-tap canonical-intent chips + free
   text (for "remember …"), session-local turn history, loading/disabled/error states. Two
   taps from anywhere in HQ, not a workbench destination — the direct fix for §1.1.
2. **`/api/ai/chat` gate-order fix** — Number One's deterministic dispatch now runs before
   the `OLLAMA_CLOUD_ENABLED` check, so the 9 canonical intents work independent of whether
   the optional LLM persona chat is switched on. Only the true LLM fallback still needs the
   flag.
3. **Mobile Home fixed** — `MobileCommandBar`'s first tab now points at `/hub` (was
   `/workbenches`), matching desktop Sidebar and the confirmed front-door architecture.
   `lib/nav.ts`'s `VALID_NAV_HREFS` build-time check extended to allow it. Directory
   reachability preserved (every WorkbenchShell page's mobile logo already links to
   `/workbenches`, `/hub` included) — nothing lost.
4. **Stale "home page" doc comment corrected** on `workbenches/page.tsx` — now accurately
   describes itself as the full directory, one tap in from the front door, not the front
   door itself.
5. **Dead tagline link removed** on Hub — "Workbenches →" (no link behind it) replaced with
   an honest label; the logo already provides that path.
6. **Mobile floating-button collision fixed** — `QuickCapture` and the new `NumberOne`
   button both now clear `MobileCommandBar`'s real footprint below `xl`, reverting to the
   original tight offset at `xl`+ where the bar is hidden. Opposite corners (capture
   bottom-right, Number One bottom-left) so the two never collide with each other either.
7. **Hub & Captain's Chair Needs You — action made visible** — each item's existing
   `actionLabel` (already correctly assigned per source: "Review", "Publish / Schedule", "Do
   this") rendered as unreadable 11px trailing text; now a real button-styled affordance on
   both surfaces, same canonical `href`, no invented action, no duplicated logic between the
   two (still one shared `buildNeedsYouItems()`).
8. **Workbench directory simplified** (`/workbenches`) — the 19 live entries now carry a
   `group` (`lib/workbenches.ts`'s new `WorkbenchGroup`/`WORKBENCH_GROUP_META`) and render as
   6 labelled sections instead of one flat grid, plus a client-side search box that
   flattens to a filtered list. The complete, unfiltered directory is still one tap away —
   only how it's scanned changed, per mission §16's explicit instruction not to assume more
   tiles need more navigation depth.

**Validation:** `tsc --noEmit` clean, `next lint` clean, full `vitest` suite green (69 files
/ 725 tests, no regressions), `next build` production build succeeds.

## 3.1 Phase 2 (same PR, same branch) — closing the Hub→Ready Room continuity gap

Found while re-reading §18/§29 against Ready Room's real code: `setNumberOneContext()` was
previously only ever called from inside `dispatchIntent()` itself — i.e. Number One only
knew "which task" if the Captain had *already* told it once that session (asked "what
matters?", said "remember …"). A Captain who instead arrived at a task the ordinary way —
Hub's Needs You "Do this" link, Ready Room's own task list, Unstick Me's "Start here" — was
looking straight at a specific task with nothing recorded anywhere Number One's ambient
widget could resolve "it" against. Asking "I'm stuck" on exactly that screen got "Which
task? I don't have one in view right now." — technically true, and exactly the kind of
machinery-narration the mission says the Captain shouldn't have to do.

Fix: new `POST /api/number-one/context` (thin wrapper around the existing, unchanged
`setNumberOneContext`), called fire-and-forget from `ActiveTaskView.tsx` (the one component
both Ready Room domains funnel into when a task is actually being worked) whenever the
active task changes. Same table, same TTL, same best-effort semantics as the dispatcher's
own writes — no new state model. Also reworded Hub's "Ask Number One" link (now "Open a
full Number One session") once the ambient widget existed, since a bare "Ask Number One"
next to a global ambient Number One button was duplicate-sounding navigation (§17) — the
link's real remaining job (a full, persisted, multi-turn `ConsultView` thread vs. the
widget's ephemeral per-session turns) is now stated, not left implicit.

**Deliberately not touched:** `/api/xo` (the web route XO's persona uses for general
freeform chat, gated behind reviewed `<starfleet-action>` proposals in Decide) does not
share this dispatcher, and was left alone — Telegram's actual XO *bot* (a separate Python
process, not this route) turns out to already have its own equivalent, independently built.
See §5 item 4 for the full finding: investigated and closed, no gap, no fix needed.

## 3.2 Phase 2 spot-checks (reviewed, no defect — recorded so the next pass doesn't re-derive
   this from scratch)

- **Captain's Chair scope boundary (§12)** — reviewed all 9 panels (`CommandStatus`,
  `NeedsYou`, `Remember`, `Intelligence`, `Capacity`, `SystemStatus`, `HqEvolution`, `Ahead`,
  `CaptainsLog`). None duplicate Hub or a dedicated workbench's own dashboard:
  `SystemStatus.tsx` is the clearest example — headline + one-line summary + a single
  "Review →" link into `/agent-status-workbench`, explicitly commented "tiny by design"
  against this exact mission boundary from the Command-Experience vNext pass that built it.
  `HqEvolution`/`Ahead`/`CaptainsLog` are the same size class (37–112 lines each). This
  surface was already close to the mission's target shape before Phase 1/2 touched it.
- **Notification deep-linking (§25)** — see §5.3 below; reviewed, confirmed sound, moved out
  of the deferred list.
- **Reduced motion (§32)** — `globals.css` already zeroes `animation-duration`/
  `transition-duration` globally under both OS-level `prefers-reduced-motion: reduce` and a
  manual Settings → Appearance → Motion override (`data-motion="reduced"`) — a blanket `*`
  rule, so `NumberOne`'s "Thinking…" `animate-pulse` and every other loading animation in the
  app already comply with no per-component work needed.

## 3.3 Phase 3 — adversarial self-review of Phase 1/2's own new code (§45)

Turned the adversarial pass on this mission's own additions rather than only on pre-existing
code, per §45's own instruction not to just report problems elsewhere:

- **Fixed:** `NumberOne.tsx`'s conversation area had no `aria-live` region — a screen-reader
  user got no announcement when "Thinking…" or a reply appeared; they'd have to manually
  re-enter the modal to discover new content. Added `role="log"`/`aria-live="polite"`.
- **Fixed, shared component:** while checking `NumberOne`'s `Modal` usage, found `Modal.tsx`
  itself (`components/ui/Modal.tsx`, ~15 call sites across the app, including this mission's
  own `QuickCapture` and the new `NumberOne`) had Escape-to-close but no Tab focus trap — a
  keyboard/screen-reader user could Tab straight out of any open modal into the page behind
  it, off-screen and unannounced. Fixed once in the shared primitive rather than per call
  site, so every existing and future `Modal` user gets it. Full suite (including every
  existing `a11y.test.tsx` axe-core case across all `Modal` usages) still green after the
  change.
- **Reviewed, no change:** floating-button tap target sizing (`NumberOne`/`QuickCapture` are
  48×48px, above the 44px minimum; the quick-intent chip row is the same
  `px-2.5 py-1.5`/~12px pattern already used throughout the existing design system, e.g.
  `QuickCapture`'s own capture-type chips — a pre-existing system-wide convention, not a
  regression introduced this mission, and out of scope to redesign system-wide in this pass).

## 3.4 Phase 4 — dead-code sweep (§35), scoped deliberately

Ran `npx knip` (the repo's own advisory dead-code tool, USS-TJR-MSN-0366) to find orphaned
components mechanically rather than by guessing. It flagged 32 unused files. Cross-checked
against `knowledge/missions/VULTURE-KNIP-DEAD-CODE-20260912-knowledge-record.md` (that
mission's own baseline from 2026-09-12, which found 31): one new file pair appeared since —
`app/captains-brief-workbench/_components/{DomainsView,KpiDashboard}.tsx`. Verified by
reading the current `captains-brief-workbench/page.tsx` itself: it was rewritten into a pure
retirement stub on 2026-09-19 (Briefs/Captain's Brief consolidation Phase 5) and no longer
imports either file, nor does anything else in the repo. **Deleted both** — a real,
confirmed-safe orphan directly caused by a route this mission's own scope touches (§1.2's
navigation work), not a guess.

**Also found and fixed, same sweep:** `app/(app)/medical/page.tsx` — the pre-redesign,
776-line LCARS-styled Medical dashboard (Overview/Pulse/Check-In/Trends tabs), confirmed zero
live inbound links anywhere in the app (only reachable by typing the URL; `lib/nav.ts`'s
`VALID_NAV_HREFS` listed it only for a build-time type check, not because anything linked
here) and fully superseded by `human-systems-workbench`'s 2026-09-06 redesign. Unlike the
`captains-brief-workbench` pair, knip couldn't see this one — a `page.tsx` is always a valid
Next.js route to knip regardless of whether anything navigates to it, so an orphaned-by-
*navigation* (not by import) page is a real blind spot that needed manual link-tracing, not
just a tool run. Converted to the same honest "this page moved" stub pattern already
established at `/home`, `/captains-brief`, `/captains-chair` (precedent: **port real
capability gaps before retiring**, per `captains-chair/page.tsx`'s own comment) — traced
each of its 4 tabs to a live successor, and specifically preserved the one genuine gap found:
`/medical/log-weight` (30-day weight-trend history; manual entry itself was separately
retired 2026-08-10) has no equivalent anywhere in `human-systems-workbench` today, so it was
kept live and linked from the new stub rather than silently orphaned. Porting a real
weight-trend view into `human-systems-workbench` so this one remaining redirect hop can
retire too is flagged in §5 below, not done in this pass.

**Found, NOT converted — flagged for a dedicated follow-up pass, not rushed:** the same
link-tracing check run against every substantial (>20 line, non-stub) page still under the
legacy `(app)` route group found **8 more fully-orphaned pages, zero live inbound links each,
2,691 lines total**: `intelligence` (693 lines), `operations` (371), `engineering` (337),
`timeline` (315), `search` (287), `automation-centre` (256), `operating-model` (249),
`captains-log` (243). Each is reachable only by typing its URL directly. Not converted in
this pass — `medical` was a clean single-page, four-tab, one-real-gap case that fit this
session's remaining time; several of these (`operations` alone spans Recent Decisions,
Friction Sources, Commander Events, and Captured Items — four distinct old views, not one)
need the same careful "trace every tab to its real successor, verify nothing genuinely unique
gets silently dropped" treatment `medical` got, and rushing 2,691 lines of that without
verifying each one risks exactly the kind of silent capability loss the `captains-chair` /
`medical` precedent was designed to avoid. Left as a fully-scoped, evidence-backed item in §5
rather than either an unverified bulk deletion or an unexamined "someday" note.

**Deliberately left alone (pre-existing MSN-0366 backlog):** the other ~30 findings (the paused `knowledge-workbench`
"Library" six-file cluster, `HomeScreen.tsx` and the rest of the pre-workbench-redesign
`/home` dashboard components, several unused exports) are the *existing*, already-documented
MSN-0366 advisory backlog — that mission's own record explicitly treats the Library cluster
as intentionally paused, not abandoned, and set "advisory only, triaged deliberately, not
auto-deleted" as the working policy for the rest. Mission 7 is a UX mission, not a codebase-
hygiene mission; re-litigating a different mission's deliberate triage backlog wasn't pulled
into this PR's scope. Left as a citation for whoever picks up MSN-0366's backlog next, not
re-added to Mission 7's own deferred register.

## 3.5 Phase 5 — continuing the legacy-page sweep, and one significant reversal of direction

Started converting the 8 pages §3.4 scoped but deliberately didn't convert yet. Two more
confirmed-safe retirements, using the same trace-every-view-to-its-successor discipline as
`medical`:

- **`captains-log`** (243 lines) — a still-fully-functional RAG-status/narrative form that
  wrote directly to `captains_log_entries`, the exact manual-capture path a platform-wide
  Captain directive (2026-08-10) retired everywhere else. Confirmed the live successor
  already exists and already explains the pause correctly
  (`human-systems-workbench/log/page.tsx`) — this page just hadn't been pointed at it. Traced
  the domain-heartbeat side-effect too (`/api/captains-log/heartbeat`, `domain_key:
  'captains_log'`) before touching anything: not referenced anywhere in `agentStatusJobs.ts`'s
  `SCHEDULER_JOBS`/HQ Status attention arithmetic, and `captains_log_entries` itself stopped
  receiving real rows back on 2026-06-28 per `lib/interruptCoverageRegistry.ts`'s own comment
  — so retiring this page doesn't newly break a monitored heartbeat, it just makes permanent
  what was already true in practice for three months. Redirects to the existing successor.
- **`automation-centre`** (256 lines) — unlike the others, carried clear internal evidence of
  already being stale, not just unlinked: its own hardcoded job/channel tables referenced
  things already retired elsewhere by name ("Slack — bot retired (MSN-0337)", jobs marked
  "RETIRED (D-3C-04)" sitting next to ones marked "Active"). Its `ALERT_THRESHOLDS` table had
  no evidence of still matching `lib/alerts.ts`'s real logic after the Mission 1-6 rebuild —
  not ported, since a stale copy of alerting rules is worse than none. Converted to a stub
  pointing at HQ Status, the real "is HQ's automation working" surface now.

**Deliberately left alone — a different judgment call, not the same as "needs more tracing
before converting":**

- **`operating-model`** (249 lines) — mostly static reference content (6 named "operating
  principles," domain priorities, a daily-schedule template), not a data view with an obvious
  successor. No sign of staleness the way `automation-centre` showed (no references to
  already-retired things); no duplicate of this content exists anywhere else in the app. This
  is doctrine, not UI — whether "Recovery First / Mission Clarity / Intelligent Defaults / ..."
  is still the Captain's actual current operating philosophy isn't something a code-reading
  pass can determine, and guessing wrong here means silently deleting real content, not
  clearing a redundant view. Left untouched; whether it should be relocated (Settings? a
  Knowledge Workbench doc?) or reaffirmed as current is a Captain call, not an engineering one.
- **`engineering`** (337 lines) — partially traced, not fully resolved. Its
  `build_request_inbox` view is confirmed superseded (live today via Captain's Chair's
  Engineering Queue panel and `lib/decide.ts`'s governance flow). Its `agent_performance` and
  `batch_jobs` views are NOT — neither table is read anywhere in `agent-status-workbench`
  (HQ Status), so unlike `captains_log`'s heartbeat this one couldn't be confirmed either
  live-but-unwatched or genuinely dead within this pass's remaining time. Needs the same
  backend-write-path trace `commander_events` got before converting.

**A significant finding worth its own heading — two of these pages are NOT legacy at all:**

- **`search`** (287 lines) and **`timeline`** (315 lines) — a real, maintained, cross-domain
  search (missions/logs/captures/events) and a real, maintained, cross-domain unified
  timeline. Both show recent, deliberate security/reliability maintenance (a documented
  2026-08-22 SQL-injection fix in `search`; both carry the same "MSN-0351: report a source
  read's success/failure explicitly, don't let a failed fetch look like an empty result"
  discipline other current, actively-maintained surfaces use). Confirmed zero live inbound
  links, same as every other page in this sweep — but nothing else in the app does either
  job. This is the opposite finding from `medical`/`captains-log`/`automation-centre`: not
  "safe to retire, superseded elsewhere," but **"a real, working capability with no way to
  reach it"** — the closest thing found this mission to Mission 7 §16's own "search" as an
  explicit intent-driven-navigation tool. **Not retired.** Flagged in §5 as a RELOCATE
  candidate (bring back into navigation, likely reachable from the Workbench directory's
  search box added in Phase 1, or its own entry point) rather than a retirement one — the
  inverse mistake (stubbing out a real, unique capability because it happened to share "zero
  live links" with genuinely dead pages) would have been exactly the kind of rushed,
  unverified deletion this whole sweep has been careful to avoid.

## 4. Core end-to-end test (§40) — status

The backend path this test exercises (remember → what am I forgetting → help me start →
I'm stuck → still can't start → too much → not now → where was I → done) was already fully
built by Mission 6B (§1.1). Phase 1 gives it its first real Captain-facing surface (the
ambient Number One widget) and fixes the one backend gate that could silently break it
(§1.4/§3.2). **Not yet exercised against a live deployment with `OLLAMA_CLOUD_ENABLED`,
Supabase, and the Model Router all live** — this environment has none of those configured
(confirmed: no `OLLAMA_CLOUD_ENABLED` in `env.local`, Supabase calls fail closed in tests
with a clear "not set" warning rather than a silent wrong answer). Flagged in §6 as the
first thing to run in a real environment before calling Phase 1 done end-to-end.

## 5. Deferred UX debt register (not closed in Phase 1 — explicitly out of scope for this
   pass, not silently dropped)

This mission's Definition of Done (§55) is large — full per-workbench PURPOSE/ENTRY/EXIT/
PRIMARY ACTION/NOISE review across all 19 live workbenches, a full accessibility pass,
before/after screenshot evidence, a full adversarial UX pass, Telegram/XO review, voice
capture reassessment, capacity-aware presentation tuning beyond what already existed, and
notification-entry review. None of that fits one implementation pass honestly. Ordered by
where the next pass should start:

1. **Per-workbench deep review** (mission §11) — only Hub, Captain's Chair's Needs You
   panel, and the directory got a structural pass. Ready Room, Human Systems, Content
   Workbench, and the 3 intelligence workbenches have not individually been reviewed
   against PURPOSE/ENTRY/EXIT/NOISE/DUPLICATION/CONTEXT/CONTINUITY/MOBILE.
2. **Hub → Ready Room contextual "Help me start" — partially closed in Phase 2** (§18/§40,
   see §3.1). Once the Captain is looking at a task in Ready Room (via Hub's "Do this" link
   or any other path), `number_one_context` is now set automatically and the ambient
   widget's "I'm stuck"/"still can't start"/"too much"/"done" resolve correctly with no
   re-explanation needed — the core gap this item described. Still open: there is no
   dedicated "Help me start" *button* on a Hub Needs You/Remember item itself that jumps
   straight to Unstick Me's decompose flow (vs. Ready Room's plain "Do" task view) — today
   that still needs either the ambient widget or a manual mode switch inside Ready Room.
   Worth a per-item action next pass if that distinction turns out to matter in practice.
3. **Notification deep-linking audit** (§25) — reviewed in Phase 2, no defect found:
   `lib/notifications.ts`'s `fireNotification` already carries a real per-alert `data.url`
   (`lib/useAlerts.ts` passes `a.href`, not a generic destination), and `public/sw.js`'s
   `notificationclick` handler already calls `client.navigate(target)` before focusing an
   existing window — not just focus-without-navigate, the specific variant of this
   anti-pattern that silently strands the Captain on whatever page was already open. Genuine
   server-initiated push for a closed app is out of MVP scope by the code's own design doc
   (`docs/MOBILE-MVP.md`), not a Mission 7 gap.
4. **Telegram/XO parity review (§26) — investigated, no gap found.** `/api/xo` (the web
   route) indeed doesn't share `lib/number-one/intent-router.ts` — but Telegram's XO bot
   (`telegram-bots/xo/`, a separate Python process; sharing TS code across runtimes isn't
   meaningful) has its own deterministic equivalent: `follow_through_nl.py`'s
   `parse_capture_intent`/`parse_update_intent` (no LLM, regex-based, same "deterministic
   over LLM-freeform for a state mutation" discipline as the web dispatcher) recognise
   "remind me/don't forget/remember to" for capture and, as a reply to a tracked reminder,
   `done` / `defer`/"not now" / `drop` / `decompose`("help me start") / weekday snooze —
   materially the same canonical-intent set Number One's web widget now surfaces, arrived at
   independently because it's a different runtime. Both write through the same canonical
   tables: `app.py`'s own header comment (Mission 3) documents that Telegram capture used to
   write straight into `personal_tasks` as "a second capture path that silently bypassed
   `captured_items` and its enrichment/classification pipeline" and was deliberately
   corrected to route through `captured_items` like every other channel (voice, portal,
   `/note`) — exactly the single-pipeline discipline Mission 7 §4 asks for, already done.
   No fix needed; this item is closed, not deferred.
5. **Voice capture reassessment (§27) — investigated, standing decision confirmed, not
   reopened.** Mission 6B already ran exactly this reassessment (§8.5 of its Convergence
   Register/Knowledge Record/Programme Closure, all three citing the same reasoning):
   Telegram voice capture is live (`voice-capture-pipeline` — Telegram → faster-whisper →
   `captured_items`, the same canonical ingress every other channel uses) and already
   satisfies "voice → capture → same routing" (§27's own target). Browser/PWA voice would
   duplicate that ingress for marginal reach against real added complexity (permissions,
   transcript confirmation UI, accessibility, failure recovery), with no captain-facing
   evidence of demand beyond the existing channel — deferred with justification, not
   silently dropped. Re-read against real usage data before reopening, not against this
   mission's brief alone.
6. **Full accessibility audit** (§31) — Phase 3 fixed a real, high-leverage finding (Modal's
   missing focus trap, §3.3 — fixed once for all ~15 call sites) plus this mission's own new
   `aria-live` gap; still relied on the existing `a11y.test.tsx` axe-core coverage rather than
   a dedicated pass, and a full contrast/zoom/screen-reader walkthrough across every surface
   was not performed.
7. **Before/after screenshot evidence** (§39/§56) — not captured; this environment has no
   way to run the app against live data (no Supabase/OLLAMA env configured) to produce
   faithful screenshots. Needs a real environment.
8. **Capacity-aware presentation tuning** (§24) — Hub's existing sanctuary/quiet-mode
   behaviour (PROTECT/RECOVER + zero Needs You collapses secondary sections) was preserved
   untouched; no new capacity-driven presentation logic was added or reviewed beyond that.
9. **Design-system consistency audit** (§30) — not performed across all 19 workbenches;
   Phase 1's own new UI (`NumberOne.tsx`) deliberately reused existing primitives (`Modal`,
   the `QuickCapture` floating-button pattern, `wb-*` tokens) rather than introducing new
   ones, but the rest of the surface set wasn't re-audited.
10. **Full adversarial UX pass** (§45) — the items in §1.2–1.6 above were found through a
    bounded discovery pass, not an exhaustive adversarial review of every surface; more
    almost certainly exists.
11. **Legacy `(app)`-group page retirement — 2 of 8 done (`medical`, `captains-log`,
    `automation-centre` = 3 actually converted across Phases 4-5), 5 remain, all fully or
    partially scoped, none guessed at.** See §3.4/§3.5 for the full evidence trail per page:
    - `operations` (371 lines) — fully traced. Recent Decisions/Captured Items/Friction
      Sources all superseded elsewhere; Commander Events needs a small "recent learning
      events" port into HQ Evolution first (real live data, `commander_events` via
      `build_learning_loop.py`, currently zero Captain-facing UI anywhere) — port that, then
      convert this page with the standard stub pattern.
    - `engineering` (337 lines) — partially traced. `build_request_inbox` confirmed
      superseded (Captain's Chair's Engineering Queue). `agent_performance`/`batch_jobs` not
      yet confirmed live-or-dead — neither is read in `agent-status-workbench`; needs the
      same backend-write-path trace `commander_events` got.
    - `intelligence` (693 lines) — not yet traced at all (largest page, lowest priority given
      `intelligence-workbench` + `briefs` both look like plausible successors by name/tab
      overlap — Latest Brief/Signals/Themes/Archive/Daily Briefs — but that's a hypothesis,
      not yet verified the way every other item on this list was).
    - `operating-model` (249 lines) — **deliberately not converted, different reason than the
      others.** Static doctrine/principles content with no duplicate anywhere else in the
      app and no internal sign of staleness — retiring it risks silently deleting real
      content, not clearing a redundant view. Needs a Captain call (keep as reference,
      relocate, or reaffirm/rewrite), not an engineering decision.
    - `search` (287 lines) and `timeline` (315 lines) — **do not retire these.** See §3.5:
      both are real, currently-maintained, unique capabilities (cross-domain search and a
      cross-domain unified timeline) with zero navigation path in, not legacy duplicates.
      RELOCATE, not RETIRE — surface them somewhere reachable (a natural fit: wire `/search`
      into the ambient ⌘/global search affordance §16 already gestures at with the Workbench
      directory's new search box; `/timeline` could sit inside Captain's Chair or Weekly
      Review). Not designed/built this pass.
12. **`/medical/log-weight`'s weight-trend view has no `human-systems-workbench`
    equivalent** (found in §3.4) — either port a real weight-trend view into
    `human-systems-workbench` (closing the last redirect hop in the `medical` cluster) or
    make a deliberate call that the redirect stays permanently; currently just preserved,
    not resolved either way.
13. **HQ Evolution "recent learning events" port** (found in §3.5, needed by item 11's
    `operations` conversion) — a small read-only view over `commander_events` (filtered to
    the `build_learning_loop.py` event shape) inside `self-improvement-findings`. Scoped, not
    built — needs the actual `commander_events` payload shape inspected first (not done this
    pass) before designing the view.

## 6. Recommended next steps

1. Run the §40/§43/§44 end-to-end/interruption/cross-surface tests against a real
   deployment (Supabase + `OLLAMA_CLOUD_ENABLED` + Model Router live) — the one thing Phase
   1 could not verify in this environment.
2. Capture before/after screenshots from that same real deployment for §39/§56's Captain
   acceptance review.
3. Work the deferred register in §5 roughly in the order listed — per-workbench review
   first (it's the input every other item downstream depends on), screenshots and the
   accessibility pass last (they're evidence-gathering, not architecture-changing).

## 7. Mission 7 knowledge record

- The gap between "canonical capability exists" and "Captain can reach it" was real and
  large — not a hypothetical the mission brief was guessing at. §1.1's Number One finding
  is the clearest single example: a fully-built, tested (10+18 passing unit tests already
  existed for the dispatcher before this mission touched it), continuity-aware capability
  that had never once been reachable outside a 7-persona advisor chat menu.
- Several of the concrete defects found (§1.2's mobile Home mismatch, §1.3's dead link,
  §1.4's gate ordering, §1.5's button collision) were not exotic — they were small,
  independently-fixable inconsistencies between two pieces of code that were each internally
  correct but had drifted from each other (mobile nav vs. desktop nav; one comment vs. the
  redirect it used to describe; an unrelated feature flag gating an unrelated capability). None
  needed new intelligence or new backend surface — only for someone to actually compare the
  two sides.
- The instinct to build a fourth reasoning surface, a new capacity-reduction action, or a
  richer chat UI was deliberately resisted in favour of exposing what Missions 1–6 already
  built correctly. Mission §4/§53's warning against backend-only or invented-logic
  "completion" was treated as load-bearing, not decorative.
