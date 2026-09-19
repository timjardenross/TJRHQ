# USS-TJR-MSN-0393 — Captain Experience & Workbench Transformation (Mission 7)

**Type:** UI + UX + navigation + interaction design. Not a backend architecture programme —
Missions 1–6 own the canonical machinery; this mission consumes and exposes it.
**Status:** Active — Phases 1-6 shipped 2026-09-19 (same session, one PR). This is a large,
multi-phase mission; this record is honest about what's actually closed versus what remains
open (see §5/§6/§6.1). Phase-by-phase build record: §3 (Phase 1: ambient Number One,
navigation fixes, directory grouping, Hub/Chair actionability), §3.1 (Phase 2: Hub→Ready Room
continuity), §3.3 (Phase 3: accessibility — Modal focus trap, aria-live), §3.4-3.6 (Phases
4-5: dead-code sweep, 5 legacy pages retired), §3.7 (Phase 6: Search/Timeline relocated from
dead-page risk into live workbenches).
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

## 3. What shipped (Phase 1 — this branch; Phases 2-6 follow in §3.1-§3.7 below)

All changes are additive/corrective to the existing canonical architecture; no new
attention/task/evidence/capacity/notification/recommendation engine was created, per
mission §4's constraint — true across every phase, not just Phase 1.

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

## 3.6 Phase 5 continued — `intelligence` retired, `commander_events` plan corrected

Two more items resolved in the same session, kept separate from §3.5 above only because they
landed after that section was written, not because they're a new phase in spirit:

- **`intelligence` (693 lines) — converted.** The largest page in the sweep, and the one
  hypothesised-but-not-yet-verified in §3.5. Traced all 6 tabs through `/api/intelligence`'s
  actual Supabase table queries rather than guessing from tab names: 3 tabs map to Briefs, 2
  to Technical OSINT Workbench, 1 to Content Workbench — all 3 confirmed live and currently
  reading the same tables. Multi-link stub, same pattern as `medical`. See §5 item 11 for the
  full trace.
- **`operations`'s Commander Events panel — the §3.5 plan was wrong, corrected rather than
  carried forward.** Inspecting the actual `commander_events` payload (not just the table
  name) showed it's build/handoff-lifecycle data from an older Slack-based flow
  (`source: "slack-build"`), and Engineering Handoffs already gets its data from a separate,
  purpose-built pipeline (`core/coordination/engineering_handoff_reader.py`) — so the "port a
  view into HQ Evolution" recommendation in §3.5 was likely solving a problem that doesn't
  exist. Not resolved either way within this pass; see §5 item 13 for the corrected, honest
  state of this question rather than a wrong plan left standing.

## 3.7 Phase 6 — `search` and `timeline` relocated (the RELOCATE recommendation from §3.5,
   actually built)

§3.5 found `search` and `timeline` were real, maintained, unique capabilities wrongly at risk
of being lumped in with the genuinely dead legacy pages — flagged as "RELOCATE, not RETIRE,
not designed/built this pass." Re-read both files in full (not just the header) to assess
whether that port was actually tractable in the time remaining, found it was, and built it:

- **`app/search/page.tsx`** and **`app/timeline/page.tsx`** (new, outside the legacy `(app)`
  route group) replace `app/(app)/search/page.tsx` and `app/(app)/timeline/page.tsx`
  (deleted, not stubbed — same URL, so both couldn't coexist; this is a genuine move, not a
  retirement). Every fetch/search function carried over byte-for-byte unchanged — zero risk
  to the actual query logic, which was already correct and well-maintained (recent SQL-
  injection fix, honest partial-failure handling). Only the outer shell and visual tokens
  changed: `LCARSPanel` → `WorkbenchShell`, `lcars-*`/department-colour tokens → the `wb-*`
  tokens every other live workbench uses. `Timeline`'s 5-colour department-dot system had no
  `wb-*` equivalent and was deliberately simplified to one consistent colour (glyph + label
  already identify each source — the colour was decorative on top of that, not the only
  differentiator, so dropping it isn't a capability loss).
- Both added to `lib/workbenches.ts`'s `LIVE_WORKBENCHES` (`work_decisions` group, alongside
  Knowledge Workbench) — reachable from the Workbench directory (including its Phase 1 search
  box) for the first time since whenever they lost their original nav entry.
