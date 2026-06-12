/**
 * Number One Coordination Engine API — /api/v1/coordination/*
 *
 * Endpoints:
 * - GET /brief        → Daily coordination brief
 * - GET /queue       → Prioritized work queue
 * - GET /escalations → XO escalations requiring attention
 *
 * Data Source: Number One Coordination Engine (MSN-0034)
 *              File-based JSON outputs with mock fallback
 * Cache TTL: 30 seconds (frequently updated)
 *
 * Integration Architecture:
 * ┌─────────────────────────────────┐
 * │ MSN-0034 Number One (Python)    │
 * │ Generates JSON outputs          │
 * └────────────┬────────────────────┘
 *              │
 *              ↓
 * ┌──────────────────────────────────────────────────┐
 * │ NumberOneAdapter (number-one-adapter.js)        │
 * │ - Reads JSON files from /core/coordination/    │
 * │ - Transforms to API format                      │
 * │ - Falls back to mock if files unavailable       │
 * └────────────┬─────────────────────────────────────┘
 *              │
 *              ↓
 * ┌──────────────────────────────────────────────────┐
 * │ This API (coordination.js)                      │
 * │ - Uses adapter for data source                  │
 * │ - Caches results (30s TTL)                      │
 * │ - Returns 3-tier fallback on error              │
 * └──────────────────────────────────────────────────┘
 *
 * Non-breaking integration:
 * - No database changes
 * - No message queues
 * - No authentication added
 * - Mock fallback ensures uptime
 * - Pure data transformation, no logic changes
 */

const express = require('express');
const router = express.Router();
const { cacheManager } = require('../cache/cache-manager');
const { asyncHandler, successResponse } = require('../middleware/error-handling');
const { NumberOneAdapter } = require('../connectors/number-one-adapter');
const { getEscalations, getDecisionRecords } = require('../connectors/supabase-connector');

// Initialize adapter
const numberOneAdapter = new NumberOneAdapter();

/**
 * GET /api/v1/coordination/brief
 * Returns daily coordination brief with recommendations
 *
 * Data Source Priority:
 * 1. Cache (fresh) — < 30 seconds
 * 2. Cache (stale) — > 30 seconds (with age metadata)
 * 3. Number One JSON files (live data)
 * 4. Mock fallback (if files unavailable)
 */
router.get('/brief', asyncHandler(async (req, res) => {
  const cacheKey = 'coordination:brief';
  const { value, isStale } = cacheManager.get(cacheKey);

  if (value) {
    const response = successResponse(value, 200, {
      source: isStale ? 'stale_cache' : 'cache',
      cacheKey: cacheKey,
      dataSource: 'from-cache'
    });
    return res.json(response);
  }

  // Get fresh data from Number One adapter
  const briefData = numberOneAdapter.getDailyBrief();

  cacheManager.set(cacheKey, briefData, 120);
  const response = successResponse(briefData, 200, {
    source: 'fresh',
    generatedAt: new Date().toISOString(),
    dataSource: numberOneAdapter.isDataAvailable() ? 'from-number-one' : 'from-mock-fallback'
  });
  res.json(response);
}));

/**
 * GET /api/v1/coordination/queue
 * Returns prioritized work queue
 *
 * Data Source: Number One JSON files or mock fallback
 */
router.get('/queue', asyncHandler(async (req, res) => {
  const cacheKey = 'coordination:queue';
  const { value, isStale } = cacheManager.get(cacheKey);

  if (value) {
    const response = successResponse(value, 200, {
      source: isStale ? 'stale_cache' : 'cache',
      cacheKey: cacheKey,
      dataSource: 'from-cache'
    });
    return res.json(response);
  }

  // Get fresh data from Number One adapter
  const queueData = numberOneAdapter.getWorkQueue();

  cacheManager.set(cacheKey, queueData, 120);
  const response = successResponse(queueData, 200, {
    source: 'fresh',
    generatedAt: new Date().toISOString(),
    dataSource: numberOneAdapter.isDataAvailable() ? 'from-number-one' : 'from-mock-fallback'
  });
  res.json(response);
}));

/**
 * GET /api/v1/coordination/escalations
 * Returns XO escalations requiring attention
 *
 * Data Source: Number One JSON files or mock fallback
 */
router.get('/escalations', asyncHandler(async (req, res) => {
  const cacheKey = 'coordination:escalations';
  const { value, isStale } = cacheManager.get(cacheKey);

  if (value) {
    return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));
  }

  // 1. Try Supabase escalations (commander_events with escalate_to_xo)
  let escalationData = null;
  let dataSource = 'mock-fallback';

  try {
    const rows = await getEscalations({ limit: 20 });
    if (rows.length > 0) {
      const mapped = rows.map(row => {
        const pri = row.metadata?.priority || '';
        const level = pri.includes('P0') ? 'CRITICAL' : pri.includes('P1') ? 'HIGH' : 'MEDIUM';
        return {
          id: row.id,
          escalation_type: row.event_type || 'XO_ESCALATION',
          mission: row.metadata?.mission_id || null,
          title: row.message_text || 'XO escalation from Slack',
          level,
          recommendation: row.metadata?.semantic_rationale || '',
          timestamp: row.created_at,
          source: 'slack'
        };
      });
      const levelSummary = {
        CRITICAL: mapped.filter(e => e.level === 'CRITICAL').length,
        HIGH: mapped.filter(e => e.level === 'HIGH').length,
        MEDIUM: mapped.filter(e => e.level === 'MEDIUM').length
      };
      escalationData = { escalations: mapped, levelSummary, timestamp: new Date().toISOString() };
      dataSource = 'supabase';
    }
  } catch (err) {
    // fall through to Number One file data
  }

  // 2. Fall back to Number One JSON file
  if (!escalationData) {
    escalationData = numberOneAdapter.getEscalations();
    dataSource = numberOneAdapter.isDataAvailable() ? 'number-one-file' : 'mock-fallback';
  }

  cacheManager.set(cacheKey, escalationData, 120);
  res.json(successResponse(escalationData, 200, {
    source: 'fresh',
    dataSource,
    generatedAt: new Date().toISOString()
  }));
}));

/**
 * GET /api/v1/coordination/decisions
 * Returns recent decision records from Supabase
 */
router.get('/decisions', asyncHandler(async (req, res) => {
  const cacheKey = 'coordination:decisions';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));

  try {
    const rows = await getDecisionRecords({ limit: 20 });
    const data = {
      decisions: rows.map(row => ({
        id: row.id,
        mission_id: row.mission_id,
        summary: row.recommendation_text?.substring(0, 120) + '...',
        decision: row.human_decision,
        decision_maker: row.decision_maker,
        reason: row.decision_reason,
        timestamp: row.decision_timestamp,
        status: row.human_decision ? 'decided' : 'pending'
      })),
      total: rows.length,
      timestamp: new Date().toISOString()
    };
    cacheManager.set(cacheKey, data, 60);
    return res.json(successResponse(data, 200, { source: 'fresh', dataSource: 'supabase' }));
  } catch (err) {
    return res.json(successResponse({ decisions: [], total: 0, error: err.message }, 200, {
      source: 'error-fallback'
    }));
  }
}));

/**
 * GET /api/v1/coordination/status
 * Returns data source status
 *
 * Useful for debugging and monitoring
 */
router.get('/status', asyncHandler(async (req, res) => {
  const status = numberOneAdapter.getStatus();
  const response = successResponse(status, 200, {
    source: 'fresh',
    timestamp: new Date().toISOString()
  });
  res.json(response);
}));

module.exports = router;
