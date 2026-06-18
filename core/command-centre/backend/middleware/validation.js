/**
 * Request validation hardening (Mission 7 Phase 3)
 *
 * Body SIZE limits and strict-JSON parsing are configured on express.json() in
 * app.js (a parse failure / oversize body surfaces in the error handler with a
 * machine reason code). This module adds the shape/semantic layer:
 *
 *   mutationContentTypeGuard — write requests carrying a body MUST be application/json
 *   objectBodyGuard          — parsed body must be a plain JSON object (not array/primitive)
 *   validate<X>              — per-endpoint bounds checks for the critical writes
 *
 * Validators reject early with HTTP 400/415, a reason code, and a correlation id,
 * and log a security event. They are intentionally conservative: they reject the
 * clearly-malformed and clamp nothing, leaving the (already defensive) handlers
 * to apply business defaults.
 */

const { logSecurityEvent } = require('./observability');

function reject(req, res, { status, reason, message, details }) {
  logSecurityEvent({ event: 'payload', reason, req, details });
  return res.status(status).json({
    error: status === 415 ? 'unsupported_media_type' : 'invalid_request',
    reason,
    message,
    requestId: req.id,
  });
}

const WRITE_METHODS = ['POST', 'PUT', 'PATCH'];

/** Reject write requests that send a body without an application/json content type. */
function mutationContentTypeGuard(req, res, next) {
  if (!WRITE_METHODS.includes(req.method)) return next();
  const hasBody = req.headers['content-length'] && Number(req.headers['content-length']) > 0
    || req.headers['transfer-encoding'];
  if (!hasBody) return next(); // empty-body POST (e.g. trigger endpoints) is allowed
  if (!req.is('application/json')) {
    return reject(req, res, {
      status: 415,
      reason: 'UNSUPPORTED_CONTENT_TYPE',
      message: 'Request body must be application/json.',
      details: { contentType: req.headers['content-type'] || null },
    });
  }
  return next();
}

/** Ensure a parsed body is a plain object (rejects arrays / primitives). */
function objectBodyGuard(req, res, next) {
  if (!WRITE_METHODS.includes(req.method)) return next();
  const b = req.body;
  if (b === undefined || b === null) return next(); // no body → handlers default
  if (typeof b !== 'object' || Array.isArray(b)) {
    return reject(req, res, {
      status: 400,
      reason: 'INVALID_BODY_TYPE',
      message: 'Request body must be a JSON object.',
    });
  }
  return next();
}

// ── Field helpers ────────────────────────────────────────────────────────────
const isMissing = (v) => v === undefined || v === null || v === '';
function intInRange(v, min, max) {
  if (isMissing(v)) return { ok: true, skipped: true };
  const n = Number(v);
  if (!Number.isFinite(n) || !Number.isInteger(n) || n < min || n > max) {
    return { ok: false };
  }
  return { ok: true, value: n };
}
function numInRange(v, min, max) {
  if (isMissing(v)) return { ok: true, skipped: true };
  const n = Number(v);
  if (!Number.isFinite(n) || n < min || n > max) return { ok: false };
  return { ok: true, value: n };
}

// ── Per-endpoint validators ──────────────────────────────────────────────────

/** POST /api/v1/coordination/intelligence-sync — decision sync. */
function validateIntelligenceSync(req, res, next) {
  const b = req.body || {};
  for (const [field, spec] of Object.entries({
    minRank: [0, 100], days: [1, 365], limit: [1, 1000],
  })) {
    if (!intInRange(b[field], spec[0], spec[1]).ok) {
      return reject(req, res, {
        status: 400, reason: 'INVALID_FIELD',
        message: `Field '${field}' must be an integer in [${spec[0]}, ${spec[1]}].`,
        details: { field, value: b[field] },
      });
    }
  }
  if (b.dryRun !== undefined && typeof b.dryRun !== 'boolean' && b.dryRun !== 'true' && b.dryRun !== 'false') {
    return reject(req, res, {
      status: 400, reason: 'INVALID_FIELD',
      message: "Field 'dryRun' must be a boolean.", details: { field: 'dryRun', value: b.dryRun },
    });
  }
  return next();
}

/** POST /api/v1/intelligence/generate — intelligence ingestion trigger. */
function validateIntelligenceGenerate(req, res, next) {
  const b = req.body || {};
  if (!intInRange(b.days, 1, 365).ok) {
    return reject(req, res, {
      status: 400, reason: 'INVALID_FIELD',
      message: "Field 'days' must be an integer in [1, 365].", details: { field: 'days', value: b.days },
    });
  }
  return next();
}

/** POST /api/v1/captains-log — captain's log write. */
function validateCaptainsLog(req, res, next) {
  const b = req.body || {};
  // Only pain_score and sleep_hours are numeric in this data model (the backend
  // coerces just these two). energy/mood/sleep_quality/captain_capacity_rating
  // are categorical text from <select>/RAG buttons (e.g. "Moderate", "Green") —
  // they must NOT be numeric-validated (doing so 400'd every real save).
  const checks = [
    ['pain_score', numInRange(b.pain_score, 0, 10)],
    ['sleep_hours', numInRange(b.sleep_hours, 0, 24)],
  ];
  for (const [field, result] of checks) {
    if (!result.ok) {
      return reject(req, res, {
        status: 400, reason: 'INVALID_FIELD',
        message: `Field '${field}' is out of range.`, details: { field, value: b[field] },
      });
    }
  }
  if (b.log_date !== undefined && !/^\d{4}-\d{2}-\d{2}$/.test(String(b.log_date))) {
    return reject(req, res, {
      status: 400, reason: 'INVALID_FIELD',
      message: "Field 'log_date' must be YYYY-MM-DD.", details: { field: 'log_date', value: b.log_date },
    });
  }
  return next();
}

/** POST /api/v1/captains-log/synthesise-week — context assembly / weekly synthesis. */
function validateSynthesiseWeek(req, res, next) {
  const b = req.body || {};
  if (!intInRange(b.days, 1, 90).ok) {
    return reject(req, res, {
      status: 400, reason: 'INVALID_FIELD',
      message: "Field 'days' must be an integer in [1, 90].", details: { field: 'days', value: b.days },
    });
  }
  return next();
}

module.exports = {
  mutationContentTypeGuard,
  objectBodyGuard,
  validateIntelligenceSync,
  validateIntelligenceGenerate,
  validateCaptainsLog,
  validateSynthesiseWeek,
};
