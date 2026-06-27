/**
 * Notification Metrics & Mission Risk API — /api/v1/notifications/*
 *
 * Endpoints:
 *   GET /metrics          → Alert resolution metrics (7d, 30d, lifetime)
 *   GET /risk             → Top-N mission risk scores
 *   GET /escalations/open → Open (unresolved) escalation records
 *   POST /escalations/:key/acknowledge → Mark escalation acknowledged
 *   POST /escalations/:key/resolve     → Manually resolve escalation
 *
 * Data source: Python modules via child_process (notifications.db SQLite)
 * Cache TTL: 60s for metrics, 30s for risk (missions change more often)
 */

const express = require('express');
const router = express.Router();
const { execFile } = require('child_process');
const path = require('path');
const { cacheManager } = require('../cache/cache-manager');
const { asyncHandler, successResponse, ApiError } = require('../middleware/error-handling');
const notificationEngine = require('../services/notification-engine');

const REPO_ROOT = path.resolve(__dirname, '../../../../..');
const SLACK_BOT = path.join(REPO_ROOT, 'slack-bot');
const PYTHON = process.env.PYTHON_BIN || 'python3';

/** Run a Python one-liner against the slack-bot virtualenv. */
function runPython(script, timeoutMs = 8000) {
  return new Promise((resolve, reject) => {
    const env = { ...process.env, PYTHONPATH: SLACK_BOT };
    execFile(
      PYTHON,
      ['-c', script],
      { cwd: SLACK_BOT, env, timeout: timeoutMs },
      (err, stdout, stderr) => {
        if (err) {
          reject(new Error(`Python error: ${stderr || err.message}`));
        } else {
          try {
            resolve(JSON.parse(stdout.trim()));
          } catch {
            reject(new Error(`JSON parse failed: ${stdout.slice(0, 200)}`));
          }
        }
      }
    );
  });
}

// ---------------------------------------------------------------------------
// GET /api/v1/notifications/metrics
// ---------------------------------------------------------------------------
router.get('/metrics', asyncHandler(async (req, res) => {
  const cacheKey = 'notifications:metrics';
  const cached = cacheManager.get(cacheKey);
  if (cached) return res.json(successResponse(cached));

  const days7  = await runPython(`
import json, sys
sys.path.insert(0, '${SLACK_BOT}')
from alert_metrics import get_notification_metrics
print(json.dumps({
  'seven_day':  get_notification_metrics(7),
  'thirty_day': get_notification_metrics(30),
  'lifetime':   get_notification_metrics(None)
}))
`);
  cacheManager.set(cacheKey, days7, 60);
  res.json(successResponse(days7));
}));

// ---------------------------------------------------------------------------
// GET /api/v1/notifications/risk?limit=10
// ---------------------------------------------------------------------------
router.get('/risk', asyncHandler(async (req, res) => {
  const limit = Math.min(parseInt(req.query.limit || '10', 10), 20);
  const cacheKey = `notifications:risk:${limit}`;
  const cached = cacheManager.get(cacheKey);
  if (cached) return res.json(successResponse(cached));

  const data = await runPython(`
import json, sys
sys.path.insert(0, '${SLACK_BOT}')
from mission_risk import get_top_risk_missions
print(json.dumps({'missions': get_top_risk_missions(${limit})}))
`);
  cacheManager.set(cacheKey, data, 30);
  res.json(successResponse(data));
}));

// ---------------------------------------------------------------------------
// GET /api/v1/notifications/escalations/open
// ---------------------------------------------------------------------------
router.get('/escalations/open', asyncHandler(async (req, res) => {
  const cacheKey = 'notifications:escalations:open';
  const cached = cacheManager.get(cacheKey);
  if (cached) return res.json(successResponse(cached));

  const data = await runPython(`
import json, sys
sys.path.insert(0, '${SLACK_BOT}')
from escalation_manager import get_open_escalations
print(json.dumps({'escalations': get_open_escalations()}))
`);
  cacheManager.set(cacheKey, data, 30);
  res.json(successResponse(data));
}));

// ---------------------------------------------------------------------------
// POST /api/v1/notifications/escalations/:key/acknowledge
// ---------------------------------------------------------------------------
router.post('/escalations/:key/acknowledge', asyncHandler(async (req, res) => {
  const key = req.params.key;
  // Validate key format to prevent injection
  if (!/^[\w:-]+$/.test(key)) {
    return res.status(400).json({ error: 'Invalid alert key format' });
  }
  const data = await runPython(`
import json, sys
sys.path.insert(0, '${SLACK_BOT}')
from escalation_manager import acknowledge_escalation
ok = acknowledge_escalation('${key}')
print(json.dumps({'acknowledged': ok, 'key': '${key}'}))
`);
  cacheManager.invalidate('notifications:escalations:open');
  res.json(successResponse(data));
}));

// ---------------------------------------------------------------------------
// POST /api/v1/notifications/escalations/:key/resolve
// ---------------------------------------------------------------------------
router.post('/escalations/:key/resolve', asyncHandler(async (req, res) => {
  const key = req.params.key;
  if (!/^[\w:-]+$/.test(key)) {
    return res.status(400).json({ error: 'Invalid alert key format' });
  }
  const data = await runPython(`
import json, sys
sys.path.insert(0, '${SLACK_BOT}')
from escalation_manager import resolve_escalation
ok = resolve_escalation('${key}')
print(json.dumps({'resolved': ok, 'key': '${key}'}))
`);
  cacheManager.invalidate('notifications:escalations:open');
  cacheManager.invalidate('notifications:metrics');
  res.json(successResponse(data));
}));

// ── In-app notification store endpoints ──────────────────────────────────────

// GET /api/v1/notifications/unread
router.get('/unread', asyncHandler(async (req, res) => {
  const notes = notificationEngine.getUnread();
  res.json(successResponse(notes, 200, { count: notes.length }));
}));

// GET /api/v1/notifications/history?limit=50
router.get('/history', asyncHandler(async (req, res) => {
  const limit = Math.min(parseInt(req.query.limit) || 50, 200);
  const notes = notificationEngine.getHistory(limit);
  res.json(successResponse(notes, 200, { count: notes.length }));
}));

// POST /api/v1/notifications/:id/read
router.post('/:id/read', asyncHandler(async (req, res) => {
  const id = parseInt(req.params.id);
  if (isNaN(id)) throw new ApiError(400, 'id must be a number');
  const found = notificationEngine.markRead(id);
  if (!found) throw new ApiError(404, `Notification ${id} not found`);
  res.json(successResponse({ id, read: true }));
}));

// POST /api/v1/notifications/read-all
router.post('/read-all', asyncHandler(async (req, res) => {
  notificationEngine.markAllRead();
  res.json(successResponse({ ok: true }));
}));

// POST /api/v1/notifications/trigger  — manual evaluation cycle (for testing)
router.post('/trigger', asyncHandler(async (req, res) => {
  await notificationEngine.evaluate();
  const notes = notificationEngine.getHistory(20);
  res.json(successResponse({ triggered: true, recent: notes.slice(0, 5) }));
}));

module.exports = router;
