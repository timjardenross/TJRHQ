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
const path = require('path');
const fs = require('fs');
const { cacheManager } = require('../cache/cache-manager');
const { asyncHandler, successResponse } = require('../middleware/error-handling');
const { NumberOneAdapter } = require('../connectors/number-one-adapter');
const { getEscalations, getDecisionRecords } = require('../connectors/supabase-connector');

// Initialize adapter
const numberOneAdapter = new NumberOneAdapter();

// Path to Number One exporter outputs
const OUTPUTS_DIR = path.resolve(__dirname, '../../../../core/coordination/outputs');

/** Read a JSON export file; return null if missing or invalid. */
function readExport(filename) {
  try {
    const raw = fs.readFileSync(path.join(OUTPUTS_DIR, filename), 'utf8');
    return JSON.parse(raw);
  } catch (_) {
    return null;
  }
}

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

  if (value && !isStale) {
    const response = successResponse(value, 200, {
      source: 'cache',
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

  if (value && !isStale) {
    const response = successResponse(value, 200, {
      source: 'cache',
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

  // 1. Primary: Number One JSON file (mission-based escalations — blocked P0, stale P0, etc.)
  const numberOneEscalations = numberOneAdapter.getEscalations();
  const missionEscalations = (numberOneEscalations.escalations || []).map(e => ({
    ...e,
    source: 'number-one'
  }));
  let dataSource = numberOneAdapter.isDataAvailable() ? 'number-one-file' : 'mock-fallback';

  // 2. Secondary: Supabase Slack escalations (commander requests needing XO attention)
  //    Deduplicated and filtered in supabase-connector; merged additively here.
  let slackEscalations = [];
  try {
    const rows = await getEscalations({ limit: 10 });
    slackEscalations = rows.map(row => {
      const pri = row.metadata?.priority || '';
      const level = pri.includes('P0') ? 'CRITICAL' : pri.includes('P1') ? 'HIGH' : 'MEDIUM';
      return {
        id: row.id,
        escalation_type: row.event_type || 'SLACK_REQUEST',
        mission: row.metadata?.mission_id || null,
        title: row.message_text || 'XO request from Slack',
        level,
        recommendation: row.metadata?.semantic_rationale || '',
        timestamp: row.created_at,
        source: 'slack'
      };
    });
    if (slackEscalations.length > 0) dataSource += '+supabase';
  } catch (_) {
    // Supabase unavailable — mission escalations still show
  }

  const allEscalations = [...missionEscalations, ...slackEscalations];
  const levelSummary = {
    CRITICAL: allEscalations.filter(e => e.level === 'CRITICAL').length,
    HIGH: allEscalations.filter(e => e.level === 'HIGH').length,
    MEDIUM: allEscalations.filter(e => e.level === 'MEDIUM').length
  };
  const escalationData = { escalations: allEscalations, levelSummary, timestamp: new Date().toISOString() };

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
  if (value && !isStale) return res.json(successResponse(value, 200, { source: 'cache' }));

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

/**
 * GET /api/v1/coordination/blockers
 * Blocker management report — all severities (critical / high / normal)
 */
router.get('/blockers', asyncHandler(async (req, res) => {
  const cacheKey = 'coordination:blockers';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value && !isStale) return res.json(successResponse(value, 200, { source: 'cache' }));

  const data = readExport('blockers.json') || {
    timestamp: new Date().toISOString(),
    total_blockers: 0,
    critical: [], high: [], normal: []
  };
  cacheManager.set(cacheKey, data, 30);
  return res.json(successResponse(data, 200, { source: 'fresh' }));
}));

/**
 * GET /api/v1/coordination/health-queue
 * Work queue with health-capacity advisory overlay
 */
router.get('/health-queue', asyncHandler(async (req, res) => {
  const cacheKey = 'coordination:health-queue';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value && !isStale) return res.json(successResponse(value, 200, { source: 'cache' }));

  const data = readExport('health_queue.json') || {
    exported_at: new Date().toISOString(),
    capacity_status: 'Unknown',
    queue: [], recommended_focus: [],
    advisory: 'Health queue data unavailable'
  };
  cacheManager.set(cacheKey, data, 30);
  return res.json(successResponse(data, 200, { source: 'fresh' }));
}));

/**
 * GET /api/v1/coordination/recommendations
 * Full RecommendationPackage — top 3 ranked missions
 */
router.get('/recommendations', asyncHandler(async (req, res) => {
  const cacheKey = 'coordination:recommendations';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value && !isStale) return res.json(successResponse(value, 200, { source: 'cache' }));

  const data = readExport('recommendations.json') || {
    assembled_at: new Date().toISOString(),
    recommendations: [],
    health_constraints_applied: false,
    total_active_missions: 0
  };
  cacheManager.set(cacheKey, data, 30);
  return res.json(successResponse(data, 200, { source: 'fresh' }));
}));

/**
 * GET /api/v1/coordination/readiness
 * Captain readiness score (0–100) with status and contributors
 */
router.get('/readiness', asyncHandler(async (req, res) => {
  const cacheKey = 'coordination:readiness';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value && !isStale) return res.json(successResponse(value, 200, { source: 'cache' }));

  const data = readExport('readiness.json') || {
    exported_at: new Date().toISOString(),
    score: null,
    status: 'Unknown',
    contributors: [],
    recommended_focus: []
  };
  cacheManager.set(cacheKey, data, 60);
  return res.json(successResponse(data, 200, { source: 'fresh' }));
}));

/**
 * GET /api/v1/coordination/lessons
 * Applicable lessons from Lessons-Learned.md / Supabase
 */
router.get('/lessons', asyncHandler(async (req, res) => {
  const cacheKey = 'coordination:lessons';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value && !isStale) return res.json(successResponse(value, 200, { source: 'cache' }));

  const data = readExport('lessons.json') || {
    exported_at: new Date().toISOString(),
    total: 0,
    lessons: []
  };
  cacheManager.set(cacheKey, data, 120);
  return res.json(successResponse(data, 200, { source: 'fresh' }));
}));

module.exports = router;
