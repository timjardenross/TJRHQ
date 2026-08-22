/**
 * Unified Timeline — /api/v1/timeline
 *
 * MSN-3A-002: Normalise events from 6 sources into a single chronological feed.
 *
 * Sources:
 *   mission_state_transitions — lifecycle changes
 *   capacity_checkins         — health check-ins (recovery_pulses' successor)
 *   captains_log_entries      — daily log filings
 *   commander_events          — escalations, decisions, notes
 *   intelligence_briefs       — published briefs
 *   captured_items            — quick captures
 *
 * GET /api/v1/timeline?from=<ISO>&to=<ISO>&types=<comma-list>&limit=<n>
 *
 * Unified event schema:
 *   { id, event_type, source, title, detail, timestamp, entity_id, entity_type, metadata }
 */

const express = require('express');
const router = express.Router();
const { asyncHandler, successResponse, ApiError } = require('../middleware/error-handling');
const { supabaseGet } = require('../connectors/supabase-connector');
const { cacheManager } = require('../cache/cache-manager');

const ALL_TYPES = ['missions', 'health', 'log', 'events', 'intelligence', 'captures'];

function _enc(v) { return encodeURIComponent(v); }

function _dateFilter(from, to) {
  const parts = [];
  if (from) parts.push(`gte.${from}`);
  if (to)   parts.push(`lte.${to}`);
  return parts;
}

async function fetchMissionTransitions(from, to, limit) {
  let q = `mission_state_transitions?select=id,mission_id,from_state,to_state,actor,transitioned_at&order=transitioned_at.desc&limit=${limit}`;
  if (from) q += `&transitioned_at=gte.${_enc(from)}`;
  if (to)   q += `&transitioned_at=lte.${_enc(to)}`;
  const rows = await supabaseGet(q).catch(() => []);
  return (rows || []).map(r => ({
    id:          `mst-${r.id}`,
    event_type:  'mission_transition',
    source:      'missions',
    title:       `Mission ${r.mission_id}: ${r.from_state || '?'} → ${r.to_state}`,
    detail:      r.actor ? `by ${r.actor}` : null,
    timestamp:   r.transitioned_at,
    entity_id:   r.mission_id,
    entity_type: 'mission',
    metadata:    { from_state: r.from_state, to_state: r.to_state },
  }));
}

async function fetchCapacityCheckins(from, to, limit) {
  // capacity_checkins is recovery_pulses' successor (Captain directive,
  // 2026-08-1x migration 0148/0150): no pulse_type/slot concept — check-ins
  // are unlimited per day. Filter to checkin_type='capacity' so evening
  // reflections don't show up as quick check-ins here.
  let q = `capacity_checkins?select=id,log_date,checkin_type,pain_score,capacity_state,regulation_state,captured_at&checkin_type=eq.capacity&order=captured_at.desc&limit=${limit}`;
  if (from) q += `&captured_at=gte.${_enc(from)}`;
  if (to)   q += `&captured_at=lte.${_enc(to)}`;
  const rows = await supabaseGet(q).catch(() => []);
  return (rows || []).map(r => {
    const signals = [];
    if (r.pain_score != null) signals.push(`pain ${r.pain_score}`);
    if (r.capacity_state)   signals.push(`capacity ${r.capacity_state}`);
    if (r.regulation_state) signals.push(`regulation ${r.regulation_state}`);
    return {
      id:          `cc-${r.id || r.log_date}`,
      event_type:  'capacity_checkin',
      source:      'health',
      title:       `Capacity check-in (${r.log_date})`,
      detail:      signals.length ? signals.join(' · ') : null,
      timestamp:   r.captured_at || `${r.log_date}T00:00:00Z`,
      entity_id:   r.log_date,
      entity_type: 'health',
      metadata:    { capacity_state: r.capacity_state, regulation_state: r.regulation_state, pain_score: r.pain_score },
    };
  });
}

async function fetchLogEntries(from, to, limit) {
  let q = `captains_log_entries?select=log_date,todays_intention,overall_note,captain_capacity_rating,pain_score&order=log_date.desc&limit=${limit}`;
  if (from) q += `&log_date=gte.${_enc(from.slice(0, 10))}`;
  if (to)   q += `&log_date=lte.${_enc(to.slice(0, 10))}`;
  const rows = await supabaseGet(q).catch(() => []);
  return (rows || []).map(r => ({
    id:          `log-${r.log_date}`,
    event_type:  'log_entry',
    source:      'log',
    title:       `Captain's Log filed — ${r.log_date}`,
    detail:      r.todays_intention ? r.todays_intention.slice(0, 100) : null,
    timestamp:   `${r.log_date}T00:00:00Z`,
    entity_id:   r.log_date,
    entity_type: 'log',
    metadata:    { capacity: r.captain_capacity_rating, pain: r.pain_score },
  }));
}

