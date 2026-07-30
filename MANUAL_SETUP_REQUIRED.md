# Manual Setup Required — Items You Need to Handle

This document lists **everything that requires your manual intervention**. Code and infrastructure are complete; these items cannot be automated.

---

## 🔴 CRITICAL: Database Setup

### 1. Apply Database Migrations

**What**: Run the two new migrations to create tables and columns  
**Why**: Code cannot modify your Supabase schema without explicit approval  
**What you need to do**:

```bash
# Option 1: Using Supabase CLI (recommended)
cd /Volumes/SSK\ SSD/GitHub/TJRHQ
supabase db push

# Option 2: Manual SQL via psql
psql -U postgres -d postgres < core/infrastructure/supabase/migrations/0085_shadow_mode_llm_scoring.sql
psql -U postgres -d postgres < core/infrastructure/supabase/migrations/0086_health_mission_correlations.sql
```

**Verify**:
```bash
# Check that columns were created
psql -U postgres -d postgres -c "SELECT column_name FROM information_schema.columns WHERE table_name='intelligence_events' AND column_name LIKE 'llm_%' LIMIT 1;"

# Check that new tables exist
psql -U postgres -d postgres -c "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'intelligence_health_%' OR table_name LIKE 'llm_%';"
```

**Timeline**: Do this before activating shadow-mode  
**Risk**: Low (additive, idempotent — safe to rerun)

---

### 2. Seed Cost Governance Configuration

**What**: Initialize default cost thresholds for LLM calls  
**Why**: Without this, cost governance defaults to "no limit" (permissive but unmonitored)  
**What you need to do**:

```bash
psql -U postgres -d postgres -f intelligence/governance/seed_cost_governance.sql
```

Or manually via Supabase dashboard:

```sql
INSERT INTO llm_cost_governance (task_type, daily_call_limit, daily_cost_limit_usd, throttle_on_exceed, enabled)
VALUES
  ('signal-scoring', 500, 0.50, 'fall_back_to_heuristic', true),
  ('brief-synthesis', 10, 2.00, 'alert', true),
  ('correlation-synthesis', 5, 0.10, 'alert', true);
```

**Timeline**: Immediately after migrations  
**Can adjust anytime**: Update `llm_cost_governance` table via dashboard if you want higher/lower limits

---

## 🟡 CRITICAL: Code Integration

### 3. Enable Shadow-Mode in Daily Batch Job

**What**: Tell the batch job to collect dual-path data  
**Why**: Code is ready, but you choose when to activate  
**What you need to do**:

Find where the daily intelligence collection job calls `enrich_and_save()`. This is likely in:
- `intelligence/scheduler.py` (look for `_daily_collection_job`)
- `platform-runtime/...` (check runtime scheduler)

**Change**:
```python
# Before:
from intelligence.ingestion.phase_a_enrichment import enrich_and_save
enrich_and_save(events, store)

# After:
from intelligence.ingestion.phase_a_enrichment import enrich_and_save
enrich_and_save(events, store, shadow_mode=True)
```

**Timeline**: After migrations + cost governance seed  
**Impact**: Doubles LLM call volume (but cost-capped), no behavior change (heuristic stays authoritative)

**Verification**: After next batch run, check:
```sql
SELECT COUNT(*) as shadow_mode_signals, COUNT(CASE WHEN llm_score_breakdown IS NOT NULL THEN 1 END) as with_llm_scores
FROM intelligence_events
WHERE collected_at >= CURRENT_DATE;
```

---

### 4. Integrate Health-Mission Correlation Job into Scheduler

**What**: Schedule daily computation of health-mission correlations  
**Why**: Code is ready, but you decide when/how often to run it  
**What you need to do**:

Add to your scheduler (wherever daily jobs live):

```python
from intelligence.workflow.health_mission_correlation_workflow import run_health_mission_correlation_job

# In your daily scheduler:
def _daily_jobs():
    # ... existing jobs ...
    
    # Issue 17: Health-mission correlations (pure stats, no LLM)
    correlation_result = run_health_mission_correlation_job()
    log.info(f"Health-mission correlation job: {correlation_result['status']}")
    # Results auto-persist to intelligence_health_correlations table
```

**Timeline**: Can do anytime (no dependencies)  
**Frequency**: Daily (after health data is collected)  
**Cost**: Free (pure statistics, no LLM calls)

---

## 🟡 REQUIRED: Configuration & Monitoring

