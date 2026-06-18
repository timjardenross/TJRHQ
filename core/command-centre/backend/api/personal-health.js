/**
 * Personal Health API — /api/v1/personal-health/*
 *
 * Exposes summary-level health status from health_daily_logs (Supabase).
 * Privacy boundary: this module reads only summary-level aggregate fields.
 * No clinical documents, diagnoses, medication details, or imaging data
 * are stored in or returned from this endpoint.
 *
 * Endpoints:
 *   GET /status   → GREEN/AMBER/RED status + key indicators (widget-friendly)
 *   GET /today    → Full today's log row (or null if not yet submitted)
 */

const express = require('express');
const router = express.Router();
const { cacheManager } = require('../cache/cache-manager');
const { asyncHandler, successResponse } = require('../middleware/error-handling');
const {
  getHealthLogToday,
  getHealthLogLatest,
  getHealthStatusSummary,
  computeHealthStatus,
  getHealthEventsToday,
} = require('../connectors/supabase-connector');
const { isConfigured } = require('../connectors/supabase-client');

const CACHE_TTL = 90; // seconds — short enough to reflect a fresh check-in promptly

// ── GET /status ───────────────────────────────────────────────────────────────

router.get('/status', asyncHandler(async (req, res) => {
  const cacheKey = 'personal-health:status';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value && !isStale) {
    return res.json(successResponse(value, 200, {
      source: 'cache',
      dataSource: 'cache',
    }));
  }

  if (!isConfigured()) {
    const fallback = {
      today_logged: false,
      status: 'UNKNOWN',
      log_date: null,
      pain_score: null,
      energy: null,
      mood: null,
      sleep_quality: null,
      error: 'Supabase not configured',
    };
    return res.json(successResponse(fallback, 200, { source: 'error-fallback' }));
  }

  try {
    const [summary, slackEntry, events] = await Promise.all([
      getHealthStatusSummary(),
      getHealthLogToday(),
      getHealthEventsToday(),
    ]);

    // Attach Slack check-in as a separate block if it has data
    if (slackEntry) {
      summary.slack_checkin = {
        logged: true,
        log_date: slackEntry.log_date,
        pain_score: slackEntry.pain_score ?? null,
        energy: slackEntry.energy ?? null,
        mood: slackEntry.mood ?? null,
        sleep_hours: slackEntry.sleep_hours ?? null,
        sleep_quality: slackEntry.sleep_quality ?? null,
        cpap_hours: slackEntry.cpap_hours ?? null,
        movement_notes: slackEntry.movement_notes ?? null,
        work_location: slackEntry.work_location ?? null,
        sitting_tolerance_minutes: slackEntry.sitting_tolerance_minutes ?? null,
        workload_constraint: slackEntry.workload_constraint ?? null,
        notes: slackEntry.notes ?? null,
        status: computeHealthStatus(slackEntry),
        source: slackEntry.source ?? 'slack',
      };
    } else {
      summary.slack_checkin = { logged: false };
    }

    // Attach today's health events
    summary.health_events = (events || []).map(e => ({
      event_date: e.event_date,
      event_type: e.event_type,
      title: e.title,
      description: e.description ?? null,
      provider: e.provider ?? null,
      outcome: e.outcome ?? null,
      follow_up_required: e.follow_up_required ?? false,
      follow_up_date: e.follow_up_date ?? null,
    }));

    cacheManager.set(cacheKey, summary, CACHE_TTL);
    return res.json(successResponse(summary, 200, {
      source: 'fresh',
      dataSource: 'supabase',
    }));
  } catch (err) {
    const fallback = {
      today_logged: false,
      status: 'UNKNOWN',
      log_date: null,
      pain_score: null,
      energy: null,
      mood: null,
      sleep_quality: null,
      slack_checkin: { logged: false },
      error: err.message,
    };
    return res.json(successResponse(fallback, 200, { source: 'error-fallback' }));
  }
}));

// ── GET /today ────────────────────────────────────────────────────────────────

router.get('/today', asyncHandler(async (req, res) => {
  const cacheKey = 'personal-health:today';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value && !isStale) {
    return res.json(successResponse(value, 200, { source: 'cache' }));
  }

  if (!isConfigured()) {
    return res.json(successResponse({ entry: null, exists: false, error: 'Supabase not configured' }, 200, {
      source: 'error-fallback',
    }));
  }

  try {
    const entry = await getHealthLogToday();
    const data = {
      entry: entry || null,
      exists: !!entry,
      status: entry ? computeHealthStatus(entry) : null,
    };
    cacheManager.set(cacheKey, data, CACHE_TTL);
    return res.json(successResponse(data, 200, { source: 'fresh', dataSource: 'supabase' }));
  } catch (err) {
    return res.json(successResponse({ entry: null, exists: false, error: err.message }, 200, {
      source: 'error-fallback',
    }));
  }
}));

module.exports = router;
