# Severity/Status Vocabulary Canonicalization — Investigation & Plan

**Written:** 2026-08-29, following the UI-Layer-Debt-Handoff-2026-08-29 pickup session (Finding 1). Prep for a dedicated migration session — the investigation below is locked in; execute directly, don't re-investigate.

**Updated same day, before any migration started:** the original draft recommended `wb-*` as the canonical token family by adoption count (49 files vs 7). That's reversed below — `tailwind.config.ts`'s own comment documents `state-*` as a ratified, contrast-validated design standard (`STARFLEET-DESIGN-STANDARD.md` §2, MSN-0310 §4.2), which `wb-*` has no equivalent backing for. Also added 2 more vocabulary instances (#9, #1a) found live on disk mid-investigation, bringing the count to 10.

## Part 1 — Inventory (verified against current code)

### Canonical / near-canonical systems already in place

| System | File:line | Values | Role |
|---|---|---|---|
| `stateToneClasses(StateTone)` | `departments.ts:110-119`; type `types.ts:32` | `ok\|warn\|crit\|unknown` | The real semantic-state system, decoupled from department identity. |
| `toneClasses(StatusTone)` | `departments.ts:97-101`; type `types.ts:17-23` | `command\|engineering\|operations\|medical\|science\|status\|neutral` | **Not severity** — department-identity color, legitimately separate. Leave untouched. |
| `Badge`/`riskToStatus` | `components/ui/Badge.tsx:3-19` | `success\|warning\|error\|info\|neutral` / `RED\|AMBER\|GREEN\|HIGH\|MEDIUM\|LOW` | A second, independent severity system — to be merged into `stateToneClasses`. |

`stateToneClasses` real consumers (13 files): `health-osint/page.tsx`, `intelligence-workbench/page.tsx`, `advisory-workbench/_components/LoopsView.tsx`, `agent-status-workbench/page.tsx`, `captains-chair-workbench/{page,alerts/page}.tsx`, `human-systems-workbench/recovery-brief/page.tsx`, `components/{ApprovalQueue,DataSourceIndicator,RecoveryConfidencePanel,EscalationBanner,ROSPanels,ConfidenceIndicator}.tsx`.

`Badge`/`riskToStatus` real consumers: `self-improvement-findings/page.tsx`, `intelligence-workbench/{escalation/[id],brief/[id]}/page.tsx`, `briefs/page.tsx`.

**Correction to the original handoff's "15 files" framing:** raw `wb-crit/warn/ok` Tailwind classes (independent of any function) appear in **49 files**; `state-crit/warn/ok/unknown` in only **7**. `wb-*` is the dominant palette by far — `stateToneClasses` is the more disciplined function but emits the minority token family.

### Bespoke severity vocabularies (6 to migrate, 1 already done, 2 to delete)

| # | File:line | Values | Renders via | Status |
|---|---|---|---|---|
| 1 | `self-improvement-findings/page.tsx:11` | `info\|low\|medium\|high\|critical` | local `SEVERITY_STATUS`/`DECISION_STATUS` maps (fixed 2026-08-29, still bespoke) | Live, migrate |
| 2 | `emergency-alert-hub-workbench/page.tsx:47-58` | `emergency_warning\|watch_and_act\|advice\|unknown` | `Badge` | Live, migrate (real domain vocab — keep the label table, route the *color* through canonical) |
| 3 | `components/ProactiveSignals.tsx:6,18-26` | `critical\|high\|medium` | hand-rolled maps onto **department-identity** classes — conflation bug | **Dead**, zero importers — delete, don't migrate |
| 4 | `lib/alerts.ts:33,55` (`AlertSeverity`, `SEVERITY_RANK`) | `critical\|high\|warning` | `captains-chair-workbench/{page,alerts/page}.tsx`, `MobileCommandBar.tsx`, `MobileAlertDrawer.tsx` via `useAlerts.ts` | **Live, highest-traffic** — main dashboard alert feed |
| 5 | `lib/hygieneRules.ts:28,31-32` | `critical\|high\|medium` | only feeds dead #3's API route | **Effectively dead** — delete alongside #3 |
| 6 | `lib/intelligenceRisk.ts:12` (`RiskLevel`) | `HIGH\|MEDIUM\|LOW\|''` | `api/intelligence/route.ts`, `investigations/{journeyCoverage,captainReview}.ts`, `(app)/intelligence/page.tsx` | **Live** — feeds business logic, not just display. Verify no exact-string logic dependents before touching casing/values. |
| 7 | `advisory-workbench/_components/LoopsView.tsx` `OUTCOME_OPTS` | `success\|partial\|failure` | `stateToneClasses` | **Already migrated 2026-08-29** — reference implementation |
| 8 | `lib/delivery.ts:46` (`Bottleneck.severity`) | `critical\|high\|medium\|low` | `components/DeliveryPanel.tsx:14,81` `SEV_TONE` maps onto **department-identity** — same conflation bug as #3 | Legacy `(app)/delivery` page, still live-rendering. Migrate. |
| 9 | `human-systems-workbench/_components/types.ts:577-586` (`capacityStateStatus`) | `green\|orange\|red` (from `capacity_checkins.capacity_state`) → `Badge` status | Well-governed, not sprawl — its own comment declares it *"THE primary capacity indicator... every place that shows Capacity Today should use this mapping"*. Keep the function, just repoint it at the merged `stateToneClasses`-backed `Badge` in step 1 below instead of `Badge`'s current standalone table. | Live, high-traffic (Captain's Chair Signal Snapshot, human-systems-workbench). Update call, don't restructure. |
| 10 | `api/health-osint/threat-assessment/route.ts:8-12,21-25` (`SEVERITY_IMPACT`, `probabilityFromFrequency`) | `critical\|severe\|moderate\|mild` → `critical\|high\|medium\|low` (impact); separately `high\|medium\|low\|unknown` (probability) | Backend risk-matrix (probability × impact × confidence) feeding `health-osint/page.tsx`'s threat-assessment view | **Different in kind from #1-8** — this computes an escalation tier from business inputs, it doesn't just recolor a label. Don't fold its internal matrix logic into the tone migration; just make sure whatever the frontend does with the *output* tier goes through the canonical adapter for color. |
| **1a** (new, found mid-session on `captains-chair-workbench/page.tsx`, added by a concurrent session while this plan was being written) | `captains-chair-workbench/page.tsx:71-86` (`CAPACITY_STATE_LABEL`, `CAPACITY_STATE_TONE`, `HEALTH_SEVERITY_TONE`) | `green\|orange\|red` → `StateTone`; `critical\|severe` → `StateTone` | Page's own comment explains these are intentionally local, "matching how this file already keeps its own `POSTURE_STATE_TONE`/`RISK_STATE_TONE` rather than reaching into another workbench's `_components`" | Live. Points at the same underlying vocab as #9 (`capacity_state`) and health-osint's severity wording — **evidence the file-local-duplication pattern is still actively growing even during this investigation.** Fold into step 1's adapter set so this file can import a shared `capacityStateToTone`/`healthSeverityToTone` instead of re-deriving its own. |