### 5. Configure LLM Provider Access

**What**: Ensure the LLM provider chain is reachable from Phase A jobs  
**Why**: Code assumes `intelligence.brief.llm_provider.LLMProvider()` is available  
**What you need to do**:

Verify that:
1. Model router is running and accessible
2. Fallback chain (Mistral → Gemini → Ollama) is configured
3. Credentials/env vars are set (if model-router requires auth)

**Check**:
```python
from intelligence.brief.llm_provider import LLMProvider
llm = LLMProvider()
# If this succeeds, you're good
```

**If it fails**: Check that `intelligence/brief/llm_provider.py` can reach the model router (network, credentials, etc.)

---

### 6. Set Up Daily Monitoring Queries

**What**: Create dashboards/alerts to monitor shadow-mode and cost  
**Why**: You need visibility into what's happening  
**What you need to do**:

Create dashboard queries (in Grafana, Supabase dashboard, or custom dashboard):

**Query 1: Daily LLM Spend**
```sql
SELECT
  cost_date,
  task_type,
  call_count,
  successful_calls,
  failed_calls,
  total_cost_usd,
  (SELECT daily_cost_limit_usd FROM llm_cost_governance WHERE task_type = llm_daily_costs.task_type) as daily_limit
FROM llm_daily_costs
WHERE cost_date >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY cost_date DESC, task_type;
```

**Query 2: Shadow-Mode Agreement Rate**
```sql
SELECT
  collected_at::date as date,
  COUNT(*) as total,
  SUM(CASE WHEN (score_provenance ->> 'llm_agree_with_heuristic')::boolean THEN 1 ELSE 0 END) as agree,
  ROUND(100.0 * SUM(CASE WHEN (score_provenance ->> 'llm_agree_with_heuristic')::boolean THEN 1 ELSE 0 END) / COUNT(*), 1) as agree_pct
FROM intelligence_events
WHERE llm_score_breakdown IS NOT NULL
  AND collected_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY collected_at::date
ORDER BY collected_at DESC;
```

**Query 3: LLM Failures**
```sql
SELECT
  call_at,
  task_type,
  provider,
  failure_reason,
  event_id
FROM llm_call_metrics
WHERE success = false
  AND call_at >= CURRENT_DATE - INTERVAL '24 hours'
ORDER BY call_at DESC;
```

**Timeline**: Set up before activating shadow-mode (optional but recommended)

---

### 7. Configure Alerts (Optional but Recommended)

**What**: Get notified if cost limits are exceeded or LLM failures spike  
**Why**: Early warning if something goes wrong  
**What you need to do**:

Set up alerts in your monitoring system:

**Alert 1: Daily Cost Exceeded**
```
IF (SELECT total_cost_usd FROM llm_daily_costs WHERE cost_date = CURRENT_DATE AND task_type = 'signal-scoring') > 0.50
  THEN notify(Slack: cost exceeded)
```

**Alert 2: LLM Failure Rate High**
```
IF (SELECT 100.0 * COUNT(CASE WHEN success = false THEN 1 END) / COUNT(*)
    FROM llm_call_metrics WHERE call_at >= NOW() - INTERVAL '24 hours') > 10
  THEN notify(Slack: LLM failures >10%)
```

**Alert 3: No Shadow-Mode Data Today**
```
IF (SELECT COUNT(*) FROM intelligence_events WHERE collected_at >= CURRENT_DATE AND llm_score_breakdown IS NOT NULL) = 0
  THEN notify(Slack: shadow-mode not running)
```

**Timeline**: Optional; implement after shadow-mode is running

---

## 🟢 TIMELINE-BASED: Issue 15 Analysis

### 8. Run Evaluation Harness (After 2+ Weeks of Shadow-Mode Data)

**What**: Analyze whether LLM actually improves outcomes  
**Why**: Determines if Issue 16 (selective augmentation) is worth building  
**When**: After at least 14 days of dual-scored signals  
**What you need to do**:

```bash
# Run the evaluation harness
python -m intelligence.analysis.evaluate_shadow_mode_data \
    --start-date 2026-08-13 \
    --days 14 \
    --output issue_15_report.json

# Check the report
cat issue_15_report.json | jq '.recommendation'
```

**Output you'll get**:
- Overall heuristic-LLM agreement % (e.g., "82.5%")
- Per-band analysis (HIGH, MEDIUM, AMBIGUOUS, LOW)
- Recommendation (e.g., "Route AMBIGUOUS (3.0-3.9) signals to LLM")

