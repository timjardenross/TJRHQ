# Data Source Mapping — MSN-0035 Phase 2
## Operational Data Flow & Assumptions

**Date**: 2026-06-08  
**Status**: Phase 2 Day 2 Complete  
**Scope**: Mission data flow from MSN-0031 → MSN-0034 → MSN-0035

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    MISSION DATA FLOW                          │
└──────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────┐
│   MSN-0031: Mission Registry        │
│   Source of Truth for Missions      │
├─────────────────────────────────────┤
│ Database: SQLite (mission_registry.db)
│ Tables:   missions, statuses, priorities
│ API:      GET /missions/*
│ Data:     Mission definitions, status, priorities
│           dependencies, blockers, assignments
└────────────────────┬────────────────┘
                     │
                     │ (feeds mission data)
                     │
                     ↓
┌─────────────────────────────────────┐
│   MSN-0034: Number One              │
│   Coordination Engine               │
├─────────────────────────────────────┤
│ Code:     /core/coordination/number_one.py
│ Input:    Mission data from MSN-0031
│ Processing: Rule-based coordination
│ Output:   - Daily brief
│          - Work queue
│          - Escalations
│          - Follow-ups
│          - Blocker analysis
└────────────────────┬────────────────┘
                     │
                     │ (exports via exporter script)
                     │
                     ↓
┌──────────────────────────────────────┐
│   JSON Output Files                  │
│   /core/coordination/outputs/        │
├──────────────────────────────────────┤
│ Files:  - daily_brief.json
│        - work_queue.json
│        - escalations.json
│        - follow_ups.json (future)
│        - blockers.json (future)
│ Format: JSON (Number One outputs)
│ TTL:    Manual regeneration on demand
└────────────────────┬─────────────────┘
                     │
                     │ (read via adapter)
                     │
                     ↓
┌──────────────────────────────────────┐
│   NumberOneAdapter (JavaScript)      │
│   /backend/connectors/               │
├──────────────────────────────────────┤
│ Logic:  - Read JSON files
│        - Transform to API format
│        - Fallback to mock if missing
│ Output: Coordination data in API format
└────────────────────┬─────────────────┘
                     │
                     │ (consumed by API)
                     │
                     ↓
┌──────────────────────────────────────┐
│   MSN-0035: Command Centre           │
│   Phase 2 Backend API                │
├──────────────────────────────────────┤
│ Endpoints: /api/v1/coordination/*
│ Data:      Live coordination outputs
│ Cache:     30 seconds
│ Fallback:  Mock data if files missing
└────────────────────┬─────────────────┘
                     │
                     │ (consumed by frontend)
                     │
                     ↓
┌──────────────────────────────────────┐
│   Dashy Dashboard                    │
│   Command Centre Frontend            │
├──────────────────────────────────────┤
│ Widget: Coordination Brief
│ Widget: Work Queue
│ Widget: Escalations
│ Update: Every 30 seconds (cached)
│ Real-time: Phase 3 (WebSockets)
└──────────────────────────────────────┘
```

---

## Data Assumptions

### 1. Mission Data Source ✅
**Assumption**: MSN-0031 Mission Registry is the single source of truth for mission data.

**Implication**:
- Number One consumes missions from MSN-0031
- MSN-0035 does NOT store missions
- MSN-0035 does NOT duplicate mission data
- All mission changes flow through MSN-0031

**Implementation**:
- Number One exporter takes missions as input
- Can read from MSN-0031 API (future Phase 2)
- Currently accepts missions as JSON file or object

### 2. Number One as Coordinator ✅
**Assumption**: MSN-0034 Number One is the authoritative source for coordination decisions.

**Implication**:
- Number One owns work queue prioritization
- Number One owns escalation logic
- Number One owns specialist recommendations
- MSN-0035 presents Number One's output, doesn't duplicate logic

**Implementation**:
- API returns Number One outputs directly
- No coordination logic in MSN-0035
- No duplicate decision-making in Phase 2

### 3. Export-Based Integration ✅
**Assumption**: Phase 2 uses file-based export for Number One integration (manual).

**Implication**:
- JSON files are the integration point
- No direct Python-to-JavaScript bridge
- No message queues needed
- No database duplication

**Implementation**:
- `number_one_exporter.py` generates JSON files
- Backend reads JSON files via adapter
- Manual export for Phase 2 (on-demand)
- Automation deferred to Phase 3+

### 4. No Automated Export ✅
**Assumption**: Phase 2 does NOT implement automated export scheduling.

**Implication**:
- JSON files must be manually regenerated
- Export happens on-demand
- Dashboard shows stale data until re-export
- No daemon processes or cron jobs yet

**Implementation**:
- Export script available: `python3 number_one_exporter.py --export-sample`
- Can be integrated into CI/CD later
- Automation design documented for Phase 3

### 5. Mock Fallback Strategy ✅
**Assumption**: Phase 2 always falls back to realistic mock data if JSON files unavailable.

**Implication**:
- Dashboard never shows "data unavailable"
- Mock data is realistic and updated
- Mock data includes all fields
- API indicates when using fallback

**Implementation**:
- NumberOneAdapter has comprehensive mock templates
- 3-tier fallback: cache → stale → placeholder
- Data source indicator in responses

---

## Data Dependencies

### MSN-0031 → MSN-0034 (Mission Data Feed)

**What MSN-0035 assumes about this dependency**:
- MSN-0031 provides mission catalog
- Missions have: id, title, status, priority, domain, blockers, dependencies
- MSN-0034 consumes and coordinates
- MSN-0035 does NOT access MSN-0031 directly

**Current State**:
- MSN-0031 exists and operational
- Number One exporter can read from MSN-0031
- Phase 2 uses file-based export as bridge

**Future State (Phase 3+)**:
- Could call MSN-0031 API directly
- Could implement real-time mission subscription
- Could eliminate JSON file export

### MSN-0034 → MSN-0035 (Coordination Output)

**What MSN-0035 provides**:
- NumberOneAdapter for data transformation
- Mock fallback for resilience
- API contracts for consumption
- Status endpoint for debugging

**Current State**:
- Manual export via `number_one_exporter.py`
- JSON files as integration point
- No automation yet

**Future State (Phase 3+)**:
- Could implement automated export
- Could add event-driven triggers
- Could implement real-time WebSocket push

---

## Export Workflow (Manual)

### How to Export Number One Data

```bash
# Step 1: Generate sample coordination data
cd /Users/timjarden-ross/Documents/GitHub/USSTJROS/core/coordination
python3 number_one_exporter.py --export-sample

# Output: Creates JSON files in outputs/
# - daily_brief.json
# - work_queue.json
# - escalations.json

# Step 2: Verify files created
ls -la outputs/
```

### How to Export from Mission Data

```bash
# If you have a missions.json file with mission definitions:
python3 number_one_exporter.py --missions missions.json

# Reads missions, runs through Number One engine, exports outputs
```

### How Phase 2 Consumes Exported Data

```javascript
// Backend receives request
GET /api/v1/coordination/brief

// NumberOneAdapter.getDailyBrief() is called
// 1. Checks cache (30s TTL)
// 2. If cache miss:
//    - Tries to read outputs/daily_brief.json
//    - If file exists: transforms and returns
//    - If file missing: uses mock data
// 3. Caches result for 30s
// 4. Returns with dataSource indicator
```

---

## Future Automation (Phase 3+)

### Options for Automated Export

**Option 1: Scheduled Export**
```bash
# Add cron job to export every 5 minutes
*/5 * * * * cd /path/to/coordination && python3 number_one_exporter.py --export-sample
```

**Option 2: Event-Driven**
```python
# When mission status changes in MSN-0031:
# 1. Trigger Number One engine
# 2. Run exporter
# 3. Regenerate JSON files
```

**Option 3: Real-Time API**
```javascript
// Skip JSON files entirely (Phase 3+)
// Number One → Direct JavaScript bridge
// Real-time WebSocket push to dashboard
```

**Option 4: Daemon Process**
```python
# Background Python daemon
# 1. Watches MSN-0031 for changes
# 2. Auto-exports Number One outputs
# 3. Updates JSON files on change
```

---

## Phase 2 Data Contract

### What MSN-0035 Guarantees

✅ **Consume**: JSON exports from Number One
✅ **Transform**: Number One format → API format
✅ **Fallback**: Mock data if exports unavailable
✅ **Cache**: 30-second TTL for performance
✅ **Status**: Indicator of data source
✅ **No Duplication**: Don't store missions or run coordination logic

### What MSN-0035 Does NOT Do

❌ **Does NOT** access MSN-0031 directly
❌ **Does NOT** run Number One logic
❌ **Does NOT** store missions locally
❌ **Does NOT** implement automated export
❌ **Does NOT** have database for coordination
❌ **Does NOT** duplicate mission data

### What Phase 2 Provides to MSN-0035

- NumberOneAdapter for data transformation
- Mock fallback templates
- API contracts for coordination data
- Status endpoint for debugging
- Test coverage (42 tests)

---

## Unresolved Questions & Recommendations

### Q: How do missions flow into Number One?
**Answer**: Currently via `--missions` flag to exporter
**Recommendation**: Phase 3 should define automated mission feed from MSN-0031

### Q: How often is coordination data refreshed?
**Answer**: Manually (must run exporter script)
**Recommendation**: Phase 3 should implement automated export (cron, event-driven, or API polling)

### Q: What if JSON files get out of sync with MSN-0031?
**Answer**: Fallback to mock data; data source indicator shows fallback in use
**Recommendation**: Phase 3 should implement consistency checking or real-time updates

### Q: Can Phase 2 talk directly to Number One Python?
**Answer**: Not in current design (JSON file bridge is intentional)
**Recommendation**: Phase 3 could implement direct bridge if performance needs it

### Q: Should WebSockets for real-time push happen in Phase 3?
**Answer**: Yes (recommended but deferred)
**Recommendation**: Phase 3 Day 3 should implement WebSocket server for live updates

---

## Testing & Verification

### Verify Data Flow

```bash
# 1. Export Number One data
python3 number_one_exporter.py --export-sample

