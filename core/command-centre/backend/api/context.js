/**
 * Context Assembly API — /api/v1/context/*
 * WP6: Context API Endpoints
 *
 * Endpoints:
 *   GET /captain-brief         → CaptainBriefContext
 *   GET /operating-picture     → CaptainOperatingPictureContext
 *   GET /health                → HealthContextPackage
 *   GET /blockers              → List<BlockerContextPackage>
 *   GET /recommendations       → RecommendationPackage
 *   GET /mission/:id           → MissionContextPackage
 *   GET /status                → Adapter status (monitoring)
 *
 * Cache TTLs:
 *   captain-brief:     120s  (daily brief, regenerate every 2 min)
 *   operating-picture: 120s
 *   health:            300s  (health data changes slowly)
 *   blockers:           60s  (blocker state can change quickly)
 *   recommendations:   120s
 *   mission/:id:        30s  (per-mission detail)
 *
 * All responses include:
 *   metadata.source:    fresh | file | stale_file | python | mock | cache | stale_cache
 *   metadata.dataAge:   age in seconds (if from file)
 *   metadata.timestamp: response timestamp
 *
 * Error handling follows existing 3-tier pattern:
 *   1. Fresh/stale cache
 *   2. Adapter fallback (file → python → mock)
 *   3. Placeholder with data_unavailable note
 */

const express = require('express');
const router = express.Router();
const { cacheManager } = require('../cache/cache-manager');
const { asyncHandler, successResponse, ApiError } = require('../middleware/error-handling');
const { ContextAssemblyAdapter } = require('../connectors/context-assembly-adapter');

const adapter = new ContextAssemblyAdapter();

// TTL constants (seconds)
const TTL = {
  CAPTAIN_BRIEF:     120,
  OPERATING_PICTURE: 120,
  HEALTH:            300,
  BLOCKERS:           60,
  RECOMMENDATIONS:   120,
  MISSION:            30,
};

/**
 * Shared handler: check cache → get from adapter → cache result → respond.
 */
function contextEndpoint(cacheKey, ttlSeconds, getFn) {
  return asyncHandler(async (req, res) => {
    const { value, isStale } = cacheManager.get(cacheKey);

    if (value) {
      return res.json(successResponse(value, 200, {
        source: isStale ? 'stale_cache' : 'cache',
        cacheKey,
      }));
    }

    const { data, source, isStale: dataIsStale, ageSeconds } = getFn();

    cacheManager.set(cacheKey, data, ttlSeconds);

    const meta = { source, cacheKey };
    if (ageSeconds !== null && ageSeconds !== undefined) meta.dataAgeSeconds = ageSeconds;
    if (dataIsStale) meta.stale = true;

    res.json(successResponse(data, 200, meta));
  });
}

// ---------------------------------------------------------------------------
// GET /api/v1/context/captain-brief
// ---------------------------------------------------------------------------
router.get(
  '/captain-brief',
  contextEndpoint(
    'context:captain-brief',
    TTL.CAPTAIN_BRIEF,
    () => adapter.getCaptainBrief()
  )
);

// ---------------------------------------------------------------------------
// GET /api/v1/context/operating-picture
// ---------------------------------------------------------------------------
router.get(
  '/operating-picture',
  contextEndpoint(
    'context:operating-picture',
    TTL.OPERATING_PICTURE,
    () => adapter.getOperatingPicture()
  )
);

// ---------------------------------------------------------------------------
// GET /api/v1/context/health
// ---------------------------------------------------------------------------
router.get(
  '/health',
  contextEndpoint(
    'context:health',
    TTL.HEALTH,
    () => adapter.getHealthContext()
  )
);

// ---------------------------------------------------------------------------
// GET /api/v1/context/blockers
// ---------------------------------------------------------------------------
router.get(
  '/blockers',
  contextEndpoint(
    'context:blockers',
    TTL.BLOCKERS,
    () => adapter.getBlockers()
  )
);

// ---------------------------------------------------------------------------
// GET /api/v1/context/recommendations
// ---------------------------------------------------------------------------
router.get(
  '/recommendations',
  contextEndpoint(
    'context:recommendations',
    TTL.RECOMMENDATIONS,
    () => adapter.getRecommendations()
  )
);

// ---------------------------------------------------------------------------
// GET /api/v1/context/mission/:id
// Dynamic per-mission context — always fetches from Python
// ---------------------------------------------------------------------------
router.get('/mission/:id', asyncHandler(async (req, res) => {
  const { id } = req.params;
  const missionId = id.toUpperCase();
  const cacheKey = `context:mission:${missionId}`;

  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) {
    return res.json(successResponse(value, 200, {
      source: isStale ? 'stale_cache' : 'cache',
      cacheKey,
      missionId,
    }));
  }

  const data = adapter.getMissionContext(missionId);

  if (!data) {
    throw new ApiError(404, `Mission context unavailable for ${missionId}`, null);
  }
  if (data.error) {
    // Python returned an error object (e.g. mission not found)
    return res.status(404).json({
      status: 'error',
      data: null,
      metadata: { source: 'python', missionId, timestamp: new Date().toISOString() },
      error: { message: data.error },
    });
  }

  cacheManager.set(cacheKey, data, TTL.MISSION);
  res.json(successResponse(data, 200, { source: 'python', missionId }));
}));

// ---------------------------------------------------------------------------
// GET /api/v1/context/status
// Monitoring — adapter status and file health
// ---------------------------------------------------------------------------
router.get('/status', asyncHandler(async (req, res) => {
  const status = adapter.getStatus();
  res.json(successResponse(status, 200, {
    source: 'fresh',
    timestamp: new Date().toISOString(),
  }));
}));

module.exports = router;
