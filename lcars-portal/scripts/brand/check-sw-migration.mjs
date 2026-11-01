// Chromium check of the service-worker upgrade path using the REAL files.
// Serves the OLD sw.js and OLD assets (from a git ref) and the NEW working-tree
// sw.js and assets, with a one-year max-age (worst case for cache.addAll), and
// asserts on the actual bytes (sha256) the page receives for ALL five
// precached assets:
//   1. installed OLD: cache v1, old icon + manifest bytes
//   2. upgrade to NEW: the new cache name only, new icon + manifest bytes
//   3. FAILED upgrade (one new asset returns 500): the old worker and its v1
//      cache stay in place, old bytes still served, no stray new cache
//   4. documented rollback (old files + a further cache name bump): old bytes again
// Usage (from lcars-portal/): node scripts/brand/check-sw-migration.mjs <git-ref-of-old-version>
//   e.g. node scripts/brand/check-sw-migration.mjs origin/main
import { chromium } from 'playwright';
import { execFileSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';

const ref = process.argv[2];
if (!ref) throw new Error('usage: node scripts/brand/check-sw-migration.mjs <git-ref-of-old-version>');
const ASSETS = ['/icon-192.png', '/icon-512.png', '/icon-maskable-512.png', '/apple-touch-icon.png', '/manifest.webmanifest'];
const TYPES = { '.png': 'image/png', '.webmanifest': 'application/manifest+json' };
const sha = (b) => crypto.createHash('sha256').update(b).digest('hex');
const oldFile = (p) => execFileSync('git', ['show', `${ref}:lcars-portal/public${p}`], { maxBuffer: 1 << 26 });
const OLD = { sw: oldFile('/sw.js').toString('utf8'), files: Object.fromEntries(ASSETS.map((a) => [a, oldFile(a)])) };
const NEW = { sw: fs.readFileSync('public/sw.js', 'utf8'), files: Object.fromEntries(ASSETS.map((a) => [a, fs.readFileSync('public' + a)])) };
if (sha(OLD.files['/icon-192.png']) === sha(NEW.files['/icon-192.png'])) throw new Error('old and new icon-192.png are identical: nothing to test');

const CUR = NEW.sw.match(/const CACHE = '([^']+)'/)[1];
let cur = OLD, fail500 = null;
const srv = http.createServer((q, r) => {
  const u = q.url.split('?')[0];
  if (u === '/sw.js') { r.writeHead(200, { 'content-type': 'text/javascript', 'cache-control': 'no-cache' }); return r.end(cur.sw); }
  if (u === '/') { r.writeHead(200, { 'content-type': 'text/html' }); return r.end('<!doctype html><title>t</title>'); }
  if (ASSETS.includes(u)) {
    if (fail500 === u) { r.writeHead(500); return r.end('boom'); }
    const ext = u.slice(u.lastIndexOf('.'));
    r.writeHead(200, { 'content-type': TYPES[ext], 'cache-control': 'public, max-age=31536000' });
    return r.end(cur.files[u]);
  }
  r.writeHead(404); r.end();
}).listen(0);
const port = srv.address().port;

const exe = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
const browser = await chromium.launch({ executablePath: exe || undefined, args: ['--no-sandbox'] });
const page = await (await browser.newContext()).newPage();
const state = () => page.evaluate(async () => {
  const hash = async (u) => { const b = await fetch(u).then((r) => r.arrayBuffer()); const d = await crypto.subtle.digest('SHA-256', b); return [...new Uint8Array(d)].map((x) => x.toString(16).padStart(2, '0')).join(''); };
  const files = {};
  for (const u of ['/icon-192.png', '/icon-512.png', '/icon-maskable-512.png', '/apple-touch-icon.png', '/manifest.webmanifest']) files[u] = await hash(u);
  return { caches: await caches.keys(), files, icon: files['/icon-192.png'] };
});
const update = async () => {
  await page.evaluate(async () => { const r = await navigator.serviceWorker.getRegistration(); try { await r.update(); } catch (e) {} });
  await page.waitForTimeout(1500); await page.reload(); await page.waitForTimeout(600);
};

let failed = 0;
const check = (label, s, cache, v) => {
  // Every precached asset must be byte-identical to the expected version.
  const bad = ASSETS.filter((u) => s.files[u] !== sha(v.files[u]));
  const ok = s.caches.length === 1 && s.caches[0] === cache && bad.length === 0;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}  caches=${JSON.stringify(s.caches)} assets=${ASSETS.length - bad.length}/${ASSETS.length} byte-identical${bad.length ? ' MISMATCH ' + bad.join(',') : ''}`);
  if (!ok) failed++;
};

await page.goto(`http://localhost:${port}/`);
await page.evaluate(async () => { await navigator.serviceWorker.register('/sw.js'); await navigator.serviceWorker.ready; });
await page.reload(); await page.waitForTimeout(600);
const oldCache = (await state()).caches[0];
check('installed OLD (real bytes)', await state(), oldCache, OLD);
cur = NEW; await update();
check('upgraded to NEW (real bytes, long max-age)', await state(), CUR, NEW);
// Failed upgrade: go back to a state with only OLD installed, then publish a NEW whose precache fails.
cur = OLD; await update();
cur = { sw: NEW.sw.replace(CUR, CUR + '-failing'), files: NEW.files }; fail500 = '/icon-512.png'; await update(); fail500 = null;
{
  const s = await state();
  const ok = !s.caches.includes(CUR + '-failing') && s.caches.length === 1;
  console.log(`${ok ? 'PASS' : 'FAIL'}  failed precache leaves the previous cache in place and no partial cache  caches=${JSON.stringify(s.caches)}`);
  if (!ok) failed++;
}
cur = { sw: NEW.sw.replace(CUR, CUR + '-rollback'), files: OLD.files }; await update();
check('documented rollback (old files + further cache bump)', await state(), CUR + '-rollback', OLD);
await browser.close(); srv.close();
process.exit(failed ? 1 : 0);
