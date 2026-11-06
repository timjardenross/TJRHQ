'use strict';

/**
 * API-key authentication for the Command Centre backend.
 *
 * Extracted from app.js so it can be unit-tested without starting the server.
 *
 * Behaviour (compatible with the previous inline middleware unless noted):
 *  - Paths in `publicPaths` (default: /health) skip authentication.
 *  - No key configured: production fails closed (503); non-production passes through.
 *  - The key must be sent in the X-Api-Key header.
 *  - CHANGED: the `api_key` query parameter is rejected by default, because
 *    query strings end up in proxy/access logs and browser history. Setting
 *    `allowQueryKey: true` (env ALLOW_QUERY_API_KEY=1) restores the old behaviour
 *    as a temporary, restart-only rollback lever.
 *  - CHANGED: comparison is constant-time (SHA-256 digests + timingSafeEqual).
 *  - NEW: up to two accepted keys (`keys`), so a key can be rotated without
 *    downtime: set BACKEND_API_KEY to the new key and BACKEND_API_KEY_PREVIOUS to
 *    the old one, update callers, then drop the previous key.
 *
 * Key values are never logged. Callbacks receive only the request path.
 */

const crypto = require('crypto');

const digest = (value) => crypto.createHash('sha256').update(String(value)).digest();

function createApiKeyAuth({
  keys = [],
  isProduction = false,
  publicPaths = ['/health'],
  allowQueryKey = false,
  onQueryKeyUse = () => {},
} = {}) {
  const validDigests = keys.filter((k) => typeof k === 'string' && k.length > 0).map(digest);
  const publicSet = new Set(publicPaths);

  return function apiKeyAuth(req, res, next) {
    if (publicSet.has(req.path)) return next();

    if (validDigests.length === 0) {
      if (isProduction) {
        return res
          .status(503)
          .json({ error: 'misconfigured', message: 'BACKEND_API_KEY is not configured' });
      }
      return next(); // dev mode: no key configured, non-production only
    }

    let provided = req.headers['x-api-key'];
    const queryKey = req.query && typeof req.query.api_key === 'string' ? req.query.api_key : undefined;

    if (!provided && queryKey !== undefined) {
      onQueryKeyUse(req.path, allowQueryKey ? 'accepted' : 'rejected');
      if (!allowQueryKey) {
        return res.status(401).json({
          error: 'unauthorised',
          message: 'The api_key query parameter is no longer supported; send the X-Api-Key header',
        });
      }
      provided = queryKey;
    }

    if (typeof provided !== 'string' || provided.length === 0) {
      return res.status(401).json({ error: 'unauthorised', message: 'Valid X-Api-Key header required' });
    }

    const providedDigest = digest(provided);
    let ok = false;
    for (const valid of validDigests) {
      if (crypto.timingSafeEqual(providedDigest, valid)) ok = true; // no early exit
    }
    if (!ok) {
      return res.status(401).json({ error: 'unauthorised', message: 'Valid X-Api-Key header required' });
    }
    return next();
  };
}

module.exports = { createApiKeyAuth };
