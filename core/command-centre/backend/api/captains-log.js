/**
 * Captain's Log API — /api/v1/captains-log/*
 *
 * Endpoints:
 *   GET  /today          → Today's log entry (or null if not yet created)
 *   POST /               → Create or update today's entry (upsert by log_date)
 *   GET  /recent?days=14 → Recent entries for trend view
 *   GET  /summary        → Lightweight summary metrics for dashboard widget
 *
 * Table: captains_log_entries (Supabase)
 * Cache TTL: 60s (today), 120s (recent/summary)
 */

const express = require('express');
const router = express.Router();
const { cacheManager } = require('../cache/cache-manager');
const { asyncHandler, successResponse } = require('../middleware/error-handling');
const { spawn } = require('child_process');
const path = require('path');
const {
  getCaptainsLogToday,
  upsertCaptainsLogEntry,
  getCaptainsLogRecent,
  getCaptainsLogSummary,
  computeCapacityScore,
} = require('../connectors/supabase-connector');
const { supabaseGet } = require('../connectors/supabase-client');

// ─── GET /today ──────────────────────────────────────────────────────────────

router.get('/today', asyncHandler(async (req, res) => {
  const cacheKey = 'captains-log:today';
  const { value, isStale } = cacheManager.get(cacheKey);

  if (value && !isStale) {
    return res.json(successResponse(value, 200, { source: 'cache', cacheKey }));
  }

  try {
    const entry = await getCaptainsLogToday();
    const data = { entry: entry || null, exists: !!entry };
    cacheManager.set(cacheKey, data, 60);
    return res.json(successResponse(data, 200, { source: 'fresh', dataSource: 'supabase' }));
  } catch (err) {
    return res.json(successResponse({ entry: null, exists: false, error: err.message }, 200, {
      source: 'error-fallback'
    }));
  }
}));

// ─── POST / ───────────────────────────────────────────────────────────────────

router.post('/', asyncHandler(async (req, res) => {
  const body = req.body || {};

  // Whitelist allowed fields — prevents any unintended column writes
  const ALLOWED = [
    'log_date', 'pain_score', 'pain_location', 'energy', 'mood',
    'sleep_hours', 'sleep_quality', 'cpap_status', 'physical_capacity',
    'what_happened', 'what_changed', 'wins', 'blockers', 'decisions_made',
    'tomorrows_priority', 'health_status', 'work_status', 'personal_status',
    'overall_note', 'source', 'captain_capacity_rating',
    'pain_triggers', 'pain_relievers', 'coping_strategies', 'activity_impact'
  ];

  const payload = {};
  for (const key of ALLOWED) {
    if (body[key] !== undefined) payload[key] = body[key];
  }

  // Default log_date to today (UTC date string YYYY-MM-DD)
  if (!payload.log_date) {
    payload.log_date = new Date().toISOString().split('T')[0];
  }

  // Coerce numeric fields
  if (payload.pain_score !== undefined) payload.pain_score = Number(payload.pain_score);
  if (payload.sleep_hours !== undefined) payload.sleep_hours = Number(payload.sleep_hours);

  const entry = await upsertCaptainsLogEntry(payload);

  // Invalidate today's cache so next GET /today is fresh
  cacheManager.clear('captains-log:today');
  cacheManager.clear('captains-log:summary');

  return res.json(successResponse({ entry }, 200, { source: 'fresh', dataSource: 'supabase' }));
}));

// ─── GET /recent ─────────────────────────────────────────────────────────────

router.get('/recent', asyncHandler(async (req, res) => {
  const days = Math.min(parseInt(req.query.days || '14', 10), 90);
  const cacheKey = `captains-log:recent:${days}`;
  const { value, isStale } = cacheManager.get(cacheKey);

  if (value && !isStale) {
    return res.json(successResponse(value, 200, { source: 'cache', cacheKey }));
  }

  try {
    const entries = await getCaptainsLogRecent(days);
    const data = { entries, count: entries.length, days };
    cacheManager.set(cacheKey, data, 120);
    return res.json(successResponse(data, 200, { source: 'fresh', dataSource: 'supabase' }));
  } catch (err) {
    return res.json(successResponse({ entries: [], count: 0, days, error: err.message }, 200, {
      source: 'error-fallback'
    }));
  }
}));

// ─── GET /summary ─────────────────────────────────────────────────────────────

