# MSN: Activate Shadow-Mode LLM Scoring (Issues 14, 20, 21)

**Status**: Ready for implementation on USS TJR (VM)  
**Date**: 2026-07-30  
**Commit**: e177bbf (feat: implement shadow-mode LLM scoring + cost governance)  
**Scope**: 2 code changes + 1 optional monitoring setup  
**Time**: ~15 minutes  
**Risk**: Low (backward compatible; Phase A has fallback handler on line 411)

---

## What's Done (Already Committed)

✅ **Database Infrastructure**
- Migrations 0085 & 0086 applied to Supabase
- `llm_call_metrics` table: audit trail for all LLM calls
- `llm_cost_governance` table: per-task-type limits (signal-scoring: $0.50/day)
- `llm_daily_costs` materialized view: daily spend tracking
- `intelligence_events` columns: llm_score_breakdown, llm_relevance_score, llm_risk_rating, score_method, score_provenance, etc.
- `intelligence_health_correlations` table: for daily health-mission correlation results

✅ **Python Infrastructure** (just committed)
- `phase_a_enrichment.py`: Added shadow_mode parameter to `enrich_and_save()`
- `llm_cost_governance.py`: Cost checking and throttling logic
- `intelligence_analyst.py`: Added `score_dual_path()` method for parallel scoring
- `health_mission_correlation_workflow.py`: Daily correlation job ready
- `correlation_synthesis.py`: LLM synthesis of correlation insights
- `evaluate_shadow_mode_data.py`: Analysis harness (Issue 15)

---

## What's Left: 2 Simple Changes

### CHANGE 1: Enable Shadow-Mode in Daily Collection Job

**File**: `intelligence/scheduler.py`  
**Line**: 407  
**Current**:
```python
_stats = enrich_and_save(ranked, store)
```

**Change to**:
```python
_stats = enrich_and_save(ranked, store, shadow_mode=True)
```

**Why**: 
- Activates dual-path scoring (heuristic + LLM in parallel) for all daily signals
- Heuristic remains authoritative; LLM results logged for analysis (Issue 15)
- Cost-capped by `llm_cost_governance` (default: $0.50/day for signal-scoring)
- Non-blocking: if LLM unavailable or cost limit hit, Phase A fallback (line 411–418) catches errors and uses plain-save
- **Zero behavior change**: all briefs still use heuristic scores

**Testing after change**:
```bash
cd /Volumes/SSK\ SSD/GitHub/TJRHQ
python3 -c "from intelligence.scheduler import _daily_collection_job; print('✅ Scheduler imports successfully')"
```

---

### CHANGE 2: Wire Health-Mission Correlation Job (Optional but Recommended)

**File**: `intelligence/scheduler.py`  
**Location**: Add new job to `_start_scheduler()` function  
**Time**: 5 minutes

**What to add** (insert AFTER line 238, before the scheduler.start() call around line 249):

```python
    # ── Issue 17: Daily health-mission correlation job ──────────────────────
    # Runs at 07:30 AEST daily (after daily collection, independent of briefs)
    # Pure statistics — correlates health metrics vs mission activity
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
    
    Correlates health metrics (pain, energy, sleep, CPAP, mood) with 
    mission activity. Pure statistics, no LLM required. Results persisted 
    to intelligence_health_correlations table.
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

**Update the startup log** (line 241–247) to include the new job in the output:

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
        "Daily collection: 06:00 (%s) | Health-mission correlation: 07:30 (%s) | "
        "Attention evaluation: every %d min | Validation suite: 06:30 (%s)",
        SCHEDULE_CRON, GITHUB_SYNC_CRON, SCHEDULE_TZ, SCHEDULE_TZ, SCHEDULE_TZ, SCHEDULE_TZ, eval_interval, SCHEDULE_TZ,
    )
```

---

## Implementation Checklist

### Required (5 min total)
- [ ] Edit `intelligence/scheduler.py` line 407: add `shadow_mode=True`
- [ ] Test import: `python3 -c "from intelligence.scheduler import _daily_collection_job; print('OK')"`
- [ ] Commit: `git commit -am "feat: activate shadow-mode LLM scoring in daily collection job"`
- [ ] Push: `git push origin main`

### Optional but Recommended (10 min)
- [ ] Edit `intelligence/scheduler.py` (add new job + function + log line)
- [ ] Test import: `python3 -c "from intelligence.scheduler import _health_mission_correlation_job; print('OK')"`
- [ ] Commit & push

