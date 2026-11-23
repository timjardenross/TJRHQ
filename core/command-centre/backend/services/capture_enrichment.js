'use strict';
/**
 * Capture enrichment (classification suggestion). Extracted from api/capture.js so the privacy gate is testable
 * without Express. Suggests only — it never routes autonomously.
 */
const guard = require('./personal_health_guard');

function _httpsPost(url, payload) {
  const https = require('https');
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const req = https.request({
      hostname: u.hostname,
      port: 443,
      path: u.pathname + u.search,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) },
    }, (res) => {
      let data = '';
      res.on('data', (c) => { data += c; });
      res.on('end', () => resolve(data));
    });
    req.on('error', reject);
    req.setTimeout(30000, () => req.destroy(new Error('Gemini timeout')));
    req.write(payload);
    req.end();
  });
}

/** Deterministic, local suggestion for personal-health (or unclassifiable) captures. Nothing is sent anywhere. */
function localPersonalSuggestion(reasons) {
  return {
    ok: true,
    classification: 'personal',
    importance: 'medium',
    suggested_route: 'captain_log',
    confidence: 0.4,
    reasoning: 'Classified locally: possible personal health content is never sent to an external model.',
    model: 'local-deterministic',
    privacy_withheld: true,
    privacy_reasons: reasons,
  };
}

async function enrichCapture(title, rawText, deps = {}) {
  const env = deps.env || process.env;
  const post = deps.post || _httpsPost;
  // Privacy gate (follow-up to #661): personal-health capture text never leaves this host. Anything personal or
  // unclassifiable gets a deterministic local suggestion; only clearly non-health captures use the external model.
  if (!guard.externalAllowed(env)) {
    const verdict = guard.assessCapture(title, rawText);
    if (verdict.personal) return localPersonalSuggestion(verdict.reasons);
  }
  const apiKey = env.GEMINI_API_KEY;
  if (!apiKey) {
    console.warn('[capture/enrich] GEMINI_API_KEY not set — enrichment unavailable');
    return { ok: false, error: 'GEMINI_API_KEY not configured' };
  }

  const text = (rawText || title || '').slice(0, 2000);

  const prompt = `You are a capture classification assistant for USS TJR command system.
Classify the provided capture text and return ONLY a JSON object with these exact keys:
{
  "classification": "<reference|mission|personal|research|decision|unclassified>",
  "importance": "<low|medium|high>",
  "suggested_route": "<captain_log|missions_inbox|decision_queue|research_inbox|note|none>",
  "confidence": <0.0-1.0>,
  "reasoning": "<one sentence>"
}
Rules:
- mission: something to build, fix, or ship
- decision: outstanding choice requiring deliberate action
- personal: health, body, energy, recovery, sleep
- research: idea, hypothesis, thing to explore
- reference: note, reminder, context, information
- unclassified: unclear or ambiguous
Return ONLY the JSON, no other text.

Capture text:
${text}`;

  const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key=${apiKey}`;
  const payload = JSON.stringify({
    contents: [{ parts: [{ text: prompt }] }],
    generationConfig: { responseMimeType: 'application/json', temperature: 0.1 },
  });

  try {
    const responseText = await post(url, payload);

    const body = JSON.parse(responseText);
    // Gemini 2.5 Flash may return thinking + text parts; join non-thought text parts
    const parts = body?.candidates?.[0]?.content?.parts ?? [];
    const content = parts
      .filter(p => !p.thought)
      .map(p => p.text || '')
      .join('')
      .trim();

    if (!content) throw new Error('Gemini returned no content');

    const json = JSON.parse(content.replace(/^```json?\s*/i, '').replace(/```\s*$/, ''));

    const VALID_CLASSES = ['reference', 'mission', 'personal', 'research', 'decision', 'unclassified'];
    const VALID_IMP     = ['low', 'medium', 'high'];
    return {
      ok:              true,
      classification:  VALID_CLASSES.includes(json.classification) ? json.classification : 'unclassified',
      importance:      VALID_IMP.includes(json.importance) ? json.importance : 'medium',
      suggested_route: json.suggested_route || 'none',
      confidence:      typeof json.confidence === 'number' ? Math.min(1, Math.max(0, json.confidence)) : 0.5,
      reasoning:       (json.reasoning || '').slice(0, 300),
      model:           'gemini-3.5-flash-lite',
    };
  } catch (err) {
    console.warn('[capture/enrich] Gemini call failed:', err.message);
    return { ok: false, error: err.message };
  }
}

module.exports = { enrichCapture, localPersonalSuggestion };
