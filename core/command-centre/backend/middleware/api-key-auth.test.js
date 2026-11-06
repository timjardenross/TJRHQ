'use strict';

// Run with: node --test core/command-centre/backend/middleware/api-key-auth.test.js
// Uses only node:test and the backend's existing express dependency (run
// `npm ci` in core/command-centre/backend first).

const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const express = require('express');
const { createApiKeyAuth } = require('./api-key-auth');

const KEY = 'test-key-aaaaaaaaaaaaaaaa';
const OLD_KEY = 'old-key-bbbbbbbbbbbbbbbbbb';

async function withServer(options, fn) {
  const app = express();
  const seen = [];
  app.use(createApiKeyAuth({ ...options, onQueryKeyUse: (path, outcome) => seen.push([path, outcome]) }));
  app.get('/health', (req, res) => res.json({ ok: true }));
  app.get('/api/v1/thing', (req, res) => res.json({ data: 'secret-data' }));
  app.use((req, res) => res.status(404).json({ error: 'not_found' }));
  const server = http.createServer(app);
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();
  const call = (path, headers = {}) =>
    new Promise((resolve, reject) => {
      http
        .get({ host: '127.0.0.1', port, path, headers }, (res) => {
          let body = '';
          res.on('data', (c) => (body += c));
          res.on('end', () => resolve({ status: res.statusCode, body }));
        })
        .on('error', reject);
    });
  try {
    await fn(call, seen);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

// Calls the middleware directly with a fake request (needed to simulate a
// non-loopback peer address).
function direct(options, req) {
  let status = 200;
  let passed = false;
  const res = {
    status(code) { status = code; return this; },
    json() { return this; },
  };
  createApiKeyAuth(options)({ headers: {}, query: {}, path: '/api/v1/thing', ...req }, res, () => { passed = true; });
  return { status, passed };
}

test('valid header key is accepted', () =>
  withServer({ keys: [KEY], isProduction: true }, async (call) => {
    assert.equal((await call('/api/v1/thing', { 'X-Api-Key': KEY })).status, 200);
  }));

test('missing and wrong keys are rejected with 401', () =>
  withServer({ keys: [KEY], isProduction: true }, async (call) => {
    assert.equal((await call('/api/v1/thing')).status, 401);
    assert.equal((await call('/api/v1/thing', { 'X-Api-Key': 'nope' })).status, 401);
    assert.equal((await call('/api/v1/thing', { 'X-Api-Key': KEY + 'x' })).status, 401);
    assert.equal((await call('/api/v1/thing', { 'X-Api-Key': KEY.slice(0, -1) })).status, 401);
  }));

test('api_key query parameter is rejected (400), even when the value is correct', () =>
  withServer({ keys: [KEY], isProduction: true }, async (call, seen) => {
    const res = await call(`/api/v1/thing?api_key=${KEY}`);
    assert.equal(res.status, 400);
    assert.ok(!res.body.includes('secret-data'));
    assert.ok(!res.body.includes(KEY), 'response must not echo the key');
    assert.deepEqual(seen, [['/api/v1/thing', 'rejected']]);
  }));

test('api_key query parameter is rejected even when a VALID header is also sent', () =>
  withServer({ keys: [KEY], isProduction: true }, async (call, seen) => {
    const res = await call(`/api/v1/thing?api_key=junk`, { 'X-Api-Key': KEY });
    assert.equal(res.status, 400);
    assert.ok(!res.body.includes('secret-data'));
    assert.deepEqual(seen, [['/api/v1/thing', 'rejected']]);
  }));

test('array / empty api_key query forms are also rejected, including on public paths', () =>
  withServer({ keys: [KEY], isProduction: true }, async (call) => {
    assert.equal((await call('/api/v1/thing?api_key[]=x', { 'X-Api-Key': KEY })).status, 400);
    assert.equal((await call('/api/v1/thing?api_key=', { 'X-Api-Key': KEY })).status, 400);
    assert.equal((await call(`/health?api_key=${KEY}`)).status, 400);
    assert.equal((await call('/health')).status, 200);
  }));

test('logged rejections contain only the path, never the query string or key', () =>
  withServer({ keys: [KEY], isProduction: true }, async (call, seen) => {
    await call(`/api/v1/thing?api_key=${KEY}&x=1`);
    assert.equal(JSON.stringify(seen).includes(KEY), false);
    assert.equal(JSON.stringify(seen).includes('x=1'), false);
  }));

test('rollback lever: allowQueryKey accepts the query form only when no header is sent', () =>
  withServer({ keys: [KEY], isProduction: true, allowQueryKey: true }, async (call, seen) => {
    assert.equal((await call(`/api/v1/thing?api_key=${KEY}`)).status, 200);
    assert.equal((await call('/api/v1/thing?api_key=wrong')).status, 401);
    assert.equal((await call('/api/v1/thing?api_key=junk', { 'X-Api-Key': KEY })).status, 200);
    assert.deepEqual(seen.map((s) => s[1]), ['accepted', 'accepted']);
  }));

test('/health is public; /api/config is not public and leaks nothing', () =>
  withServer({ keys: [KEY], isProduction: true }, async (call) => {
    assert.equal((await call('/health')).status, 200);
    const anon = await call('/api/config');
    assert.equal(anon.status, 401);
    assert.ok(!anon.body.includes(KEY));
    const authed = await call('/api/config', { 'X-Api-Key': KEY });
    assert.equal(authed.status, 404);
    assert.ok(!authed.body.includes(KEY));
  }));

test('fail closed: no key configured returns 503 in production AND in development', () =>
  Promise.all([true, false].map((isProduction) =>
    withServer({ keys: [], isProduction }, async (call) => {
      assert.equal((await call('/api/v1/thing')).status, 503);
      assert.equal((await call('/health')).status, 200);
    }))));

test('fail closed: empty-string keys count as no key', () =>
  withServer({ keys: ['', undefined], isProduction: false }, async (call) => {
    assert.equal((await call('/api/v1/thing')).status, 503);
  }));

test('explicit local-only dev opt-in: loopback allowed, non-loopback refused', () => {
  const opts = { keys: [], isProduction: false, allowUnauthenticatedDev: true };
  assert.equal(direct(opts, { socket: { remoteAddress: '127.0.0.1' } }).passed, true);
  assert.equal(direct(opts, { socket: { remoteAddress: '::1' } }).passed, true);
  assert.equal(direct(opts, { socket: { remoteAddress: '::ffff:127.0.0.1' } }).passed, true);
  const remote = direct(opts, { socket: { remoteAddress: '203.0.113.9' } });
  assert.equal(remote.passed, false);
  assert.equal(remote.status, 503);
  assert.equal(direct(opts, { socket: undefined }).passed, false);
});

test('dev opt-in is ignored in production and when not exactly true', () => {
  const lo = { socket: { remoteAddress: '127.0.0.1' } };
  assert.equal(direct({ keys: [], isProduction: true, allowUnauthenticatedDev: true }, lo).passed, false);
  assert.equal(direct({ keys: [], isProduction: false, allowUnauthenticatedDev: 'yes' }, lo).passed, false);
  assert.equal(direct({ keys: [], isProduction: false }, lo).passed, false);
});

test('dev opt-in never weakens auth when a key IS configured', () => {
  const opts = { keys: [KEY], isProduction: false, allowUnauthenticatedDev: true };
  assert.equal(direct(opts, { socket: { remoteAddress: '127.0.0.1' } }).status, 401);
});

test('rotation: both current and previous keys accepted, others not', () =>
  withServer({ keys: [KEY, OLD_KEY], isProduction: true }, async (call) => {
    assert.equal((await call('/api/v1/thing', { 'X-Api-Key': KEY })).status, 200);
    assert.equal((await call('/api/v1/thing', { 'X-Api-Key': OLD_KEY })).status, 200);
    assert.equal((await call('/api/v1/thing', { 'X-Api-Key': 'third' })).status, 401);
  }));

test('rotation: after the previous key is removed it stops working', () =>
  withServer({ keys: [KEY], isProduction: true }, async (call) => {
    assert.equal((await call('/api/v1/thing', { 'X-Api-Key': OLD_KEY })).status, 401);
  }));

test('empty header never matches', () =>
  withServer({ keys: [KEY, '', undefined], isProduction: true }, async (call) => {
    assert.equal((await call('/api/v1/thing', { 'X-Api-Key': '' })).status, 401);
  }));
