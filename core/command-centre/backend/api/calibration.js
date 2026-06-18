/**
 * Calibration API — /api/v1/calibration/*
 *
 * WP3: Exposes calibration metrics for COP, Number One, and XO dashboards.
 *
 * Endpoints:
 *   GET  /summary          → Latest calibration summary (agreement rate, mismatches)
 *   GET  /daily?days=30    → Daily calibration rows
 *   POST /run              → Trigger a calibration run (spawns Python)
 *   GET  /weighting-analysis → Weighting recommendations (WP4, spawns Python)
 *   GET  /xo-oversight     → XO governance view (WP6)
 */

const express = require('express');
const router = express.Router();
const { spawn } = require('child_process');
const path = require('path');

const { cacheManager } = require('../cache/cache-manager');
const { asyncHandler, successResponse } = require('../middleware/error-handling');
const { supabaseGet } = require('../connectors/supabase-client');

const REPO_ROOT = path.resolve(__dirname, '../../../../');

// ─── Helpers ──────────────────────────────────────────────────────────────────

function calibrationStatus(rate) {
  if (rate === null || rate === undefined) return 'Unknown';
  if (rate >= 85) return 'Green';
  if (rate >= 70) return 'Amber';
  return 'Red';
}

function spawnPython(scriptName, args = []) {
  return new Promise((resolve, reject) => {
    const scriptPath = path.join(REPO_ROOT, 'core', 'health', scriptName);
    const proc = spawn('python3', [scriptPath, ...args], {
      cwd: REPO_ROOT, env: { ...process.env }, timeout: 60000,
    });
    let stdout = '', stderr = '';
    proc.stdout.on('data', d => { stdout += d.toString(); });
    proc.stderr.on('data', d => { stderr += d.toString(); });
    proc.on('close', (code) => {
      if (code !== 0) return reject(new Error(stderr.trim() || `exit ${code}`));
      try { resolve(JSON.parse(stdout)); } catch { resolve({ raw: stdout.trim() }); }
    });
    proc.on('error', reject);
  });
}

// ─── GET /summary ─────────────────────────────────────────────────────────────

router.get('/summary', asyncHandler(async (req, res) => {
  const cacheKey = 'calibration:summary';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value && !isStale) return res.json(successResponse(value, 200, { source: 'cache' }));

  try {
    const rows = await supabaseGet('capacity_calibration_summary?order=summary_date.desc&limit=1');
    const summary = Array.isArray(rows) ? rows[0] : null;
    const data = summary ? {
      ...summary,
      calibration_status: calibrationStatus(summary.agreement_rate),
    } : null;
    cacheManager.set(cacheKey, data, 120);
    return res.json(successResponse(data, 200, { source: 'fresh', dataSource: 'supabase' }));
  } catch (err) {
    return res.json(successResponse(null, 200, { source: 'error-fallback', error: err.message }));
  }
}));

// ─── GET /daily ───────────────────────────────────────────────────────────────

router.get('/daily', asyncHandler(async (req, res) => {
  const days = Math.min(parseInt(req.query.days || '30', 10), 90);
  const cacheKey = `calibration:daily:${days}`;
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value && !isStale) return res.json(successResponse(value, 200, { source: 'cache' }));

  try {
    const rows = await supabaseGet(
      `capacity_calibration?order=log_date.desc&limit=${days}`
    );
    const data = { rows: Array.isArray(rows) ? rows : [], count: Array.isArray(rows) ? rows.length : 0, days };
    cacheManager.set(cacheKey, data, 120);
    return res.json(successResponse(data, 200, { source: 'fresh', dataSource: 'supabase' }));
  } catch (err) {
    return res.json(successResponse({ rows: [], count: 0, days, error: err.message }, 200, { source: 'error-fallback' }));
  }
}));

// ─── POST /run ────────────────────────────────────────────────────────────────

router.post('/run', asyncHandler(async (req, res) => {
  const days = Math.min(parseInt(req.body?.days || '30', 10), 90);
  cacheManager.clear('calibration:summary');
  for (let d = 1; d <= 90; d++) cacheManager.clear(`calibration:daily:${d}`);

  try {
    const result = await spawnPython('calibration_engine.py', ['--days', String(days)]);
    if (result.success) {
      cacheManager.set('calibration:summary', {
        ...result,
        calibration_status: calibrationStatus(result.agreement_rate),
      }, 300);
    }
    return res.json(successResponse(result, 200, { source: 'fresh', dataSource: 'calibration_engine.py' }));
  } catch (err) {
    return res.json(successResponse({ success: false, error: err.message }, 200, { source: 'error-fallback' }));
  }
}));

// ─── GET /weighting-analysis ──────────────────────────────────────────────────

router.get('/weighting-analysis', asyncHandler(async (req, res) => {
  const days = Math.min(parseInt(req.query.days || '45', 10), 90);
  const cacheKey = `calibration:weighting:${days}`;
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value && !isStale) return res.json(successResponse(value, 200, { source: 'cache' }));

  try {
    const result = await spawnPython('weighting_analysis.py', ['--days', String(days)]);
    cacheManager.set(cacheKey, result, 300);
    return res.json(successResponse(result, 200, { source: 'fresh', dataSource: 'weighting_analysis.py' }));
  } catch (err) {
    return res.json(successResponse({ success: false, error: err.message }, 200, { source: 'error-fallback' }));
  }
}));

// ─── GET /xo-oversight ───────────────────────────────────────────────────────

router.get('/xo-oversight', asyncHandler(async (req, res) => {
  const cacheKey = 'calibration:xo-oversight';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value && !isStale) return res.json(successResponse(value, 200, { source: 'cache' }));

  try {
    // Latest summary
    const summaryRows = await supabaseGet('capacity_calibration_summary?order=summary_date.desc&limit=1');
    const latest = Array.isArray(summaryRows) ? summaryRows[0] : null;

    // 30-day trend: last 30 summary rows (one per run day)
    const trendRows = await supabaseGet('capacity_calibration_summary?order=summary_date.desc&limit=30');
    const trend = Array.isArray(trendRows) ? trendRows.map(r => ({
      date: r.summary_date,
      agreement_rate: r.agreement_rate,
      calibration_status: calibrationStatus(r.agreement_rate),
    })) : [];

    const data = {
      current_accuracy: latest?.agreement_rate ?? null,
      calibration_status: latest ? calibrationStatus(latest.agreement_rate) : 'Unknown',
      calibration_confidence: latest?.calibration_confidence ?? 'insufficient',
      false_green_count: latest?.false_green_count ?? 0,
      false_amber_count: latest?.false_amber_count ?? 0,
      false_red_count: latest?.false_red_count ?? 0,
      consecutive_low_days: latest?.consecutive_low_days ?? 0,
      weighting_review_flag: latest?.weighting_review_flag ?? false,
      governance_recommendation: latest?.weighting_review_flag
        ? 'Health Capacity Model Review Required — agreement rate below 70% for 14+ consecutive days'
        : null,
      trend_30d: trend,
    };

    cacheManager.set(cacheKey, data, 120);
    return res.json(successResponse(data, 200, { source: 'fresh', dataSource: 'supabase' }));
  } catch (err) {
    return res.json(successResponse({ error: err.message }, 200, { source: 'error-fallback' }));
  }
}));

module.exports = router;
