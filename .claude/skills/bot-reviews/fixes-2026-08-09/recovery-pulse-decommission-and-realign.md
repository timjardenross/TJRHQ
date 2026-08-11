# Recovery Pulse: Decommission mood/stress + Realign Workbenches

**Date:** 2026-08-10
**Authority:** Captain directive — Telegram bot's energy/nervous_system/body_signals/day_win model is canonical for `recovery_pulses`; decommission the alternate mood/stress path and realign every display surface.
**Status:** Implemented, verified, committed, pushed (`152e0d16` → `e8dce382`).

## Context

Tonight's earlier Recovery Pulse redesign work (`recovery-pulse-3x-implementation.md`, `recovery-pulse-redesign-implemented.md`) found `recovery_pulses` had two independent write models:

1. **Canonical (Telegram bot)** — `telegram-bots/xo/app.py`, writes `energy`/`nervous_system`/`body_signals`/`day_win`.
2. **Alternate (divergent)** — two independent live writers of `mood`/`stress`: the LCARS Portal's Medical Bay manual pulse page, and the Command Centre backend's `POST /api/v1/personal-health/pulse`.

This mission decommissions writer #2 (both instances) and realigns every reader found — verified fresh rather than assumed unchanged, per the brief. **No schema change**: `mood`/`stress` columns and all historical rows are untouched; only new writes and derived displays changed.

## A) Decommission — writers repointed, not deleted

**Judgment call:** repointed both manual-entry writers to the canonical field set rather than removing the capability. The Captain's own directive framed this as "stop writing the divergent fields," not "remove manual entry," and both surfaces are otherwise-reasonable fallbacks for logging without Telegram. Flagging this so the alternative (delete manual entry outright) can be chosen instead if that's not what's wanted.

1. **LCARS Portal Medical Bay** (`lcars-portal/src/app/human-systems-workbench/medical/pulse/page.tsx`) — full redesign. Pulse types reduced to the canonical 3 (morning/midday/evening, matching the 2026-08-10 4→3 migration). Field set and exact wording now mirror the Telegram bot's `_kb_energy`/`_kb_mood`(nervous system)/`_kb_stress`(body signals)/`_kb_day_win` per pulse type. `readiness`/`pain`/`notes` kept as additive manual-only context (legitimate columns, still read elsewhere — not part of the divergence). Its backing API route (`api/human-systems/pulse/route.ts`) now also strips `mood`/`stress` server-side as defense in depth, regardless of caller.

2. **Command Centre backend** (`core/command-centre/backend/api/personal-health.js`, `POST /pulse`) — `VALID_PULSE_TYPES` reduced to the canonical 3; field validation and payload construction switched from `mood`/`stress` to `nervous_system`/`body_signals`/`day_win`, validated against `recovery_pulses`' real `CHECK` constraints (`calm/activated/dysregulated`, `quiet/present/significant`, `something_did/nothing_much/rough_day`).

3. **A third live writer surfaced during verification, not named in the original brief**: the Command Centre frontend's static dashboard (`core/command-centre/frontend/index.html`) has its own compact "Sickbay → Log Recovery Pulse" form that POSTs to the endpoint in #2. Repointed to match: its MOOD dropdown is now NERVOUS SYSTEM, the pulse-type selector dropped "End of Day". This is the confirmed caller of the endpoint in #2 — I found no other live callers via repo-wide grep.

