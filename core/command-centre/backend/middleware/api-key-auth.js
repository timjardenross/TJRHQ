'use strict';

/**
 * API-key authentication for the Command Centre backend.
 *
 * Extracted from app.js so it can be unit-tested without starting the server.
 *
 * Rules:
 *  1. Fail closed. With no key configured every non-public request gets 503,
 *     whatever NODE_ENV is. The only exception is an explicit, local-only dev
 *     opt-in (`allowUnauthenticatedDev`): it is ignored in production and only
 *     serves requests that come from the loopback interface.
 *  2. The key is read from the X-Api-Key header only.
 *  3. Any `api_key` query parameter is rejected with 400, even when a valid
 *     header is also present, and on public paths too. Query strings end up in
 *     proxy/access logs and browser history. Only the request path is logged,
 *     never the query string or any credential value.
 *  4. Comparison is constant-time (SHA-256 digests + timingSafeEqual, no early
 *     exit across the accepted keys).
 *  5. Up to two keys are accepted so a key can be rotated without downtime:
 *     set BACKEND_API_KEY to the new key and BACKEND_API_KEY_PREVIOUS to the old
 *     one, update every caller, then drop the previous key.
 *
 * Temporary emergency rollback: `allowQueryKey: true` (env ALLOW_QUERY_API_KEY=1)
 * restores the old behaviour of accepting `?api_key=` when no header is sent.
 * It is deprecated and scheduled for removal (see docs/security-remediation-runbook.md).
 */

const crypto = require('crypto');

const digest = (value) => crypto.createHash('sha256').update(String(value)).digest();

const LOOPBACK_ADDRESSES = new Set(['127.0.0.1', '::1', '::ffff:127.0.0.1']);
const isLoopbackRequest = (req) => LOOPBACK_ADDRESSES.has(req.socket && req.socket.remoteAddress);

const hasQueryApiKey = (req) =>
  Boolean(req.query) && Object.prototype.hasOwnProperty.call(req.query, 'api_key');

function createApiKeyAuth({
  keys = [],
  isProduction = false,
  allowUnauthenticatedDev = false,
  publicPaths = ['/health'],
  allowQueryKey = false,
  onQueryKeyUse = () => {},
} = {}) {
  const validDigests = keys.filter((k) => typeof k === 'string' && k.length > 0).map(digest);
  const publicSet = new Set(publicPaths);
  // Unauthenticated dev mode needs the explicit opt-in AND a non-production process.
  const devOpen = allowUnauthenticatedDev === true && !isProduction;

  return function apiKeyAuth(req, res, next) {
    const queryKeyPresent = hasQueryApiKey(req);

    if (queryKeyPresent && !allowQueryKey) {
      onQueryKeyUse(req.path, 'rejected');
      return res.status(400).json({
        error: 'bad_request',
        message: 'The api_key query parameter is not accepted; send the X-Api-Key header',
      });
    }

    if (publicSet.has(req.path)) return next();

    if (validDigests.length === 0) {
      if (devOpen && isLoopbackRequest(req)) return next();
      return res
        .status(503)
        .json({ error: 'misconfigured', message: 'BACKEND_API_KEY is not configured' });
    }

    let provided = req.headers['x-api-key'];
    // detect-secrets flags the identifier `api_key` below; there is no secret value in this file.
    if (!provided && queryKeyPresent && allowQueryKey && typeof req.query.api_key === 'string') { // pragma: allowlist secret
      onQueryKeyUse(req.path, 'accepted');
      provided = req.query.api_key;
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

module.exports = { createApiKeyAuth, isLoopbackRequest };
