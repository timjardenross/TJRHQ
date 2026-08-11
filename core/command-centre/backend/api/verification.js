/**
 * Verification State API — /api/v1/verification/*
 *
 * STARSHIP-REDESIGN.md §4: the read-side of the verification engine. Home
 * will eventually call GET /state to render "Nothing needs you, Captain" /
 * the Unsure/Blind degraded copy — this endpoint is the only place that
 * decision gets made, so Home itself never has to reason about staleness.
 *
 * Reads the latest row core/platform/verification_engine.py wrote to
 * verification_state. Deliberately does NOT recompute anything live (no
 * scanning domain_heartbeat_latest here) - the pass already did that work on
 * its own schedule. The one thing this endpoint adds on top of the stored
 * row: deriving BLIND. verification_engine.py never asserts blind about
 * itself (a dead pass can't self-report), so this endpoint checks whether
 * the stored row's computed_at has itself gone stale against the
 * verification_engine domain's own cadence+grace, exactly per spec §4.3's
 * three-word state model.
 */

const express = require('express');
const router = express.Router();
const { asyncHandler, successResponse } = require('../middleware/error-handling');
const { cacheManager } = require('../cache/cache-manager');
const { supabaseGet } = require('../connectors/supabase-connector');

const CACHE_TTL_SECONDS = 15;

router.get('/state', asyncHandler(async (req, res) => {
  const cacheKey = 'verification:state';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));

  const [stateRows, registryRows, allDomainsRows] = await Promise.all([
    supabaseGet('verification_state?select=computed_at,state,degraded_domains,reason&order=computed_at.desc&limit=1'),
    supabaseGet('domain_registry?domain_key=eq.verification_engine&select=expected_cadence_minutes,grace_period_minutes'),
    supabaseGet('domain_registry?active=eq.true&select=domain_key'),
  ]);

  const registry = registryRows[0] || { expected_cadence_minutes: 5, grace_period_minutes: 15 };
  const maxAgeMs = (registry.expected_cadence_minutes + registry.grace_period_minutes) * 60 * 1000;
  const totalDomains = allDomainsRows.length;

  const latest = stateRows[0] || null;
  const nowMs = Date.now();
  const computedAtMs = latest ? new Date(latest.computed_at).getTime() : null;
  const isBlind = !latest || (nowMs - computedAtMs) > maxAgeMs;

  let data;
  if (isBlind) {
    data = {
      state: 'blind',
      last_verified_at: latest ? latest.computed_at : null,
      degraded_domains: [],
      total_domains: totalDomains,
      reason: latest
        ? 'Verification has not run recently enough to trust its last result'
        : 'Verification has never completed a pass',
    };
  } else {
    data = {
      state: latest.state, // 'sure' | 'unsure'
      last_verified_at: latest.computed_at,
      degraded_domains: latest.degraded_domains || [],
      total_domains: totalDomains,
      reason: latest.reason || null,
    };
  }

  cacheManager.set(cacheKey, data, CACHE_TTL_SECONDS);
  res.json(successResponse(data, 200, { source: 'fresh' }));
}));

module.exports = router;
