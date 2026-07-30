# MSN: Activate Shadow-Mode LLM Scoring
**Status**: Ready for implementation on USS TJR VM  
**Date**: 2026-07-30  
**Scope**: 3 code changes + 1 verification  
**Timeline**: ~20 minutes  
**Risk**: Low (backward compatible, gated by shadow_mode flag)

---

## Overview

This mission activates the shadow-mode dual-path LLM scoring infrastructure (Issues 14, 20, 21) on the USS TJR platform. All database migrations and cost governance have been applied; these are the final code changes needed.

**Prerequisites**: ✅ Complete
- Database migrations 0085 & 0086 applied
- Cost governance seeded with default limits
- All Python modules ready (intelligence/governance/, intelligence/analysis/, etc.)

---

## Mission Tasks

### ITEM 1: Enable Shadow-Mode in Daily Collection Job
**File**: `intelligence/scheduler.py`  
**Line**: 407  
**Time**: 2 minutes

**Current code**:
```python
_stats = enrich_and_save(ranked, store)
```

**Change to**:
```python
_stats = enrich_and_save(ranked, store, shadow_mode=True)
```

**Why**: Activates dual-path scoring (heuristic + LLM in parallel) for all daily collected signals. Heuristic path remains authoritative; LLM path collected for analysis (Issue 15).

**Impact**:
- Daily collection job (06:00 AEST) will now collect both heuristic and LLM scores
- Cost-capped by `llm_cost_governance` table (default: $0.50/day for signal-scoring)
- Non-blocking: if LLM unavailable or cost limit hit, falls back to heuristic
- **No behavior change**: heuristic score still used for all intelligence briefs

---

### ITEM 2: Wire Health-Mission Correlation Job
**File**: `intelligence/scheduler.py`  
**Location**: Add new job to `_start_scheduler()` function  
**Time**: 5 minutes

**What to add** (insert AFTER line 238, before the log.info on line 241):

```python
    # ── Issue 17: Daily health-mission correlation wiring ──────────────────────
    # Runs at 07:30 AEST daily (after daily collection, independent of briefs)
    # Pure statistics, no LLM — correlates health metrics vs mission activity
    scheduler.add_job(
        _health_mission_correlation_job,
        CronTrigger(hour=7, minute=30, timezone=tz),
        id="health_mission_correlation",
        replace_existing=True,
    )
```

**Add this function** (insert AFTER the `_daily_collection_job()` function, around line 432):

```python
def _health_mission_correlation_job() -> None:
    """Issue 17: Daily health-mission correlation computation.
    
    Runs at 07:30 AEST daily — computes Pearson correlations between:
    - Pain vs mission activity
    - Energy vs mission activity
    - Sleep vs next-day mission activity
    - CPAP usage vs next-day productivity
    - Mood vs mission engagement
    
    Pure statistics, no LLM required. Results persisted to 
    intelligence_health_correlations table for dashboard display (Issue 18).
    """
    log.info("Health-mission correlation job triggered")
    try:
        from intelligence.workflow.health_mission_correlation_workflow import run_health_mission_correlation_job
        result = run_health_mission_correlation_job()
        log.info("Health-mission correlation complete: status=%s n_health=%d n_missions=%d",
                 result.get('status'), result.get('n_health_entries', 0), result.get('n_mission_days', 0))
        _record_heartbeat("health_mission_correlation", "ok", detail=result.get('status'))
    except Exception as exc:
        log.error("Health-mission correlation job failed: %s", exc)
        _record_heartbeat("health_mission_correlation", "failed", error_message=str(exc))
```

**Why**: 
- Schedules daily computation of health-mission correlations (Issue 17)
- Results feed into correlation synthesis (Issue 18) 
- Independent of LLM infrastructure — pure statistics
- Non-blocking: if data insufficient, logs and continues

**Update the startup log** (line 241-247):

