'use strict';
/**
 * Capture enrichment (classification suggestion). Extracted from api/capture.js so the privacy gate is testable
 * without Express. Suggests only — it never routes autonomously.
 */
const guard = require('./personal_health_guard');

/** Deterministic, local suggestion for personal-health (or unclassifiable) captures. Nothing is sent anywhere. */
function localPersonalSuggestion(reasons) {
  return {
    ok: true,
    classification: 'personal',
    importance: 'medium',
    suggested_route: 'captain_log',
    confidence: 0.4,
    reasoning: 'Classified locally: captured text is never sent to an external model.',
    model: 'local-deterministic',
    privacy_withheld: true,
    privacy_reasons: reasons,
  };
}

/**
 * Captured text is private or unclassified, so it is never sent to an external model. Personal-health
 * text gets a deterministic local suggestion; anything else is reported blocked and the capture stays
 * queued for the local enrichment worker.
 */
async function enrichCapture(title, rawText) {
  const verdict = guard.assessCapture(title, rawText);
  if (verdict.personal) return localPersonalSuggestion(verdict.reasons);
  console.warn('[capture/enrich] external classification disabled: capture left queued for the local worker');
  return { ok: false, blocked: true, error: 'external classification disabled; queued for local enrichment' };
}

module.exports = { enrichCapture, localPersonalSuggestion };
