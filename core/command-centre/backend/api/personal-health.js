/**
 * Personal Health API — /api/v1/personal-health/*
 *
 * MSN-F: Capacity check-in data from Supabase.
 * Sources: capacity_checkins table, capacity_checkins_today view
 *          (recovery_pulses / recovery_confidence_today / recovery_pulse_adherence_7d's
 *          successors — those tables/views remain in place as historical data
 *          but are no longer read from or written to here), captains_log_entries
 *          (capacity/pain).
 */

const express = require('express');
const router = express.Router();
const { cacheManager } = require('../cache/cache-manager');
const { asyncHandler, successResponse } = require('../middleware/error-handling');
const { supabaseGet, computeCapacityScore } = require('../connectors/supabase-connector');

// ── GET /api/v1/personal-health/status ─────────────────────────────────────
// Recovery confidence today + capacity status.
router.get('/status', asyncHandler(async (req, res) => {
  const cacheKey = 'personal-health:status';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));

  const [confidence, logRows] = await Promise.allSettled([
    supabaseGet('capacity_checkins_today?select=*&limit=1'),
    supabaseGet('captains_log_entries?select=*&order=log_date.desc&limit=1'),
  ]);

  const conf = confidence.status === 'fulfilled' && confidence.value && confidence.value[0]
    ? confidence.value[0] : null;
  const latestLog = logRows.status === 'fulfilled' && logRows.value && logRows.value[0]
    ? logRows.value[0] : null;

  const { score: capacityScore, status: capacityStatus } = computeCapacityScore(latestLog);

  const data = {
    // capacity_checkins_today (recovery_confidence_today's successor,
    // 2026-08-22 realign): check-ins are unlimited per day, not slotted
    // morning/midday/evening, so there's no confidence percentage or
    // *_done booleans any more — checkins_today/has_checked_in/
    // checkin_label are the honest replacement.
    recovery_confidence: conf ? {
      checkins_today:              conf.checkins_today ?? 0,
      has_checked_in:              conf.has_checked_in ?? false,
      checkin_label:               conf.checkin_label ?? 'No check-in today',
      latest_capacity_state:       conf.latest_capacity_state ?? null,
      latest_regulation_state:     conf.latest_regulation_state ?? null,
      latest_pain_score:           conf.latest_pain_score ?? null,
      latest_executive_function:   conf.latest_executive_function ?? null,
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

  // capacity_checkins is recovery_pulse_adherence_7d / recovery_pulses'
  // successor (2026-08-22 realign): no separate adherence view exists yet,
  // so both fields below are sourced from the same 28-day capacity_checkins
  // query. `recent_pulses` renamed to `recent_checkins` to match.
  const checkins = await supabaseGet(
    'capacity_checkins?select=log_date,checkin_type,captured_at,capacity_state,regulation_state,pain_score,executive_function,selected_action&checkin_type=eq.capacity&order=captured_at.desc&limit=28'
  );

  const data = {
    adherence_7d: checkins || [],
    recent_checkins: checkins || [],
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
    supabaseGet('capacity_checkins_today?select=*&limit=1'),
    supabaseGet('captains_log_entries?select=*&order=log_date.desc&limit=3'),
  ]);

  const conf = confRows.status === 'fulfilled' && confRows.value && confRows.value[0]
    ? confRows.value[0] : null;
  const logs = logRows.status === 'fulfilled' ? (logRows.value || []) : [];

  const flags = [];

  // capacity_checkins_today (recovery_confidence_today's successor,
  // 2026-08-22 realign) has no confidence percentage — check-ins aren't
  // slotted/counted toward a target any more. Gate on whether a check-in
  // has happened at all today instead of fabricating a fake percentage.
  if (!conf || !conf.has_checked_in) {
    flags.push({ level: 'warning', message: 'No capacity check-in today', type: 'low_confidence' });
  } else if (conf.latest_capacity_state === 'red') {
    flags.push({ level: 'critical', message: `Latest capacity check-in: red (${conf.latest_regulation_state || 'unknown regulation'})`, type: 'low_confidence' });
  } else if (conf.latest_capacity_state === 'orange') {
    flags.push({ level: 'warning', message: `Latest capacity check-in: orange (${conf.latest_regulation_state || 'unknown regulation'})`, type: 'low_confidence' });
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

// ── POST /api/v1/personal-health/pulse ─────────────────────────────────────
// RETIRED 2026-08-22: this endpoint used to upsert into recovery_pulses, a
// table the Telegram bot no longer reads or writes (capacity check-ins are
// now captured via the XO Telegram bot's /capacity command into
// capacity_checkins, which has no pulse_type/slot concept — check-ins are
// unlimited per day, not capped at 3 named slots). Writing to
// recovery_pulses here would be a silent, invisible duplicate write path
// that nothing downstream reads any more, so the handler is retired rather
// than repointed. The route is kept registered (it's a documented public
// API surface per the note this comment replaces) but now only returns 410.
router.post('/pulse', asyncHandler(async (req, res) => {
  res.status(410).json({
    error: 'This endpoint is retired. Capacity check-ins are now captured via the XO Telegram bot (/capacity command).',
  });
}));

module.exports = router;
