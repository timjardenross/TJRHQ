const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');

const { NumberOneAdapter } = require('../connectors/number-one-adapter');

test('fails closed when Number One outputs are missing', () => {
  const tempDir = fs.mkdtempSync(os.tmpdir() + '/number-one-');
  const adapter = new NumberOneAdapter(tempDir);

  assert.equal(adapter.isDataAvailable(), false);
  assert.equal(adapter.getStatus().status, 'UNAVAILABLE');
  assert.throws(() => adapter.getDailyBrief(), error => error && error.code === 'NUMBER_ONE_UNAVAILABLE');
  assert.throws(() => adapter.getWorkQueue(), error => error && error.code === 'NUMBER_ONE_UNAVAILABLE');
  assert.throws(() => adapter.getEscalations(), error => error && error.code === 'NUMBER_ONE_UNAVAILABLE');

  fs.rmSync(tempDir, { recursive: true, force: true });
});

test('production banner does not advertise mock data', () => {
  const appSource = fs.readFileSync(require.resolve('../app'), 'utf8');
  assert.doesNotMatch(appSource, /Mock Data:\\s+LOADED/);
});
