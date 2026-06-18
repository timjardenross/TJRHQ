/**
 * Observability & security logging (Mission 7 Phase 4)
 *
 * Two responsibilities:
 *   1. requestId  — assign a correlation ID to every request (reuse an inbound
 *      X-Request-Id from Caddy if present, otherwise mint a UUID) and echo it
 *      back on the response so a client/edge log line can be tied to a backend
 *      log line.
 *   2. logSecurityEvent — emit a single structured JSON record for every
 *      security-relevant denial/failure. Records go to stdout (captured by
 *      journald → `journalctl -u starfleet-backend`) AND are appended to a
 *      durable audit file. File writes are best-effort and never throw.
 *
 * Every event carries: event, reason (machine code), endpoint, method,
 * requestId, ip, and optional details — so every denial is explainable.
 */

const fs = require('fs');
const path = require('path');
const { v4: uuidv4 } = require('uuid');

const LOG_DIR = path.resolve(__dirname, '..', 'logs');
const SECURITY_LOG = path.join(LOG_DIR, 'security.log');

// Ensure the audit directory exists once at load. Best-effort: if it fails we
// still log to stdout, so observability degrades gracefully rather than crashing.
let fileLoggingEnabled = true;
try {
  fs.mkdirSync(LOG_DIR, { recursive: true });
} catch (e) {
  fileLoggingEnabled = false;
  console.error(`[SECURITY] audit file disabled (cannot create ${LOG_DIR}): ${e.message}`);
}

/** Express middleware: attach a correlation ID and surface it on the response. */
function requestId(req, res, next) {
  const inbound = req.headers['x-request-id'];
  // Only trust a sane inbound id; otherwise mint our own.
  req.id = (typeof inbound === 'string' && /^[\w.-]{1,128}$/.test(inbound)) ? inbound : uuidv4();
  res.setHeader('X-Request-Id', req.id);
  next();
}

/**
 * Emit one structured security event.
 * @param {object} e
 * @param {string} e.event    high-level category, e.g. 'rate_limit', 'auth', 'payload'
 * @param {string} e.reason   machine-readable reason code, e.g. 'RATE_LIMIT_EXCEEDED'
 * @param {object} [e.req]    the Express request (used to derive endpoint/method/ip/id)
 * @param {string} [e.endpoint] override endpoint tag
 * @param {object} [e.details] extra context (no secrets)
 */
function logSecurityEvent({ event, reason, req, endpoint, details } = {}) {
  const record = {
    ts: new Date().toISOString(),
    level: 'security',
    event,
    reason,
    endpoint: endpoint || (req ? `${req.method} ${req.originalUrl || req.url}` : undefined),
    method: req ? req.method : undefined,
    requestId: req ? req.id : undefined,
    ip: req ? req.ip : undefined,
    ...(details ? { details } : {}),
  };

  const line = JSON.stringify(record);
  // stdout → journald (always)
  console.warn(`[SECURITY] ${line}`);
  // durable audit file (best-effort)
  if (fileLoggingEnabled) {
    fs.appendFile(SECURITY_LOG, line + '\n', (err) => {
      if (err) console.error(`[SECURITY] audit append failed: ${err.message}`);
    });
  }
}

module.exports = { requestId, logSecurityEvent, SECURITY_LOG };