**Current**:
```python
    log.info(
        "Scheduler started. ORI cron: %s (UTC) | GitHub sync: %s (%s) | "
        "Captain's briefs: morning 07:00, midday 12:30, EOD 18:00, weekly Mon 07:00 (%s) | "
        "Daily collection: 06:00 (%s) | Attention evaluation: every %d min | "
        "Validation suite: 06:30 (%s)",
        SCHEDULE_CRON, GITHUB_SYNC_CRON, SCHEDULE_TZ, SCHEDULE_TZ, SCHEDULE_TZ, eval_interval, SCHEDULE_TZ,
    )
```

**Change to**:
```python
    log.info(
        "Scheduler started. ORI cron: %s (UTC) | GitHub sync: %s (%s) | "
        "Captain's briefs: morning 07:00, midday 12:30, EOD 18:00, weekly Mon 07:00 (%s) | "
        "Daily collection: 06:00 (%s) | Health-mission correlation: 07:30 (%s) | Attention evaluation: every %d min | "
        "Validation suite: 06:30 (%s)",
        SCHEDULE_CRON, GITHUB_SYNC_CRON, SCHEDULE_TZ, SCHEDULE_TZ, SCHEDULE_TZ, SCHEDULE_TZ, eval_interval, SCHEDULE_TZ,
    )
```

---

### ITEM 3: Verify LLM Provider Access
**Location**: Run from VM command line  
**Time**: 3 minutes

**Command**:
```bash
cd /Volumes/SSK\ SSD/GitHub/TJRHQ
python3 -c "from intelligence.brief.llm_provider import LLMProvider; p = LLMProvider(); print(f'✅ LLM provider available: {p}')"
```

**Expected output**:
```
✅ LLM provider available: <LLMProvider object at 0x...>
```

**If it fails**:
- Check that model router is running and accessible
- Verify `intelligence/brief/llm_provider.py` can reach the fallback chain (Mistral → Gemini → Ollama)
- Check network connectivity to LLM endpoints
- If persistent, contact operations — not a blocker (fallback to heuristic always works)

**Why**: Ensures the LLM provider chain is reachable before shadow-mode goes live.

---

### ITEM 4: Verify All Changes (Dry-run Test)
**Time**: 5 minutes  

**Command 1: Test phase A enrichment with shadow_mode**:
```bash
python3 -m intelligence.analysis.test_shadow_mode_scoring --demo
```

**Expected**: Should complete without errors, showing heuristic vs LLM scoring comparison.

**Command 2: Test scheduler loads without errors**:
```bash
python3 -c "from intelligence import scheduler; print('✅ Scheduler module loads successfully')"
```

**Expected**: Should print success message with no exceptions.

---

## Implementation Checklist

### Code Changes (2 files)
- [ ] **File 1** — `intelligence/scheduler.py` line 407
  - [ ] Change `enrich_and_save(ranked, store)` 
  - [ ] To `enrich_and_save(ranked, store, shadow_mode=True)`
  - [ ] Verify no syntax errors

- [ ] **File 2** — `intelligence/scheduler.py` (add new job + function)
  - [ ] Add `_health_mission_correlation_job()` function (after line 432)
  - [ ] Add `scheduler.add_job(_health_mission_correlation_job, ...)` (after line 238)
  - [ ] Update startup log message (lines 241-247)
  - [ ] Verify no syntax errors

### Verification (3 checks)
- [ ] Run test: `python3 -m intelligence.analysis.test_shadow_mode_scoring --demo`
  - [ ] Completes without errors
  - [ ] Shows heuristic vs LLM agreement metrics

- [ ] Run LLM provider check: `python3 -c "from intelligence.brief.llm_provider import LLMProvider; LLMProvider()"`
  - [ ] No import errors
  - [ ] Returns provider object

- [ ] Run scheduler import test: `python3 -c "from intelligence import scheduler; print('OK')"`
  - [ ] Loads without syntax errors
  - [ ] Can import all dependencies

