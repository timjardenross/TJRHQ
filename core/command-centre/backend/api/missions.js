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
const { supabaseGet } = require('../connectors/supabase-connector');

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