**Inventory is now 10 items** (was 8 at investigation time, was 7 at handoff time) — the vocab count keeps growing while unmigrated, which is itself the argument for finishing this soon and shipping the CI gate.

### The `wb-*` / `state-*` Tailwind token-family split — **decision flipped: `state-*` is canonical**

Original recommendation (adoption count: `wb-*` in 49 files vs `state-*` in 7) is **overturned** by a fact missed on first pass: `tailwind.config.ts:95-102`'s comment on the `state` block says these colors are a **ratified design standard** — *"operational status colours are sacred, never overridden by department colour,"* revived from `STARFLEET-DESIGN-STANDARD.md` §2, carried forward by MSN-0310 §4.2, with every value contrast-validated (≥3:1 fill, ≥4.5:1 text) against `docs/design-tokens/PHASE-1A-CONTRAST-MATRIX.md`. `wb-*` has no equivalent governance — it's just what most pages happened to use. **Authority beats adoption count here: `state-*` is canonical.**

This actually *simplifies* the migration: `stateToneClasses` already emits `state-*` classes, so **no internal rewrite of the function is needed** (Part 2, item 3 below is now much smaller than originally scoped — adding one tone, not swapping a token family). The larger, separate follow-on question — whether the 49 files using raw `wb-crit/warn/ok` classes for severity-like meaning should eventually move onto `state-*` too — is real but **out of scope for this migration** and shouldn't block it; track it as its own future item.

