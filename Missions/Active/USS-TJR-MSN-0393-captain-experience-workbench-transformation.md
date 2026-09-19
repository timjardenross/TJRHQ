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

**Deliberately not touched:** `/api/xo` (Telegram's XO persona) does not share this
dispatcher — it runs a separate LLM-freeform + governed `<starfleet-action>`-block proposal
system that routes mutations through Decide for review, rather than Number One's direct
canonical-intent execution. Investigated whether this is a gap or a deliberate different
trust model for a less-controlled surface (Telegram) and could not resolve it with
confidence in this pass — left as deferred item §5.4 rather than merging two systems with
different governance postures without being sure that's correct.

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
4. **Telegram/XO parity review** (§26) — `/api/xo` is a separate, simpler endpoint from
   `/api/ai/chat` and does not currently run through the same canonical intent dispatcher;
   worth checking whether Telegram should get the same 9 intents Number One now surfaces on
   web, or whether it already has an equivalent path this review didn't find.
5. **Voice capture reassessment** (§27) — not investigated this pass.
6. **Full accessibility audit** (§31) — Phase 1 relied on the existing `a11y.test.tsx`
   axe-core coverage (which now includes the new floating buttons via `WorkbenchShell`, and
   passed) plus following established focus/label/contrast patterns; a dedicated
   contrast/zoom/screen-reader pass across the full surface set was not performed.
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
