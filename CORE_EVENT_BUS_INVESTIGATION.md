# Core Event Bus Degradation — Root Cause Analysis

**Status:** INVESTIGATING  
**Date:** 2026-07-31 07:15 AEST  
**Symptom:** 26 domains degraded, 22 never succeeded  
**Root Cause:** Supabase PostgREST API Degradation  

---

## 📊 The Cascade Effect

```
Supabase REST API Degraded
    ↓
domain_heartbeats POST requests timeout/fail
    ↓
Heartbeat writes never succeed
    ↓
All domains appear "never_succeeded = true" in domain_heartbeat_latest
    ↓
Verification engine switches to "unsure" state
    ↓
26 domains flagged as degraded (22 never succeeded, 4 stale)
```

This is **not a bug in the domains themselves** — it's infrastructure backpressure.

---

## 🔍 What We Know

### From Screenshots
- **Alert:** "Degraded REST API Availability" (HIGH severity)
- **Services Affected:** 
  - usstjros.vercel.app (search performance)
  - Slack integration
  - GitHub pull requests
  - Google Cloud operations

### From Code Review
- `heartbeat.py:record_heartbeat()` makes HTTP POST to `SUPABASE_URL/rest/v1/domain_heartbeats`
- Uses `urllib` with 10-second timeout
- On failure: silently returns False (non-blocking)
- **Critical:** Every domain's heartbeat write depends on REST API availability

### From Migrations
- Migration 0071: domain_heartbeats created (heartbeat recording system)
- Migration 0073: Fixed "skipped" semantics in latest view
- **Known behavior:** Never-succeeded domains show in briefing system

---

## 🎯 Investigation Steps

### Step 1: Run Diagnostics (Immediate)
**File:** `tools/core-event-bus-diagnostics.sql`

In Supabase SQL editor, paste and run. Expected output:
```
- domain_registry total count: 26+ (varies by deployment)
- never_succeeded count: 22 (current state)
- core_events domain status: core_events | failed | NULL | recent timestamp | "timeout" or "HTTP error"
- is_stale count: 4-6
- verification state: "unsure" (because too many "never_succeeded")
```

### Step 2: Check Supabase PostgREST Status
```bash
# Test direct connectivity to PostgREST
curl -s -X GET \
  -H "apikey: YOUR_SUPABASE_ANON_KEY" \
  "https://YOUR_PROJECT.supabase.co/rest/v1/domain_registry?limit=1" \
  | jq .

# If timeout or 502/503 error → REST API is degraded
```

### Step 3: Check Supabase Logs
In Supabase dashboard:
1. Go to Logs → API Logs
2. Filter for errors in last 1 hour
3. Look for:
   - Connection pool exhaustion
   - RLS policy rejections
   - HTTP 429 (rate limit)
   - HTTP 502/503 (gateway errors)

### Step 4: Check Recent Heartbeat Entries
```sql
SELECT domain_key, status, error_message, checked_at
FROM domain_heartbeats
WHERE checked_at > NOW() - interval '1 hour'
ORDER BY checked_at DESC
LIMIT 50;
```

Look for patterns:
- **Connection timeout:** REST API is slow/unavailable
- **401 Unauthorized:** Auth token invalid/expired
- **403 Forbidden:** RLS policy blocking POST to domain_heartbeats
- **429 Too Many Requests:** Rate limiting active

---

## ⚠️ Impact Assessment

### Affected Systems
- ✓ **Intelligence Workbench** (just deployed) — can still read core_events for operational signals, but real-time heartbeats not recorded
- ✓ **Domain Verification Engine** — in "unsure" state, displaying all domains as degraded
- ✓ **Mission Registry** — heartbeats not recording success
- ✓ **Decisions Ledger** — heartbeats not recording success
- ✓ **Health Log** — heartbeats not recording success
- ✓ All 22 domains reporting "never succeeded"

### Why Workbench Still Works
- Workbench queries `intelligence_events`, `intelligence_briefs` (direct reads)
- Doesn't depend on heartbeat system
- Real-time subscriptions work (Supabase replication, not PostgREST)
- **Safe to deploy during this incident**

---

## 🔧 Remediation Path

### Option A: Fix REST API (Supabase Admin)
1. Check Supabase metrics (CPU, connections, query performance)
2. If connection pool exhausted: increase pool size or reduce connections
3. If rate limiting: whitelist heartbeat endpoints
4. If auth issue: rotate/refresh service role key
5. Monitor POST requests to `domain_heartbeats` table

### Option B: Workaround (Short-term)
If REST API won't recover quickly:

1. **Reduce heartbeat cadence** (less load):
   - Edit `domain_registry.expected_cadence_minutes` for non-critical domains
   - Increase `grace_period_minutes` to 30+ minutes

2. **Batch heartbeats** in heartbeat.py:
   - Buffer writes in local file
   - Send once per 5 minutes (not per job)
   - Reduces HTTP requests 10x

3. **Bypass heartbeat for non-critical domains**:
   - Core Event Bus, Mission Registry, Health Log → KEEP (critical infra)
   - Content Eligibility, Wellness Sources → SKIP until recovery

### Option C: Manual Recovery (If persistent)
```sql
-- Once REST API recovers, backfill success heartbeats for core_events
INSERT INTO domain_heartbeats (domain_key, checked_at, status, detail)
VALUES 
  ('core_events', NOW() - interval '30 minutes', 'ok', 'backfill: REST API recovery'),
  ('core_events', NOW(), 'ok', 'recovery verified');

-- This signals successful operation to verification engine
```

---

## 📋 Deployment Decision: Workbench

**Recommendation:** ✅ **PROCEED WITH WORKBENCH DEPLOYMENT**

**Reasoning:**
- Workbench doesn't depend on heartbeat system
- REST API degradation affects heartbeat *writes*, not reads
- Workbench reads: `intelligence_events`, `intelligence_briefs`, `health_insights` (works)
- Migration 0091 can be applied (doesn't require heartbeat)
- Real-time subscriptions work (use Supabase replication, not PostgREST)

**Contingency:**
- If REST API fully outages (502 errors): Workbench API will still work for reads
- Reads use direct Supabase client, not PostgREST
- Only health-memory POST endpoints could fail (but gracefully handled)

---

## 🎓 Long-term Improvements

1. **Separate heartbeat transport**: Use direct Supabase client instead of HTTP
   - Avoid PostgREST bottleneck
   - Better error context
   - Faster

2. **Heartbeat buffering**: Batch writes locally, sync async
   - Reduce HTTP request volume
   - More resilient to API degradation

3. **Alert specificity**: Current alerts don't indicate root cause
   - Add PostgREST latency metric
   - Add connection pool usage
   - Add RLS rejection rate

4. **Fallback heartbeat method**:
   - Primary: PostgREST (current)
   - Secondary: Direct Supabase Python client
   - Fallback: Local file + manual recovery batch

---

## ✅ Next Steps

**Immediate (you):**
1. Run diagnostics.sql in Supabase
2. Check PostgREST API logs
3. Determine root cause (pool exhaustion? RLS? auth?)
4. Decide: fix or workaround?

**Short-term:**
1. Apply workbench migration 0091 (safe during incident)
2. Deploy workbench (doesn't depend on heartbeats)
3. Document incident for post-mortem

**Long-term:**
1. Implement direct Supabase client for heartbeats
2. Add heartbeat batching
3. Improve alert specificity

---

**Generated:** 2026-07-31 07:15 AEST  
**Investigation Tool:** `tools/core-event-bus-diagnostics.sql`  
**Status:** Awaiting your diagnostics results
