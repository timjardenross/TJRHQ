# Shadow-Mode LLM Scoring Implementation

**Issues**: 14, 20, 21  
**Status**: Ready to activate  
**Activation Date**: 2026-07-30  

## Overview

This implementation adds three critical capabilities to the USS TJR Intelligence Platform:

1. **Issue 14: Shadow-Mode LLM Scoring** — Run heuristic and LLM paths in parallel on every signal, log both outputs, change nothing live.
2. **Issue 20: Structured Output + Disclosure** — Mark every score with its provenance (heuristic vs LLM) for audit trail.
3. **Issue 21: Cost Governance** — Monitor LLM call volume and spend, enforce daily limits, fall back to heuristic if exceeded.

Together, these enable **safe, evidence-driven AI adoption**: collect comparative data for 2+ weeks, prove LLM value via Issue 15 evaluation harness, then gradually route signals to LLM as confidence builds.

## Architecture

### Database Layer (Migration 0085)

**New columns on `intelligence_events`:**
- `llm_score_breakdown` — LLM path's 10-dimension scores
- `llm_relevance_score` — LLM path's 1.0–5.0 overall score
- `llm_risk_rating` — LLM path's HIGH/MEDIUM/LOW rating
- `llm_provider` — Which model generated it (mistral, gemini, ollama)
- `score_method` — Disclosure: 'heuristic' | 'llm' | 'blended' (currently always 'heuristic')
- `score_provenance` — JSON metadata: when each path ran, whether they agree, version

**New tables:**
- `llm_call_metrics` — Audit trail of every LLM call (tokens, latency, cost, success)
- `llm_cost_governance` — Per-task-type cost thresholds and policies
- `llm_daily_costs` (materialized view) — Daily spend summary by task type

### Code Layer

**New modules:**
- `intelligence/governance/llm_cost_governance.py` — Cost checker + call logger
- Updated `intelligence/analysis/intelligence_analyst.py` — Added `score_dual_path()` method + shadow-mode support
- Updated `intelligence/ingestion/phase_a_enrichment.py` — Support for shadow-mode parameter
- Updated `intelligence/models.py` — Added `DualPathScoringResult` dataclass

**Updated docs:**
- `specialists/knowledge-packs/Intelligence-Brief-Standard.md` — Provenance section + field definitions

## Activation Steps

### 1. Apply Database Migration

```bash
# This creates the new columns and tables
supabase db push  # or manually run 0085_shadow_mode_llm_scoring.sql
```

### 2. Seed Cost Governance Configuration

```bash
# Initialize default thresholds for signal-scoring, brief-synthesis, etc.
psql -d supabase_db < intelligence/governance/seed_cost_governance.sql
```

Or via Supabase dashboard:
```sql
INSERT INTO llm_cost_governance (task_type, daily_call_limit, daily_cost_limit_usd, throttle_on_exceed, enabled)
VALUES (
  'signal-scoring',
  500,                      -- up to 500 calls/day (normal: ~50)
  0.50,                     -- up to $0.50/day
  'fall_back_to_heuristic', -- exceed → fall back to heuristic
  true
);
```

### 3. Enable Shadow-Mode in Batch Job

Edit `intelligence/scheduler.py` (or wherever daily batch job is called):

**Before:**
```python
def _daily_collection_job(self):
    # ... collection logic ...
    from intelligence.ingestion.phase_a_enrichment import enrich_and_save
    enrich_and_save(events, store)  # Uses default: shadow_mode=False
```

**After:**
```python
def _daily_collection_job(self):
    # ... collection logic ...
    from intelligence.ingestion.phase_a_enrichment import enrich_and_save
    enrich_and_save(events, store, shadow_mode=True)  # Issue 14: collect dual-path data
```

### 4. Verify & Monitor

Run the test script:
```bash
python -m intelligence.analysis.test_shadow_mode_scoring --demo
```

Check that the database has the new columns:
```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'intelligence_events'
AND column_name IN ('llm_score_breakdown', 'score_provenance');
```

Monitor cost via:
```sql
SELECT * FROM llm_daily_costs WHERE cost_date = CURRENT_DATE;
```

## How It Works

### Scoring Flow (Shadow-Mode)

```
Signal → IntelligenceAnalyst.score_dual_path()
  ├─ Run heuristic path (fast, always succeeds)
  │  └─ Returns SignalScore {score_breakdown, total_score, risk_rating, method='heuristic'}
  │
  ├─ Cost check: can_call_llm('signal-scoring') → allowed?
  │
  ├─ If allowed: Fire LLM call (non-blocking timeout, graceful fail)
  │  ├─ Parse JSON output
  │  ├─ Log call to llm_call_metrics (tokens, latency, cost, success)
  │  └─ Return SignalScore or None
  │
  └─ Compare both paths
     ├─ Do they agree on risk_rating?
     ├─ Build provenance metadata
     └─ Return DualPathScoringResult {heuristic, llm, agree, provenance}
            ↓
        Phase A persists both:
        ├─ score_breakdown (heuristic) — authoritative
        ├─ llm_score_breakdown (LLM) — shadow, for comparison
        ├─ score_method: 'heuristic' — disclosure (not yet using LLM)
        └─ score_provenance — full trail {heuristic_scored_at, llm_scored_at, agree, ...}
```

### Cost Governance Flow