async function fetchCommanderEvents(from, to, limit) {
  let q = `commander_events?select=id,event_type,title,description,mission_id,created_at&order=created_at.desc&limit=${limit}`;
  if (from) q += `&created_at=gte.${_enc(from)}`;
  if (to)   q += `&created_at=lte.${_enc(to)}`;
  const rows = await supabaseGet(q).catch(() => []);
  return (rows || []).map(r => ({
    id:          `ev-${r.id}`,
    event_type:  r.event_type || 'event',
    source:      'events',
    title:       r.title || `Event: ${r.event_type}`,
    detail:      r.description ? r.description.slice(0, 120) : null,
    timestamp:   r.created_at,
    entity_id:   r.mission_id || r.id,
    entity_type: 'event',
    metadata:    { event_type: r.event_type, mission_id: r.mission_id },
  }));
}

async function fetchIntelligenceBriefs(from, to, limit) {
  let q = `intelligence_briefs?select=id,headline,source,published_at&order=published_at.desc&limit=${limit}`;
  if (from) q += `&published_at=gte.${_enc(from)}`;
  if (to)   q += `&published_at=lte.${_enc(to)}`;
  const rows = await supabaseGet(q).catch(() => null);
  if (!rows) return [];
  return rows.map(r => ({
    id:          `intel-${r.id}`,
    event_type:  'intelligence_brief',
    source:      'intelligence',
    title:       r.headline || 'Intelligence brief',
    detail:      r.source ? `Source: ${r.source}` : null,
    timestamp:   r.published_at,
    entity_id:   r.id,
    entity_type: 'intelligence',
    metadata:    { source: r.source },
  }));
}

async function fetchCaptures(from, to, limit) {
  let q = `captured_items?select=id,title,raw_text,item_type,processing_status,captured_at&order=captured_at.desc&limit=${limit}`;
  if (from) q += `&captured_at=gte.${_enc(from)}`;
  if (to)   q += `&captured_at=lte.${_enc(to)}`;
  const rows = await supabaseGet(q).catch(() => []);
  return (rows || []).map(r => ({
    id:          `cap-${r.id}`,
    event_type:  'capture',
    source:      'captures',
    title:       r.title || r.raw_text?.slice(0, 80) || '(captured item)',
    detail:      `${r.item_type} · ${r.processing_status}`,
    timestamp:   r.captured_at,
    entity_id:   r.id,
    entity_type: 'capture',
    metadata:    { item_type: r.item_type, status: r.processing_status },
  }));
}

// ── GET /api/v1/timeline ─────────────────────────────────────────────────────
router.get('/', asyncHandler(async (req, res) => {
  const from  = req.query.from  || null;
  const to    = req.query.to    || null;
  const limit = Math.min(parseInt(req.query.limit) || 50, 200);

  const typeParam = (req.query.types || '').trim();
  const types = typeParam
    ? typeParam.split(',').map(t => t.trim().toLowerCase()).filter(t => ALL_TYPES.includes(t))
    : ALL_TYPES;

  // Per-source limit: spread the total across sources, cap at 30 per source
  const perSource = Math.min(Math.ceil(limit / types.length) + 5, 30);

  const cacheKey = `timeline:${from}:${to}:${types.join(',')}:${limit}`;
  const cached = cacheManager.get(cacheKey);
  if (cached.value) return res.json(successResponse(cached.value, 200, { source: 'cache' }));

  const fetchers = [];
  if (types.includes('missions'))     fetchers.push(fetchMissionTransitions(from, to, perSource));
  if (types.includes('health'))       fetchers.push(fetchCapacityCheckins(from, to, perSource));
  if (types.includes('log'))          fetchers.push(fetchLogEntries(from, to, perSource));
  if (types.includes('events'))       fetchers.push(fetchCommanderEvents(from, to, perSource));
  if (types.includes('intelligence')) fetchers.push(fetchIntelligenceBriefs(from, to, perSource));
  if (types.includes('captures'))     fetchers.push(fetchCaptures(from, to, perSource));

  const settled = await Promise.allSettled(fetchers);
  const events = settled
    .filter(r => r.status === 'fulfilled')
    .flatMap(r => r.value || [])
    .filter(e => e.timestamp);

  // Sort descending
  events.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

  const trimmed = events.slice(0, limit);
  const data = {
    from:   from || null,
    to:     to   || null,
    total:  trimmed.length,
    types,
    events: trimmed,
  };

  cacheManager.set(cacheKey, data, 60);
  res.json(successResponse(data, 200, { source: 'fresh', limit }));
}));

// ── GET /api/v1/timeline/recent — convenience: last 7 days, all types ────────
router.get('/recent', asyncHandler(async (req, res) => {
  const limit  = Math.min(parseInt(req.query.limit) || 30, 100);
  const days   = Math.min(parseInt(req.query.days) || 7, 30);
  const from   = new Date(Date.now() - days * 86400000).toISOString();
  req.query.from  = from;
  req.query.limit = String(limit);
  // Delegate to main handler
  return router.handle({ ...req, url: `/?from=${encodeURIComponent(from)}&limit=${limit}`, query: { from, limit: String(limit) } }, res, () => {});
}));

module.exports = router;
