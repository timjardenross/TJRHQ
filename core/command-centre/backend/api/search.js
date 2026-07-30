/**
 * Universal Search — /api/v1/search
 *
 * MSN-3A-001: Cross-domain retrieval across missions, decisions, log entries,
 * captured items, and intelligence briefs.
 *
 * GET /api/v1/search?q=<query>&types=<comma-list>&limit=<n>
 *
 * types: missions, decisions, log, captures, intelligence (default: all)
 * limit: per-domain result cap, max 20, default 5
 */

const express = require('express');
const router = express.Router();
const { asyncHandler, successResponse, ApiError } = require('../middleware/error-handling');
const { supabaseGet } = require('../connectors/supabase-connector');

const ALL_TYPES = ['missions', 'decisions', 'log', 'captures', 'intelligence'];

function _enc(v) {
  return encodeURIComponent(v);
}

async function searchMissions(q, limit) {
  const rows = await supabaseGet(
    `missions?or=(title.ilike.*${_enc(q)}*,mission_id.ilike.*${_enc(q)}*,domain.ilike.*${_enc(q)}*)&select=mission_id,title,status,domain,updated_at&order=updated_at.desc&limit=${limit}`
  );
  return (rows || []).map(r => ({
    type:       'mission',
    id:         r.mission_id,
    title:      r.title,
    detail:     `${r.status} · ${r.domain || '—'}`,
    timestamp:  r.updated_at,
    tab_target: 'command',
    entity_id:  r.mission_id,
  }));
}

async function searchDecisions(q, limit) {
  // decision-register.txt is a flat file — search via governance API isn't ideal;
  // query commander_events for decision-type events as a proxy
  const rows = await supabaseGet(
    `commander_events?or=(title.ilike.*${_enc(q)}*,description.ilike.*${_enc(q)}*)&event_type=eq.decision&select=id,title,description,created_at&order=created_at.desc&limit=${limit}`
  );
  return (rows || []).map(r => ({
    type:       'decision',
    id:         r.id,
    title:      r.title || '(untitled decision)',
    detail:     r.description ? r.description.slice(0, 120) : '',
    timestamp:  r.created_at,
    tab_target: 'records',
    entity_id:  r.id,
  }));
}

async function searchLog(q, limit) {
  const rows = await supabaseGet(
    `captains_log_entries?or=(overall_note.ilike.*${_enc(q)}*,todays_intention.ilike.*${_enc(q)}*)&select=log_date,todays_intention,overall_note,captain_capacity_rating&order=log_date.desc&limit=${limit}`
  );
  return (rows || []).map(r => ({
    type:       'log',
    id:         r.log_date,
    title:      `Captain's Log — ${r.log_date}`,
    detail:     (r.todays_intention || r.overall_note || '').slice(0, 120),
    timestamp:  r.log_date,
    tab_target: 'records',
    entity_id:  r.log_date,
  }));
}

async function searchCaptures(q, limit) {
  const rows = await supabaseGet(
    `captured_items?or=(title.ilike.*${_enc(q)}*,raw_text.ilike.*${_enc(q)}*)&select=id,title,raw_text,item_type,processing_status,captured_at&order=captured_at.desc&limit=${limit}`
  );
  return (rows || []).map(r => ({
    type:       'capture',
    id:         r.id,
    title:      r.title || r.raw_text?.slice(0, 80) || '(untitled)',
    detail:     `${r.item_type} · ${r.processing_status}`,
    timestamp:  r.captured_at,
    tab_target: 'records',
    entity_id:  r.id,
  }));
}

async function searchIntelligence(q, limit) {
  const rows = await supabaseGet(
    `intelligence_briefs?or=(headline.ilike.*${_enc(q)}*,body.ilike.*${_enc(q)}*,source.ilike.*${_enc(q)}*)&select=id,headline,body,source,published_at&order=published_at.desc&limit=${limit}`
  ).catch(() => null);
  if (!rows) return [];
  return rows.map(r => ({
    type:       'intelligence',
    id:         r.id,
    title:      r.headline || '(no headline)',
    detail:     (r.body || '').slice(0, 120),
    timestamp:  r.published_at,
    tab_target: 'astrometrics',
    entity_id:  r.id,
  }));
}

// ── GET /api/v1/search ───────────────────────────────────────────────────────
router.get('/', asyncHandler(async (req, res) => {
  const q     = (req.query.q || '').trim();
  const limit = Math.min(parseInt(req.query.limit) || 5, 20);
  const typeParam = (req.query.types || '').trim();
  const types = typeParam
    ? typeParam.split(',').map(t => t.trim().toLowerCase()).filter(t => ALL_TYPES.includes(t))
    : ALL_TYPES;

  if (!q) throw new ApiError(400, 'q (search query) is required');
  if (q.length < 2) throw new ApiError(400, 'q must be at least 2 characters');

  const searches = [];
  if (types.includes('missions'))     searches.push(searchMissions(q, limit));
  if (types.includes('decisions'))    searches.push(searchDecisions(q, limit));
  if (types.includes('log'))          searches.push(searchLog(q, limit));
  if (types.includes('captures'))     searches.push(searchCaptures(q, limit));
  if (types.includes('intelligence')) searches.push(searchIntelligence(q, limit));

  const settled = await Promise.allSettled(searches);
  const results = settled
    .filter(r => r.status === 'fulfilled')
    .flatMap(r => r.value || []);

  // Sort by timestamp desc across all domains
  results.sort((a, b) => {
    if (!a.timestamp) return 1;
    if (!b.timestamp) return -1;
    return new Date(b.timestamp) - new Date(a.timestamp);
  });

  const grouped = {};
  for (const r of results) {
    if (!grouped[r.type]) grouped[r.type] = [];
    grouped[r.type].push(r);
  }

  res.json(successResponse({
    query:   q,
    total:   results.length,
    types:   types,
    results,
    grouped,
  }, 200, { limit, domains_searched: types.length }));
}));

module.exports = router;
