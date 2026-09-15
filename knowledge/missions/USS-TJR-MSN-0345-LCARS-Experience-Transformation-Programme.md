# USS-TJR-MSN-0345 — LCARS Experience Transformation Programme

**Mission type:** platform experience transformation. Design and implementation authorised.
**Status:** complete — treated as the implementation programme for MSN-0344 (delivered same session), not a new design exercise, per explicit direction. Priority order followed exactly: Decisions Inbox → Captain's Chair completion → Operational Picture → Since Last Session → Experience Principles.
**Verification:** every change compile-checked (`tsc --noEmit`, 0 errors across the whole app after each of the 5 items), test-verified (38/38 passing throughout), and lint-clean (0 new warnings — 1 pre-existing warning in an untouched file).

---

## 1. Decisions Inbox — built

**`/decisions`** (new route), backed by `lib/decisions.ts` (new). Merges 3 sources into one priority-ordered list, without inventing any new governance:

- **Missions** awaiting Captain/XO approval — same query `CaptainApprovalQueue` already runs, decided via the same existing `/api/missions/{id}/approve|reject` routes.
- **Engineering** build-inbox items awaiting review — same `fetchEngineeringQueue()`/`setQueueItemStatus()` functions `/engineering-queue` already uses, reused directly, not reimplemented.
- **Intelligence** recommendations flagged `requires_approval: true` — wired and real, but returns empty today. Direct grep confirmed `requires_approval` (defined in `core/platform/captain_brief_contract.py`) is never set `True` anywhere in the codebase. Rendered honestly as a real, live, currently-empty section with an explanation, not hidden and not faked.

**Prioritisation:** one merged sort order across mission and engineering items (blocked/priority-tier/age), not grouped by source system — items render in one list, highest-urgency first, regardless of which system they came from. This is a real heuristic merge, not literally the Priority Engine's `score_event()` (that function scores `core_events` rows; missions and build-inbox items don't currently emit through it) — disclosed as such in `lib/decisions.ts`'s own comments rather than overclaimed as "Captain Intelligence-driven ranking."

**Nav:** added as its own top-level "Decisions" area — the gap MSN-0344 explicitly declined to paper over with a nav link to a page that didn't exist yet.

---

## 2. Captain's Chair Completion — done for the panels that had real data

Direct code read (MSN-0344) found 4 panels still explicitly labelled mock (`DataSourceIndicator live={false} mockLabel="Preview Data"`). Resolved all 4, honestly:

| Panel | Outcome | Why |
|---|---|---|
| **Today's Briefing** | **Live.** Now reads the same `/api/captain-brief` data `/captains-brief` renders (confidence, priority/warning/recommendation/next-action counts). | Real data already existed one API call away. |
| **Captain's Timeline** | **Live.** Now reads today's real `core_events` (Event Bus), the same table 12+ real platform emit-points write to. | Real data existed, just never queried from this panel. |
| **Department Row** | **Partially live.** Fabricated per-department metric *numbers* removed. Real department names/links kept (they route to real, live pages) — now honestly labelled live, because the navigation itself is real even though the numbers weren't. | Building real cross-domain metrics for 5 unrelated departments in one pass would be new backend work across multiple domains — bigger than "replace with live data where supported by real data" authorises. |
| **Ship Status** | **Retired.** No real per-subsystem health source exists anywhere in the platform. | A permanently-fake panel is worse than no panel — matches the Experience Principles' honesty principle (§5 below), and this mission's own instruction not to build new backend services. |

Grid layout adjusted (3-column → 2-column where Ship Status was removed) so the page doesn't carry an empty gap.

---

## 3. Operational Picture — built, on Captain's Chair

Not a new page — a new panel on Captain's Chair, directly under `CaptainIntelligencePanel`, reusing the **same** `/api/captain-brief` fetch Today's Briefing already makes (one network call feeds two panels — no duplicate fetching, no new backend route). Shows the top 5 warnings + operational-intelligence items, each with domain, reason, `risk_score`, recommended action, and — reusing the exact evidence-disclosure component shipped for Captain's Brief in MSN-0344 — expandable supporting evidence. "Understand the situation within seconds" is answered with real, already-computed fields (`risk_score`, `confidence`, `Recommendation.evidence`), not a new intelligence pipeline.

**Not built:** the fuller `/intelligence` page rework (retiring its own 3rd severity vocabulary in favour of `ConfidenceIndicator`) MSN-0344 scoped separately — that's a larger, riskier change to an existing 685-line page with multiple tabs, correctly left for its own pass rather than folded in here.