**Your decision**: Based on the report, decide:
- Is LLM worth using? (If >85% agreement, heuristic is already good)
- Which confidence band should be routed to LLM?
- Should you proceed with Issue 16?

**Timeline**: Do this starting week 3 (after 2 weeks of shadow-mode data)

---

## 🟢 TIMELINE-BASED: Issue 16 Activation

### 9. Configure & Activate Selective Augmentation

**What**: Route ambiguous signals to LLM (based on Issue 15 recommendation)  
**When**: After Issue 15 determines the threshold  
**What you need to do**:

1. **Decide** on the threshold (from Issue 15 report)
2. **Update** Phase A enrichment to use selective routing:

```python
from intelligence.analysis.selective_augmentation import (
    AugmentationThreshold, augment_signal
)
from intelligence.governance import LLMCostGovernance

# In your enrichment flow:
threshold = AugmentationThreshold(
    score_min=3.0,  # from Issue 15 report
    score_max=3.9,  # from Issue 15 report
    band_name="AMBIGUOUS (3.0-3.9)",
    expected_llm_improvement_pct=8.2,  # from Issue 15 report
)

cost_gov = LLMCostGovernance()
analyst = IntelligenceAnalyst(use_llm=True, cost_governor=cost_gov)

# For each signal:
result = augment_signal(
    signal,
    heuristic_score,
    analyst,
    cost_governor=cost_gov,
    threshold=threshold,
)
```

3. **Monitor** QA pass rates before/after

**Timeline**: Week 4+ (after Issue 15 analysis)

---

## 🟢 TIMELINE-BASED: Issue 17/18 Integration

### 10. Add Health-Mission Correlation Results to Dashboard

**What**: Display correlation insights on Home or Intelligence dashboard  
**When**: After Issue 17 is running (daily correlation computation)  
**What you need to do**:

Add to your dashboard template/component:

```python
from intelligence.workflow.health_mission_correlation_workflow import get_latest_correlations
from intelligence.brief.correlation_synthesis import synthesize_correlation_insights, display_correlation_brief

# Fetch latest correlation data
correlations = get_latest_correlations()

if correlations and correlations.get('status') == 'ok':
    # Generate insights (Issue 18)
    synthesis = synthesize_correlation_insights(correlations)
    
    # Format for display
    brief_text = display_correlation_brief(synthesis)
    
    # Render on dashboard
    dashboard.add_section('Health-Mission Insights', brief_text)
```

**Timeline**: After Issue 17 is running (week 2+)

---

## 🟢 OPTIONAL: Fine-Tuning & Advanced

### 11. Adjust Cost Governance Thresholds

**What**: Modify daily call limits or cost ceilings based on actual spend  
**Why**: Initial seed values are conservative; you might want different limits  
**What you need to do**:

```sql
UPDATE llm_cost_governance
SET
  daily_call_limit = 1000,        -- More calls per day
  daily_cost_limit_usd = 2.00,    -- Higher daily budget
  throttle_on_exceed = 'alert'    -- Warn but don't block
WHERE task_type = 'signal-scoring';
```

**Timeline**: Anytime; adjust after you see actual spend patterns

---

### 12. Customize Grounding Rules (Issue 18)

**What**: Modify the LLM synthesis prompt to match your preferences  
**Why**: The current prompt forbids causal claims; you might want different constraints  
**What you need to do**:

Edit `intelligence/brief/correlation_synthesis.py`:

```python
_SYSTEM_PROMPT = (
    "... your custom rules here ..."
)
```

**Examples**:
- Stricter: "Never mention r-values < 0.5"
- Looser: "You may mention potential mechanisms (but caveat with 'possibly')"
- Domain-specific: "Flag if correlations contradict known CPAP research"

**Timeline**: Optional; only if default rules don't fit your domain

---

### 13. Create Issue 19 Placeholder (Future)

**What**: When Issues 16 + 18 have production data, decide on cross-source reasoning  
**Why**: Cross-source reasoning is complex and needs evidence from earlier stages  
**What you need to do**:

After Issues 16 and 18 have shipped and generated real insights (month 3+):
1. Review what insights were actionable
2. Decide: Does cross-source reasoning (LLM reasoning across Operational + Health + Watchlist data) add value?
3. Design the scope (see `USSTJROS-AI-Native-Roadmap.md` Issue 19 section)

