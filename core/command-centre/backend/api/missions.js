/**
 * Mission Registry API — /api/v1/missions/*
 *
 * Data Source: core/mission-control/registry/mission-index.txt (file-based)
 * Cache TTL: 60 seconds
 */

const express = require('express');
const router = express.Router();
const { cacheManager } = require('../cache/cache-manager');
const { asyncHandler, successResponse, ApiError } = require('../middleware/error-handling');
const { getActiveMissions, getBlockedMissions, getMissionSummary, getMissionById } = require('../connectors/mission-registry-reader');

router.get('/summary', asyncHandler(async (req, res) => {
  const cacheKey = 'missions:summary';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));

  const data = getMissionSummary();
  cacheManager.set(cacheKey, data, 60);
  res.json(successResponse(data, 200, { source: 'fresh', dataSource: 'mission-index.txt' }));
}));

router.get('/active', asyncHandler(async (req, res) => {
  const cacheKey = 'missions:active';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));

  const missions = getActiveMissions();
  cacheManager.set(cacheKey, missions, 60);
  res.json(successResponse(missions, 200, { source: 'fresh', count: missions.length, dataSource: 'mission-index.txt' }));
}));

router.get('/blocked', asyncHandler(async (req, res) => {
  const cacheKey = 'missions:blocked';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));

  const missions = getBlockedMissions();
  cacheManager.set(cacheKey, missions, 60);
  res.json(successResponse(missions, 200, { source: 'fresh', count: missions.length }));
}));

router.get('/:id/detail', asyncHandler(async (req, res) => {
  const { id } = req.params;
  const cacheKey = `mission:${id}:detail`;
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));

  const mission = getMissionById(id);
  if (!mission) throw new ApiError(404, `Mission ${id} not found`);

  cacheManager.set(cacheKey, mission, 60);
  res.json(successResponse(mission, 200, { source: 'fresh' }));
}));

module.exports = router;
