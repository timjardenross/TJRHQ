# Severity/Status Vocabulary Canonicalization — Investigation & Plan

**Written:** 2026-08-29, following the UI-Layer-Debt-Handoff-2026-08-29 pickup session (Finding 1). Prep for a dedicated migration session — the investigation below is locked in; execute directly, don't re-investigate.

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

### The `wb-*` / `state-*` Tailwind token-family split

- `wb-*` (`tailwind.config.ts:60-83`): base tones fail AA as white-on-fill; `-on` variants ARE the correct solid-button fill. Confirmed consistent everywhere.
- `state-*` (`departments.ts:110-114`, `tailwind.config.ts:36-39`): `-on` is a darkened *text* color for `/15`-tinted backgrounds, never a fill. Confirmed consistent across all 7 consumers, no exceptions.
- Genuinely incompatible conventions sharing the `-on` suffix — not a bug in either alone, a foot-gun when mixed (already caused one near-miss this session).
- Adoption: `wb-*` 49 files vs `state-*` 7 files.

### `ProcessingStatus`/`ReviewStatus` — separate issue, NOT part of this migration

`types.ts` (VM document pipeline, `processing_documents` table) and `capture.ts` (captured-items pipeline, `captured_items` table) each define these names independently with different values — a naming collision between two unrelated domains, not severity sprawl. Fix is a rename for clarity (`DocumentProcessingStatus`/`DocumentReviewStatus` vs `CaptureProcessingStatus`/`CaptureReviewStatus`) plus updating the untyped duplicates in `(app)/operations/page.tsx`, `(app)/timeline/page.tsx`, `(app)/search/page.tsx`. Small, independent, no color/rendering logic — do separately, don't bundle into the tone migration.

## Part 2 — Proposed Canonical System

**1. Tone enum: keep `ok|warn|crit|unknown`, add a 5th — `info`.** The 4-tier base is right (already the most disciplined, decoupled from department identity). `info` is needed because Badge's `success|warning|error|info|neutral` and Finding's `info` severity both encode a real "benign/FYI, not just unknown" state that `unknown` doesn't capture. Collapses:
- `info|low|medium|high|critical` → `info|ok|warn|warn|crit` (low→ok, medium→warn is the default call — confirm with whoever owns that page, not a technical blocker)
- `critical|high|warning` → `crit|warn|warn`
- `HIGH|MEDIUM|LOW|''` → `crit|warn|ok|unknown`
- `critical|high|medium|low` → `crit|warn|warn|ok`
- `emergency_warning|watch_and_act|advice|unknown` → `crit|warn|ok|unknown` (keep the label table for display text, route only the color)

**2. One mapping function.** Keep `toneClasses(StatusTone)` untouched (different concept, already correct). Merge `Badge`/`riskToStatus` into `stateToneClasses` (add `info`); `Badge.tsx` calls `stateToneClasses` internally instead of its own table. Every bespoke vocabulary gets a small adapter (`severityToTone`, `alertSeverityToTone`, `riskLevelToTone`, etc.) living next to `stateToneClasses` in `departments.ts`, mapping its own values onto the 5-tone enum before calling it. End state: **one function turns any semantic state into CSS classes.**

**3. Token family: `wb-*` becomes canonical.** By evidence (49 files vs 7, every live modern workbench built on it) not preference. `stateToneClasses`'s implementation switches to emit `wb-*` classes (with `-on` correctly used as the fill variant) — an internal change, invisible to callers. Delete `state-*` Tailwind definitions + safelist entries once all 7 consumers are migrated. Don't try to keep both "by convention documentation" — two live conventions under one suffix is an active foot-gun, not stable.

**4. Migration order (verify visually after each step):**
1. `Badge.tsx`/`RiskPill.tsx` — internal refactor onto `stateToneClasses`, add `info`. No caller-visible change. **Do first, everything else depends on it.**
2. `emergency-alert-hub-workbench/page.tsx` (#2) — low risk, already Badge-based.
3. `self-improvement-findings/page.tsx` (#1) — replace this session's local maps with shared adapter. Verify severity/decision badges stay visually distinguishable across 5 tones.
4. `lib/alerts.ts` + 4 consumers (#4) — highest-traffic, do with care; visually verify the main dashboard afterward.
5. `lib/intelligenceRisk.ts` + consumers (#6) — check `journeyCoverage.ts`/`captainReview.ts` for exact-string business logic first, not just render sites.
6. `lib/delivery.ts`/`DeliveryPanel.tsx` (#8) — fix the department-color conflation, same bug shape as #3.
7. Delete `ProactiveSignals.tsx`, `hygieneRules.ts`, `api/proactive-signals/route.ts` outright (#3/#5, confirmed dead).
8. Once all 7 `state-*` consumers are migrated, delete `state-*` Tailwind tokens + old `STATE_CLASSES` body.
9. Separately: rename `capture.ts`'s `ProcessingStatus`/`ReviewStatus` (not part of this migration's PR).

**5. CI gate: partial automation.** A script can flag a `type`/`interface` field or type alias whose string-literal union contains 2+ words from a severity dictionary (`critical|crit|high|medium|warn|low|ok|error|info`), defined outside `departments.ts`/`types.ts`/`Badge.tsx` — same style as `tools/check_config_loaders.py`. Would have caught #1, #4, #6, #8 and #2's Badge-status union. **Can't catch** domain-worded vocabularies with no dictionary overlap (`emergency_warning|watch_and_act|advice`, `success|partial|failure`) — those need a code-review checklist item, not automation. Recommend: ship the dictionary gate as a warning (not hard-fail, avoid false positives on unrelated enums) plus the checklist item for the semantic cases.