### Deployment (1 step)
- [ ] Commit changes with message:
  ```
  feat: activate shadow-mode LLM scoring (Issue 14) + health-mission correlation wiring (Issue 17)
  
  - Enable dual-path scoring in daily collection job (enrich_and_save shadow_mode=True)
  - Wire health-mission correlation job to run daily at 07:30 AEST
  - Cost-governed by llm_cost_governance ($0.50/day for signal-scoring)
  - Non-blocking: falls back to heuristic if LLM unavailable
  - Health correlations independent of LLM infrastructure
  ```

- [ ] Push to main branch
  - [ ] Verify CI/CD passes (if applicable)
  - [ ] Check for any pre-commit hook failures

---

## Activation Sequence

### T+0 min: Pre-flight
1. ✅ Migrations applied (done earlier)
2. ✅ Cost governance seeded (done earlier)
3. ⏳ Code changes (this mission)

### T+15 min: Deploy
4. Edit `intelligence/scheduler.py` (Items 1–2)
5. Run verification tests (Item 3–4)
6. Commit & push

### T+20 min: Live
7. Next daily collection job (06:00 AEST) runs with `shadow_mode=True`
8. Starts collecting dual-scored signals
9. At 07:30 AEST, correlation job runs independently

---

## Monitoring After Activation

**First 24 hours** — Watch for:
- ✅ `llm_call_metrics` table starts populating (check before 06:01 AEST)
- ✅ `intelligence_events` has `llm_score_breakdown` values (non-null)
- ✅ `intelligence_health_correlations` table gets first row at ~07:30 AEST

**Query to check daily collection**:
```sql
SELECT COUNT(*) as shadow_mode_signals, 
       COUNT(CASE WHEN llm_score_breakdown IS NOT NULL THEN 1 END) as with_llm_scores
FROM intelligence_events
WHERE collected_at >= CURRENT_DATE;
```

**Query to check health correlations**:
```sql
SELECT computed_at, status, n_health_entries, n_mission_days
FROM intelligence_health_correlations
ORDER BY computed_at DESC LIMIT 1;
```

**Query to check LLM costs**:
```sql
SELECT task_type, call_count, total_cost_usd, successful_calls, failed_calls
FROM llm_daily_costs
WHERE cost_date = CURRENT_DATE;
```

---

## Rollback (if needed)

**Revert shadow-mode** (5 minutes):
```bash
# Change line 407 back to:
_stats = enrich_and_save(ranked, store)  # Remove shadow_mode=True

# And comment out the health-mission correlation job:
# scheduler.add_job(_health_mission_correlation_job, ...)
```

**Impact of rollback**:
- ✅ Future signals scored heuristic-only (current behavior)
- ✅ Existing dual-scored data remains in database (no data loss)
- ✅ Health correlations stop accumulating (can re-enable later)

---

## Success Criteria

Mission complete when:
- ✅ All 3 code changes applied to `intelligence/scheduler.py`
- ✅ All verification tests pass (no import errors, LLM accessible)
- ✅ Changes committed & pushed to main
- ✅ First scheduled collection job (06:00 AEST) completes with `shadow_mode=True`
- ✅ `llm_daily_costs` shows activity for signal-scoring task
- ✅ `intelligence_events.llm_score_breakdown` has values for new signals

---

## Questions / Troubleshooting

**Q: What if LLM provider is unreachable?**  
A: Non-blocking fallback to heuristic. Cost governance still applies. Check model router logs.

**Q: What if daily collection job fails after changes?**  
A: Phase A enrichment has a try/except fallback (line 411–418). Check logs for "Phase A enrichment failed; plain-save fallback".

**Q: Can I test shadow-mode before the 06:00 job runs?**  
A: Yes — run `python -m intelligence.analysis.test_shadow_mode_scoring --demo` anytime.

**Q: When should I run Item 15 evaluation harness?**  
A: After 2+ weeks of dual-scored data (approximately 2026-08-13). See `MANUAL_SETUP_REQUIRED.md` Item 8.

---

**Author**: Claude Code (AI Native Roadmap Issues 14, 17, 20, 21)  
**Contact**: See `ROADMAP_COMPLETE_SUMMARY.md` for architecture details