```
Before firing LLM call:
  LLMCostGovernance.can_call_llm('signal-scoring')
    ├─ Fetch config: daily_call_limit=500, daily_cost_limit_usd=0.50
    ├─ Query llm_daily_costs view: today's count + spend
    ├─ Check: have we hit limits?
    │  ├─ If yes and throttle_on_exceed='fall_back_to_heuristic': return allowed=False
    │  ├─ If yes and throttle_on_exceed='alert': log warning, return allowed=True
    │  └─ If no: return allowed=True
    └─ Return CostCheckResult {allowed, reason, daily_calls_so_far, ...}

After LLM call (success or fail):
  LLMCostGovernance.log_call(
    task_type='signal-scoring',
    provider='mistral',
    input_tokens=500,
    output_tokens=200,
    success=True,
    event_id='xyz',
  )
    └─ Insert row to llm_call_metrics
       (materialized view llm_daily_costs auto-refreshes hourly)
```

## Data for Issue 15 (Evaluation Harness)

After 2+ weeks of shadow-mode, the following data will exist:

**For every signal:**
- Heuristic score (score_breakdown, relevance_score, risk_rating)
- LLM score (llm_score_breakdown, llm_relevance_score, llm_risk_rating)
- Agreement status (score_provenance.llm_agree_with_heuristic)

**Linked to ground truth:**
- Human QA decisions (brief_qa_agent's qa_pass/reject history)
- Final inclusion in brief (brief_id)

**Issue 15 script will:**
1. Pull signals with both heuristic + LLM scores
2. Cross-reference with human QA decisions
3. Compute agreement rates (overall + by confidence band)
4. Identify ambiguous band where LLM adds value
5. Recommend Issue 16 threshold + routing policy

## Configuration

### Cost Governance

Edit `intelligence/governance/seed_cost_governance.sql` to adjust thresholds:

```sql
UPDATE llm_cost_governance
SET
  daily_call_limit = 1000,        -- More calls
  daily_cost_limit_usd = 2.00,    -- Higher budget
  throttle_on_exceed = 'alert'    -- Warn but don't block
WHERE task_type = 'signal-scoring';
```

### Shadow-Mode Tuning

For fine-grained control, pass custom parameters to `enrich_and_save()`:

```python
from intelligence.governance import LLMCostGovernance
from intelligence.analysis.intelligence_analyst import IntelligenceAnalyst

cost_gov = LLMCostGovernance()  # Reads from llm_cost_governance table
analyst = IntelligenceAnalyst(
    use_llm=True,
    shadow_mode=True,
    cost_governor=cost_gov,
)

enrich_and_save(events, store, analyst=analyst, shadow_mode=True)
```

## Monitoring & Alerts

### Daily Cost Report

```sql
SELECT
  task_type,
  call_count,
  successful_calls,
  failed_calls,
  total_cost_usd,
  last_call_at
FROM llm_daily_costs
WHERE cost_date = CURRENT_DATE;
```

### LLM Call Failures

```sql
SELECT
  call_at,
  task_type,
  provider,
  failure_reason,
  event_id
FROM llm_call_metrics
WHERE success = false
  AND call_at > CURRENT_TIMESTAMP - INTERVAL '1 day'
ORDER BY call_at DESC;
```

### Agreement Statistics (Preview of Issue 15 work)

```sql
SELECT
  COUNT(*) as total_shadow_mode_calls,
  SUM(CASE WHEN (score_provenance ->> 'llm_agree_with_heuristic')::boolean THEN 1 ELSE 0 END) as agree_count,
  ROUND(100.0 * SUM(CASE WHEN (score_provenance ->> 'llm_agree_with_heuristic')::boolean THEN 1 ELSE 0 END) / COUNT(*), 1) as agree_percent
FROM intelligence_events
WHERE score_provenance ->> 'llm_attempted' = 'true'
  AND llm_score_breakdown IS NOT NULL
  AND collected_at > CURRENT_DATE - INTERVAL '2 weeks';
```

## Rollback Plan

If issues arise, deactivation is simple:

1. **Stop shadow-mode**: Set `shadow_mode=False` in batch job
2. **No data loss**: All dual-path columns remain (can re-enable anytime)
3. **No behavior change**: Heuristic was always authoritative anyway

## Troubleshooting

### Issue: LLM calls are timing out

**Likely cause**: Model router unreachable or overloaded.

**Fix**: Check that `intelligence/brief/llm_provider.py` can reach the model router. Cost governance will automatically log these failures.

### Issue: Cost is higher than expected

**Fix**: Check `llm_daily_costs` view:
```sql
SELECT * FROM llm_daily_costs WHERE cost_date = CURRENT_DATE;
```

If above `daily_cost_limit_usd`, the next day's calls will be throttled or blocked (per `throttle_on_exceed` policy).

### Issue: Shadow-mode not capturing LLM scores

**Likely cause**: `score_dual_path()` not being called (check if `shadow_mode=True` is passed to `enrich_and_save()`).

**Fix**: Verify the batch job calls:
```python
enrich_and_save(..., shadow_mode=True)
```

And that `use_llm=True` is set on the analyst.

## Next Steps

1. **Weeks 1–2**: Shadow-mode live, collect dual-path data
2. **Week 3**: Run Issue 15 evaluation harness analysis
3. **Week 4**: Decide on Issue 16 routing threshold based on Issue 15 results
4. **Week 5+**: Implement Issue 16 (selective augmentation) if Issue 15 shows LLM adds value

## References

- **Issue 14**: `https://github.com/TJRHQ/USS-TJR-Platform/issues/14`
- **Issue 15**: `https://github.com/TJRHQ/USS-TJR-Platform/issues/15`
- **Issue 20**: `https://github.com/TJRHQ/USS-TJR-Platform/issues/20`
- **Issue 21**: `https://github.com/TJRHQ/USS-TJR-Platform/issues/21`
- **Brief Standard**: `specialists/knowledge-packs/Intelligence-Brief-Standard.md`
- **Cost Governance**: `intelligence/governance/llm_cost_governance.py`
- **Test Script**: `python -m intelligence.analysis.test_shadow_mode_scoring --demo`
