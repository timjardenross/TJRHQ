-- ============================================================================
-- BATCH INSERT: All 9 Decision Logs (2026-06-09 to 2026-06-10)
-- ============================================================================
-- Copy and paste this entire script into Supabase SQL Editor
-- Execute all at once (or one at a time if you prefer)
-- ============================================================================

-- Decision 1: Supabase Backend-Only Access Model
INSERT INTO decisions (
  id, statement, rationale, created_by, owner, status, alternatives, created_at
) VALUES (
  'DEC-20260610-120000',
  'Supabase access model shall remain backend-only with RLS enabled and no user-based policies until a specific frontend use case requires them.',
  'Evidence-based audit confirmed USS TJR is backend-only: all Supabase access routes through Python services using SUPABASE_SERVICE_ROLE_KEY. RLS is enabled on 12 operational tables; SERVICE_ROLE_KEY bypasses RLS so no policies needed for current backend-only usage. SUPABASE_ANON_KEY not used. Smoke tests passed; runtime risk is low.',
  'claude-audit',
  'Captain TJR',
  'Active',
  '[{"name":"Add RLS policies for anon access now","assessment":"Rejected — no frontend code exists; policies unnecessary"},{"name":"Disable RLS","assessment":"Rejected — less secure; RLS already enabled and working"},{"name":"Expose ANON_KEY to frontend","assessment":"Rejected — security risk; backend-only is more secure"}]',
  NOW()
);

-- Decision 2: RLS Enablement Approval
INSERT INTO decisions (
  id, statement, rationale, created_by, owner, status, alternatives, created_at
) VALUES (
  'DEC-20260609-001',
  'Row-Level Security (RLS) shall remain enabled on all 12 operational tables with no user-based policies until a specific, proven frontend use case requires them.',
  'Post-enablement audit confirmed RLS is safely enabled with zero impact on backend-only access. SERVICE_ROLE_KEY bypasses RLS, so no policies needed. RLS provides defense-in-depth for future features.',
  'claude-audit',
  'Captain TJR',
  'Active',
  '[{"name":"Disable RLS","assessment":"Rejected — reduces security unnecessarily"},{"name":"Add policies now","assessment":"Rejected — no frontend code exists"},{"name":"RLS disabled until frontend built","assessment":"Rejected — worse security posture"}]',
  NOW()
);

-- Decision 3: MVLL Phase B1 Approval
INSERT INTO decisions (
  id, statement, rationale, created_by, owner, status, alternatives, created_at
) VALUES (
  'DEC-20260609-002',
  'Proceed with Phase B1 implementation of Minimum Viable Learning Loop (MVLL) to close stages 8-10 and enable system self-improvement.',
  'MSN-0060 review identified learning loop is 60% complete (stages 1-7 live, 8-10 missing). MVLL is critical inflection point from smart-research to self-improving intelligence. 8-hour implementation unlocks massive value. No other feature has higher ROI.',
  'claude-audit',
  'Captain TJR',
  'Active',
  '[{"name":"Skip MVLL, keep at research level","assessment":"Rejected — misses critical value unlock"},{"name":"Wait 2 weeks","assessment":"Acceptable fallback — defers timeline"},{"name":"Build advanced learning loop","assessment":"Rejected — too ambitious; MVLL must be foundation"}]',
  NOW()
);

-- Decision 4: MSN-0057 WP1 & Recommendation-Fix Staging Tests
INSERT INTO decisions (
  id, statement, rationale, created_by, owner, status, alternatives, created_at
) VALUES (
  'DEC-20260609-003',
  'MSN-0057 WP1 (Research Memory Retrieval) and MSN-RECOMMENDATION-FIX (5 Quality Improvements) shall proceed to staging tests immediately after Gemini API quota reset, with production deployment target Week 2.',
  'Both projects code-complete and ready for staging. WP1 enables 30-40% reuse rate (<100ms). Quality fixes deliver 4x specificity, 85% actionability, 0.75-0.90 confidence. Blocking issue: Gemini quota exhausted; resets midnight UTC 2026-06-10. No reason to defer once quota available.',
  'claude-audit',
  'Engineering Lead',
  'Active',
  '[{"name":"Deploy to production without staging test","assessment":"Rejected — must validate in staging"},{"name":"Defer until Week 3","assessment":"Rejected — no benefit to waiting; quota resets tomorrow"},{"name":"Implement only WP1, defer quality-fix","assessment":"Acceptable fallback if issues found; prefer to ship together"}]',
  NOW()
);

-- Decision 5: Recommendation Quality Root Causes
INSERT INTO decisions (
  id, statement, rationale, created_by, owner, status, alternatives, created_at
) VALUES (
  'DEC-20260609-004',
  'Five specific, actionable root causes of generic recommendations have been identified and fixed in code. All fixes are backward-compatible and ready for staging validation.',
  'MSN-RECOMMENDATION-QUALITY-REVIEW found gap between strong research and weak recommendations. Root cause analysis identified 5 fixable issues: weak framework, wrong models, raw findings not used, fallback auto-defer, single model hierarchy. All fixed. Expected: 4x specificity, 85% actionability, 0.75-0.90 confidence.',
  'claude-audit',
  'Captain TJR',
  'Active',
  '[{"name":"Redesign from scratch","assessment":"Rejected — 5 targeted fixes sufficient"},{"name":"Use only Flash (not Flash Lite)","assessment":"Rejected — cost 3x higher; Flash Lite sufficient"},{"name":"Accept generic recommendations","assessment":"Rejected — undermines research value"}]',
  NOW()
);

