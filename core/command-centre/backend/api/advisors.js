/**
 * Advisor Console API — /api/v1/advisors/*
 *
 * MSN-B Phase 1: single-turn specialist sessions, persona selection,
 * context injection. Reuses existing specialist infrastructure.
 */

const express = require('express');
const router = express.Router();
const { asyncHandler, successResponse, ApiError } = require('../middleware/error-handling');
const { getPersonas, requestAdvice } = require('../connectors/advisor-adapter');

// ── GET /api/v1/advisors/personas ───────────────────────────────────────────
router.get('/personas', asyncHandler(async (req, res) => {
  res.json(successResponse(getPersonas(), 200, { source: 'static' }));
}));

// ── POST /api/v1/advisors/session ───────────────────────────────────────────
// Body: { question: string, advisor_key: string, context?: object }
router.post('/session', asyncHandler(async (req, res) => {
  const { question, advisor_key, context } = req.body || {};
  if (!question || !question.trim()) throw new ApiError(400, 'question is required');
  if (!advisor_key)                  throw new ApiError(400, 'advisor_key is required');

  const result = requestAdvice({ question: question.trim(), advisor_key, context });
  if (!result.ok) throw new ApiError(400, result.error || 'Advisor request failed');

  res.json(successResponse(result, 200, { degraded: result.degraded || false }));
}));

module.exports = router;
