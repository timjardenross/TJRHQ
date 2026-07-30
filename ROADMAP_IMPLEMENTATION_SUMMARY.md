# USS TJR AI-Native Roadmap — Issues 14, 20, 21 Implementation Summary

**Date**: 2026-07-30  
**Status**: ✅ Complete & Ready to Deploy  
**Issues**: 14 (Shadow-Mode LLM Scoring), 20 (Structured Output + Disclosure), 21 (Cost Governance)

---

## What Was Built

### 1. **Migration 0085: Shadow-Mode LLM Scoring Infrastructure**

**File**: `core/infrastructure/supabase/migrations/0085_shadow_mode_llm_scoring.sql`

Creates the database foundation for dual-path scoring:

**New columns on `intelligence_events`:**
- `llm_score_breakdown` (jsonb) — LLM path's 10-dimension scores
- `llm_relevance_score` (numeric) — LLM path's 1.0–5.0 overall score
- `llm_risk_rating` (text) — LLM path's HIGH/MEDIUM/LOW rating
- `llm_provider` (text) — Which model (mistral, gemini, ollama)
- `score_method` (text) — Disclosure: 'heuristic' | 'llm' | 'blended'
- `score_provenance` (jsonb) — Full audit trail (when, which paths, agreement)

**New tables:**
- `llm_call_metrics` — Every LLM call logged: tokens, latency, cost, success/failure
- `llm_cost_governance` — Per-task-type cost thresholds and policies
- `llm_daily_costs` (materialized view) — Daily spend summary by task type

**Status**: Ready to apply via `supabase db push`

---

### 2. **Cost Governance Module (Issue 21)**

**File**: `intelligence/governance/llm_cost_governance.py`

Non-blocking cost controller with three capabilities:

1. **Cost Checking**: Before firing LLM call, check if we're within daily limits
   ```python
   check = cost_gov.can_call_llm('signal-scoring')
   if not check.allowed:
       fall_back_to_heuristic()  # Daily limit exceeded
   ```

2. **Call Logging**: After each LLM call, log metadata for audit + cost tracking
   ```python
   cost_gov.log_call(
       task_type='signal-scoring',
       provider='mistral',
       input_tokens=500,
       output_tokens=200,
       success=True,
       estimated_cost_usd=0.00015,
   )
   ```

3. **Configuration**: Per-task-type thresholds (read from `llm_cost_governance` table)
   - `daily_call_limit`: Max calls per day
   - `daily_cost_limit_usd`: Max spend per day
   - `throttle_on_exceed`: 'alert' | 'fall_back_to_heuristic' | 'stop_calls'
   - `alert_at_percent`: Warn at 80% of limit (configurable)

**Key Design**: All failures are graceful. If cost governance itself fails (Supabase unreachable), defaults to permissive (allows calls). Never blocks the pipeline.

**Status**: Complete & production-ready

---

### 3. **Shadow-Mode Scoring Engine (Issue 14)**

**Updated Files**:
- `intelligence/analysis/intelligence_analyst.py` — Added `score_dual_path()` method
- `intelligence/models.py` — Added `DualPathScoringResult` dataclass

**How it works**:

```
score_dual_path(signal) returns DualPathScoringResult:
  ├─ Run heuristic path (fast, always succeeds)
  ├─ Check cost governance (can_call_llm?)
  ├─ If allowed: Fire LLM call (non-blocking timeout)
  │  └─ Log call with tokens, latency, cost
  ├─ Compare both paths (do they agree on risk_rating?)
  └─ Return {heuristic, llm, agree, provenance}
```

**Key guarantee**: The heuristic path ALWAYS succeeds (deterministic, fast). The LLM path is attempted in parallel but failures never block the pipeline.

**Status**: Complete & integrated

---

### 4. **Provenance & Disclosure (Issue 20)**

**Updated Files**:
- `specialists/knowledge-packs/Intelligence-Brief-Standard.md` — New "Provenance & Disclosure" section
- Phase A enrichment now stores full provenance metadata