`platform-runtime/commands/recovery_pulse.py` (the Slack `/recovery-pulse` modal) was investigated fresh and confirmed still **inactive** (`starfleet-slack-bot.service` not running, per earlier tonight's investigation) — left untouched, consistent with that investigation's explicit scope decision. Noted in passing: its code already writes Slack's "mood"/"stress" modal fields into the `nervous_system`/`body_signals` *columns* (not `mood`/`stress`), so it's not a divergent writer by column name — but the option values it would send don't obviously match those columns' `CHECK` constraints, so if ever reactivated it would most likely fail closed (upsert exception, logged, not saved) rather than write bad data. Not fixed — dormant, zero live risk, out of this mission's named scope.

## B) Realign — readers updated to canonical fields

Re-verified the reader list fresh rather than trusting the brief's list unchanged; it held up, plus more turned up.

| Surface | What changed |
|---|---|
| `lcars-portal/src/lib/useRecoveryConfidence.ts` + `RecoveryConfidencePanel.tsx` | `recovery_confidence_today` stopped returning `latest_mood`/`latest_stress` when migration `0115` landed earlier tonight — the panel's mood/stress tiles had already gone silently blank (fields typed but never populated). Now reads/shows the canonical `latest_nervous_system`/`latest_body_signals`, which the view has exposed since that same migration. |
| `lcars-portal/src/app/api/wellness/route.ts` | Derived `nervous_system_state` from a `stress`-only heuristic and never read `recovery_pulses.nervous_system`. Now prefers the real captured `nervous_system` reading, falling back to the `stress` heuristic only when null — the same MSN-0355 priority rule `ros-data.ts`/`lib/human-systems.ts` already apply, so this route stops disagreeing with them. |
| `lcars-portal/src/app/api/human-systems/route.ts` (Workbench API) | Same fix as above — `loadCtx`'s `recovery_pulses` select was missing `nervous_system`/`body_signals` entirely. |
| `lcars-portal/src/app/(app)/timeline/page.tsx`, Command Centre `api/timeline.js` | Detail line now shows `ns {value}` when the canonical field is present; falls back to `mood {value} (legacy)` only for rows that predate it — historical mood data stays visible as legacy context rather than disappearing. |
| `lcars-portal/src/app/(app)/operating-model/page.tsx` | Same legacy-fallback pattern; also fixed a pre-existing display bug where text categories (`moderate`, `calm`) were rendered with a nonsensical `/10` numeric suffix. |
| `lcars-portal/src/app/(app)/medical/page.tsx` | Pulse-tab copy updated from "...mood and nervous system state up to 4 times daily" to describe the repointed 3x/day canonical flow. |
| Command Centre `personal-health.js` (`GET /status`, `GET /trends`) + frontend `index.html` render | Switched from `latest_mood`/`latest_stress` to `latest_nervous_system`/`latest_body_signals`. While in this exact block: found and fixed a **pre-existing, unrelated bug** — `pulses_today`/`confidence_score` were reading columns (`pulse_count`/`confidence_score`) that don't exist on the view (real names: `pulses_completed`/`recovery_confidence`), so this endpoint's confidence numbers always read `0` regardless of mood/stress. Fixed since it directly blocked verifying my own change renders real data on this surface. |
| `core/intelligence/operating_picture.py` (backs the live `/operating_picture` Telegram command) | Found during the reader sweep, not in the original brief. Its `recovery_confidence_today` query used column names (`confidence_pct`, `band`, `nervous_system_state`) the view has never had — always returned `None`. Fixed to the real columns (`recovery_confidence`, `confidence_label`, `latest_nervous_system`) while adding `nervous_system` to its pulse select. |

**Intentionally left as-is (Part A's already-decided, out-of-scope follow-up):** `RecoveryConfidencePanel`'s 4-dot pulse ledger (AM/Mid/EOD/PM) and the Command Centre Sickbay dashboard's "X/4 pulses today" / 4-slot ledger. Both still reference `end_of_day_done`, which the view keeps as a column for exactly this backward-compat reason. Reconciling the *pulse-count display* (4→3, not a mood/stress concern) was explicitly flagged as deferred follow-up in tonight's earlier Part A implementation note — left alone here to avoid scope creep into an already-made decision.

## Verification

- **`npx tsc --noEmit`** on the full `lcars-portal` project — clean.
- **`npx eslint`** on all 9 changed TS/TSX files — clean.
- **`npx vitest run`** (full suite, 38 files) — 404/406 passing; the 2 failures are pre-existing, unrelated to this change (missing `app/decide/page.tsx` and `app/ask/page.tsx` in this checkout — a different in-flight piece of work, not touched here).
- **`python3 -m py_compile`** on `operating_picture.py` — clean.
- **`node --check`** on `personal-health.js`, `timeline.js`, and the extracted inline `<script>` block from `index.html` — clean.
- **Live Supabase query** (`recovery_confidence_today`, `recovery_pulses` CHECK constraints, live rows) confirmed: the view has never exposed `latest_mood`/`latest_stress` since migration `0115` (applied earlier tonight) — only `latest_nervous_system`/`latest_body_signals`/`latest_energy`/`latest_readiness`/`latest_pain_score`. Today's real row (`energy: moderate, nervous_system: dysregulated, body_signals: present`) renders sensibly through the realigned `RecoveryConfidencePanel` logic by inspection.
- **Repo-wide grep sweep** across `.ts/.tsx/.js/.py/.html` for `recovery_pulses` + `mood`/`stress` co-occurrence, both before and after edits, confirmed no remaining writer of `mood`/`stress` and no remaining reader still expecting the columns the view dropped.

## Judgment calls for the Captain to confirm or redirect

1. **Repoint vs. delete manual entry** — chose to repoint both manual-entry writers (Portal + Command Centre) to canonical fields, preserving the capability, rather than removing them. If the intent was actually to retire manual pulse entry entirely, that's a different, larger change (remove the pages/routes, not just their field model).
2. **Third writer found, not in the original brief** — the Command Centre frontend's Sickbay pulse form (`index.html`) is the actual live caller of the backend `/pulse` endpoint. Repointed for consistency with #2.
3. **Two pre-existing, unrelated bugs fixed opportunistically** because they sat in the exact lines being touched and blocked verifying the realignment itself: Command Centre `personal-health.js`'s `pulses_today`/`confidence_score` reading the wrong view columns (always `0`), and `operating_picture.py`'s confidence-view query using columns that never existed (always `None`). Both are disclosed here rather than folded in silently.
4. **Slack `/recovery-pulse` modal** — confirmed still dormant, left untouched. Its Mood/Stress-labelled fields already write to the `nervous_system`/`body_signals` columns by name (an earlier, separate rename), but the option *values* likely don't satisfy those columns' `CHECK` constraints — a reactivation would most likely fail closed, not corrupt data. Not fixed; flagged for whenever that service's fate is decided.