- Confirmed the one real dependency §3.5 flagged before building anything: `search`'s
  "Captain's Log" and "Events" result types link to `/timeline` — both moved in the same
  commit, so neither stranded the Captain on the other's now-orphaned old location.
- Left `timeline`'s "Log" source as-is (reads `captains_log_entries`, which stopped receiving
  rows 2026-06-28, so it will render consistently empty) — not a bug this port should silently
  paper over, just documented in the new file's own header comment so it doesn't read as one
  later.

**Validation:** `rm -rf .next` + fresh `tsc --noEmit` (the route move left stale generated
`.next/types` referencing the deleted path — cache artifact, not a real error, confirmed clean
after a rebuild), lint clean, full 725-test suite green, production build succeeds with both
routes now building as plain static pages outside the `(app)` group.

## 3.8 Phase 7 — `operations` converted; 7 of 8 original legacy pages now fully resolved

Closed the one item §3.5/§3.6 had left properly blocked (not guessed at): `operations`'s
Commander Events panel. With `commander_events` confirmed genuinely live but Captain-facing-UI-
free (§3.6), and no confident case for silently dropping real data, converted the page with an
honest, visible flag instead of either extreme: the 3 superseded views (Recent Decisions,
Captured Items, Friction Sources) route to their real successors exactly like every other
conversion this sweep; Commander Events gets a plain-language note that the underlying data
has no dedicated view anywhere in HQ yet, rather than a link that goes nowhere or silence that
loses the finding. Building the actual "recent build/handoff activity" view belongs in
Engineering Handoffs (the payload shape is build/handoff lifecycle data, not HQ Evolution
content — see §3.6's correction) as real feature work, not something to improvise inside a
retirement pass; left in §5 for whoever picks it up.

**Of the original 8 legacy pages this sweep scoped, 7 are now resolved**: 6 converted to
honest stubs (`medical`, `captains-log`, `automation-centre`, `intelligence`, `engineering`,
`operations`), `search`/`timeline` relocated into the live app. Only `operating-model`
remains untouched — deliberately, because it needs a Captain's decision about real doctrine
content, not an engineering trace.

Typecheck/lint/full 725-test suite/production build all clean.

## 3.9 Phase 8 — cleanup/audit pass: computed contrast ratios for real, rather than trusting
   header-comment claims (§31)

With the legacy-page sweep closed, ran a mechanical check (WCAG 2.2 relative-luminance
contrast, computed directly — same method the codebase's own prior contrast work uses, not
eyeballed) against every colour token actually shipping, rather than sampling more pages by
eye. Two findings, different severity and different fix:

**Fixed:** `globals.css`'s own header comment claims every theme's `--wb-ink2` (secondary
body text) is "contrast-validated... >=4.5:1 (AA body text)" against both `--wb-bg` and
`--wb-surface`. Computed all 5 themes directly: **2 of 5 failed the claim** —
`archive` (the *default* theme, `:root` with no `[data-theme]` needed — what every new
Captain sees) at 4.46:1 against `--wb-bg`, and `sanctuary` at 4.31:1. Both fixed with a ~1-2%
darkening of the same hue (`archive` → 4.59:1/5.00:1, `sanctuary` → 4.51:1/4.83:1) — small
enough to be visually unnoticeable, verified by the same formula that found the gap, not by
eye. `command`, `midnight`, `horizon` already genuinely passed (4.65-8.24:1).

**Found, NOT fixed — a bigger, pre-existing, already-governed issue, correctly not
touched:** the `state-ok/warn/crit/unknown/info` token group (`tailwind.config.ts`, the
colour system `stateToneClasses()` actually renders through Hub, Captain's Chair's Needs You,
`SystemStatus.tsx`, and every other status indicator in the app) is **not theme-aware** — 5
fixed hex values, not CSS custom properties, unlike `wb-*`. Traced why: this token group was
built and contrast-validated by an earlier mission (`docs/design-tokens/
PHASE-1A-CONTRAST-MATRIX.md`, MSN-0315 Phase 1A) — but validated **only against the
pre-adaptive-themes LCARS backgrounds** (`space #dce8f4` / `panel #eaf1f8` / `panel-2
#ccd8ec`), which predate the 5-theme `wb-*` system entirely. That work was never re-run
against the newer theme backgrounds it now has to coexist with. Computed it now, against all
5: `state-ok`/`state-info` `DEFAULT` fail 4.5:1 against every theme's background (3.57-4.41:1
— these were designed to ≥3:1 as small graphical fills, per that doc's own stated threshold
for `DEFAULT` values, so this specific failure may be expected/acceptable by that doc's own
rule, not a new regression). **The real finding**: the `-on` variants — described in that
doc as "unaffected, already comfortably pass everywhere they're used as text" — genuinely did
pass against the old light-only backgrounds (5.28-7.17:1, confirmed in that doc) but **fail
badly against `midnight`** (the dark theme, `--wb-bg: #111820`): 1.43-2.31:1 across all five
state colours' `-on` variants, when rendered as body text the same way they render everywhere
else. `Midnight` is a fully live, named, selectable theme (`lib/theme.ts`: "Midnight — A
calmer mind. A clearer tomorrow.") — a Captain who picks it for its own reduced-stimulation
premise gets close-to-illegible status text throughout the app.

**Not fixed, deliberately, same governance principle this whole mission has followed for
brand/doctrine content:** that Phase 1A doc's own conclusion — "changing ratified brand hex
values is a Visual Design Officer call, not an engineering one" — applies exactly here too,
and its own prescribed component-level mitigation path (pair the fill with an already-
passing outline/ring rather than recolour the fill) wasn't attempted blind, without being
able to see the actual rendered result in a browser. Full numbers and both prescribed fix
paths are in §5 item 14 for whoever has live-environment access to verify a fix visually
before shipping one.

**Also fixed, same pass:** a real, repeated pattern of visually-labelled-but-not-
programmatically-labelled form fields — a `<p>` styled to look like a field label
immediately above an `<input>`/`<textarea>`, with no `<label>`, `htmlFor`/`id` pairing, or
`aria-label` connecting them, so a screen reader announces the field with no name at all.
Found by reading actual JSX around every raw `<input>`/`<textarea>` in the app (a first grep
for "missing aria-label" was mostly false positives — many inputs are correctly wrapped
inside a `<label>` or paired with a `<fieldset>`/`<legend>`, which a single-line grep can't
see; had to actually read the surrounding markup, not just pattern-match it), not by
guessing where it might occur. Real instances, all fixed with `aria-label` matching the
visible text (least invasive: doesn't touch the existing `<p>`/visual styling):
- **`(auth)/login/page.tsx`'s Password-mode form** — the highest-stakes instance: every
  Captain who has ever used HQ has seen this page, and its email/password inputs had *no*
  label of any kind, relying on placeholder text alone (which disappears once typing starts
  and isn't reliably announced as a label). The Magic Link form 40 lines below already uses
  the correct `sr-only <label>` + `id` pattern for the same email field — mirrored here
  rather than left inconsistent within the same file.
- `captains-chair-workbench/notebook/page.tsx` — all 4 capture-form fields (quick-mode
  textarea, Title, Thought or intelligence, Tags).
- `content-workbench/_components/ContentStudio.tsx`'s Schedule datetime input,
  `stageBodies.tsx`'s Framing angle / AI-revision-instructions / QA-notes inputs.
- `briefs/page.tsx`'s Search briefs input, `advisory-workbench/_components/OutcomesView.tsx`'s
  "What did HQ miss?" input.

Not exhaustive — every raw `<input>`/`<textarea>` outside `components/ui/Input.tsx` (which
already requires a `label` prop) was checked, but a component that builds its own custom
input wrapper elsewhere in the tree, not matched by a plain `<input`/`<textarea` grep, could
still have the same gap unfound.

## 4. Core end-to-end test (§40) — status

The backend path this test exercises (remember → what am I forgetting → help me start →
I'm stuck → still can't start → too much → not now → where was I → done) was already fully
built by Mission 6B (§1.1). Phase 1 gives it its first real Captain-facing surface (the
ambient Number One widget) and fixes the one backend gate that could silently break it
(§1.4/§3.2). **Not yet exercised against a live deployment with `OLLAMA_CLOUD_ENABLED`,
Supabase, and the Model Router all live** — this environment has none of those configured
(confirmed: no `OLLAMA_CLOUD_ENABLED` in `env.local`, Supabase calls fail closed in tests
with a clear "not set" warning rather than a silent wrong answer). Flagged in §6 as the
first thing to run in a real environment before calling this mission done end-to-end —
still true after Phases 2-6 (§3.1's continuity fix strengthens the same untested path, it
doesn't change what's blocking verification).

## 5. Deferred UX debt register (not closed across Phases 1-6 — explicitly out of scope for
   this pass, not silently dropped)

This mission's Definition of Done (§55) is large — full per-workbench PURPOSE/ENTRY/EXIT/
PRIMARY ACTION/NOISE review across all live workbenches (now 21, after Phase 6 added Search
and Timeline), a full accessibility pass, before/after screenshot evidence, a full
adversarial UX pass, Telegram/XO review (closed with evidence, item 4 below), voice
capture reassessment, capacity-aware presentation tuning beyond what already existed, and
notification-entry review. None of that fits one implementation pass honestly. Ordered by
where the next pass should start:

1. **Per-workbench deep review** (mission §11) — **substantially broadened since first
   written.** Every live workbench has now at least had its purpose/architecture/recency
   verified by opening and reading it (Hub, Captain's Chair, Ready Room, Human Systems,
   Weekly Review, Engineering Handoffs, Emergency Alerts, Content Workbench, Settings,
   Knowledge Workbench, Physical Readiness, Shopping List, Search, Timeline) — none showed
   the kind of drift this mission expected to find; each had already been through a
   deliberate, recent, well-reasoned redesign of its own (see §7's knowledge record). Not yet
   done: a full formal PURPOSE/ENTRY/EXIT/NOISE/DUPLICATION/CONTEXT/CONTINUITY/MOBILE write-up
   per workbench (mission §11's exact template) — what happened instead was closer to "prove
   it's not broken before assuming it needs a review," which is what this pass's remaining
   time allowed. The 3 intelligence workbenches (Technical OSINT, Health OSINT, Briefs) and
   Advisory got a lighter read than the others.
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
6. **Full accessibility audit** (§31) — Phase 3 fixed Modal's missing focus trap (§3.3, all
   ~15 call sites) plus this mission's own new `aria-live` gap; Phase 8 (§3.9) computed real
   WCAG contrast ratios for every colour token actually shipping (not sampled by eye), fixed
   2 of 5 themes' secondary-text contrast, found (but correctly didn't blind-fix) the bigger
   `state-*`/`midnight` finding in item 14 above, and fixed every found instance of a
   visually-labelled-but-not-programmatically-labelled form field across the app (read the
   actual JSX around every raw `<input>`/`<textarea>`, not grepped for — see §3.9's full list,
   `(auth)/login`'s Password form was the highest-stakes one). Still not done: zoom behaviour,
   a real screen-reader walkthrough, and keyboard-navigation testing beyond the Modal fix —
   none of those are computable without a live browser the way contrast/markup structure are.
7. **Before/after screenshot evidence** (§39/§56) — not captured; this environment has no
   way to run the app against live data (no Supabase/OLLAMA env configured) to produce
   faithful screenshots. Needs a real environment.
8. **Capacity-aware presentation tuning (§24) — reviewed further, confirmed sound, no gap
   found.** Hub's sanctuary/quiet-mode behaviour (PROTECT/RECOVER + zero Needs You collapses
   secondary sections) was preserved untouched. Additionally checked the UNKNOWN case
   specifically, since §24 calls it out by name ("use conservative presentation rather than
   assuming Green") — `commandState.ts` already handles it exactly that way, in its own
   words: `"No capacity check-in yet today — today is unknown, not clear."` (deliberately
   distinct language from an actual clear/green day, not defaulted to looking calm). Ready
   Room's own posture-driven mode default (`app/ready-room/page.tsx`) explicitly does nothing
   on UNKNOWN rather than guessing a mode — same discipline. No UI-invented capacity logic
   found anywhere reviewed this session; every capacity read traced back to the same
   canonical Human Systems posture. Not exhaustively reviewed (every workbench individually),
   but the pattern held everywhere it was checked.
9. **Design-system consistency audit (§30) — extended in Phase 8, still not exhaustive.**
   Phase 1's own new UI (`NumberOne.tsx`) deliberately reused existing primitives (`Modal`,
   the `QuickCapture` floating-button pattern, `wb-*` tokens) rather than introducing new
   ones. Phase 8 (§3.9) went further and made the token system itself more consistent with
   its own documented claims — 2 themes' text contrast actually fixed to match what the
   header comment already asserted, plus found the deeper `state-*`/theme mismatch (item 14).
   Still not done: a full visual pass across all 21 workbenches for spacing/typography/
   component-choice drift, since that needs eyes on a rendered page, not just token math.
10. **Full adversarial UX pass (§45) — ongoing self-review found and fixed 3 real issues in
    this mission's own new code, not just pre-existing surfaces.** Phase 3: Modal's missing
    focus trap, Number One's missing `aria-live`. Phase 6: Timeline's new toggle buttons
    missing `aria-pressed`/focus-visible on the very commit that shipped them. Each caught by
    treating this mission's own output with the same suspicion as everything else, not by a
    separate dedicated pass — the discipline generalizes, but a genuinely separate, focused
    adversarial pass (the items §45 itself lists: duplicate navigation, stale UI state,
    misleading state, back-button problems, giant text walls, notification loops, ...) was
    not run as its own exercise across the whole product.
11. **Legacy `(app)`-group page retirement — 7 of 8 resolved (§3.8 closes the last tractable
    one).** 6 converted to honest stubs (`medical`, `captains-log`, `automation-centre`,
    `intelligence`, `engineering`, `operations`); `search` and `timeline` relocated rather
    than retired (§3.7, real capabilities, now live at their own top-level routes). Only
    `operating-model` remains open, deliberately — a Captain call, not an engineering one; see
    below. See §3.4/§3.5/§3.6/§3.7/§3.8 for the full evidence trail per page:
    - `intelligence` (693 lines, the largest page in the sweep) — **converted in Phase 5**.
      All 6 tabs traced through `/api/intelligence`'s actual table queries (not tab names
      alone): Latest Brief/Daily Briefs/ORI Archive → `intelligence_briefs`/
      `captains_daily_briefs` → Briefs; Signals/Themes → `intelligence_events`/
      `intelligence_source_registry`/`_health` → Technical OSINT Workbench (its own header
      comment confirms it's the direct re-anchoring of this exact tab pair); Content →
      `content_signals`/`comms_content` → Content Workbench (owns the same two tables per its
      own header comment). All 3 successors confirmed live; multi-link stub, same pattern as
      `medical`.
    - `operations` (371 lines) — **converted in Phase 7 (§3.8).** 3 of 4 views traced and
      superseded (Recent Decisions/Captured Items/Friction Sources); Commander Events was the
      open one — confirmed genuinely live (§3.6) but with no Captain-facing UI anywhere,
      neither dropped silently nor blocked on building new UI to resolve the page: the stub
      says plainly that data has no dedicated view yet (see item 13 for where that view
      should eventually live).
    - `engineering` (337 lines) — **converted.** `build_request_inbox` confirmed superseded
      (Captain's Chair's Engineering Queue). `agent_performance`/`batch_jobs` got the full
      backend-write-path trace `commander_events` got (not the quick grep that missed
      `commander_events`'s real caller) — repo-wide, Python and TypeScript both: zero live
      readers or writers of either table found anywhere outside this page and
      `lib/engineeringMetrics.ts` itself (which only exists to compute rates from them).
      Weaker confidence than `medical`/`captains-log` (a thorough-but-negative search, not a
      confirmed-dead write path) — said so explicitly in the stub's own comment rather than
      overclaiming certainty. `lib/engineeringMetrics.ts` itself is worth noting as unusually
      well-cared-for code to be retiring: its own header comment documents MSN-0351 removing
      a fabricated "Cognitive Load Reduction" composite score it used to compute, in favour of
      honest separate rates — good work, just for data with no evidence of still flowing.
    - `operating-model` (249 lines) — **deliberately not converted, different reason than the
      others.** Static doctrine/principles content with no duplicate anywhere else in the
      app and no internal sign of staleness — retiring it risks silently deleting real
      content, not clearing a redundant view. Needs a Captain call (keep as reference,
      relocate, or reaffirm/rewrite), not an engineering decision.
    - `search` (287 lines) and `timeline` (315 lines) — **RELOCATED in Phase 6 (§3.7), not
      retired.** Both were real, currently-maintained, unique capabilities (cross-domain
      search and a cross-domain unified timeline) with zero navigation path in — the opposite
      finding from the rest of this sweep. Now live at `app/search/page.tsx` /
      `app/timeline/page.tsx`, `WorkbenchShell`-shelled, reachable from the Workbench
      directory. See §3.7 for the full build record.
12. **`/medical/log-weight`'s weight-trend view has no `human-systems-workbench`
    equivalent** (found in §3.4) — either port a real weight-trend view into
    `human-systems-workbench` (closing the last redirect hop in the `medical` cluster) or
    make a deliberate call that the redirect stays permanently; currently just preserved,
    not resolved either way.
13. **`operations`'s "Commander Events" panel — correction to the §3.5 finding, now scoped
    differently.** Inspected the actual `commander_events` payload `build_learning_loop.py`
    writes: it's build/handoff-lifecycle data (`decision_id`, `outcome_id`, `mission_title`,
    `status`, `batch_status`, `handoff_path`, `source: "slack-build"`), not "learning loop"
    content in the HQ Evolution sense — the "port into HQ Evolution" idea in §3.5 was based on
    the table name alone, before reading what it actually holds. More importantly:
    Engineering Handoffs (`engineering-handoffs`, confirmed live) already gets its handoff
    data from a separate, purpose-built pipeline
    (`core/coordination/engineering_handoff_reader.py`, not `commander_events`) — so this
    `commander_events` write looks like a vestigial side-effect of an older Slack-based build
    flow (`source: "slack-build"`) that predates the current pipeline, not a genuine gap
    needing a new UI at all. Not confirmed either way within this pass (would need to trace
    whether anything still reads what `engineering_handoff_reader.py` itself consumes, and
    whether that trace connects back to `build_learning_loop.py`'s writes) — flagged as
    "investigate before building anything," reversing the earlier "port a view" conclusion
    rather than carrying a wrong plan forward. **Update (Phase 7, §3.8): `operations` itself
    was converted** rather than left blocked on this — the stub is honest that Commander
    Events data has no view yet rather than pretending the page conversion depended on
    building one. This item is now purely about the future view itself, not about unblocking
    a retirement.
14. **`state-*` status colour system needs re-validation against the 5 adaptive themes,
    especially `midnight`** (found in §3.9, full numbers there) — `state-ok`/`state-info`
    `DEFAULT` values sit under 4.5:1 against every theme (likely acceptable, designed to a
    ≥3:1 graphical-fill bar per the original Phase 1A doc) but every state colour's `-on`
    text variant — previously verified fine, before the theme system existed — now fails
    badly (1.4-2.3:1) specifically against `midnight`, a real, live, selectable dark theme.
    Two fix paths already prescribed by the original Phase 1A doc's own governance (pair the
    fill with an already-passing outline/ring, or a Visual Design Officer-approved shade
    revision) — needs whoever picks this up to actually see the rendered result in a browser
    before choosing one, not another blind numeric fix.

## 6. Recommended next steps

1. Run the §40/§43/§44 end-to-end/interruption/cross-surface tests against a real
   deployment (Supabase + `OLLAMA_CLOUD_ENABLED` + Model Router live) — the one thing Phase
   1 could not verify in this environment.
2. Capture before/after screenshots from that same real deployment for §39/§56's Captain
   acceptance review.
3. Work the deferred register in §5 roughly in the order listed — per-workbench review
   first (it's the input every other item downstream depends on), screenshots and the
   accessibility pass last (they're evidence-gathering, not architecture-changing).

## 6.1 Experience inventory (mission deliverable §37)

Every route this session actually opened and read, not a route list copied from the
directory config. Disposition per the mission's own vocabulary (KEEP / REDESIGN / SIMPLIFY /
MERGE / RELOCATE / RETIRE). "Mobile quality" reflects what the code shows (`WorkbenchShell`
+ `wb-*` tokens = the current, verified-mobile-safe system; a legacy `(app)`-group page = not
verified, different system) — no live-environment mobile testing was possible this session.

| Route | Purpose | Canonical data | Mobile | Disposition |
|---|---|---|---|---|
| `/hub` | Ambient orientation front door | `commandState.ts`/`captainsChairSynthesis.ts` (shared with Chair) | `WorkbenchShell`, current | KEEP — uplifted Phase 1-3 |
| `/workbenches` | Full directory, one tap from Hub | `LIVE_WORKBENCHES` | Sidebar/directory grid, current | KEEP — simplified Phase 1 |
| `/captains-chair-workbench` | Executive perspective: attention, decisions, change | 9 panels, own `_components/` | `WorkbenchShell`, current | KEEP — scope-checked Phase 2, sound |
| `/ready-room` | Execution: start/continue/unstick/regulate/complete | `personal_tasks`, `getReadyRoomContext` | `WorkbenchShell`, current | KEEP — continuity-fixed Phase 2 |
| `/capture-workbench` | Inbox triage for everything captured | `captured_items` | `WorkbenchShell`, current | KEEP |
| `/mission-workbench` (+`[id]`) | Every mission, capacity-aware | `missions` | `WorkbenchShell`, current | KEEP |
| `/weekly-review` | Interpreted weekly synthesis | `weekly_reviews` + live per-workbench reads | `WorkbenchShell`, current | KEEP — already redesigned around significance, not source |
| `/intelligence-workbench` (+`brief/escalation [id]`) | Technical OSINT triage (Today/Watching/Library) | `intelligence_events` | `WorkbenchShell`, current | KEEP |
| `/health-osint` | Health/performance-research intelligence | own tables | `WorkbenchShell`, current | KEEP |
| `/health-osint-curation` | Sunday review queue for auto-ingested signals | same | `WorkbenchShell`, current | KEEP — deliberate zero-nav, documented |
| `/emergency-alert-hub-workbench` | Official AU emergency alerts, severity-ranked | own tables + `domain_heartbeats` | `WorkbenchShell`, current | KEEP — explicitly designed against "raw volume = workload" |
| `/briefs` (+`domains/[key]`) | Canonical brief archive + cross-domain Domains view | `intelligence_briefs`, `captains_daily_briefs` | `WorkbenchShell`, current | KEEP — absorbed `/intelligence`'s Briefs-shaped tabs this mission |
| `/human-systems-workbench` (+sub-routes) | Personal capacity intelligence | `capacity_checkins` et al. | `WorkbenchShell`, current | KEEP — scope-checked, no clinical-dashboard drift found |
| `/physical-readiness` (+sub-routes) | Exercise library/history, read-only | own tables | `WorkbenchShell`, current | KEEP — not deeply reviewed this pass |
| `/shopping-list-workbench` | Prioritised buy list | own tables | `WorkbenchShell`, current | KEEP — not deeply reviewed this pass |
| `/content-workbench` | Capture→draft→proof→publish pipeline | `comms_content`/`content_signals` | `WorkbenchShell`, current, kanban already demoted off mobile default | KEEP — absorbed `/intelligence`'s Content tab this mission |
| `/advisory-workbench` | Multi-persona consult incl. Number One's full session | `advisory_sessions` | `WorkbenchShell`, current | KEEP — clarified vs. the new ambient widget, Phase 2 |
| `/knowledge-workbench` | Command memory, searchable | `architecture_records` et al. | `WorkbenchShell`, current | KEEP — Library branch intentionally paused, not dead |
| `/agent-status-workbench` | Is HQ itself working properly | `domain_heartbeats` | `WorkbenchShell`, current | KEEP — now the confirmed successor for 3 retired pages |
| `/self-improvement-findings` (HQ Evolution) | Overnight discovery/improvement | own tables | `WorkbenchShell`, current | KEEP |
| `/engineering-handoffs` | Approved handoffs, direct PR links | `engineering_handoff_reader.py` | `WorkbenchShell`, current | KEEP — exemplary scope discipline, deliberately read-only |
| `/search` **(new location)** | Cross-domain search | `missions`/`captains_log_entries`/`captured_items`/`mission_execution_events` | `WorkbenchShell`, current — **relocated this mission** | KEEP — was RETIRE-adjacent risk, correctly RELOCATED Phase 6 |
| `/timeline` **(new location)** | Cross-domain chronological feed | same 5 sources | `WorkbenchShell`, current — **relocated this mission** | KEEP — relocated alongside `/search`, Phase 6 |
| `/settings` (+sections) | Preferences, connections, AI/automation | various | current | KEEP — not reviewed this pass |
| `/model-crew` | Model routing status | `/api/model/*` | `WorkbenchShell`, current | KEEP — already moved off a 3rd bespoke theme, 2026-09-06 |
| `/investigate` | Runs one Investigation Engine type | `investigationEngine.ts` | zero-nav, deliberate | KEEP — contextual-entry by design, documented |
| `(app)/medical` | *(retired this mission)* | — | — | **RETIRED Phase 4** — 4-tab stub, weight-history preserved |
| `(app)/captains-log` | *(retired this mission)* | — | — | **RETIRED Phase 5** — redirects to the already-correct successor |
| `(app)/automation-centre` | *(retired this mission)* | — | — | **RETIRED Phase 5** — self-evidently stale |
| `(app)/intelligence` | *(retired this mission)* | — | — | **RETIRED Phase 5** — 3-way stub, all successors verified live |
| `(app)/engineering` | *(retired this mission)* | — | — | **RETIRED Phase 5** — thorough-but-negative backend trace |
| `(app)/operations` | *(retired this mission)* | — | — | **RETIRED Phase 7** — 3-link stub; Commander Events flagged honestly, not dropped or blocked on |
| `(app)/operating-model` | Static operating principles/doctrine | none (static content) | legacy, not current | **HOLD — Captain call**, not an engineering decision |
| `(app)/decisions`, `/captains-brief`, `/captains-chair`, `/home`, `/knowledge`, `/knowledge-library`, `/missions`, `/medical/check-in`, `/medical/log-activity` | Pre-existing redirect stubs | — | — | KEEP as-is — already correctly retired by earlier missions, verified still accurate |
| `(app)/medical/log-weight` | 30-day weight-trend history, entry retired | `weight_logs` | legacy, not current | **KEEP, flagged** — real capability, no `human-systems-workbench` equivalent yet (§5 item 12) |

Not inventoried: the other ~15 `(app)`-group routes untouched this mission (`stage-progression`,
`comms`, `delivery`, `operating-model`'s siblings, etc.) — most are already confirmed
redirect/notice stubs from earlier retirement passes per `lib/nav.ts`'s own history; none
showed up in the zero-live-inbound-link sweep as full, still-rendering pages the way
`medical`/`captains-log`/`automation-centre`/`intelligence`/`engineering`/`search`/`timeline`
did, so they weren't re-verified individually this pass.

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
- "Zero live inbound links" is necessary but not sufficient evidence a page is safe to
  retire — §3.5's `search`/`timeline` finding is the clearest proof. Both shared every
  surface signal of the genuinely dead pages (orphaned by navigation, old design system,
  no recent visible activity) and were in fact the opposite: real, maintained, unique
  capabilities. What actually distinguished them was reading what each page *did*, not how
  it was reached — the discipline this whole sweep tried to hold to (trace every view to its
  real successor, or its absence, before touching anything) is what caught this one before
  it became a real capability loss instead of a documented finding.
- Table names lie by association. §3.5 first read `commander_events`'s name and reasoned
  "learning loop → HQ Evolution is the natural home" — wrong, discovered only by reading the
  actual payload (`build_learning_loop.py`'s build/handoff-lifecycle data) and tracing where
  Engineering Handoffs' real data pipeline lives. The fix wasn't to delete the wrong
  conclusion quietly; it was corrected in place (§3.6) with the reasoning that changed it
  left visible, on the theory that a record someone else has to re-derive from scratch is
  worse than one that shows its own mistake and the evidence that fixed it.
- Codebase health here was consistently higher than the mission brief's framing assumed.
  Nearly every workbench opened this session (Human Systems, Captain's Chair, Weekly Review,
  Engineering Handoffs, Emergency Alerts, Settings, Content Workbench) had already been
  through a dedicated, well-reasoned redesign pass with language and priorities matching
  this mission's own — not evidence Mission 7 was unnecessary, but evidence the genuine gaps
  were concentrated in specific, findable places (connective tissue between surfaces,
  navigation drift, orphaned pages from superseded redesigns) rather than spread evenly
  across the whole product. Chasing that concentration, rather than re-reviewing everything
  from zero, is what made 6 phases in one session possible without shipping guesses.
