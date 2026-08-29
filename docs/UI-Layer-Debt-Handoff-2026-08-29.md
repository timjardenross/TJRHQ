# LCARS Portal UI-Layer Debt — Session Kickoff Brief

**Written:** 2026-08-29, by Claude (Sonnet 5) following two council reviews of workbench structure.
**Purpose:** hand off the UI-layer findings a prior audit flagged, re-verified fresh today rather than trusted as-is. Two of the four original findings turned out **stale or wrong** — don't re-derive the old numbers, start from what's below.

## Context

Today's session consolidated backend duplication (notification senders, config loaders — done, committed, tested, CI-gated). The council explicitly parked UI-layer work for its own session: different skillset (frontend), different verification method (visual/manual, not a test suite), and the backend momentum shouldn't drag it into a rushed side-quest.

Before writing this brief, every finding below was re-checked against the current codebase — not copied from the original audit. Two were stale. Trust the numbers here, not the ones in older memory notes.

---

## Finding 1: Severity/status vocabulary sprawl — **still real, confirmed**

`stateToneClasses` (`src/lib/departments.ts:118`) is the canonical `ok/warn/crit/unknown` token set and is genuinely adopted — 15 files use it, real progress since it was introduced. But at least **6 more independent vocabularies** coexist untouched, doing the same job differently:

| Location | Vocabulary |
|---|---|
| `src/app/self-improvement-findings/page.tsx` | `info \| low \| medium \| high \| critical` |
| `src/app/emergency-alert-hub-workbench/page.tsx` | own `SEVERITY_LABELS`/`SEVERITY_BADGE` maps |
| `src/components/ProactiveSignals.tsx` | `Severity = critical \| high \| medium` |
| `src/lib/alerts.ts` | `AlertSeverity = critical \| high \| warning` (note: "warning" not "medium" — different word for the same tier) |
| `src/lib/hygieneRules.ts` | own `critical \| high \| medium` + a separate `SEVERITY_RANK` |
| `src/lib/intelligenceRisk.ts` | `RiskLevel = HIGH \| MEDIUM \| LOW \| ''` (uppercase, different casing convention entirely) |

Also worth checking while in this area: `src/lib/capture.ts` and `src/lib/types.ts` each independently define their own `ProcessingStatus` and `ReviewStatus` types with **different value sets** — that's not domain variety, that's the same concept duplicated with drift. Worth a specific look, not just folded into the severity work.

