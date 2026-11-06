'use strict';

// Boots the real app.js as a child process and checks authentication end to end.
// Run with: node --test core/command-centre/backend/middleware/app-auth.integration.test.js
//
// Notes:
//  - Variables are set to '' (not left unset) when a case needs them absent:
//    app.js loads a dotenv file from the repo root, and dotenv never overrides a
//    variable that already exists in the environment, so a developer's real
//    BACKEND_API_KEY cannot leak into the "missing key" cases.
//  - The child gets a minimal environment (no inherited secrets).

const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');

const BACKEND_DIR = path.resolve(__dirname, '..');
const KEY = 'integration-key-aaaaaaaaaaaa';
const OLD_KEY = 'integration-old-bbbbbbbbbbbb';

const freePort = () =>
  new Promise((resolve, reject) => {
    const s = net.createServer();
    s.listen(0, '127.0.0.1', () => {
      const { port } = s.address();
      s.close(() => resolve(port));
    });
    s.on('error', reject);
  });

const get = (port, urlPath, headers = {}) =>
  new Promise((resolve, reject) => {
    http
      .get({ host: '127.0.0.1', port, path: urlPath, headers, timeout: 4000 }, (res) => {
        let body = '';
        res.on('data', (c) => (body += c));
        res.on('end', () => resolve({ status: res.statusCode, body }));
      })
      .on('error', reject);
  });

async function withApp(extraEnv, fn) {
  const port = await freePort();
  const env = {
    PATH: process.env.PATH,
    NODE_PATH: process.env.NODE_PATH || '',
    PORT: String(port),
    NODE_ENV: '',
    BACKEND_API_KEY: '',
    BACKEND_API_KEY_PREVIOUS: '',
    ALLOW_QUERY_API_KEY: '',
    ALLOW_UNAUTHENTICATED_DEV: '',
    ...extraEnv,
  };
  const child = spawn(process.execPath, ['app.js'], { cwd: BACKEND_DIR, env, stdio: ['ignore', 'pipe', 'pipe'] });
  let logs = '';
  child.stdout.on('data', (d) => (logs += d));
  child.stderr.on('data', (d) => (logs += d));
  try {
    let up = false;
    for (let i = 0; i < 60 && !up; i++) {
      try { up = (await get(port, '/health')).status === 200; } catch { await new Promise((r) => setTimeout(r, 250)); }
    }
    assert.ok(up, `app.js did not start. Logs:\n${logs.slice(-800)}`);
    await fn(port, () => logs);
  } finally {
    child.kill('SIGTERM');
    await new Promise((r) => { child.on('exit', r); setTimeout(r, 2000); });
  }
}

test('startup without a key fails closed in production (503), /health stays up', () =>
  withApp({ NODE_ENV: 'production' }, async (port) => {
    assert.equal((await get(port, '/api/v1/health/summary')).status, 503);
    assert.equal((await get(port, '/health')).status, 200);
  }));

test('startup without a key fails closed with NODE_ENV unset and development too', async () => {
  for (const nodeEnv of ['', 'development']) {
    await withApp({ NODE_ENV: nodeEnv }, async (port) => {
      assert.equal((await get(port, '/api/v1/health/summary')).status, 503, `NODE_ENV='${nodeEnv}'`);
    });
  }
});

test('local-only dev opt-in serves loopback requests without a key', () =>
  withApp({ NODE_ENV: 'development', ALLOW_UNAUTHENTICATED_DEV: '1' }, async (port, logs) => {
    assert.equal((await get(port, '/api/v1/health/summary')).status, 200);
    assert.match(logs(), /LOCAL-ONLY/);
    // Opt-in mode must listen on loopback only: the machine's other addresses refuse the connection.
    const external = Object.values(os.networkInterfaces()).flat().find((i) => i && i.family === 'IPv4' && !i.internal);
    if (external) {
      await assert.rejects(
        new Promise((resolve, reject) => {
          http.get({ host: external.address, port, path: '/health', timeout: 2000 }, resolve).on('error', reject);
        }),
        /ECONNREFUSED|ETIMEDOUT|EHOSTUNREACH/,
      );
    }
  }));

test('dev opt-in is ignored when NODE_ENV=production', () =>
  withApp({ NODE_ENV: 'production', ALLOW_UNAUTHENTICATED_DEV: '1' }, async (port, logs) => {
    assert.equal((await get(port, '/api/v1/health/summary')).status, 503);
    assert.match(logs(), /ignored when NODE_ENV=production/);
  }));

test('with a key: header ok, no key 401, header+query 400, query-only 400, logs clean', () =>
  withApp({ NODE_ENV: 'production', BACKEND_API_KEY: KEY }, async (port, logs) => {
    const p = '/api/v1/health/summary';
    assert.equal((await get(port, p, { 'X-Api-Key': KEY })).status, 200);
    assert.equal((await get(port, p)).status, 401);
    assert.equal((await get(port, `${p}?api_key=${KEY}`, { 'X-Api-Key': KEY })).status, 400);
    assert.equal((await get(port, `${p}?api_key=${KEY}`)).status, 400);
    const out = logs();
    assert.ok(out.includes('api_key query parameter rejected'), 'rejection should be logged');
    assert.ok(!out.includes(KEY), 'key value must never be logged');
    assert.ok(!out.includes('api_key='), 'query string must never be logged');
  }));

test('/api/config is gone: 401 anonymous, 404 authenticated, never returns the key', () =>
  withApp({ NODE_ENV: 'production', BACKEND_API_KEY: KEY }, async (port) => {
    const anon = await get(port, '/api/config');
    assert.equal(anon.status, 401);
    assert.ok(!anon.body.includes(KEY));
    const authed = await get(port, '/api/config', { 'X-Api-Key': KEY });
    assert.equal(authed.status, 404);
    assert.ok(!authed.body.includes(KEY));
  }));

test('two-key rotation window through the real app', () =>
  withApp({ NODE_ENV: 'production', BACKEND_API_KEY: KEY, BACKEND_API_KEY_PREVIOUS: OLD_KEY }, async (port) => {
    const p = '/api/v1/health/summary';
    assert.equal((await get(port, p, { 'X-Api-Key': KEY })).status, 200);
    assert.equal((await get(port, p, { 'X-Api-Key': OLD_KEY })).status, 200);
    assert.equal((await get(port, p, { 'X-Api-Key': 'other' })).status, 401);
  }));

test('emergency rollback flag restores query-only auth and warns at startup', () =>
  withApp({ NODE_ENV: 'production', BACKEND_API_KEY: KEY, ALLOW_QUERY_API_KEY: '1' }, async (port, logs) => {
    assert.equal((await get(port, `/api/v1/health/summary?api_key=${KEY}`)).status, 200);
    assert.match(logs(), /ALLOW_QUERY_API_KEY is enabled/);
    assert.ok(!logs().includes(KEY));
  }));
