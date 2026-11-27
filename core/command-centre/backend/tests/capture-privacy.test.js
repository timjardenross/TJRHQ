/**
 * Capture enrichment privacy: raw personal-health capture text must never be sent to an external model
 * (default-deny, fail-closed), and no other captured text is sent either (private or unclassified stays local).
 * Run: npm test
 */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const { enrichCapture } = require('../services/capture_enrichment');
const guard = require('../services/personal_health_guard');

const FIXTURES = JSON.parse(fs.readFileSync(path.resolve(__dirname, '..', '..', '..', 'security', 'personal_health_fixtures.json'), 'utf8'));
const GOOD_RESPONSE = JSON.stringify({ candidates: [{ content: { parts: [{ text: JSON.stringify({
  classification: 'mission', importance: 'high', suggested_route: 'missions_inbox', confidence: 0.8, reasoning: 'build task' }) }] } }] });

function deps(env = { GEMINI_API_KEY: 'test-key' }) {
  const calls = [];
  return { calls, env, post: async (url, payload) => { calls.push({ url, payload }); return GOOD_RESPONSE; } };
}

test('personal capture is classified locally and never sent', async () => {
  const d = deps();
  const r = await enrichCapture('', 'Slept badly again, pain 7/10 today', d);
  assert.equal(d.calls.length, 0);
  assert.equal(r.ok, true); assert.equal(r.classification, 'personal'); assert.equal(r.model, 'local-deterministic'); assert.equal(r.privacy_withheld, true);
});

test('structured health forms are never sent', async () => {
  for (const t of FIXTURES.structured_positive) {
    const d = deps();
    const r = await enrichCapture('note', t, d);
    assert.equal(d.calls.length, 0, `sent: ${t}`);
    assert.equal(r.model, 'local-deterministic');
  }
});

test('mixed content is treated conservatively', async () => {
  const d = deps();
  const r = await enrichCapture('Deploy plan', 'Fix the deploy script this week; also my back pain is flaring up', d);
  assert.equal(d.calls.length, 0); assert.equal(r.privacy_withheld, true);
});

test('a personal title alone is enough to withhold', async () => {
  const d = deps();
  await enrichCapture('Migraine again', 'Review the retry logic in the router', d);
  assert.equal(d.calls.length, 0);
});

test('non-health (unclassified) capture is never sent and is reported queued', async () => {
  const d = deps();
  const r = await enrichCapture('Router retries', 'Add retry logic to the model router deploy script', d);
  assert.equal(d.calls.length, 0);
  assert.equal(r.ok, false); assert.equal(r.blocked, true);
});

test('missing API key changes nothing: still no send, still queued', async () => {
  const d = deps({});
  const r = await enrichCapture('x', 'Add retry logic to the router', d);
  assert.equal(r.blocked, true); assert.equal(d.calls.length, 0);
});

test('the health opt-in does not open captured text to an external model', async () => {
  const d = deps({ GEMINI_API_KEY: 'k', HEALTH_LLM_EXTERNAL_ALLOWED: '1' });
  await enrichCapture('', 'Slept badly again, pain 7/10 today', d);
  await enrichCapture('Router', 'Add retry logic', d);
  assert.equal(d.calls.length, 0);
});

test('governance summary is deterministic and makes no outbound request', async () => {
  const https = require('node:https');
  const original = https.request;
  let sent = 0;
  https.request = () => { sent += 1; throw new Error('external request attempted'); };
  process.env.GEMINI_API_KEY = 'k'; process.env.MISTRAL_API_KEY = 'k';
  try {
    const { generateSummary } = require('../api/governance');
    const r = await generateSummary({ decisions: [{ id: 'D-1', title: 'synthetic' }], lessons: [], adrs: [], directives: [] });
    assert.equal(r.provider, 'deterministic'); assert.match(r.text, /1 governance decisions/); assert.equal(sent, 0);
  } finally { https.request = original; delete process.env.GEMINI_API_KEY; delete process.env.MISTRAL_API_KEY; }
});

test('values other than an explicit opt-in stay closed', async () => {
  for (const v of ['', '0', 'false', 'maybe']) {
    const d = deps({ GEMINI_API_KEY: 'k', HEALTH_LLM_EXTERNAL_ALLOWED: v });
    await enrichCapture('', 'pain 7/10', d);
    assert.equal(d.calls.length, 0, `value '${v}' opened the gate`);
  }
});

test('structured negatives are not flagged by the structured detector (parity with Python)', () => {
  for (const t of FIXTURES.structured_negative) {
    const verdict = guard.assessCapture(t);
    assert.ok(!verdict.reasons.some((r) => r !== 'free_text_health_term'), `structured match on: ${t}`);
  }
});

test('unreadable pattern file fails closed (treated as personal)', () => {
  const code = `const fs=require('fs');const o=fs.readFileSync;fs.readFileSync=(p,...a)=>{if(String(p).includes('personal_health_patterns'))throw new Error('missing');return o(p,...a)};
    const g=require(${JSON.stringify(path.resolve(__dirname, '..', 'services', 'personal_health_guard'))});console.log(JSON.stringify(g.assessCapture('Add retry logic')))`;
  const out = JSON.parse(execFileSync(process.execPath, ['-e', code], { encoding: 'utf8' }));
  assert.equal(out.personal, true); assert.deepEqual(out.reasons, ['detector_unavailable']);
});

test('capture.js no longer calls an external model directly', () => {
  const src = fs.readFileSync(path.resolve(__dirname, '..', 'api', 'capture.js'), 'utf8');
  assert.ok(!/generativelanguage|api\.mistral/.test(src));
  assert.match(src, /services\/capture_enrichment/);
});
