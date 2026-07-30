/**
 * Mission Registry API — /api/v1/missions/*
 *
 * Data Source: Supabase public.missions table (single system of record)
 * Cache TTL: 60 seconds
 *
 * MSN-BOT-SOR: mission-index.txt and missions.db are NOT authoritative here.
 * All reads go through supabaseGet() → PostgREST.
 */

const express = require('express');
const router = express.Router();
const { cacheManager } = require('../cache/cache-manager');
const { asyncHandler, successResponse, ApiError } = require('../middleware/error-handling');
const { supabaseGet, supabasePatch } = require('../connectors/supabase-connector');

const CLOSED_STATUSES = ['Closed', 'Archived'];

router.get('/summary', asyncHandler(async (req, res) => {
  const cacheKey = 'missions:summary';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));

  const rows = await supabaseGet('missions?select=*&order=created_at.desc&limit=200');
  const active = rows.filter(m => !CLOSED_STATUSES.includes(m.status));
  const blocked = rows.filter(m => m.status === 'Blocked');
  const byStatus = {};
  for (const m of rows) byStatus[m.status] = (byStatus[m.status] || 0) + 1;

  const data = { total: rows.length, active: active.length, blocked: blocked.length, closed: rows.length - active.length, by_status: byStatus };
  cacheManager.set(cacheKey, data, 60);
  res.json(successResponse(data, 200, { source: 'fresh', dataSource: 'supabase' }));
}));

router.get('/active', asyncHandler(async (req, res) => {
  const cacheKey = 'missions:active';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));

  const rows = await supabaseGet(`missions?status=not.in.(${CLOSED_STATUSES.join(',')})&select=*&order=created_at.desc&limit=200`);
  cacheManager.set(cacheKey, rows, 60);
  res.json(successResponse(rows, 200, { source: 'fresh', count: rows.length, dataSource: 'supabase' }));
}));

router.get('/blocked', asyncHandler(async (req, res) => {
  const cacheKey = 'missions:blocked';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));

  const rows = await supabaseGet('missions?status=eq.Blocked&select=*&order=created_at.desc');
  cacheManager.set(cacheKey, rows, 60);
  res.json(successResponse(rows, 200, { source: 'fresh', count: rows.length, dataSource: 'supabase' }));
}));

// GET /list — paginated mission list for Command Console queue
// Excludes Closed/Archived by default; ?include_closed=1 to override
router.get('/list', asyncHandler(async (req, res) => {
  const limit = Math.min(parseInt(req.query.limit) || 50, 200);
  const includeClosed = req.query.include_closed === '1';
  const cacheKey = `missions:list:${limit}:${includeClosed}`;
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));

  let qs = `missions?select=*&order=created_at.desc&limit=${limit}`;
  if (!includeClosed) qs += `&status=not.in.(${CLOSED_STATUSES.join(',')})`;
  const rows = await supabaseGet(qs);
  cacheManager.set(cacheKey, rows, 30);
  res.json(successResponse(rows, 200, { source: 'fresh', count: rows.length, dataSource: 'supabase' }));
}));

// PATCH /:id/status — update mission status, record transition
// Body: { status: string, note?: string, actor?: string }
const VALID_STATUSES = [
  'Idea', 'Designed', 'Approved for Engineering', 'Implemented',
  'Tested', 'Awaiting Number One Review', 'Validated',
  'Awaiting XO Approval', 'Awaiting Captain Approval', 'Approved',
  'Closed', 'Blocked', 'Archived', 'Requires Rework',
];

router.patch('/:id/status', asyncHandler(async (req, res) => {
  const { id } = req.params;
  const { status, note, actor } = req.body;

  if (!status) throw new ApiError(400, 'status is required');
  if (!VALID_STATUSES.includes(status)) {
    throw new ApiError(400, `Invalid status "${status}". Valid values: ${VALID_STATUSES.join(', ')}`);
  }

  const mid = id.startsWith('USS-TJR-') ? id : `USS-TJR-${id}`;
  const now = new Date().toISOString();

  // Fetch current mission to get previous status
  let current = null;
  for (const tryId of [mid, id]) {
    const rows = await supabaseGet(`missions?id=eq.${encodeURIComponent(tryId)}&select=id,status&limit=1`);
    if (rows && rows.length > 0) { current = rows[0]; break; }
  }
  if (!current) throw new ApiError(404, `Mission ${id} not found`);

  const fromStatus = current.status;
  const updated = await supabasePatch(`missions?id=eq.${encodeURIComponent(current.id)}`, {
    status,
    updated_at: now.replace('Z', '').replace('T', 'T'),
  });

  // Record transition
  try {
    const { supabaseUpsert } = require('../connectors/supabase-connector');
    const crypto = require('crypto');
    await supabaseUpsert('mission_state_transitions', {
      id: crypto.randomUUID(),
      mission_id: current.id,
      from_state: fromStatus || null,
      to_state: status,
      actor: actor || 'Captain',
      transitioned_at: now,
      note: note || null,
      source: 'command-centre-ui',
    }, 'id');
  } catch (transErr) {
    console.warn('[missions] transition record failed (non-blocking):', transErr.message);
  }

  // Invalidate list caches
  cacheManager.clear();

  res.json(successResponse({ id: current.id, from_status: fromStatus, to_status: status, updated_at: now }, 200, {
    source: 'fresh', dataSource: 'supabase'
  }));
}));

router.get('/:id/detail', asyncHandler(async (req, res) => {
  const { id } = req.params;
  const cacheKey = `mission:${id}:detail`;
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));

  const mid = id.startsWith('USS-TJR-') ? id : `USS-TJR-${id}`;
  let rows = await supabaseGet(`missions?mission_id=eq.${encodeURIComponent(mid)}&select=*&limit=1`);
  if (!rows || rows.length === 0) {
    rows = await supabaseGet(`missions?mission_id=eq.${encodeURIComponent(id)}&select=*&limit=1`);
  }
  if (!rows || rows.length === 0) throw new ApiError(404, `Mission ${id} not found`);

  const mission = rows[0];
  cacheManager.set(cacheKey, mission, 60);
  res.json(successResponse(mission, 200, { source: 'fresh', dataSource: 'supabase' }));
}));

module.exports = router;
