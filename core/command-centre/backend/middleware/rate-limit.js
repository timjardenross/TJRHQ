/**
 * Rate limiting layer (Mission 7 Phase 2)
 *
 * NOTE ON PLACEMENT: the deployed Caddy is the standard apt build and does not
 * include a rate_limit module, so per-IP limiting is enforced here in Node,
 * immediately behind Caddy. app.js sets `trust proxy = loopback`, so req.ip is
 * the real client IP from Caddy's X-Forwarded-For (Caddy is the only thing that
 * connects to 127.0.0.1:5000), making per-IP keying accurate and unspoofable
 * from outside.
 *
 * Four tiers, smallest blast radius first:
 *   burstLimiter    — anti-spike: caps requests/second (stops tight loops & floods)
 *   generalLimiter  — sustained per-IP ceiling for all /api traffic
 *   mutationLimiter — stricter ceiling for write methods (POST/PUT/PATCH/DELETE)
 *   syncLimiter     — long cooldown window for expensive sync/generate endpoints
 *
 * All limits are env-overridable for tuning under real load.
 */

const { rateLimit } = require('express-rate-limit');
const { logSecurityEvent } = require('./observability');

const num = (v, d) => (v !== undefined && !Number.isNaN(Number(v)) ? Number(v) : d);

// Build a limiter with a shared 429 handler that logs a security event and
// returns a structured, correlation-tagged response.
function makeLimiter({ windowMs, limit, tier }) {
  return rateLimit({
    windowMs,
    limit,
    standardHeaders: true,   // RateLimit-* headers
    legacyHeaders: false,
    // Don't penalise CORS preflight.
    skip: (req) => req.method === 'OPTIONS',
    handler: (req, res /*, next, options */) => {
      const retryAfter = Math.ceil(windowMs / 1000);
      logSecurityEvent({
        event: 'rate_limit',
        reason: 'RATE_LIMIT_EXCEEDED',
        req,
        details: { tier, limit, windowMs, retryAfterSeconds: retryAfter },
      });
      res.setHeader('Retry-After', String(retryAfter));
      res.status(429).json({
        error: 'rate_limited',
        reason: 'RATE_LIMIT_EXCEEDED',
        tier,
        message: `Too many requests. Try again in ~${retryAfter}s.`,
        retryAfterSeconds: retryAfter,
        requestId: req.id,
      });
    },
  });
}

// Anti-spike: e.g. 20 requests per 1s window per IP.
const burstLimiter = makeLimiter({
  windowMs: num(process.env.RL_BURST_WINDOW_MS, 1000),
  limit: num(process.env.RL_BURST_MAX, 20),
  tier: 'burst',
});

// Sustained ceiling: e.g. 150 requests per 60s per IP across all /api.
const generalLimiter = makeLimiter({
  windowMs: num(process.env.RL_GENERAL_WINDOW_MS, 60_000),
  limit: num(process.env.RL_GENERAL_MAX, 150),
  tier: 'general',
});

// Writes are stricter: e.g. 25 mutations per 60s per IP.
const mutationLimiter = makeLimiter({
  windowMs: num(process.env.RL_MUTATION_WINDOW_MS, 60_000),
  limit: num(process.env.RL_MUTATION_MAX, 25),
  tier: 'mutation',
});

// Expensive sync/generate endpoints: long cooldown, e.g. 6 per 5 minutes per IP.
// Guards against accidental recursive/loop triggering of the intelligence and
// decision-sync pipelines.
const syncLimiter = makeLimiter({
  windowMs: num(process.env.RL_SYNC_WINDOW_MS, 300_000),
  limit: num(process.env.RL_SYNC_MAX, 6),
  tier: 'sync',
});

// Apply the mutation limiter only to write methods (so GETs aren't double-charged).
function mutationLimiterIfWrite(req, res, next) {
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(req.method)) {
    return mutationLimiter(req, res, next);
  }
  return next();
}

module.exports = {
  burstLimiter,
  generalLimiter,
  mutationLimiter,
  mutationLimiterIfWrite,
  syncLimiter,
};