**Timeline**: Future; do this when 16 + 18 have proven themselves

---

## 📋 Checklist: What to Do Now

### Immediately (Today)

- [ ] Read `ROADMAP_COMPLETE_SUMMARY.md` (understand architecture)
- [ ] Read `ACTIVATE_SHADOW_MODE.md` (understand activation)
- [ ] Review all new code files (spot-check for issues)
- [ ] Run test: `python -m intelligence.analysis.test_shadow_mode_scoring --demo`

### Before Activation (This Week)

- [ ] **Item 1**: Apply migrations (0085, 0086)
- [ ] **Item 2**: Seed cost governance configuration
- [ ] **Item 3**: Enable shadow-mode in batch job
- [ ] **Item 4**: Add health-mission correlation job to scheduler
- [ ] **Item 5**: Verify LLM provider is accessible
- [ ] **Item 6**: Set up monitoring queries (optional)
- [ ] **Item 7**: Configure alerts (optional)

### Week 3+ (After Shadow-Mode Data)

- [ ] **Item 8**: Run Issue 15 evaluation harness
- [ ] **Item 9**: Configure Issue 16 based on Issue 15 results (if LLM is valuable)

### Week 2+ (Parallel)

- [ ] Check that Issue 17 correlation job is running daily
- [ ] View correlation results on dashboard

---

## 🆘 Troubleshooting

### "Migrations failed"
**Cause**: Supabase connection issue or syntax error  
**Fix**: 
1. Check `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` env vars
2. Run migration manually: `psql -U postgres -d postgres < migration.sql`
3. Check Supabase dashboard for errors

### "shadow_mode=True causes errors"
**Cause**: LLM provider chain unavailable or IntelligenceAnalyst not imported correctly  
**Fix**:
1. Test: `python -c "from intelligence.brief.llm_provider import LLMProvider; LLMProvider()"`
2. Check that model router is running
3. Verify `use_llm=True` is passed to IntelligenceAnalyst

### "Cost limits keep getting hit"
**Cause**: Default limits are too low for your batch size  
**Fix**: Update cost governance:
```sql
UPDATE llm_cost_governance SET daily_cost_limit_usd = 5.00 WHERE task_type = 'signal-scoring';
```

### "No shadow-mode data appearing"
**Cause**: `shadow_mode=True` not passed, or batch job not running  
**Fix**:
1. Verify batch job has: `enrich_and_save(..., shadow_mode=True)`
2. Check that batch job actually ran: `SELECT MAX(collected_at) FROM intelligence_events;`
3. Check logs for errors

---

## Summary: What Requires Your Involvement

| Item | Type | Complexity | Time | Block? |
|------|------|-----------|------|--------|
| 1. Run migrations | Infra | Low | 5 min | ✅ Yes |
| 2. Seed cost config | Infra | Low | 2 min | ✅ Yes |
| 3. Enable shadow-mode | Code | Low | 5 min | ✅ Yes |
| 4. Wire correlation job | Code | Low | 10 min | ⚠️ Depends |
| 5. Verify LLM access | Config | Medium | 15 min | ✅ Yes |
| 6. Setup monitoring | Ops | Medium | 20 min | ⚠️ Optional |
| 7. Configure alerts | Ops | Medium | 20 min | ⚠️ Optional |
| 8. Run Issue 15 analysis | Analysis | Low | 5 min | ⚠️ Week 3+ |
| 9. Activate Issue 16 | Code | Medium | 15 min | ⚠️ Week 4+ |
| 10. Display correlations | UI | Medium | 20 min | ⚠️ Week 2+ |
| 11. Adjust cost limits | Config | Low | 2 min | ⚠️ Optional |
| 12. Customize prompts | Code | Medium | 20 min | ⚠️ Optional |
| 13. Plan Issue 19 | Design | High | varies | ⚠️ Month 3+ |

**Total time to activation**: ~45 min (items 1–5)  
**Total time to full pipeline**: ~2–3 hours (including optional monitoring)

---

## Questions?

- **Implementation details**: See `ROADMAP_COMPLETE_SUMMARY.md`
- **Activation steps**: See `ACTIVATE_SHADOW_MODE.md`
- **Architecture**: See `intelligence/SHADOW_MODE_IMPLEMENTATION.md`
- **Code issues**: Refer to test script: `python -m intelligence.analysis.test_shadow_mode_scoring --demo`
