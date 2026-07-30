# Intelligence Workbench — Implementation Complete

**Status:** Phase 1B Complete, Phase 1C Pending  
**Last Updated:** 2026-07-30  
**Blocker:** Phase 1C classifier + health synthesis data pipeline (TBD scope)

---

## What's Implemented ✓

### Frontend UI
- ✓ Domain toggle (Operational Signals ↔ Health Intelligence)
- ✓ KPI cards with real-time updates
- ✓ Hot incidents card with risk-based sorting
- ✓ Briefs card with approval status tracking
- ✓ Health insights card with source articles
- ✓ Health events card with event type filtering
- ✓ Commit/discard actions for health insights
- ✓ Error banner with fallback UI
- ✓ Accessibility support (keyboard navigation, ARIA labels)
- ✓ Real-time subscription to intelligence_events
- ✓ Phase 1C classifier dashboard (placeholder)

### Backend API Routes

#### `/api/intelligence-workbench?domain=[operational|health]`
**Status:** ✓ Implemented and improved

Operational mode:
- Queries `intelligence_briefs` for pending approval (limit 20)
- Queries `intelligence_events` for 7-day hot signals with:
  - Confidence >= 60 filter (critical for data quality)
  - CVE/CWE exclusion (not operational signals)
  - Suppressed = false filter
  - Ranked by rank_score DESC
- Calculates KPIs:
  - signals_7d: 7-day high-confidence signal count
  - briefs_pending: non-PUBLISHED briefs count
  - red_active: RED-level incidents count

Health mode:
- Queries `health_insights` with joined `health_source_articles`
- Properly populates source_articles array for UI rendering
- Queries `health_events` for 30-day history (limit 20)
- Queries `analytics_health_daily` for KPI metrics (last 7 days)
- Calculates KPIs:
  - capacity_score: physical_capacity from latest daily metric
  - sleep_hours: sleep duration from latest daily metric
  - pain_level: pain_score from latest daily metric

#### `/api/intelligence-workbench/brief?id=<brief_id>`
**Status:** ✓ Complete — read-only brief detail with linked signals and audit trail

#### `/api/intelligence-workbench/action`
**Status:** ✓ Complete — governance action bridge (signal scoring, verification, escalation)

#### `/api/health-memory`
**Status:** ✓ Complete — commit/discard workflow for health insights
- POST with decision: "commit" or "discard"
- Updates `health_insights.committed_to_memory` and timestamps
- Proper error handling and response payloads

### Database Schema

#### Migration 0091: Intelligence Workbench Phase B
- ✓ Added `source_governed` to `core_events` for filtering
- ✓ Added all required columns to `health_insights`:
  - source_articles (jsonb)
  - committed_to_memory (boolean)
  - committed_at (timestamptz)
  - reviewed_at (timestamptz)
  - overall_status (text: OK|CAUTION|ALERT)
- ✓ Added `confidence_level` to `intelligence_events`
- ✓ Created `health_source_articles` junction table
- ✓ Created/verified `analytics_health_daily` view

#### Existing Tables
- ✓ `intelligence_events`: Full Phase A workflow columns
- ✓ `intelligence_briefs`: Approval workflow + signal_ids
- ✓ `intelligence_source_registry`: terms_reviewed governance gate
- ✓ `health_events`: Event logging with type/source tracking
- ✓ `health_daily_logs`: Daily check-in records
- ✓ `captain_readiness_history`: Readiness snapshots for metrics

### Testing
- ✓ Unit tests: Operational signals filtering (confidence, CVE/CWE, KPI calculations)
- ✓ Unit tests: Health insights KPI calculations and data transformation
- ✓ Unit tests: Commit/discard workflow logic

### Documentation
- ✓ Implementation checklist (this file)
- ✓ API route documentation
- ✓ Database schema documentation

---

## What Needs Manual Verification

### Pre-Deployment Checks

1. **Database Backfill**
   - [ ] Apply migration 0091 to production Supabase
   - [ ] Verify `source_governed` column exists on `core_events`
   - [ ] Verify all health_insights columns exist and are nullable

2. **Data Quality Audit**
   - [ ] Check `intelligence_source_registry.terms_reviewed` flags
   - [ ] Verify AWS Health Dashboard, GCP Status, Azure Status are marked `true`
   - [ ] Verify Entertainment News, Weather, General News are marked `false`
   - [ ] Verify confidence scores are populated on intelligence_events

3. **RLS Policies**
   - [ ] Authenticated users can read `intelligence_briefs`
   - [ ] Authenticated users can read `intelligence_events`
   - [ ] Authenticated users can read/write `health_insights`
   - [ ] Authenticated users can read/write `health_source_articles`
   - [ ] Service role bypasses for admin operations

4. **Real-time Subscriptions**
   - [ ] PostgREST realtime enabled for `intelligence_events`
   - [ ] Test subscription: open workbench, add signal to intelligence_events, verify UI updates

