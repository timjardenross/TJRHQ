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

test('api_key query parameter is rejected by default, even when correct', () =>
  withServer({ keys: [KEY], isProduction: true }, async (call, seen) => {
    const res = await call(`/api/v1/thing?api_key=${KEY}`);
    assert.equal(res.status, 401);
    assert.ok(!res.body.includes('secret-data'));
    assert.ok(!res.body.includes(KEY), 'response must not echo the key');
    assert.deepEqual(seen, [['/api/v1/thing', 'rejected']]);
  }));

test('api_key query parameter works only when allowQueryKey is on (rollback lever)', () =>
  withServer({ keys: [KEY], isProduction: true, allowQueryKey: true }, async (call, seen) => {
    assert.equal((await call(`/api/v1/thing?api_key=${KEY}`)).status, 200);
    assert.equal((await call('/api/v1/thing?api_key=wrong')).status, 401);
    assert.equal(seen[0][1], 'accepted');
  }));

test('valid header still works when a stray api_key query param is present', () =>
  withServer({ keys: [KEY], isProduction: true }, async (call) => {
    assert.equal((await call('/api/v1/thing?api_key=junk', { 'X-Api-Key': KEY })).status, 200);
  }));

test('/health is public; /api/config is no longer public and does not leak a key', () =>
  withServer({ keys: [KEY], isProduction: true }, async (call) => {
    assert.equal((await call('/health')).status, 200);
    const anon = await call('/api/config');
    assert.equal(anon.status, 401);
    assert.ok(!anon.body.includes(KEY));
    const authed = await call('/api/config', { 'X-Api-Key': KEY });
    assert.equal(authed.status, 404);
    assert.ok(!authed.body.includes(KEY));
  }));

test('production without a configured key fails closed (503)', () =>
  withServer({ keys: [], isProduction: true }, async (call) => {
    assert.equal((await call('/api/v1/thing')).status, 503);
    assert.equal((await call('/health')).status, 200);
  }));

test('non-production without a configured key passes through (dev mode)', () =>
  withServer({ keys: [], isProduction: false }, async (call) => {
    assert.equal((await call('/api/v1/thing')).status, 200);
  }));

test('rotation: both current and previous keys accepted, others not', () =>
  withServer({ keys: [KEY, OLD_KEY], isProduction: true }, async (call) => {
    assert.equal((await call('/api/v1/thing', { 'X-Api-Key': KEY })).status, 200);
    assert.equal((await call('/api/v1/thing', { 'X-Api-Key': OLD_KEY })).status, 200);
    assert.equal((await call('/api/v1/thing', { 'X-Api-Key': 'third' })).status, 401);
  }));

test('empty or undefined entries in keys never match an empty header', () =>
  withServer({ keys: [KEY, '', undefined], isProduction: true }, async (call) => {
    assert.equal((await call('/api/v1/thing', { 'X-Api-Key': '' })).status, 401);
  }));
