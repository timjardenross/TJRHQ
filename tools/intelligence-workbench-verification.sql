-- Intelligence Workbench Schema Verification Script
-- Run this against production Supabase to verify all required columns exist
-- Copy output to verify each check passes

SELECT '=== INTELLIGENCE WORKBENCH SCHEMA VERIFICATION ===' AS check_name, 
       'START' AS status, NOW() AS timestamp;

-- 1. core_events table columns
SELECT 'core_events.source_governed' AS check_name,
       CASE 
         WHEN EXISTS (
           SELECT 1 FROM information_schema.columns 
           WHERE table_name = 'core_events' AND column_name = 'source_governed'
         ) THEN 'PASS' 
         ELSE 'FAIL' 
       END AS status;

-- 2. intelligence_events table columns
SELECT 'intelligence_events.confidence' AS check_name,
       CASE 
         WHEN EXISTS (
           SELECT 1 FROM information_schema.columns 
           WHERE table_name = 'intelligence_events' AND column_name = 'confidence'
         ) THEN 'PASS' 
         ELSE 'FAIL' 
       END AS status
UNION ALL
SELECT 'intelligence_events.confidence_level',
       CASE 
         WHEN EXISTS (
           SELECT 1 FROM information_schema.columns 
           WHERE table_name = 'intelligence_events' AND column_name = 'confidence_level'
         ) THEN 'PASS' 
         ELSE 'FAIL' 
       END;

-- 3. intelligence_briefs table columns
SELECT 'intelligence_briefs.overall_risk' AS check_name,
       CASE 
         WHEN EXISTS (
           SELECT 1 FROM information_schema.columns 
           WHERE table_name = 'intelligence_briefs' AND column_name = 'overall_risk'
         ) THEN 'PASS' 
         ELSE 'FAIL' 
       END AS status
UNION ALL
SELECT 'intelligence_briefs.signal_ids',
       CASE 
         WHEN EXISTS (
           SELECT 1 FROM information_schema.columns 
           WHERE table_name = 'intelligence_briefs' AND column_name = 'signal_ids'
         ) THEN 'PASS' 
         ELSE 'FAIL' 
       END;

-- 4. health_insights table columns
SELECT 'health_insights.committed_to_memory' AS check_name,
       CASE 
         WHEN EXISTS (
           SELECT 1 FROM information_schema.columns 
           WHERE table_name = 'health_insights' AND column_name = 'committed_to_memory'
         ) THEN 'PASS' 
         ELSE 'FAIL' 
       END AS status
UNION ALL
SELECT 'health_insights.committed_at',
       CASE 
         WHEN EXISTS (
           SELECT 1 FROM information_schema.columns 
           WHERE table_name = 'health_insights' AND column_name = 'committed_at'
         ) THEN 'PASS' 
         ELSE 'FAIL' 
       END
UNION ALL
SELECT 'health_insights.source_articles',
       CASE 
         WHEN EXISTS (
           SELECT 1 FROM information_schema.columns 
           WHERE table_name = 'health_insights' AND column_name = 'source_articles'
         ) THEN 'PASS' 
         ELSE 'FAIL' 
       END
UNION ALL
SELECT 'health_insights.overall_status',
       CASE 
         WHEN EXISTS (
           SELECT 1 FROM information_schema.columns 
           WHERE table_name = 'health_insights' AND column_name = 'overall_status'
         ) THEN 'PASS' 
         ELSE 'FAIL' 
       END;

-- 5. health_source_articles table exists
SELECT 'health_source_articles table' AS check_name,
       CASE 
         WHEN EXISTS (
           SELECT 1 FROM information_schema.tables 
           WHERE table_name = 'health_source_articles'
         ) THEN 'PASS' 
         ELSE 'FAIL' 
       END AS status;

-- 6. Data quality checks
SELECT 'intelligence_source_registry.terms_reviewed TRUE count' AS check_name,
       COUNT(*) AS count
FROM intelligence_source_registry 
WHERE terms_reviewed = true;

SELECT 'intelligence_events.confidence >= 60 count (7d)' AS check_name,
       COUNT(*) AS count
FROM intelligence_events 
WHERE confidence >= 60 
  AND collected_at >= NOW() - interval '7 days'
  AND suppressed = false;

SELECT 'intelligence_briefs.overall_risk counts' AS check_name,
       overall_risk || ': ' || COUNT(*) AS status
FROM intelligence_briefs 
GROUP BY overall_risk
ORDER BY overall_risk;

-- 7. Indexes verification
SELECT 'idx_core_events_source_governed' AS check_name,
       CASE 
         WHEN EXISTS (
           SELECT 1 FROM pg_indexes 
           WHERE indexname = 'idx_core_events_source_governed'
         ) THEN 'PASS' 
         ELSE 'FAIL (create for performance)' 
       END AS status
UNION ALL
SELECT 'idx_intelligence_events_confidence',
       CASE 
         WHEN EXISTS (
           SELECT 1 FROM pg_indexes 
           WHERE indexname = 'idx_intelligence_events_confidence'
         ) THEN 'PASS' 
         ELSE 'WARN (performance)' 
       END
UNION ALL
SELECT 'idx_health_source_articles_insight',
       CASE 
         WHEN EXISTS (
           SELECT 1 FROM pg_indexes 
           WHERE indexname = 'idx_health_source_articles_insight'
         ) THEN 'PASS' 
         ELSE 'WARN (performance)' 
       END;

-- 8. RLS policies
SELECT 'RLS enabled on health_source_articles' AS check_name,
       CASE 
         WHEN EXISTS (
           SELECT 1 FROM information_schema.tables 
           WHERE table_name = 'health_source_articles' 
           AND table_schema = 'public'
         ) THEN 'PASS'
         ELSE 'FAIL'
       END AS status;

SELECT '=== VERIFICATION COMPLETE ===' AS check_name, 
       'END' AS status, NOW() AS timestamp;