- `wb-*` (`tailwind.config.ts:60-83`): base tones fail AA as white-on-fill; `-on` variants ARE the correct solid-button fill. Confirmed consistent everywhere. No governance document backs this family.
- `state-*` (`departments.ts:110-114`, `tailwind.config.ts:95-108`): `-on` is a darkened *text* color for `/15`-tinted backgrounds, never a fill. Ratified (see above), contrast-validated, has `ok/warn/crit/unknown` already defined — only missing `info`.
- Genuinely incompatible `-on` conventions between the two families — not a bug in either alone, a foot-gun when mixed (already caused one near-miss this session). Reason enough on its own to pick one and stop growing the other for this purpose, independent of the authority argument above.

**Colors that will actually be used** (once `info` is added):

| Tone | Fill (`DEFAULT`) | Text (`on`, for `/15`-tinted backgrounds) |
|---|---|---|
| ok | `#278A44` | `#1B5E20` |
| warn | `#9C5D10` | `#7A4610` |
| crit | `#C43030` | `#7A1616` |
| unknown | `#5A6690` | `#33395C` |
| info | **not yet defined — needs picking + contrast validation before use** (see Part 2, item 1) |

### `ProcessingStatus`/`ReviewStatus` — separate issue, NOT part of this migration

`types.ts` (VM document pipeline, `processing_documents` table) and `capture.ts` (captured-items pipeline, `captured_items` table) each define these names independently with different values — a naming collision between two unrelated domains, not severity sprawl. Fix is a rename for clarity (`DocumentProcessingStatus`/`DocumentReviewStatus` vs `CaptureProcessingStatus`/`CaptureReviewStatus`) plus updating the untyped duplicates in `(app)/operations/page.tsx`, `(app)/timeline/page.tsx`, `(app)/search/page.tsx`. Small, independent, no color/rendering logic — do separately, don't bundle into the tone migration.

## Part 2 — Proposed Canonical System

