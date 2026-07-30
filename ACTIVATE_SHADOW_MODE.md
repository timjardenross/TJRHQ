# Shadow-Mode Activation — Quick Start

## 3-Step Activation

### 1. Apply Database Migration (2 min)

```bash
cd /Volumes/SSK\ SSD/GitHub/TJRHQ
supabase db push
```

This creates:
- New columns on `intelligence_events` (llm_score_breakdown, score_provenance, etc.)
- New table `llm_call_metrics` (every LLM call logged)
- New table `llm_cost_governance` (cost thresholds)
- New view `llm_daily_costs` (daily spend summary)

**Verify**:
```bash
psql -U postgres -d postgres -c "SELECT column_name FROM information_schema.columns WHERE table_name='intelligence_events' AND column_name LIKE 'llm_%' LIMIT 1;"
```

### 2. Seed Cost Governance Configuration (1 min)

```bash
psql -U postgres -d postgres -f intelligence/governance/seed_cost_governance.sql
```

This initializes default thresholds:
- **signal-scoring**: 500 calls/day, $0.50/day ceiling
- **brief-synthesis**: 10 calls/day, $2.00/day ceiling
- **correlation-synthesis**: 5 calls/day, $0.10/day ceiling

### 3. Enable Shadow-Mode in Batch Job (2 min)

Find where the daily intelligence batch job calls `enrich_and_save()`:

**Before**:
```python
def _daily_collection_job(self):
    # ... collection code ...
    from intelligence.ingestion.phase_a_enrichment import enrich_and_save
    enrich_and_save(events, store)  # Default: shadow_mode=False
```

**After**:
```python
def _daily_collection_job(self):
    # ... collection code ...
    from intelligence.ingestion.phase_a_enrichment import enrich_and_save
    enrich_and_save(events, store, shadow_mode=True)  # ← Enable shadow-mode
```

## Done! 🎉

Shadow-mode is now active. Starting with the next daily batch:
- Both heuristic and LLM paths run on every signal
- Both results are stored (heuristic remains authoritative)
- All calls are logged for cost tracking + Issue 15 analysis
- Daily spend is monitored via `llm_daily_costs` table

## Verify It's Working

Check logs after the next batch run:

```bash
# See heuristic vs LLM agreement
psql -U postgres -d postgres << EOF
SELECT
  COUNT(*) as total,
  SUM(CASE WHEN (score_provenance ->> 'llm_agree_with_heuristic')::boolean THEN 1 ELSE 0 END) as agree,
  ROUND(100.0 * SUM(CASE WHEN (score_provenance ->> 'llm_agree_with_heuristic')::boolean THEN 1 ELSE 0 END) / COUNT(*), 1) as agree_pct
FROM intelligence_events
WHERE score_provenance ->> 'llm_attempted' = 'true'
  AND llm_score_breakdown IS NOT NULL
  AND collected_at >= CURRENT_DATE;
EOF
```

```bash
# See daily cost
psql -U postgres -d postgres << EOF
SELECT task_type, call_count, successful_calls, failed_calls, total_cost_usd
FROM llm_daily_costs
WHERE cost_date = CURRENT_DATE;
EOF
```

## Monitoring

### Daily Cost Report (SQL)
```sql
SELECT * FROM llm_daily_costs WHERE cost_date = CURRENT_DATE;
```

### LLM Failures (SQL)
```sql
SELECT call_at, task_type, provider, failure_reason, event_id
FROM llm_call_metrics
WHERE success = false
  AND call_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
ORDER BY call_at DESC;
```

### Agreement Rate (for Issue 15 preview)
```sql
SELECT
  ROUND(100.0 * SUM(CASE WHEN (score_provenance ->> 'llm_agree_with_heuristic')::boolean THEN 1 ELSE 0 END) / COUNT(*), 1) as agree_pct
FROM intelligence_events
WHERE llm_score_breakdown IS NOT NULL
  AND collected_at >= CURRENT_DATE - INTERVAL '7 days';
```

## Rollback (if needed)

```python
# Change back to:
enrich_and_save(events, store, shadow_mode=False)
```

All shadow-mode columns remain (no data loss). Can re-enable anytime.

## Next: Issue 15 (Week 3+)

After 2+ weeks of shadow-mode data, run the Issue 15 evaluation harness to:
1. Compare heuristic vs LLM against QA decisions
2. Identify confidence band where LLM adds value
3. Recommend Issue 16 routing threshold

See `ROADMAP_IMPLEMENTATION_SUMMARY.md` for full timeline.

---

**Questions?** See `intelligence/SHADOW_MODE_IMPLEMENTATION.md` for detailed architecture & troubleshooting.
