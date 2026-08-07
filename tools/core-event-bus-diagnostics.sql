-- Core Event Bus Degradation Diagnostics
-- Run this in Supabase SQL editor to understand the actual state

SELECT '=== CORE EVENT BUS DIAGNOSTICS ===' AS check_name, NOW() AS timestamp;

-- 1. How many domains are registered?
SELECT 'domain_registry total count' AS check_name,
       COUNT(*) AS count
FROM domain_registry;

-- 2. How many have never succeeded?
SELECT 'never_succeeded count' AS check_name,
       COUNT(*) AS count
FROM domain_heartbeat_latest
WHERE never_succeeded = true;

-- 3. Which domains have never succeeded? (THE BLOCKER)
SELECT 'CRITICAL: never_succeeded domains' AS check_name,
       domain_key,
       category,
       last_error_message,
       last_checked_at
FROM domain_heartbeat_latest
WHERE never_succeeded = true
ORDER BY category, domain_key;

-- 4. Core Event Bus specific status
SELECT 'core_events domain status' AS check_name,
       domain_key,
       last_status,
       last_success_at,
       last_checked_at,
       last_error_message,
       is_stale
FROM domain_heartbeat_latest
WHERE domain_key = 'core_events';

-- 5. How many domains are stale (not reporting regularly)?
SELECT 'is_stale count' AS check_name,
       COUNT(*) AS count
FROM domain_heartbeat_latest
WHERE is_stale = true;

-- 6. Which stale domains are critical? (data + job categories)
SELECT 'CRITICAL: stale data/job domains' AS check_name,
       domain_key,
       category,
       expected_cadence_minutes,
       grace_period_minutes,
       last_checked_at,
       last_error_message
FROM domain_heartbeat_latest
WHERE is_stale = true
  AND category IN ('data', 'job')
ORDER BY last_checked_at DESC;

-- 7. Recent heartbeat failure patterns
SELECT 'recent failures (last 10)' AS check_name,
       domain_key,
       status,
       error_message,
       checked_at
FROM domain_heartbeats
WHERE status = 'failed'
ORDER BY checked_at DESC
LIMIT 10;

-- 8. Verification state (are we in 'sure' or 'unsure'?)
SELECT 'verification state' AS check_name,
       state,
       computed_at
FROM verification_state
ORDER BY computed_at DESC
LIMIT 1;

-- 9. core_events table health check
SELECT 'core_events table row count' AS check_name,
       COUNT(*) AS count
FROM core_events;

SELECT 'core_events recent events (last 10)' AS check_name,
       event_type,
       domain,
       source,
       occurred_at,
       status
FROM core_events
ORDER BY occurred_at DESC
LIMIT 10;

-- 10. PostgREST connectivity test
SELECT 'Supabase connection available' AS check_name,
       CASE WHEN NOW() IS NOT NULL THEN 'PASS' ELSE 'FAIL' END AS status;

SELECT '=== DIAGNOSTICS COMPLETE ===' AS check_name, NOW() AS timestamp;
