/**
 * Regression tests: Command Centre must never serve mock or fallback data.
 * Missing or invalid Number One output must surface as NumberOneUnavailableError
 * (HTTP 503), and no mock fixture may be reachable from production code.
 *
 * Run: npm test   (uses the Node.js built-in test runner; no extra dependencies)
 */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { NumberOneAdapter, NumberOneUnavailableError } = require('../connectors/number-one-adapter');

const BACKEND_DIR = path.resolve(__dirname, '..');

const VALID_OUTPUTS = {
  'daily_brief.json': JSON.stringify({
    system_health: 'operational',
    top_priorities: [],
    escalations: [],
    total_missions: 0,
    blocked_count: 0,
    recommended_actions: []
  }),
  'work_queue.json': JSON.stringify({ items: [] }),
  'escalations.json': JSON.stringify({ escalations: [] })
};

function outputDir(files = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'number-one-outputs-'));
  for (const [name, body] of Object.entries(files)) {
    fs.writeFileSync(path.join(dir, name), body);
  }
  return dir;
}

function adapterFor(files) {
  const adapter = new NumberOneAdapter(outputDir(files));
  adapter.setDebug(false);
  return adapter;
}

const READERS = [
  ['daily_brief.json', 'getDailyBrief'],
  ['work_queue.json', 'getWorkQueue'],
  ['escalations.json', 'getEscalations']
];

test('adapter exposes no mock data methods', () => {
  const adapter = adapterFor({});
  for (const name of ['getMockBrief', 'getMockQueue', 'getMockEscalations']) {
    assert.equal(adapter[name], undefined, `${name} must not exist`);
  }
});

for (const [file, method] of READERS) {
  test(`${method} throws 503 when ${file} is missing`, () => {
    const adapter = adapterFor({});
    assert.throws(() => adapter[method](), (err) =>
      err instanceof NumberOneUnavailableError &&
      err.statusCode === 503 &&
      err.code === 'NUMBER_ONE_UNAVAILABLE' &&
      err.file === file
    );
  });

  test(`${method} throws 503 when ${file} is not valid JSON`, () => {
    const adapter = adapterFor({ ...VALID_OUTPUTS, [file]: '{not json' });
    assert.throws(() => adapter[method](), (err) =>
      err instanceof NumberOneUnavailableError && err.statusCode === 503 && err.file === file
    );
  });

  test(`${method} throws 503 when ${file} is not an object or array`, () => {
    for (const body of ['null', '42', '"text"']) {
      const adapter = adapterFor({ ...VALID_OUTPUTS, [file]: body });
      assert.throws(() => adapter[method](), (err) =>
        err instanceof NumberOneUnavailableError && err.statusCode === 503
      );
    }
  });
}

test('valid Number One output is transformed and carries no mock markers', () => {
  const adapter = adapterFor(VALID_OUTPUTS);
  const results = READERS.map(([, method]) => adapter[method]());
  for (const result of results) {
    assert.doesNotMatch(JSON.stringify(result), /mock/i);
  }
});

test('isDataAvailable and getStatus report unavailable when outputs are missing', () => {
  const missing = adapterFor({});
  assert.equal(missing.isDataAvailable(), false);
  assert.equal(missing.getStatus().status, 'UNAVAILABLE');

  const present = adapterFor(VALID_OUTPUTS);
  assert.equal(present.isDataAvailable(), true);
  assert.equal(present.getStatus().status, 'LIVE_FROM_NUMBER_ONE');
});

test('production sources contain no mock fixture or mock-data label', () => {
  const forbidden = /getMock|Mock Data|MOCK_FALLBACK|mock-fallback|ENABLE_MOCK_DATA/;
  for (const rel of ['connectors/number-one-adapter.js', 'api/coordination.js', 'app.js']) {
    const source = fs.readFileSync(path.join(BACKEND_DIR, rel), 'utf8');
    assert.doesNotMatch(source, forbidden, `${rel} still references mock data`);
  }
});

test('.env.example no longer enables mock data', () => {
  const envExample = fs.readFileSync(path.join(BACKEND_DIR, '.env.example'), 'utf8');
  assert.doesNotMatch(envExample, /ENABLE_MOCK_DATA/);
});