---

## 4. Since Last Session — built, honestly scoped

New `lib/sinceLastSession.ts` + a Captain's Chair panel, placed first on the page (above even `MobileOperatingPicture`), per Objective 3's "first screen" ask.

**Mechanism:** a `localStorage` timestamp marker — read on page load, diffed against real `core_events` since that time, then updated to now. Zero new backend service, per this mission's explicit constraint. Real limitation, disclosed in the code and the UI: this resets if the Captain clears browser storage or switches device — a genuine constraint of the honest, scoped approach, not hidden.

**What it actually answers, of MSN-0344's original 6 questions:**

| Question | Answered? | Why |
|---|---|---|
| What changed? | **Yes, really** — real `core_events` count + per-domain breakdown since the marker | Data exists |
| What completed? | No | No `core_events` types cleanly map to "completed" across missions/engineering yet |
| What became worse? | No | Would need a snapshotted risk-trend to diff against — doesn't exist |
| What needs attention? | Indirectly, via Operational Picture (§3) and Decisions Inbox (§1), not duplicated here | Avoids a 4th place showing the same warnings |
| What was delegated? | No | The Operating Model (MSN-0322 §3.3) itself already names this as "a principle with no instrument" — confirmed still true |
| What was learned? | No | Would need a browser-callable Pattern Library read — the library is Python/server-side only today |

This is 1 of 6 questions genuinely answered, disclosed as such directly in the panel's own copy — not presented as a completed "Since Last Session capability" when it's a real, honest first slice of one.

---

## 5. Experience Principles — published

`knowledge/architecture/LCARS-Experience-Principles.md` (new) — 11 principles, each cited to a concrete piece of evidence from what MSN-0344/0345 actually built or corrected this session, not written in the abstract before any implementation existed. **Not unilaterally declared a Canonical Architecture Artefact** (that promotion sits alongside FD-0001/Blueprint/Operating Model and is the Captain's call) — flagged as a recommendation in the document itself, not claimed.

---

## Corrections to MSN-0344's Assumptions, Found While Building

Per the explicit instruction to document corrections with evidence rather than silently build around them:

1. **Decisions Inbox prioritisation is a heuristic merge, not a literal Priority Engine call.** MSN-0344's design sketch implied Priority-Engine-driven ranking; building it revealed missions/engineering items don't emit through `core_events`/`score_event()` today, so true Engine-driven ranking isn't available yet without a further integration. Disclosed in code rather than overclaimed.
2. **"Operational Intelligence recommendations" as a Decisions source is real but currently always empty**, confirmed by direct grep, not assumed. Built anyway (live-wired, honestly empty) rather than skipped, since the alternative (silently dropping the requested 3rd source) would have been less transparent than showing it real-and-empty.
3. **Department Row couldn't fully go live without new backend work** — MSN-0344 didn't anticipate this specific panel would split into "structure real, numbers fake" rather than a clean live/mock binary; the actual fix (strip the fake numbers, keep the real links) is a finer-grained honest outcome than MSN-0344's design implied.

---

## Verification Summary

- `tsc --noEmit`: 0 errors, after every one of the 5 items and again at the end.
- `vitest run`: 38/38 passing throughout, no regressions.
- `next lint`: 0 new warnings.
- Files touched: `lcars-portal/src/lib/nav.ts`, `lcars-portal/src/lib/decisions.ts` (new), `lcars-portal/src/lib/sinceLastSession.ts` (new), `lcars-portal/src/app/(app)/decisions/page.tsx` (new), `lcars-portal/src/app/(app)/captains-chair/page.tsx`, `knowledge/architecture/LCARS-Experience-Principles.md` (new). No file outside `lcars-portal/` and this one `knowledge/` doc was touched.

---

## Executive Summary

This mission built what MSN-0344 designed and scoped, in the priority order given: a real Decisions Inbox merging 3 governed sources with zero new governance invented; Captain's Chair's 4 remaining mock panels resolved (2 live, 1 partially live with honest scope reduction, 1 retired rather than left fake); a real Operational Picture reusing already-computed backend fields; a genuinely scoped Since Last Session (1 of 6 originally-envisioned questions, answered honestly, not oversold); and a permanent Experience Principles document grounded in evidence from this exact build, not written in the abstract.

Three corrections to MSN-0344's own assumptions were found and disclosed while building, not silently absorbed. Everything shipped is compile-checked, test-verified, and lint-clean. The LCARS Portal is measurably closer to "the operating system the backend has already become" — not because the vision changed, but because five concrete, honestly-scoped pieces of it are now real.
