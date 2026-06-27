/**
 * Personal Health API — /api/v1/personal-health/*
 *
 * MSN-F: Recovery Pulse data from Supabase.
 * Sources: recovery_pulses table, recovery_confidence_today view,
 *          recovery_pulse_adherence_7d view, captains_log_entries (capacity).
 */

const express = require('express');
const router = express.Router();
const { cacheManager } = require('../cache/cache-manager');
const { asyncHandler, successResponse, ApiError } = require('../middleware/error-handling');
const { supabaseGet, computeCapacityScore } = require('../connectors/supabase-connector');

// ── GET /api/v1/personal-health/status ─────────────────────────────────────
// Recovery confidence today + capacity status.
router.get('/status', asyncHandler(async (req, res) => {
  const cacheKey = 'personal-health:status';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));

  const [confidence, logRows] = await Promise.allSettled([
    supabaseGet('recovery_confidence_today?select=*&limit=1'),
    supabaseGet('captains_log_entries?select=*&order=log_date.desc&limit=1'),
  ]);

  const conf = confidence.status === 'fulfilled' && confidence.value && confidence.value[0]
    ? confidence.value[0] : null;
  const latestLog = logRows.status === 'fulfilled' && logRows.value && logRows.value[0]
    ? logRows.value[0] : null;

  const { score: capacityScore, status: capacityStatus } = computeCapacityScore(latestLog);

  const data = {
    recovery_confidence: conf ? {
      pulses_today:     conf.pulse_count ?? 0,
      confidence_score: conf.confidence_score ?? 0,
      confidence_label: conf.confidence_label ?? 'No data',
      morning_done:     conf.morning_done ?? false,
      midday_done:      conf.midday_done ?? false,
      end_of_day_done:  conf.end_of_day_done ?? false,
      evening_done:     conf.evening_done ?? false,
      latest_energy:    conf.latest_energy ?? null,
      latest_mood:      conf.latest_mood ?? null,
      latest_stress:    conf.latest_stress ?? null,
      latest_readiness: conf.latest_readiness ?? null,
      latest_pain:      conf.latest_pain ?? null,
    } : null,
    capacity: {
      score:  capacityScore,
      status: capacityStatus,
    },
    log_date: latestLog ? latestLog.log_date : null,
  };

  cacheManager.set(cacheKey, data, 90);
  res.json(successResponse(data, 200, { source: 'fresh', dataSource: 'supabase' }));
}));

// ── GET /api/v1/personal-health/trends ─────────────────────────────────────
// 7-day recovery pulse adherence and signal trends.
router.get('/trends', asyncHandler(async (req, res) => {
  const cacheKey = 'personal-health:trends';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));

  const rows = await supabaseGet(
    'recovery_pulse_adherence_7d?select=*&order=log_date.desc&limit=7'
  );

  const pulses = await supabaseGet(
    'recovery_pulses?select=log_date,pulse_type,pain_score,energy,mood,stress,readiness&order=captured_at.desc&limit=28'
  );

  const data = {
    adherence_7d: rows || [],
    recent_pulses: pulses || [],
  };

  cacheManager.set(cacheKey, data, 300);
  res.json(successResponse(data, 200, { source: 'fresh', dataSource: 'supabase' }));
}));

// ── GET /api/v1/personal-health/watchlist ──────────────────────────────────
// Health flags: low confidence, pain escalation, low capacity.
router.get('/watchlist', asyncHandler(async (req, res) => {
  const cacheKey = 'personal-health:watchlist';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));

  const [confRows, logRows] = await Promise.allSettled([
    supabaseGet('recovery_confidence_today?select=*&limit=1'),
    supabaseGet('captains_log_entries?select=*&order=log_date.desc&limit=3'),
  ]);

  const conf = confRows.status === 'fulfilled' && confRows.value && confRows.value[0]
    ? confRows.value[0] : null;
  const logs = logRows.status === 'fulfilled' ? (logRows.value || []) : [];

  const flags = [];

  if (conf && conf.confidence_score < 25) {
    flags.push({ level: 'critical', message: `Recovery confidence critical: ${conf.confidence_score}%`, type: 'low_confidence' });
  } else if (conf && conf.confidence_score < 50) {
    flags.push({ level: 'warning', message: `Recovery confidence low: ${conf.confidence_score}%`, type: 'low_confidence' });
  }

  // Pain escalation: pain >= 7 for 3 consecutive days
  const highPainDays = logs.filter(l => l.pain_score != null && l.pain_score >= 7).length;
  if (highPainDays >= 2) {
    flags.push({ level: 'warning', message: `Pain ≥7 for ${highPainDays} recent days`, type: 'pain_escalation' });
  }

  const { score: capScore, status: capStatus } = computeCapacityScore(logs[0] || null);
  if (capStatus === 'Red') {
    flags.push({ level: 'critical', message: `Capacity RED — score ${capScore}/100`, type: 'low_capacity' });
  } else if (capStatus === 'Amber') {
    flags.push({ level: 'warning', message: `Capacity AMBER — score ${capScore}/100`, type: 'low_capacity' });
  }

  cacheManager.set(cacheKey, { flags, capacity_score: capScore, capacity_status: capStatus }, 120);
  res.json(successResponse({ flags, capacity_score: capScore, capacity_status: capStatus }, 200, { source: 'fresh' }));
}));

module.exports = router;
