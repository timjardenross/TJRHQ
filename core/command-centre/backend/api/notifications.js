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
const { asyncHandler, successResponse } = require('../middleware/error-handling');
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

// Mission 6B §8.2: the in-app unread/history/read-all/:id/read routes that
// used to live here were retired — they read/wrote notification-engine.js's
// in-memory `_store`, which had zero live UI consumer (confirmed by
// repo-wide search) and reset on every process restart, so "read" state was
// decorative rather than canonical. The real value here — signal
// evaluation + Telegram delivery — is unaffected; see that file's header
// comment. A future in-app notification surface belongs on Follow-
// Through's canonical personal_tasks state, not a new local store.

// POST /api/v1/notifications/trigger  — manual evaluation cycle (for testing)
router.post('/trigger', asyncHandler(async (req, res) => {
  await notificationEngine.evaluate();
  res.json(successResponse({ triggered: true }));
}));

module.exports = router;
