# Chief Engineer Review — EOD Summary "Platform Health" Alert Verification

**Requested by:** Captain TJR, 2026-08-09, in response to the 18:00 AEST XO Telegram End-of-Day Summary
**Authority:** Advisory (USS-TJR-003, Engineering Division)
**Verification method:** direct read of source code (`core/platform/infra_narrative.py`, `core/platform/verification_engine.py`, `core/platform/heartbeat.py`, `intelligence/captains_brief.py`), live Supabase queries against project `cjvrpjwewsrumnbdydgg` (service-role `domain_heartbeat_latest`/`verification_state`/`domain_heartbeats` + direct table counts on `missions`, `decision_records`, `health_daily_logs`, `captains_log_entries`, `processing_documents`, `comms_content`), `pg_policy`/`pg_class` inspection for RLS, and `systemctl`/`journalctl` on the host for the cron/timer units that populate these signals.

## Mission Summary

Verify whether tonight's EOD alert — "23 data sources and jobs have never succeeded... meaning no mission or decision data has ever been recorded" and "Knowledge Library Ingestion... 47 permanent failures" — reflects reality, and explain why the "Content Review (4)" section looks wrong against the Content Workbench UI.

## Assessment

### 1. "No mission or decision data has ever been recorded" — **FALSE**. The underlying claim is a hallucinated overstatement of a monitoring-instrumentation gap, not a finding about real data.

**Direct proof the data exists** (live queries, 2026-08-09):
- `missions`: **148 rows**, real mission IDs (USS-TJR-MSN-0001 through 0180+), real status transitions, most recently updated 2026-06-27.
- `decision_records`: **31 rows**, real decisions including `human_decision`, `decision_maker`, `decision_reason` fields populated.
- `health_daily_logs`: **7 rows**, most recent 2026-07-17.
- `captains_log_entries`: **6 rows**, most recent 2026-06-28.

All four systems the alert names by name ("Mission Registry," "Decisions Ledger," "Daily Health Log," "Captain's Log") have genuine, populated, actively-used tables.

**What "never_succeeded" actually measures:** `core/platform/verification_engine.py` does not check these tables at all. It reads a separate, much newer self-health layer — `domain_registry`/`domain_heartbeats`/`domain_heartbeat_latest` (migration 0071, 2026-08-07) — where each domain is supposed to call a one-line `record_heartbeat(domain_key, status="ok")` at its own write point. `never_succeeded` means *"this heartbeat call has never fired,"* not *"this table has no data."*