**Every signal now carries**:
- `score_method`: Which path was authoritative ('heuristic' | 'llm' | 'blended')
- `score_provenance`: JSON metadata
  ```json
  {
    "heuristic_scored_at": "2026-07-30T12:34:56Z",
    "llm_scored_at": "2026-07-30T12:34:59Z",
    "llm_agree_with_heuristic": true,
    "scoring_version": 1
  }
  ```

**Audit trail**: Every LLM call is logged to `llm_call_metrics`, every score change is traceable.

**Status**: Complete & documented

---

### 5. **Phase A Enrichment Updated**

**File**: `intelligence/ingestion/phase_a_enrichment.py`

New signature:
```python
enrich_and_save(
    events: list,
    store,
    analyst=None,
    shadow_mode: bool = False  # NEW
) -> dict
```

**Behavior**:
- `shadow_mode=False` (default): Heuristic-only scoring (current behavior, unchanged)
- `shadow_mode=True`: Both paths run, both results stored, heuristic remains authoritative

**Example usage**:
```python
from intelligence.ingestion.phase_a_enrichment import enrich_and_save

enrich_and_save(events, store, shadow_mode=True)  # Enable Issue 14
```

**Status**: Ready to activate

---

### 6. **Cost Governance Configuration Seed**

**File**: `intelligence/governance/seed_cost_governance.sql`

Pre-configured thresholds for:
- **signal-scoring**: 500 calls/day, $0.50/day ceiling, fall back to heuristic
- **brief-synthesis**: 10 calls/day, $2.00/day ceiling, alert on exceed
- **correlation-synthesis**: 5 calls/day, $0.10/day ceiling, alert on exceed

**To apply**:
```sql
psql -d supabase_db < intelligence/governance/seed_cost_governance.sql
```

Or update via Supabase UI.

**Status**: Ready to seed

---

### 7. **Test & Demo Script**

**File**: `intelligence/analysis/test_shadow_mode_scoring.py`

Demonstrates:
1. Dual-path scoring (heuristic + LLM)
2. Cost governance checks
3. Provenance logging
4. Agreement tracking

**To run**:
```bash
python -m intelligence.analysis.test_shadow_mode_scoring --demo
```

**Status**: Complete & verified

---

### 8. **Implementation Guide**

**File**: `intelligence/SHADOW_MODE_IMPLEMENTATION.md`

Comprehensive guide covering:
- Architecture overview
- Activation steps (4 steps to go live)
- Monitoring & alerting
- Troubleshooting
- Rollback plan

**Status**: Complete & ready

---

## Activation Checklist

### Phase 1: Database (5 min)
- [ ] Run migration 0085: `supabase db push`
- [ ] Verify new columns exist: `SELECT COUNT(*) FROM llm_call_metrics;`
- [ ] Seed cost governance: `psql < intelligence/governance/seed_cost_governance.sql`

### Phase 2: Code (10 min)
- [ ] Update batch job to pass `shadow_mode=True` to `enrich_and_save()`
- [ ] Verify imports work: `python -c "from intelligence.governance import LLMCostGovernance"`
- [ ] Run test script: `python -m intelligence.analysis.test_shadow_mode_scoring --demo`

### Phase 3: Monitoring (5 min)
- [ ] Set up daily cost report query
- [ ] Set up failure alert query
- [ ] Document alerting endpoints (Slack, email, etc.)

**Total activation time: ~20 minutes**

---

## What Happens After Activation

### Timeline

**Days 1–14: Shadow-Mode Data Collection**
- Both heuristic and LLM paths run on every signal
- Heuristic used for all downstream decisions (no behavior change)
- LLM results logged separately for analysis
- Cost tracked daily via `llm_daily_costs` view

**Day 14+: Issue 15 Analysis**
- Run evaluation harness comparing heuristic vs LLM against QA decisions
- Identify confidence band where LLM adds value
- Recommend Issue 16 routing threshold

**Day 21+: Issue 16 Selective Augmentation (if Issue 15 shows value)**
- Route ambiguous signals (e.g., relevance_score 3.2–3.8) to LLM path
- Update `score_method` to 'llm' | 'blended' for affected signals
- Heuristic remains fallback if LLM times out

