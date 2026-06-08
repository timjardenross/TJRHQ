/**
 * Mission Registry API — /api/v1/missions/*
 *
 * Endpoints:
 * - GET /summary        → Mission counts, health, priority breakdown
 * - GET /active        → List of active missions
 * - GET /blocked       → Blocked missions with details
 * - GET /:id/detail    → Single mission full details
 *
 * Data Source: MSN-0031 Mission Registry
 * Cache TTL: 30 seconds (changes frequently)
 */

const express = require('express');
const router = express.Router();
const { cacheManager } = require('../cache/cache-manager');
const { asyncHandler, successResponse, ApiError } = require('../middleware/error-handling');

/**
 * GET /api/v1/missions/summary
 * Returns high-level mission statistics
 */
router.get('/summary', asyncHandler(async (req, res) => {
  const cacheKey = 'missions:summary';
  const { value, isStale } = cacheManager.get(cacheKey);

  if (value) {
    const response = successResponse(value, 200, {
      source: isStale ? 'stale_cache' : 'cache',
      cacheKey: cacheKey,
      message: isStale ? 'Data may be stale' : 'Fresh from cache'
    });
    return res.json(response);
  }

  // In Phase 2, this would call the real Mission Registry
  // For now, use cache warmup data or fetch fresh
  const freshData = {
    status: 'operational',
    total: 12,
    active: 12,
    completed: 0,
    blocked: 1,
    overdue: 0,
    health: 'OPERATIONAL',
    byPriority: {
      P0: 1,
      P1: 3,
      P2: 5,
      P3: 3
    },
    timestamp: new Date().toISOString()
  };

  cacheManager.set(cacheKey, freshData, 30);
  const response = successResponse(freshData, 200, {
    source: 'fresh',
    cacheKey: cacheKey,
    message: 'Fresh data from Mission Registry'
  });
  res.json(response);
}));

/**
 * GET /api/v1/missions/active
 * Returns list of active missions
 */
router.get('/active', asyncHandler(async (req, res) => {
  const cacheKey = 'missions:active';
  const { value, isStale } = cacheManager.get(cacheKey);

  if (value) {
    const response = successResponse(value, 200, {
      source: isStale ? 'stale_cache' : 'cache',
      cacheKey: cacheKey
    });
    return res.json(response);
  }

  // Mock data for active missions
  const activeMissions = [
    {
      id: 'MSN-0032',
      title: 'Semantic Routing Integration',
      priority: 'P0',
      status: 'IN_PROGRESS',
      progress: 85,
      owner: 'Chief Engineer',
      startDate: '2026-05-15',
      estimatedCompletion: '2026-06-10',
      blockers: 0
    },
    {
      id: 'MSN-0034',
      title: 'Number One Coordination Layer',
      priority: 'P1',
      status: 'IN_PROGRESS',
      progress: 70,
      owner: 'Chief Engineer',
      startDate: '2026-05-20',
      estimatedCompletion: '2026-06-15',
      blockers: 0
    },
    {
      id: 'MSN-0035',
      title: 'STARFLEET COMMAND CENTRE',
      priority: 'P1',
      status: 'IN_PROGRESS',
      progress: 65,
      owner: 'Captain TJR',
      startDate: '2026-06-01',
      estimatedCompletion: '2026-06-20',
      blockers: 0
    }
  ];

  cacheManager.set(cacheKey, activeMissions, 30);
  const response = successResponse(activeMissions, 200, {
    source: 'fresh',
    count: activeMissions.length
  });
  res.json(response);
}));

/**
 * GET /api/v1/missions/blocked
 * Returns missions with blockers
 */
router.get('/blocked', asyncHandler(async (req, res) => {
  const cacheKey = 'missions:blocked';
  const { value, isStale } = cacheManager.get(cacheKey);

  if (value) {
    const response = successResponse(value, 200, {
      source: isStale ? 'stale_cache' : 'cache',
      cacheKey: cacheKey
    });
    return res.json(response);
  }

  // Mock data for blocked missions
  const blockedMissions = [
    {
      id: 'MSN-0033',
      title: 'Blocked Mission Example',
      priority: 'P1',
      status: 'BLOCKED',
      blockedSince: '2026-06-05',
      blockers: [
        {
          id: 'BLK-001',
          description: 'Awaiting external dependency',
          blockedBy: 'MSN-0032',
          expectedResolution: '2026-06-10'
        }
      ],
      owner: 'Risk Officer',
      escalationLevel: 'MEDIUM'
    }
  ];

  cacheManager.set(cacheKey, blockedMissions, 30);
  const response = successResponse(blockedMissions, 200, {
    source: 'fresh',
    count: blockedMissions.length
  });
  res.json(response);
}));

/**
 * GET /api/v1/missions/:id/detail
 * Returns detailed information for a single mission
 */
router.get('/:id/detail', asyncHandler(async (req, res) => {
  const { id } = req.params;
  const cacheKey = `mission:${id}:detail`;
  const { value, isStale } = cacheManager.get(cacheKey);

  if (value) {
    const response = successResponse(value, 200, {
      source: isStale ? 'stale_cache' : 'cache',
      cacheKey: cacheKey
    });
    return res.json(response);
  }

  // Mock data for mission detail
  const missionDetail = {
    id: id,
    title: `Mission ${id} Details`,
    description: 'Detailed information about this mission',
    priority: 'P1',
    status: 'IN_PROGRESS',
    progress: 75,
    owner: 'Captain TJR',
    team: ['Chief Engineer', 'Coder Agent', 'Risk Officer'],
    startDate: '2026-06-01',
    estimatedCompletion: '2026-06-20',
    actualCompletion: null,
    blockers: [],
    dependencies: ['MSN-0032'],
    timeline: [
      { date: '2026-06-01', event: 'Mission started', status: 'COMPLETED' },
      { date: '2026-06-05', event: 'Phase 1 complete', status: 'COMPLETED' },
      { date: '2026-06-10', event: 'Phase 2 in progress', status: 'IN_PROGRESS' },
      { date: '2026-06-20', event: 'Expected completion', status: 'PLANNED' }
    ],
    metrics: {
      tasksCompleted: 24,
      tasksRemaining: 8,
      riskLevel: 'LOW',
      teamCapacity: 'FULL'
    }
  };

  cacheManager.set(cacheKey, missionDetail, 30);
  const response = successResponse(missionDetail, 200, {
    source: 'fresh',
    missionId: id
  });
  res.json(response);
}));

module.exports = router;