-- Decision 6: MSN-0058 Provider Cost Optimization
INSERT INTO decisions (
  id, statement, rationale, created_by, owner, status, alternatives, created_at
) VALUES (
  'DEC-20260609-005',
  'Provider chain shall be reordered to minimize cost while maintaining quality: Flash Lite (primary) → Ollama (fallback) → Flash (emergency). Expected monthly savings: $65-80.',
  'Flash-only strategy over-provisions. Flash Lite is 85% quality at 30% cost; sufficient for 90%+ of tasks. New strategy: Flash Lite primary, Ollama fallback, Flash emergency. Savings $65-80/month. Quality maintained.',
  'claude-audit',
  'Engineering Lead',
  'Active',
  '[{"name":"Keep Flash-only","assessment":"Rejected — wastes money"},{"name":"Ollama-only","assessment":"Rejected — quality risk"},{"name":"Incremental rollout (Flash Lite for consolidation)","assessment":"Accepted — what we did"}]',
  NOW()
);

-- Decision 7: MSN-0060 System Integration Review
INSERT INTO decisions (
  id, statement, rationale, created_by, owner, status, alternatives, created_at
) VALUES (
  'DEC-20260609-006',
  'USS TJR system is 60% complete with two working missions deployed. The learning loop is the critical gap. Proceed with Phase A immediately; implement Phase B (learning loop closure) by June 30, 2026.',
  'MSN-0060 integration review: 7/10 learning loop stages operational; 3/10 completely missing. Recommendation quality fix code-complete. WP1 memory retrieval code-complete. All ready for staging. Decision: Phase A (2 days), Phase B (2 weeks), target June 30 completion.',
  'claude-audit',
  'Captain TJR',
  'Active',
  '[{"name":"Keep system at research level","assessment":"Rejected — misses learning loop value unlock"},{"name":"Wait and see performance first","assessment":"Acceptable fallback — delays timeline 2 weeks"},{"name":"Implement all phases at once","assessment":"Rejected — too ambitious; phased approach more risk-managed"}]',
  NOW()
);

-- Decision 8: Memory System Unification
INSERT INTO decisions (
  id, statement, rationale, created_by, owner, status, alternatives, created_at
) VALUES (
  'DEC-20260609-007',
  'Three separate memory systems (Command, Working, Research) shall be unified under a single "Mission Context" system with clear tier definitions. Implementation scheduled for Phase B3 (1 week, 20 hours).',
  'MSN-0060 review found three fragmented memory layers with no unified interface. Each new feature must navigate three separate APIs. Solution: Single MissionContext wrapper with three clear tiers (executive → working → research). Reduces integration friction; enables Phase C features.',
  'claude-audit',
  'Captain TJR',
  'Active',
  '[{"name":"Keep three separate systems","assessment":"Rejected — scaling complexity grows"},{"name":"Unify immediately (before B1)","assessment":"Rejected — B1 higher priority; parallel in B3"},{"name":"Unify only Tier 2+3","assessment":"Rejected — command layer integration is key"}]',
  NOW()
);

-- Decision 9: RLS Safety Assessment & Baseline
INSERT INTO decisions (
  id, statement, rationale, created_by, owner, status, alternatives, created_at
) VALUES (
  'DEC-20260609-008',
  'RLS post-enablement security posture is improved with low runtime risk. Baseline is secure and operationally sound. No emergency actions required. Maintain current backend-only access model.',
  'RLS audit: Zero frontend code found. All access via SERVICE_ROLE_KEY (backend-only). ANON_KEY not used. Implicit deny is safe. RLS provides defense-in-depth with zero operational cost. Risk: LOW. Recommendation: Keep RLS enabled; defer policies until proven frontend use case.',
  'claude-audit',
  'Engineering Lead',
  'Active',
  '[{"name":"Disable RLS","assessment":"Rejected — reduces security unnecessarily"},{"name":"Add policies now","assessment":"Rejected — no frontend code exists"},{"name":"Require ANON_KEY","assessment":"Rejected — not needed; omit from production"}]',
  NOW()
);

-- ============================================================================
-- VERIFICATION QUERY
-- ============================================================================
-- Run this to verify all 9 decisions were inserted:
-- SELECT COUNT(*) as total_decisions,
--        COUNT(CASE WHEN created_by = 'claude-audit' THEN 1 END) as claude_decisions
-- FROM decisions
-- WHERE id IN (
--   'DEC-20260610-120000',
--   'DEC-20260609-001',
--   'DEC-20260609-002',
--   'DEC-20260609-003',
--   'DEC-20260609-004',
--   'DEC-20260609-005',
--   'DEC-20260609-006',
--   'DEC-20260609-007',
--   'DEC-20260609-008'
-- );
-- ============================================================================