5. **API Response Validation**
   - [ ] GET /api/intelligence-workbench?domain=operational returns valid OperationalPayload
   - [ ] GET /api/intelligence-workbench?domain=health returns valid HealthPayload
   - [ ] All field types match TypeScript definitions
   - [ ] KPI numbers match SQL counts in database

### Manual Testing Plan

1. **Operational Mode**
   - [ ] Toggle to "Operational Signals" tab
   - [ ] Verify KPI cards show correct counts
   - [ ] Verify "Hot incidents" populated from last 7 days
   - [ ] Verify RED incidents highlighted in red
   - [ ] Click "Review Brief" link, navigates to /intelligence-workbench/brief/{id}
   - [ ] Verify brief detail shows linked signals
   - [ ] Real-time: Add new signal to DB, verify appears in UI within 5 seconds
   - [ ] Verify error banner if API fails

2. **Health Mode**
   - [ ] Toggle to "Health Intelligence" tab
   - [ ] Verify KPI cards show capacity, sleep, pain scores
   - [ ] Verify "Weekly synthesis" card populated with insights
   - [ ] Verify source articles render with links
   - [ ] Click "Commit" on insight, verify button state changes
   - [ ] Click "Discard" on insight, verify it disappears on next reload
   - [ ] Verify "Recent health events" populated
   - [ ] Verify error banner if API fails

3. **Accessibility**
   - [ ] Tab navigation works between domain toggle and content
   - [ ] ARIA labels present on toggle
   - [ ] Keyboard can activate buttons
   - [ ] Focus visible on interactive elements
   - [ ] Screen reader announces domain toggle correctly

---

## What's Blocked (Phase 1C)

### Classifier & Synthesis
- [ ] Health insights classifier (scope TBD)
- [ ] Source article extraction from wellness sources
- [ ] Daily metrics computation (Phase 1C scope)
- [ ] Deterministic findings extraction

**Why Blocked:** Phase 1C classifier outputs not yet available. Workbench has placeholders for these:
- `health_insights.llm_narrative` (placeholder: NULL)
- `health_insights.deterministic_findings` (placeholder: NULL)
- `analytics_health_daily.overall_note` (placeholder: NULL)

**Next Steps:** Once Phase 1C classifier is ready:
1. Backfill classifier outputs into health_insights
2. Populate analytics_health_daily from classifier
3. Test health mode with real synthesis data
4. Remove placeholder UI

---

## Deployment Checklist

- [ ] Migration 0091 applied to production
- [ ] RLS policies verified
- [ ] Data quality audit passed
- [ ] Unit tests pass locally
- [ ] Manual testing completed (operational mode)
- [ ] Manual testing completed (health mode)
- [ ] Accessibility tested
- [ ] Error scenarios tested
- [ ] Real-time subscription tested
- [ ] API response payloads validated
- [ ] Documentation updated
- [ ] Team trained on workbench UI/workflow
- [ ] Monitoring alerts set for API errors

---

## Operational Runbook

### Monitor in Production
- Watch API error rate: `/api/intelligence-workbench` should have <1% 5xx errors
- Watch query performance: intelligence_events queries should complete in <500ms
- Watch real-time latency: new signals should appear in UI within 5 seconds
- Watch database connections: Supabase connection pool should not exhaust

### Troubleshooting

**Operational signals not appearing:**
1. Check intelligence_events table: `SELECT COUNT(*) FROM intelligence_events WHERE confidence >= 60 AND suppressed = false AND collected_at >= NOW() - interval '7 days'`
2. Check source_registry: Are sources with relevant signals marked as active?
3. Check confidence scores: Are new events getting populated with confidence >= 60?

**Health insights empty:**
1. Check health_insights table: `SELECT COUNT(*) FROM health_insights WHERE period_start >= NOW() - interval '7 days'`
2. Check health_source_articles: `SELECT COUNT(*) FROM health_source_articles`
3. Phase 1C blocker: Are classifier outputs available?

**Real-time not updating:**
1. Check Supabase PostgREST status
2. Check browser console for WebSocket errors
3. Try manual refresh with domain toggle

**Commit/discard not working:**
1. Check `/api/health-memory` response status
2. Verify authenticated user session
3. Check health_insights update permissions (RLS policy)

---

## Sign-Off Criteria

Workbench is production-ready when all of the above manual verification checks pass:

- ✓ UI renders without errors
- ✓ Operational mode: signals visible, KPIs accurate, briefs linked
- ✓ Health mode: insights visible, source articles render, commit/discard work
- ✓ Real-time subscriptions working
- ✓ Error scenarios handled gracefully
- ✓ Accessibility verified
- ✓ RLS policies correct
- ✓ Database queries performant
- ✓ All team members trained

---

## Future Work (Phase 1C+)

1. Classifier integration: health insights synthesis
2. Source article extraction: automated from wellness content sources
3. Daily metrics computation: capacity/sleep/pain aggregations
4. Advanced analytics: trend detection, anomaly alerts
5. Memory integration: committed insights surface in other workbenches
6. Briefing generation: automated briefs from health insights
