/**
 * OR Intelligence API routes
 * Mounted at /api/v1/intelligence
 *
 * GET /api/v1/intelligence/latest          Latest brief
 * GET /api/v1/intelligence/archive         Brief archive (paginated)
 * GET /api/v1/intelligence/source-health   Source health per-source
 * GET /api/v1/intelligence/sources         Source registry
 * GET /api/v1/intelligence/events          Recent events (filterable)
 * GET /api/v1/intelligence/themes          Emerging themes from latest brief
 * POST /api/v1/intelligence/generate       Trigger on-demand generation
 */

const express = require('express');
const router = express.Router();
const { IntelligenceAdapter } = require('../connectors/intelligence-adapter');

const adapter = new IntelligenceAdapter();

// ── Helper: consistent error envelope ────────────────────────────────────────
function fail(res, status, message, detail = null) {
  const body = { status: 'FAILED', error: message };
  if (detail) body.detail = String(detail).slice(0, 500);
  return res.status(status).json(body);
}

// ── GET /latest ───────────────────────────────────────────────────────────────
router.get('/latest', async (req, res) => {
  try {
    const result = await adapter.getLatestBrief();
    res.json(result);
  } catch (err) {
    fail(res, 503, 'Could not retrieve latest brief', err.message);
  }
});

// ── GET /brief/:id ────────────────────────────────────────────────────────────
router.get('/brief/:id', async (req, res) => {
  try {
    const brief = await adapter.getBriefById(req.params.id);
    if (!brief) return fail(res, 404, 'Brief not found', req.params.id);
    res.json({ status: 'ARCHIVED', brief });
  } catch (err) {
    fail(res, 503, 'Could not retrieve brief', err.message);
  }
});

// ── GET /archive ──────────────────────────────────────────────────────────────
router.get('/archive', async (req, res) => {
  try {
    const limit  = Math.min(parseInt(req.query.limit  || '20', 10), 100);
    const offset = parseInt(req.query.offset || '0',  10);
    const result = await adapter.getBriefArchive({ limit, offset });
    res.json(result);
  } catch (err) {
    fail(res, 503, 'Could not retrieve brief archive', err.message);
  }
});

// ── GET /source-health ────────────────────────────────────────────────────────
router.get('/source-health', async (req, res) => {
  try {
    const result = await adapter.getSourceHealth();
    res.json(result);
  } catch (err) {
    fail(res, 503, 'Could not retrieve source health', err.message);
  }
});

// ── GET /sources ──────────────────────────────────────────────────────────────
router.get('/sources', async (req, res) => {
  try {
    const result = await adapter.getSourceRegistry();
    res.json(result);
  } catch (err) {
    fail(res, 503, 'Could not retrieve source registry', err.message);
  }
});

// ── GET /events ───────────────────────────────────────────────────────────────
router.get('/events', async (req, res) => {
  try {
    const { type, geography, risk, limit, days } = req.query;
    const result = await adapter.getEvents({
      eventType:  type,
      geography,
      risk,
      limit: limit ? parseInt(limit, 10) : 50,
      days:  days  ? parseInt(days,  10) : 14,
    });
    res.json(result);
  } catch (err) {
    fail(res, 503, 'Could not retrieve events', err.message);
  }
});

// ── GET /themes ───────────────────────────────────────────────────────────────
router.get('/themes', async (req, res) => {
  try {
    const result = await adapter.getThemes();
    res.json(result);
  } catch (err) {
    fail(res, 503, 'Could not retrieve themes', err.message);
  }
});

// ── POST /generate ────────────────────────────────────────────────────────────
router.post('/generate', async (req, res) => {
  try {
    const { days } = req.body || {};
    // Async: start generation and return accepted immediately
    res.status(202).json({
      status: 'ACCEPTED',
      message: 'Brief generation started',
      trigger_type: 'on_demand',
    });
    // Fire generation in background (non-blocking for the HTTP response)
    setImmediate(() => {
      try {
        adapter.generateNow({ days });
      } catch (err) {
        console.error('[INTELLIGENCE] On-demand generation failed:', err.message);
      }
    });
  } catch (err) {
    fail(res, 500, 'Failed to start generation', err.message);
  }
});

module.exports = router;