# 2. Check JSON files created
ls -la /core/coordination/outputs/

# 3. Start backend
cd /command-centre/backend
npm start

# 4. Verify API returns data
curl http://localhost:5000/api/v1/coordination/brief

# 5. Check data source indicator
# Response should include: "dataSource": "from-number-one"
```

### Verify Fallback

```bash
# 1. Delete JSON files
rm /core/coordination/outputs/*.json

# 2. Call API again
curl http://localhost:5000/api/v1/coordination/brief

# 3. Should still return data with:
# "dataSource": "from-mock-fallback"
```

### Run Integration Tests

```bash
npm test -- coordination-integration.test.js

# Should see: 42 tests passing
```

---

## Conclusion

**Phase 2 Day 2** establishes clean data flow from MSN-0034 Number One to MSN-0035 Command Centre via:
1. Manual export of Number One outputs to JSON
2. NumberOneAdapter for transformation
3. Mock fallback for resilience
4. Clean API contract for consumption

**This design**:
- Maintains MSN-0031 as single source of truth
- Respects MSN-0034 as coordination authority
- Adds no new database or duplication
- Provides graceful fallback
- Clearly marks all future automation points

**Phase 3 can enhance** by automating export, adding real-time updates, or implementing direct bridges without changing Phase 2 assumptions.

---

**Status**: Data flow assumptions documented and implemented ✅  
**Phase 2**: Complete with clean architecture  
**Phase 3**: Ready for automation and real-time enhancements