**Suggested first step:** pick the target taxonomy (`stateToneClasses`'s 4-tier `ok/warn/crit/unknown` is the existing canonical one — extend it rather than inventing a 5th), then migrate the 6 vocabularies above one at a time. This is the same "canonical exists, unenforced" shape as today's backend work — the pattern that worked today (migrate + CI gate) likely transfers, though a severity *taxonomy* gate would need to check for new bespoke type unions, not a grep signature like today's — worth designing that check before or alongside the migration, not after.

## Finding 2: API layer has no backend abstraction at all — **original framing was wrong, reframe entirely**

The old finding was "25/29 routes bypass the Command Centre backend." That's stale in a specific way: **there is no Command Centre backend to bypass.**

- Total API routes today: **90** (`route.ts` files under `src/app/api`) — the surface has roughly tripled since the old 29-route baseline.
- `src/lib/command-centre.ts` exists (273 lines, looks like exactly the central layer the old finding assumed) but **has zero importers anywhere in the codebase, including its own API routes.** It's dead code that was never wired in.
- **89 of 90 routes talk directly to Supabase.** The one exception (`api/advisory/loops/route.ts`) reads local files — not a bypass case, just a different kind of route.

This is worse than the original finding implied, but differently shaped: it's not "most routes skip the good layer," it's "the good layer was built once, never adopted, and everything grew up around it instead." Given 90 routes now exist directly coupled to Supabase, a lift-and-shift onto `command-centre.ts` is a much bigger job than it would have been at 29 routes — this needs a real scoping decision (retrofit vs. accept direct-Supabase as the actual pattern and formally retire `command-centre.ts`) before any migration work starts, not a mechanical "migrate them all."

**Suggested first step:** don't start migrating routes. First decide: is `command-centre.ts` worth reviving as the real abstraction layer, or is "routes talk to Supabase directly" simply what this platform's API layer actually is now and `command-centre.ts` should be deleted as dead code? That's a 30-minute architectural call, not a coding task, and it determines whether the other 89 routes are a problem at all.

## Finding 3: Health OSINT / Human Systems domain split — **unresolved, unchanged**

Both remain fully separate top-level workbenches with separate routes, APIs, and data domains:
- **Health OSINT** (`/health-osint`) — external clinical-trial/performance-research intelligence.
- **Human Systems** (`/human-systems-workbench`) — personal recovery/medical/readiness tracking. Recently had an internal VNext consolidation (its own tab split was removed per the page's own comment), but that was internal tidying, not a cross-workbench boundary decision.

No comments, ADRs, or code found addressing whether these two should have a clearer boundary or whether the split is intentional and just needs documenting as such. This is a genuine open question, not obviously a bug — worth a short "is this actually two domains" decision before any restructuring.

## Finding 4: Nav unreachability — **mostly stale, the 59% figure does not hold**

This was the biggest surprise. Re-checked properly (traced actual `Link`/`href` references, not just the primary sidebar list):

- The literal top-level sidebar nav (`src/lib/nav.ts`) is sparse — only 2-3 direct links.
- But `WorkbenchShell.tsx`'s persistent workbench switcher renders all 11 entries from `src/lib/workbenches.ts` (`LIVE_WORKBENCHES`) on every page — so those 11 workbenches are genuinely one click away from anywhere in the app, even though they're not in the literal `nav.ts` list. The old 59%-unreachable stat likely counted against `nav.ts` alone and missed this switcher.
- Of 38 real page routes (excluding the legacy `(app)/` directory and API routes), the **actual confirmed orphans — zero incoming links anywhere in the codebase** — are just two:
  - `src/app/comms-workbench/page.tsx`
  - `src/app/self-improvement-findings/page.tsx`
- `src/app/investigate/page.tsx` is effectively orphaned too: it's only reachable through `HomeScreen.tsx`, which is exclusively mounted inside the legacy `(app)/captains-chair/page.tsx` — not the live app.
- A few others (`mission-workbench`, `knowledge-workbench`, `health-osint-curation`) are reachable but only through secondary in-app links (buried in another workbench's UI, not a nav tile) — worth a look for discoverability, but not orphaned.
- `/home` is a deliberate retired redirect stub, not a bug.

**Real orphan count: ~3 of 38 pages (~8%), not 59%.** Still worth fixing — `comms-workbench` and `self-improvement-findings` genuinely have no path in from the live app — but this is a small, bounded fix (add 2-3 tiles/links), not the large nav-IA rework the original number implied.

---

## Suggested order for the next session

1. **Nav orphans (Finding 4)** — smallest, cleanest win. Add `comms-workbench` and `self-improvement-findings` to `LIVE_WORKBENCHES` (or wherever makes sense), fix `investigate`'s reachability. Bounded, single-session.
2. **Command Centre decision (Finding 2)** — not code, a scoping call. Decide revive-vs-retire before anything else touches the API layer. Do this early since it affects whether Finding 2 is even a real task.
3. **Severity vocabulary consolidation (Finding 1)** — biggest real chunk of work, same shape as today's backend consolidation (canonical exists, migrate + gate). Good candidate for its own multi-commit session once the target taxonomy is picked.
4. **Health OSINT / Human Systems (Finding 3)** — a decision, not urgent. Fold into whichever session touches either workbench next, doesn't need to be dedicated time on its own.

## Files to start from

`src/lib/nav.ts`, `src/lib/workbenches.ts`, `src/components/ui/WorkbenchShell.tsx`, `src/lib/departments.ts` (canonical `stateToneClasses`), `src/lib/alerts.ts`, `src/lib/hygieneRules.ts`, `src/lib/intelligenceRisk.ts`, `src/app/self-improvement-findings/page.tsx`, `src/app/emergency-alert-hub-workbench/page.tsx`, `src/lib/command-centre.ts`, `src/lib/capture.ts` + `src/lib/types.ts` (duplicate `ProcessingStatus`/`ReviewStatus`).
