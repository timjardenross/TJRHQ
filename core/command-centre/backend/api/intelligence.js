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
    const { spawn } = require('child_process');
    const path = require('path');
    const REPO_ROOT = path.resolve(__dirname, '../../../../');
    const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';
    const SCHEDULER_PY = path.join(REPO_ROOT, 'intelligence', 'scheduler.py');

    const args = ['--once'];
    if (days) args.push('--days', String(days));

    const child = spawn(PYTHON_BIN, [SCHEDULER_PY, ...args], {
      cwd: REPO_ROOT,
      env: { ...process.env, PYTHONPATH: REPO_ROOT },
      detached: false,
    });

    child.stdout.on('data', d => process.stdout.write(`[INTELLIGENCE] ${d}`));
    child.stderr.on('data', d => process.stderr.write(`[INTELLIGENCE] ${d}`));
    child.on('close', code => {
      if (code !== 0) console.error(`[INTELLIGENCE] Generator exited with code ${code}`);
      else console.log('[INTELLIGENCE] Brief generation complete');
    });
    child.on('error', err => console.error('[INTELLIGENCE] Spawn error:', err.message));

    res.status(202).json({
      status: 'ACCEPTED',
      message: 'Brief generation started',
      trigger_type: 'on_demand',
    });
  } catch (err) {
    fail(res, 500, 'Failed to start generation', err.message);
  }
});

// ── GET /operating-picture ─────────────────────────────────────────────────────
// MSN-0200 P1E: synthesised executive operating picture
// Cache TTL: 5 min (fast enough for Telegram /operating_picture command)
const { cacheManager } = require('../cache/cache-manager');
const { spawnSync } = require('child_process');

router.get('/operating-picture', async (req, res) => {
  const cacheKey = 'intelligence:operating-picture';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value && !isStale) {
    return res.json({ status: 'ok', source: 'cache', ...value });
  }

  const path = require('path');
  const REPO_ROOT = path.join(__dirname, '../../../../');
  const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';

  const result = spawnSync(
    PYTHON_BIN,
    ['-c', `
import sys, json
sys.path.insert(0, '${REPO_ROOT}')
sys.path.insert(0, '${path.join(REPO_ROOT, 'core/intelligence')}')
from operating_picture import get_operating_picture
print(json.dumps(get_operating_picture(), default=str))
`],
    {
      cwd: REPO_ROOT,
      timeout: 15000,
      encoding: 'utf8',
      env: { ...process.env, PYTHONPATH: REPO_ROOT },
    }
  );

  if (result.error || result.status !== 0) {
    // Return stale cache if available rather than hard fail
    if (value) return res.json({ status: 'STALE', source: 'stale_cache', ...value });
    return fail(res, 503, 'Operating picture unavailable', result.stderr?.slice(0, 300));
  }

  let picture;
  try {
    picture = JSON.parse(result.stdout);
  } catch (e) {
    if (value) return res.json({ status: 'STALE', source: 'stale_cache', ...value });
    return fail(res, 500, 'Operating picture parse failed', e.message);
  }

  cacheManager.set(cacheKey, picture, 300); // 5 min TTL
  return res.json({ status: 'ok', source: isStale ? 'refreshed' : 'live', ...picture });
});

module.exports = router;
