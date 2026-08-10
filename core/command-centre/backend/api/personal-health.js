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
const { supabaseGet, supabaseUpsert, computeCapacityScore } = require('../connectors/supabase-connector');

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
      // Fixed 2026-08-10 while realigning the adjacent mood/stress fields:
      // the view's real columns are pulses_completed/recovery_confidence,
      // not pulse_count/confidence_score — this always read 0 before.
      pulses_today:     conf.pulses_completed ?? 0,
      confidence_score: conf.recovery_confidence ?? 0,
      confidence_label: conf.confidence_label ?? 'No data',
      morning_done:     conf.morning_done ?? false,
      midday_done:      conf.midday_done ?? false,
      end_of_day_done:  conf.end_of_day_done ?? false,
      evening_done:     conf.evening_done ?? false,
      latest_energy:         conf.latest_energy ?? null,
      // Recovery Pulse realign (2026-08-10): recovery_confidence_today no
      // longer exposes latest_mood/latest_stress (dropped in migration
      // 0115) — it exposes the canonical latest_nervous_system/
      // latest_body_signals instead, which the Telegram bot actually
      // populates. latest_pain also corrected to the view's real column
      // name (latest_pain_score); the old key always read null.
      latest_nervous_system: conf.latest_nervous_system ?? null,
      latest_body_signals:   conf.latest_body_signals ?? null,
      latest_readiness:      conf.latest_readiness ?? null,
      latest_pain:           conf.latest_pain_score ?? null,
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

  // Canonical fields (energy/nervous_system/body_signals/day_win) — mood/
  // stress dropped from this select, see 2026-08-10 realign note above.
  const pulses = await supabaseGet(
    'recovery_pulses?select=log_date,pulse_type,pain_score,energy,nervous_system,body_signals,day_win,readiness&order=captured_at.desc&limit=28'
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

// ── POST /api/v1/personal-health/pulse ─────────────────────────────────────
// Submit a recovery pulse check-in from the web UI.
//
// Recovery Pulse decommission/realign (Captain directive, 2026-08-10): the
// Telegram bot (telegram-bots/xo/app.py) writes energy/nervous_system/
// body_signals/day_win and is now canonical; mood/stress were this
// endpoint's own alternate, divergent write path (a second independent
// writer alongside the LCARS Portal's Medical Bay page, which has been
// repointed the same way). This endpoint had no confirmed live caller at
// the time of this change, but is repointed rather than removed since it's
// a public API surface that could be hit directly. Pulse types are now the
// canonical 3 (morning/midday/evening — end_of_day was folded into midday,
// see migration 0115); the field/value sets below mirror telegram-bots/xo/
// app.py's _kb_energy / _kb_mood (nervous system) / _kb_stress (body
// signals) / _kb_day_win exactly, and the recovery_pulses CHECK constraints
// (nervous_system: calm/activated/dysregulated, body_signals: quiet/
// present/significant, day_win: something_did/nothing_much/rough_day).
// Body: { pulse_type, pain_score?, energy?, nervous_system?, body_signals?, day_win?, readiness?, notes? }
const VALID_PULSE_TYPES    = ['morning', 'midday', 'evening'];
const VALID_ENERGY         = ['low', 'moderate', 'high'];
const VALID_NERVOUS_SYSTEM = ['calm', 'activated', 'dysregulated'];
const VALID_BODY_SIGNALS   = ['quiet', 'present', 'significant'];
const VALID_DAY_WIN        = ['something_did', 'nothing_much', 'rough_day'];
const VALID_READINESS      = ['low', 'moderate', 'high'];

router.post('/pulse', asyncHandler(async (req, res) => {
  const { pulse_type, pain_score, energy, nervous_system, body_signals, day_win, readiness, notes } = req.body || {};

  if (!pulse_type || !VALID_PULSE_TYPES.includes(pulse_type)) {
    throw new ApiError(400, `pulse_type must be one of: ${VALID_PULSE_TYPES.join(', ')}`);
  }
  if (pain_score != null && (isNaN(Number(pain_score)) || Number(pain_score) < 0 || Number(pain_score) > 10)) {
    throw new ApiError(400, 'pain_score must be 0–10');
  }
  if (energy         && !VALID_ENERGY.includes(energy))                 throw new ApiError(400, `energy must be: ${VALID_ENERGY.join(', ')}`);
  if (nervous_system  && !VALID_NERVOUS_SYSTEM.includes(nervous_system)) throw new ApiError(400, `nervous_system must be: ${VALID_NERVOUS_SYSTEM.join(', ')}`);
  if (body_signals    && !VALID_BODY_SIGNALS.includes(body_signals))     throw new ApiError(400, `body_signals must be: ${VALID_BODY_SIGNALS.join(', ')}`);
  if (day_win         && !VALID_DAY_WIN.includes(day_win))               throw new ApiError(400, `day_win must be: ${VALID_DAY_WIN.join(', ')}`);
  if (readiness       && !VALID_READINESS.includes(readiness))           throw new ApiError(400, `readiness must be: ${VALID_READINESS.join(', ')}`);

  const today = new Date().toISOString().split('T')[0];
  const payload = {
    log_date:    today,
    pulse_type,
    source:      'manual',
    captured_at: new Date().toISOString(),
    ...(pain_score != null && { pain_score: Number(pain_score) }),
    ...(energy         && { energy }),
    ...(nervous_system && { nervous_system }),
    ...(body_signals   && { body_signals }),
    ...(day_win        && { day_win }),
    ...(readiness      && { readiness }),
    ...(notes          && { notes: notes.trim() }),
  };

  const result = await supabaseUpsert('recovery_pulses', payload, 'log_date,pulse_type');
  cacheManager.clear(); // Invalidate so status endpoint refreshes
  res.json(successResponse(result, 201, { log_date: today, pulse_type, source: 'web' }));
}));

// ── GET /api/v1/personal-health/trends ─────────────────────────────────────
// 14-day sleep and capacity trend from captains_log_entries.
router.get('/trends', asyncHandler(async (req, res) => {
  const days = Math.min(parseInt(req.query.days) || 14, 30);
  const cacheKey = `personal-health:trends:${days}`;
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));

  const entries = await supabaseGet(
    `captains_log_entries?select=log_date,pain_score,energy,mood,sleep_hours,sleep_quality,cpap_hours,captain_capacity_rating&order=log_date.asc&limit=${days}`
  );

  const rows = (entries || []).map(e => {
    const { score, status } = computeCapacityScore(e);
    return {
      date:       e.log_date,
      pain:       e.pain_score,
      energy:     e.energy,
      mood:       e.mood,
      sleep_h:    e.sleep_hours,
      sleep_q:    e.sleep_quality,
      cpap_h:     e.cpap_hours,
      capacity:   score,
      cap_status: status,
    };
  });

  // Correlation: pain vs sleep
  const paired = rows.filter(r => r.pain != null && r.sleep_h != null);
  let correlation = null;
  if (paired.length >= 3) {
    const painAvg  = paired.reduce((s, r) => s + r.pain, 0) / paired.length;
    const sleepAvg = paired.reduce((s, r) => s + r.sleep_h, 0) / paired.length;
    const cov = paired.reduce((s, r) => s + (r.pain - painAvg) * (r.sleep_h - sleepAvg), 0) / paired.length;
    const painSD  = Math.sqrt(paired.reduce((s, r) => s + (r.pain - painAvg) ** 2, 0) / paired.length);
    const sleepSD = Math.sqrt(paired.reduce((s, r) => s + (r.sleep_h - sleepAvg) ** 2, 0) / paired.length);
    correlation = painSD && sleepSD ? Math.round((cov / (painSD * sleepSD)) * 100) / 100 : null;
  }

  const data = { days, rows, correlation, data_points: rows.length };
  cacheManager.set(cacheKey, data, 120);
  res.json(successResponse(data, 200, { source: 'fresh', dataSource: 'supabase' }));
}));

module.exports = router;
