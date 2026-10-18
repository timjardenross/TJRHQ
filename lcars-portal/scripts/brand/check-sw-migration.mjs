// Chromium check of the service-worker upgrade path for the brand icons.
// Serves an OLD sw.js (cache v1) and the NEW public/sw.js, with assets sent
// with a one-year max-age (the worst case for cache.addAll), and asserts:
//   install old -> upgrade to new (new icons + manifest served, v1 cache gone)
//   -> documented rollback (old files + cache bump to v3: old icons served).
// Usage (from lcars-portal/): node scripts/brand/check-sw-migration.mjs <old-sw.js>
//   e.g. git show <base>:lcars-portal/public/sw.js > /tmp/old-sw.js
import { chromium } from 'playwright';
import fs from 'node:fs';
import http from 'node:http';

const oldPath = process.argv[2];
if (!oldPath) throw new Error('usage: node scripts/brand/check-sw-migration.mjs <old-sw.js>');
const OLD = fs.readFileSync(oldPath, 'utf8');
const NEW = fs.readFileSync('public/sw.js', 'utf8');
const ASSETS = ['/icon-192.png', '/icon-512.png', '/icon-maskable-512.png', '/apple-touch-icon.png', '/manifest.webmanifest'];
let sw = OLD, gen = 'old';

const srv = http.createServer((q, r) => {
  const u = q.url.split('?')[0];
  if (u === '/sw.js') { r.writeHead(200, { 'content-type': 'text/javascript', 'cache-control': 'no-cache' }); return r.end(sw); }
  if (u === '/') { r.writeHead(200, { 'content-type': 'text/html' }); return r.end('<!doctype html><title>t</title>'); }
  if (ASSETS.includes(u)) { r.writeHead(200, { 'content-type': 'text/plain', 'cache-control': 'public, max-age=31536000' }); return r.end(`${gen}:${u}`); }
  r.writeHead(404); r.end();
}).listen(0);
const port = srv.address().port;

const exe = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
const browser = await chromium.launch({ executablePath: exe || undefined, args: ['--no-sandbox'] });
const page = await (await browser.newContext()).newPage();
const state = () => page.evaluate(async () => ({
  caches: await caches.keys(),
  icon: await fetch('/icon-192.png').then((r) => r.text()),
  manifest: await fetch('/manifest.webmanifest').then((r) => r.text()),
}));
const update = async () => {
  await page.evaluate(async () => { const r = await navigator.serviceWorker.getRegistration(); await r.update(); });
  await page.waitForTimeout(1500); await page.reload(); await page.waitForTimeout(600);
};

let failed = 0;
const expectState = (label, s, cache, gen) => {
  const ok = s.caches.length === 1 && s.caches[0] === cache && s.icon === `${gen}:/icon-192.png` && s.manifest === `${gen}:/manifest.webmanifest`;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}  caches=${JSON.stringify(s.caches)} icon=${s.icon}`);
  if (!ok) failed++;
};

await page.goto(`http://localhost:${port}/`);
await page.evaluate(async () => { await navigator.serviceWorker.register('/sw.js'); await navigator.serviceWorker.ready; });
await page.reload(); await page.waitForTimeout(600);
const oldCache = (await state()).caches[0];
expectState('installed OLD sw', await state(), oldCache, 'old');
sw = NEW; gen = 'new'; await update();
expectState('upgraded to NEW sw (long max-age)', await state(), 'lcars-static-v2', 'new');
// Plain revert (old sw.js, old files): informational only. Under a one-year
// max-age the old worker's addAll reads the HTTP cache and re-caches NEW icons.
sw = OLD; gen = 'old'; await update();
const plain = await state();
console.log(`INFO  plain revert to OLD sw.js  caches=${JSON.stringify(plain.caches)} icon=${plain.icon}`);
// Documented rollback: restore the old files AND bump the cache name again
// (v3), keeping cache: 'reload'. This must serve the old icons.
sw = NEW.replace('lcars-static-v2', 'lcars-static-v3'); gen = 'old'; await update();
expectState('documented rollback (old files + cache v3)', await state(), 'lcars-static-v3', 'old');
await browser.close(); srv.close();
process.exit(failed ? 1 : 0);