**Live query confirms the scale of the gap:** 22 of 31 registered domains show `never_succeeded=true` right now (this matches the alert's "23" — the 23rd, `weekly_health_synthesis`, is a genuinely-different case: it *has* succeeded before, on 2026-07-17, and is merely stale now). Of those 22:

- **16 domains have literally zero `record_heartbeat()` call sites anywhere in the repo** (`grep` confirmed empty for `advisory_sessions`, `appointment_prep`, `decision_outcome_reminder`, `decision_review`, `engineering_handoff`, `governance_records`, `insight_outcomes`, `knowledge_freshness`, `lessons_learned`, `morning_brief`, `pain_escalation`, `physical_readiness`, `shakedown_digest`, `stale_missions_job`, **`decisions`**, **`captains_log`**). Nobody has ever wired the instrumentation for these — pure coverage gap.
- **`missions` and `health_daily_logs`** specifically: a commit from three weeks ago (`db77436`, 2026-07-18, "fix: payments_disruption classifier false positives; wire missing heartbeats") wired real `record_heartbeat()` calls into their actual write paths (`platform-runtime/commands/mission_lifecycle.py`, `health_check.py`). **That commit's own message states the exact failure mode being verified tonight:** *"verification_state has reported 'unsure' on 97/97 passes since inception; most of that is this class of gap, not real degradation."* Even so, both still show `never_succeeded=true` today — because no mission status change or new daily health log has happened through those specific code paths since the fix landed, so the wired heartbeat simply hasn't had an opportunity to fire yet. This is an unproven fix, not evidence the underlying system is broken.

**Where the alarming language comes from:** `intelligence/captains_brief.py`'s `generate_eod_summary()` inserts `infra['narrative']` verbatim into the Telegram message. That narrative is produced by `core/platform/infra_narrative.py::_generate()`, an LLM call (Gemini → Mistral → Ollama chain) whose system prompt says *"only use the domain data provided — never invent a cause"* but contains **no constraint against overstating impact/severity**. Given a bare `never_succeeded=true` flag per domain, the LLM inferred and asserted the causal claim *"meaning no mission or decision data has ever been recorded"* — a leap the structured data does not support and that is directly falsified by the live tables. This is exactly the gap the Captain suspected: an LLM synthesis layer overstating a narrower, more mundane signal (missing monitoring instrumentation) as a platform-wide data-loss event.

**The one item in this set that is genuinely live and real right now:**
- **Knowledge Library Ingestion (`knowledge_library`)**: `processing_documents` currently has **47 rows in `permanently_failed`** (confirmed by live count query — matches the alert's number exactly) out of 850 total. This part of the alert is accurate as a snapshot.
- However, the framing "job is failing... preventing new knowledge from being added" overstates causality:
  - `vm-processing.service` (the actual ingestion worker, runs every 10 min via `vm-processing.timer`) is alive and healthy per `journalctl` — it's scanning and reporting `new: 0, skipped: 834`. It's finding nothing new to ingest, not being blocked from ingesting.
  - The 47 permanently-failed count has been **frozen and unchanged since 2026-07-12** — not actively growing tonight.
  - **A separate, real, currently-active bug was found while verifying this**: `vm-processing-healthcheck.service` (the component that computes and reports this exact "failing" status via heartbeat) has been crashing on every run, every 30 minutes, since 2026-07-12, with `cannot create .../vm-processing/logs/vm-processing-healthcheck.log: Directory nonexistent` — the `logs/` directory the systemd unit writes to no longer exists on disk (likely lost in a redeploy/rsync around that date; `core/infrastructure/vm-processing/` was resynced 2026-08-07 without recreating it). So the "47 permanent failures, job is failing" verdict itself is a 4-week-old frozen snapshot from before this reporting pipeline broke, not a live-monitored current status — coincidentally still numerically accurate, but not because anything is being actively watched.

**Verdict on claim (1): FALSE as stated.** No mission or decision data loss has occurred; all four named systems have real, populated tables. What is real: (a) a self-health monitoring layer with a severe, mostly pre-existing and partially-acknowledged instrumentation gap (16 of 22 domains never wired at all, 2 more wired-but-unproven), which the LLM narrative generator converted into a false "no data has ever been recorded" claim with no guardrail against doing so; and (b) one genuinely real but frozen/stale finding (47 permanently-failed knowledge documents) whose own reporting pipeline has itself been silently broken for the same three-plus weeks.

### 2. Content Review (4) "doesn't align with the Content Workbench UI" — data matches exactly; it's a labeling/default-view mismatch, not a data mismatch.

- `intelligence/captains_brief.py::_get_content_review_queue()` queries `comms_content` for `status in (draft, review, ready_to_publish)`.
- Live query confirms exactly what the alert showed: **3 rows with `status='review'`, 1 row with `status='ready_to_publish'`** — titles/pillars match what the Captain saw in the alert.
- **RLS ruled out**: `comms_content` has row-level security enabled with a single policy `auth_read` (`FOR SELECT USING (true)`, role `authenticated`) — any authenticated session sees every row, same as the service-role client `captains_brief.py` uses. This is not a repeat of the earlier `ros-data.ts` dual-client RLS bug (checked and confirmed different).
- The Content Workbench's own `GET /api/content-workbench` (`lcars-portal/src/app/api/content-workbench/route.ts`) queries a **superset**: `status in (opportunity, draft, review, approved, ready_to_publish)`. All 4 alert items are included in that superset — live query confirms no `opportunity`/`draft`/`approved` rows currently exist, so the workbench's real item count matches the alert's 4 exactly.
- **The actual mismatch is presentational.** The workbench's `stageOf()` (same route file) maps `status='review'` and `status='ready_to_publish'` both to `stage='proofing'`, and `ContentBoard.tsx`'s `STAGE_LABEL` renders that column with the header **"Proofing"** — there is no column anywhere in the UI labeled "Content Review" or "Review." A Captain scanning for a "Content Review" queue that matches the Telegram section header won't find one by that name; the same 4 items are all sitting together under "Proofing."
- **A second, more concrete cause on mobile/narrow viewports**: `ContentBoard.tsx` initializes `activeMobileStage` to `'capture'` (line 750) and, below the `sm` breakpoint, renders *only* the single active stage (`items.filter(i => i.stage === activeMobileStage)`). Since there are currently zero items in `capture`, `research`, or `content_prep`, a Captain opening the workbench on a phone lands by default on an **empty "Capture" column** and must manually tap across to "Proofing" to see the 4 real items — which would read as "the workbench doesn't show what the bot said," even though the data is identical underneath.

**Verdict on claim (2): the 4 items are real and correctly represented in both places.** The apparent mismatch is (a) a naming gap — "Content Review" (Telegram) vs. "Proofing" (Workbench), no shared vocabulary — and (b) a UI default that opens on the wrong (empty) stage on mobile.

## Recommendations

1. **Constrain the infra-narrative LLM prompt** (`core/platform/infra_narrative.py::_SYSTEM_PROMPT`) to state explicitly that `never_succeeded` describes heartbeat-instrumentation coverage on the *monitoring* layer, not the underlying data/table, and to forbid claims like "no data has ever been recorded" unless a structured field says so. This is the direct fix for tonight's false alarm and will recur on every domain in the 16-domain zero-instrumentation set until either this prompt is fixed or the instrumentation gap is closed.
2. **Finish the instrumentation-wiring work `db77436` started but left incomplete** — `decisions` and `captains_log` have zero heartbeat call sites (same class of gap already fixed for `missions`/`health_daily_logs`/`recovery_pulses`); wire them the same way. Track separately from #1 since #1 is the more urgent fix (stops the false alarms immediately regardless of wiring progress).
3. **Fix `vm-processing-healthcheck.service`'s missing `logs/` directory** (`core/infrastructure/vm-processing/logs/` doesn't exist on disk) — this is a live, currently-failing systemd unit (crashing every 30 min for 3+ weeks) independent of the narrative-accuracy issue, and it's the reason the 47-permanently-failed knowledge library figure is a frozen July 12 snapshot rather than a monitored current one.
4. **Separately worth the Captain's attention (found opportunistically, not requested)**: `comms_content` id `68b17461` ("The Telstra outage is a stark reminder...") has been sitting in `ready_to_publish` since 2026-07-12 — a real, four-week-old actionable item.
5. **Content Workbench**: default `activeMobileStage` to the stage with the most items (or the first non-empty stage) rather than hardcoding `'capture'`, so the mobile view doesn't open on an empty column when there's real work waiting elsewhere. Low priority, cosmetic.

## Next Actions

- Immediate (Captain-facing): treat tonight's "no mission or decision data has ever been recorded" line as false and disregard; the 47-permanent-failures figure is real but stale/frozen, not an active worsening event.
- Engineering: item 1 (prompt fix) is the highest-leverage single change — it stops future false alarms of this exact shape without waiting on the slower instrumentation-completeness work in item 2.
- No code changes made during this verification — read-only investigation only, per the task's "verify, don't trust" framing.

## Mission Status

Advisory only — verification complete, no implementation authorized or performed. Items 1–5 above are recommendations for the Captain/relevant owner to prioritize, not actions taken.