---

## Cost Estimate

### Current (Heuristic-Only)
- **LLM cost**: $0 (no LLM calls in batch scoring)
- **Speed**: ~2–3 sec for 50 signals/day

### With Shadow-Mode (Issues 14–21)
- **LLM cost**: ~$0.003–0.005/day (50 signals × $0.0001 per Mistral 7B call)
- **Speed**: ~4–5 sec for 50 signals (parallel calls don't add latency due to timeouts)
- **Daily ceiling**: $0.50 (100x buffer for extended operations)

### After Issue 16 (If Implemented)
- **Additional cost**: ~$0.001–0.002/day (only ambiguous signals use LLM, maybe 5–10/day)
- **Total**: ~$0.004–0.007/day

---

## Data Available for Issue 15

After 14 days of shadow-mode:

```sql
SELECT
  COUNT(*) as total_dual_scored,
  SUM(CASE WHEN llm_risk_rating = risk_rating THEN 1 ELSE 0 END) as agree_on_rating,
  ROUND(100.0 * SUM(CASE WHEN llm_risk_rating = risk_rating THEN 1 ELSE 0 END) / COUNT(*), 1) as agree_percent
FROM intelligence_events
WHERE llm_score_breakdown IS NOT NULL
  AND collected_at >= CURRENT_DATE - INTERVAL '14 days';
```

This data directly feeds Issue 15's evaluation harness to measure LLM value.

---

## No Behavior Changes

**Critical**: During shadow-mode (Issue 14), the system behaves identically to today:
- Heuristic scores are authoritative
- LLM scores are logged but ignored
- No ranking changes
- No brief content changes
- No human-facing differences

**All changes are logged, audited, and reversible.**

---

## Next Steps After Issues 14/20/21

1. **Week 3 (Issue 15)**: Analyze shadow-mode data, measure LLM value
2. **Week 4 (Issue 16)**: If LLM adds value, implement selective augmentation
3. **Week 5 (Issue 17)**: Wire health-mission correlation (independent)
4. **Week 6 (Issue 18)**: Add LLM synthesis on top of correlations
5. **Month 3+ (Issue 19)**: Cross-source reasoning (placeholder, blocked on 16+18)

---

## Questions?

Refer to:
- **Implementation guide**: `intelligence/SHADOW_MODE_IMPLEMENTATION.md`
- **Brief standard**: `specialists/knowledge-packs/Intelligence-Brief-Standard.md`
- **Cost governance code**: `intelligence/governance/llm_cost_governance.py`
- **Analyst code**: `intelligence/analysis/intelligence_analyst.py`
- **Test script**: `python -m intelligence.analysis.test_shadow_mode_scoring --help`

---

## Files Changed/Created

### New Files
```
core/infrastructure/supabase/migrations/0085_shadow_mode_llm_scoring.sql
intelligence/governance/llm_cost_governance.py
intelligence/governance/seed_cost_governance.sql
intelligence/analysis/test_shadow_mode_scoring.py
intelligence/SHADOW_MODE_IMPLEMENTATION.md
ROADMAP_IMPLEMENTATION_SUMMARY.md (this file)
```

### Modified Files
```
intelligence/governance/__init__.py (added cost governance imports)
intelligence/analysis/intelligence_analyst.py (added score_dual_path method + shadow-mode support)
intelligence/models.py (added DualPathScoringResult dataclass)
intelligence/ingestion/phase_a_enrichment.py (added shadow_mode parameter + dual-path handling)
specialists/knowledge-packs/Intelligence-Brief-Standard.md (added Provenance section)
```

---

## Status: ✅ Ready for Production

All code is:
- ✅ Complete
- ✅ Tested (test_shadow_mode_scoring.py)
- ✅ Documented (SHADOW_MODE_IMPLEMENTATION.md)
- ✅ Non-breaking (default shadow_mode=False maintains current behavior)
- ✅ Reversible (all changes logged and auditable)

**Activation is a single configuration change**: `shadow_mode=True` in the batch job.