router.get('/summary', asyncHandler(async (req, res) => {
  const cacheKey = 'captains-log:summary';
  const { value, isStale } = cacheManager.get(cacheKey);

  if (value && !isStale) {
    return res.json(successResponse(value, 200, { source: 'cache', cacheKey }));
  }

  try {
    const summary = await getCaptainsLogSummary();
    cacheManager.set(cacheKey, summary, 120);
    return res.json(successResponse(summary, 200, { source: 'fresh', dataSource: 'supabase' }));
  } catch (err) {
    return res.json(successResponse({
      today_logged: false, latest_pain_score: null, avg_pain_7d: null,
      latest_energy: null, latest_mood: null, trend_direction: null,
      tomorrows_priority: null, error: err.message
    }, 200, { source: 'error-fallback' }));
  }
}));

// ─── POST /synthesise-week ────────────────────────────────────────────────────

router.post('/synthesise-week', asyncHandler(async (req, res) => {
  const days = Math.min(parseInt(req.body?.days || '7', 10), 90);

  // Invalidate summary and recent caches so consumers see fresh data
  cacheManager.clear('captains-log:summary');
  for (let d = 1; d <= 90; d++) cacheManager.clear(`captains-log:recent:${d}`);

  return new Promise((resolve) => {
    const repoRoot = path.resolve(__dirname, '../../../../');
    const scriptPath = path.join(repoRoot, 'core', 'health', 'weekly_synthesis.py');

    const proc = spawn('python3', [scriptPath, '--days', String(days), '--no-update-md'], {
      cwd: repoRoot,
      env: { ...process.env },
      timeout: 60000,
    });

    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', d => { stdout += d.toString(); });
    proc.stderr.on('data', d => { stderr += d.toString(); });

    proc.on('close', (code) => {
      if (code !== 0) {
        const response = successResponse(
          { success: false, error: stderr.trim() || 'synthesis script exited non-zero', exit_code: code },
          200,
          { source: 'fresh' }
        );
        resolve(res.json(response));
        return;
      }

      let insight = {};
      try {
        insight = JSON.parse(stdout);
      } catch {
        insight = { raw: stdout.trim() };
      }

      // Cache the narrative for quick re-reads
      cacheManager.set('captains-log:latest-synthesis', insight, 300);

      const response = successResponse(
        { success: true, insight },
        200,
        { source: 'fresh', dataSource: 'weekly_synthesis.py' }
      );
      resolve(res.json(response));
    });

    proc.on('error', (err) => {
      const response = successResponse(
        { success: false, error: err.message },
        200,
        { source: 'error-fallback' }
      );
      resolve(res.json(response));
    });
  });
}));

// ─── GET /latest-synthesis ────────────────────────────────────────────────────

router.get('/latest-synthesis', asyncHandler(async (req, res) => {
  const cacheKey = 'captains-log:latest-synthesis';
  const { value } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: 'cache' }));

  // Try to read latest from Supabase health_insights via the shared client.
  try {
    const rows = await supabaseGet('health_insights?order=period_start.desc&limit=1');
    const insight = Array.isArray(rows) ? rows[0] : rows;

    if (insight) {
      cacheManager.set(cacheKey, insight, 300);
      return res.json(successResponse(insight, 200, { source: 'fresh', dataSource: 'supabase' }));
    }
  } catch (_) { /* fall through */ }

  return res.json(successResponse(null, 200, { source: 'error-fallback' }));
}));

// ─── GET /capacity-model ──────────────────────────────────────────────────────

router.get('/capacity-model', asyncHandler(async (req, res) => {
  const WEIGHTS = {
    pain_max_deduction: 35,
    energy_low: 20, energy_moderate: 8, energy_high: 0,
    sleep_lt_5h: 15, sleep_lt_6h: 8, sleep_gte_6h: 0,
    mood_low: 10, mood_stable: 4, mood_positive: 0,
    capacity_worse: -10, capacity_same: 0, capacity_better: 5,
  };
  return res.json(successResponse({
    weights: WEIGHTS,
    thresholds: { Green: 80, Amber: 55 },
    formula: 'score = 100 - (pain_score/10 × 35) - energy_deduction - sleep_deduction - mood_deduction + physical_capacity_modifier, clamped 0–100',
    version: '1.0',
  }, 200, { source: 'fresh' }));
}));

module.exports = router;