### Verification (Post-deployment, next 24 hours)
- [ ] At 06:00 AEST: Check logs for "Phase A enrichment: canonical=N duplicate=M" message
- [ ] Query: `SELECT COUNT(*) FROM llm_daily_costs WHERE cost_date = CURRENT_DATE;`
  - Expected: 1 row for 'signal-scoring'
- [ ] Query: `SELECT COUNT(*) FROM llm_call_metrics WHERE call_at >= CURRENT_DATE;`
  - Expected: >0 rows (LLM calls were made)
- [ ] If Change 2 applied, query at 07:30 AEST: `SELECT COUNT(*) FROM intelligence_health_correlations WHERE computed_at >= CURRENT_DATE;`
  - Expected: 1 row (correlation job ran)

---

## Monitoring Queries

**Daily LLM spend** (run after 06:00 AEST):
```sql
SELECT task_type, call_count, total_cost_usd, successful_calls, failed_calls
FROM llm_daily_costs
WHERE cost_date = CURRENT_DATE;
```

**Shadow-mode agreement rate** (sample after 1+ days of data):
```sql
SELECT
  ROUND(100.0 * SUM(CASE WHEN llm_risk_rating = risk_rating THEN 1 ELSE 0 END) / COUNT(*), 1) as agree_pct
FROM intelligence_events
WHERE llm_score_breakdown IS NOT NULL
  AND collected_at >= CURRENT_DATE - INTERVAL '1 day';
```

**LLM call audit trail**:
```sql
SELECT call_at, task_type, provider, success, latency_ms
FROM llm_call_metrics
WHERE call_at >= CURRENT_DATE
ORDER BY call_at DESC
LIMIT 10;
```

---

## Rollback (if needed)

If issues arise:

```bash
# Revert line 407
git checkout HEAD~1 intelligence/scheduler.py
# Or manually change line 407 back to:
#   _stats = enrich_and_save(ranked, store)

git commit -am "fix: disable shadow-mode LLM scoring"
git push origin main
```

**Impact of rollback**:
- ✅ Future signals scored heuristic-only (revert to current behavior)
- ✅ Existing dual-scored data in database remains (no loss)
- ✅ Next daily collection job uses heuristic path again

---

## Success Criteria

Mission complete when:
1. ✅ Change 1 applied and committed
2. ✅ Next daily collection job (06:00 AEST) completes without errors
3. ✅ `llm_daily_costs` shows activity for signal-scoring task
4. ✅ `intelligence_events.llm_score_breakdown` has values for new signals
5. ✅ Logs show "Phase A enrichment: canonical=N duplicate=M" (no "plain-save fallback")

If Change 2 applied:
6. ✅ `intelligence_health_correlations` has new row after 07:30 AEST

---

## Q&A

**Q: What if LLM provider is unreachable?**  
A: Phase A has try/except (line 137). If scoring fails, it logs a warning and continues to save the event. Dual-scored data will be incomplete (null llm_* columns) but the signal is still persisted.

**Q: Will this slow down the daily collection job?**  
A: Shadow-mode runs both paths in parallel (not sequential). Estimated overhead: +500ms–1s per batch of 30 signals. Collection job currently runs 06:00–06:05 AEST; should remain <10 min.

**Q: When should I run Issue 15 evaluation harness?**  
A: After 2+ weeks of dual-scored data (approximately 2026-08-13). Command:
```bash
python -m intelligence.analysis.evaluate_shadow_mode_data \
    --start-date 2026-08-13 \
    --days 14 \
    --output report.json
```

**Q: Can I test shadow-mode before 06:00?**  
A: Yes:
```bash
python3 -m intelligence.analysis.test_shadow_mode_scoring --demo
```

**Q: What if cost governance table is empty?**  
A: Defaults are already seeded (signal-scoring: $0.50/day, brief-synthesis: $2.00/day). If missing:
```sql
INSERT INTO llm_cost_governance (task_type, daily_call_limit, daily_cost_limit_usd, throttle_on_exceed, enabled)
VALUES ('signal-scoring', 500, 0.50, 'fall_back_to_heuristic', true);
```

---

## Timeline

**T+0** — Apply changes (5 min)  
**T+5** — Commit & push (1 min)  
**T+6** — Next daily collection job (06:00 AEST) picks up changes  
**T+7** — Verify database activity, check logs

---

**Author**: Claude Code  
**Issue References**: Issues 14 (shadow-mode), 20 (provenance/disclosure), 21 (cost governance), 17 (health correlation)  
**Commit Hash**: e177bbf