**1. Tone enum: keep `ok|warn|crit|unknown`, add a 5th — `info`.** The 4-tier base is right (already the most disciplined, decoupled from department identity, and — now confirmed — the ratified one). `info` is needed because Badge's `success|warning|error|info|neutral` and Finding's `info` severity both encode a real "benign/FYI, not just unknown" state that `unknown` doesn't capture. `state.info` has no color yet — **needs picking and running through the same contrast-validation process** documented for the other four (`docs/design-tokens/PHASE-1A-CONTRAST-MATRIX.md`, ≥3:1 fill / ≥4.5:1 text), not asserted from this investigation. A reasonable starting point to validate: the app's existing teal/sage accent (`wb-sage`/`wb-sage-deep`, already used as Badge's informational tone) rather than inventing a new hue family — but that's a proposal for the contrast check to confirm or reject, not a final answer. Vocabulary collapses onto the 5-tone enum:
- `info|low|medium|high|critical` → `info|ok|warn|warn|crit` (low→ok, medium→warn is the default call — confirm with whoever owns that page, not a technical blocker)
- `critical|high|warning` → `crit|warn|warn`
- `HIGH|MEDIUM|LOW|''` → `crit|warn|ok|unknown`
- `critical|high|medium|low` → `crit|warn|warn|ok`
- `emergency_warning|watch_and_act|advice|unknown` → `crit|warn|ok|unknown` (keep the label table for display text, route only the color)
- `green|orange|red` (capacity_state, #9/#1a) → `ok|warn|crit`
- `critical|severe` (health severity, #1a) → `crit|warn`

**2. One mapping function.** Keep `toneClasses(StatusTone)` untouched (different concept, already correct — this is the real LCARS department-identity palette, gold/orange/red/etc., not part of this migration at all). Merge `Badge`/`riskToStatus` into `stateToneClasses` (add `info`); `Badge.tsx` calls `stateToneClasses` internally instead of its own table. Every bespoke vocabulary gets a small adapter (`severityToTone`, `alertSeverityToTone`, `riskLevelToTone`, `capacityStateToTone`, etc.) living next to `stateToneClasses` in `departments.ts`, mapping its own values onto the 5-tone enum before calling it. `human-systems-workbench`'s existing `capacityStateStatus` (#9) and `captains-chair-workbench`'s new local maps (#1a) both repoint to the shared adapter instead of hand-rolling their own. End state: **one function turns any semantic state into CSS classes.**

**3. Token family: `state-*` is canonical — decision flipped from the first draft.** `stateToneClasses` already emits `state-*` classes, so **this step is now just "add `info`," not "rewrite the function to emit a different family."** No `wb-*`/`state-*` swap needed for this migration to complete. The separate, larger question — migrating the 49 files currently using raw `wb-crit/warn/ok` classes for severity-like meaning onto `state-*` too — is real (see previous section) but tracked as its own future item, not a blocker here.

**4. Migration order (verify visually after each step):**
1. Pick and contrast-validate `state.info`'s color (Part 2 item 1) — do this first, everything downstream needs the value.
2. `Badge.tsx`/`RiskPill.tsx` — internal refactor onto `stateToneClasses`, add `info`. No caller-visible change. Everything else depends on it.
3. `emergency-alert-hub-workbench/page.tsx` (#2) — low risk, already Badge-based.
4. `self-improvement-findings/page.tsx` (#1) — replace this session's local maps with shared adapter. Verify severity/decision badges stay visually distinguishable across 5 tones.
5. `lib/alerts.ts` + 4 consumers (#4) — highest-traffic, do with care; visually verify the main dashboard afterward.
6. `lib/intelligenceRisk.ts` + consumers (#6) — check `journeyCoverage.ts`/`captainReview.ts` for exact-string business logic first, not just render sites.
7. `lib/delivery.ts`/`DeliveryPanel.tsx` (#8) — fix the department-color conflation, same bug shape as #3.
8. `human-systems-workbench/_components/types.ts`'s `capacityStateStatus` (#9) and `captains-chair-workbench/page.tsx`'s local maps (#1a) — repoint both to the shared adapter from step 2, delete the duplicated local logic.
9. `api/health-osint/threat-assessment/route.ts` (#10) — leave the probability×impact×confidence matrix logic alone; just make sure the frontend consuming its output tier uses the canonical adapter for color, not its own mapping.
10. Delete `ProactiveSignals.tsx`, `hygieneRules.ts`, `api/proactive-signals/route.ts` outright (#3/#5, confirmed dead).
11. Separately: rename `capture.ts`'s `ProcessingStatus`/`ReviewStatus` (not part of this migration's PR).

**5. CI gate: partial automation.** A script can flag a `type`/`interface` field or type alias whose string-literal union contains 2+ words from a severity dictionary (`critical|crit|high|medium|warn|low|ok|error|info`), defined outside `departments.ts`/`types.ts`/`Badge.tsx` — same style as `tools/check_config_loaders.py`. Would have caught #1, #4, #6, #8 and #2's Badge-status union. **Can't catch** domain-worded vocabularies with no dictionary overlap (`emergency_warning|watch_and_act|advice`, `success|partial|failure`) — those need a code-review checklist item, not automation. Recommend: ship the dictionary gate as a warning (not hard-fail, avoid false positives on unrelated enums) plus the checklist item for the semantic cases.
