'use strict';
/**
 * Personal-health guard for the command centre (Node). Same detector as the Python policy
 * (core/security/personal_data_policy.py) and the LCARS portal guard: both read
 * core/security/personal_health_patterns.json. Default-deny: personal health content is never sent to an
 * external model unless HEALTH_LLM_EXTERNAL_ALLOWED=1. Fails closed: if the detector cannot run, the text is
 * treated as personal.
 */
const fs = require('node:fs');
const path = require('node:path');

const PATTERN_FILE = path.resolve(__dirname, '..', '..', '..', 'security', 'personal_health_patterns.json');
const TRUE_VALUES = ['1', 'true', 'yes', 'on'];

let _compiled = null;
function _load() {
  if (_compiled) return _compiled;
  const doc = JSON.parse(fs.readFileSync(PATTERN_FILE, 'utf8'));
  _compiled = {
    structured: doc.structured.map((e) => ({ name: e.name, rx: new RegExp(e.regex, 'i') })),
    freeText: doc.conservative_free_text.map((r) => new RegExp(r, 'i')),
  };
  return _compiled;
}

function externalAllowed(env = process.env) {
  return TRUE_VALUES.includes(String(env.HEALTH_LLM_EXTERNAL_ALLOWED || '').trim().toLowerCase());
}

/**
 * Assess free-text capture content. Conservative: structured patterns OR the broad free-text lexicon mark it
 * personal; an unreadable pattern file marks it personal. Returns { personal, reasons }.
 */
function assessCapture(...texts) {
  try {
    const { structured, freeText } = _load();
    const hay = texts.filter(Boolean).join('\n');
    const reasons = structured.filter((p) => p.rx.test(hay)).map((p) => p.name);
    if (freeText.some((rx) => rx.test(hay))) reasons.push('free_text_health_term');
    return { personal: reasons.length > 0, reasons };
  } catch (_err) {
    return { personal: true, reasons: ['detector_unavailable'] };
  }
}

module.exports = { externalAllowed, assessCapture, PATTERN_FILE };
