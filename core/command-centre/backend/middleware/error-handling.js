/**
 * Error Handling Middleware
 *
 * Purpose: Implement 3-tier fallback strategy
 * 1. Return cached/stale data if available
 * 2. Show last-updated timestamp with "stale" flag
 * 3. Return placeholder with "data unavailable" message
 *
 * Never show raw errors to users.
 */

const { cacheManager } = require('../cache/cache-manager');
const { logSecurityEvent } = require('./observability');

/**
 * Structured error response builder
 */
class ApiError extends Error {
  constructor(message, statusCode = 500, cacheKey = null) {
    super(message);
    this.statusCode = statusCode;
    this.cacheKey = cacheKey;
    this.timestamp = new Date().toISOString();
  }
}

/**
 * Global error handler middleware
 */
const errorHandler = (err, req, res, next) => {
  console.error(`[ERROR] ${err.message}`, err.stack);

  // ── Request-validation failures (Mission 7 Phase 3) ──────────────────────────
  // body-parser surfaces malformed JSON and oversized bodies here. Reject early
  // with a machine reason code + correlation id and log a security event — these
  // must NOT fall through to the cache fallback (it would mask the bad input).
  const isParseError = err.type === 'entity.parse.failed'
    || (err instanceof SyntaxError && err.status === 400 && 'body' in err);
  const isTooLarge = err.type === 'entity.too.large' || err.status === 413;
  if (isParseError || isTooLarge) {
    const reason = isTooLarge ? 'PAYLOAD_TOO_LARGE' : 'MALFORMED_JSON';
    const status = isTooLarge ? 413 : 400;
    logSecurityEvent({ event: 'payload', reason, req, details: { limit: err.limit, length: err.length } });
    return res.status(status).json({
      error: 'invalid_request',
      reason,
      message: isTooLarge ? 'Request payload exceeds the allowed size.' : 'Request body is not valid JSON.',
      requestId: req && req.id,
    });
  }

  const statusCode = err.statusCode || 500;
  const cacheKey = err.cacheKey;

  // Try 3-tier fallback
  if (cacheKey) {
    const { value: cachedData, isStale, age } = cacheManager.get(cacheKey);

    if (cachedData) {
      // Tier 1 & 2: Return cached/stale data with metadata
      const response = {
        status: isStale ? 'stale' : 'cached',
        data: cachedData,
        metadata: {
          source: isStale ? 'stale_cache' : 'fresh_cache',
          ageSeconds: Math.round(age / 1000),
          cacheKey: cacheKey,
          message: isStale
            ? `Data is ${Math.round(age / 1000)}s old (may be stale)`
            : 'Using cached data'
        },
        error: {
          message: 'Using cached data due to API error',
          originalError: process.env.NODE_ENV === 'development' ? err.message : 'Service temporarily unavailable',
          timestamp: new Date().toISOString()
        }
      };
      return res.status(200).json(response); // Always 200 for cached fallback
    }
  }

  // Tier 3: Return placeholder with data unavailable
  const placeholderResponse = {
    status: 'error',
    data: null,
    metadata: {
      source: 'placeholder',
      message: 'Data unavailable'
    },
    error: {
      message: 'Service temporarily unavailable. Please try again later.',
      code: err.code || 'UNKNOWN_ERROR',
      timestamp: new Date().toISOString()
    }
  };

  res.status(statusCode).json(placeholderResponse);
};

/**
 * Middleware to catch async route errors
 */
const asyncHandler = (fn) => (req, res, next) => {
  Promise.resolve(fn(req, res, next)).catch(next);
};

/**
 * Validation error handler
 */
const validateRequest = (schema) => {
  return (req, res, next) => {
    const { error } = schema.validate(req.query);
    if (error) {
      const err = new ApiError(error.details[0].message, 400);
      return next(err);
    }
    next();
  };
};

/**
 * Success response formatter
 */
const successResponse = (data, statusCode = 200, metadata = {}) => {
  return {
    status: 'success',
    statusCode: statusCode,
    data: data,
    metadata: {
      timestamp: new Date().toISOString(),
      ...metadata
    }
  };
};

/**
 * Partial success response (cached with some fresh)
 */
const partialSuccessResponse = (freshData, cachedData = null, message = 'Partial data available') => {
  return {
    status: 'partial',
    statusCode: 200,
    data: freshData,
    cached: cachedData,
    metadata: {
      timestamp: new Date().toISOString(),
      message: message
    }
  };
};

module.exports = {
  ApiError,
  errorHandler,
  asyncHandler,
  validateRequest,
  successResponse,
  partialSuccessResponse
};
