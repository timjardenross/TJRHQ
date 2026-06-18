/**
 * API-key authentication — the single shared auth source for the backend.
 *
 * Every request is validated here against process.env.BACKEND_API_KEY. No keys
 * are hardcoded anywhere; the expected key is read from the environment once at
 * startup. Mount this once in app.js so all routes validate via one middleware.
 */

const crypto = require('crypto');
const { logSecurityEvent } = require('./observability');

/** Constant-time comparison that never throws on length mismatch. */
function safeEqual(a, b) {
  const ab = Buffer.from(String(a));
  const bb = Buffer.from(String(b));
  if (ab.length !== bb.length) return false;
  return crypto.timingSafeEqual(ab, bb);
}

/**
 * Build the shared API-key auth middleware.
 * @param {object} [opts]
 * @param {string[]} [opts.publicPaths]  Paths that bypass auth (e.g. health checks).
 * @throws if BACKEND_API_KEY is not set (fail fast — never run unauthenticated).
 * @returns Express middleware.
 */
function createApiKeyAuth({ publicPaths = ['/health'] } = {}) {
  const expected = process.env.BACKEND_API_KEY;
  if (!expected) {
    throw new Error('BACKEND_API_KEY is required. Set it in .env before starting the backend.');
  }
  const publicSet = new Set(publicPaths);

  return function apiKeyAuth(req, res, next) {
    if (publicSet.has(req.path)) return next();
    const provided = req.headers['x-api-key'] || req.query.api_key || '';
    if (!provided || !safeEqual(provided, expected)) {
      logSecurityEvent({
        event: 'auth',
        reason: provided ? 'AUTH_INVALID_KEY' : 'AUTH_MISSING_KEY',
        req,
      });
      return res.status(401).json({
        error: 'unauthorised',
        reason: provided ? 'AUTH_INVALID_KEY' : 'AUTH_MISSING_KEY',
        message: 'Valid X-Api-Key header required',
        requestId: req.id,
      });
    }
    next();
  };
}

module.exports = { createApiKeyAuth, safeEqual };
