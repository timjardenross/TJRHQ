import { describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

// Executes the real public/sw.js in a minimal ServiceWorker-like sandbox.
function load(opts: { addAllFails?: boolean } = {}) {
  const listeners: Record<string, (e: unknown) => void> = {};
  const opened: string[] = [];
  const added: unknown[][] = [];
  let keys = ['lcars-static-v1', 'unrelated-cache'];
  const deleted: string[] = [];
  class FakeRequest {
    constructor(public url: string, public init?: { cache?: string }) {}
    get cache() { return this.init?.cache ?? 'default'; }
    method = 'GET';
  }
  const caches = {
    open: async (name: string) => { opened.push(name); return { addAll: async (r: unknown[]) => { added.push(r); if (opts.addAllFails) throw new Error('precache failed'); }, put: async () => {} }; },
    keys: async () => keys,
    delete: async (k: string) => { deleted.push(k); keys = keys.filter((x) => x !== k); return true; },
    match: async () => undefined,
  };
  const self = {
    location: { origin: 'https://hq.test' },
    addEventListener: (t: string, fn: (e: unknown) => void) => { listeners[t] = fn; },
    skipWaiting: vi.fn(),
    clients: { claim: vi.fn(async () => {}) },
  };
  const src = readFileSync(path.join(process.cwd(), 'public', 'sw.js'), 'utf8');
  vm.runInNewContext(src, { self, caches, Request: FakeRequest, URL, fetch: vi.fn(), Promise });
  return { listeners, opened, added, deleted, self, FakeRequest };
}

const waitUntil = () => { const p: Promise<unknown>[] = []; return { e: { waitUntil: (x: Promise<unknown>) => p.push(x) }, done: () => Promise.all(p) }; };

describe('public/sw.js (brand Stage 1)', () => {
  it('uses cache v2, so installed v1 copies are replaced', async () => {
    const { listeners, opened } = load();
    const w = waitUntil(); listeners.install(w.e); await w.done();
    expect(opened).toEqual(['lcars-static-v2']);
  });

  it('precaches every static asset with cache: "reload" so a long HTTP max-age cannot serve old icons', async () => {
    const { listeners, added } = load();
    const w = waitUntil(); listeners.install(w.e); await w.done();
    const reqs = added[0] as { url: string; cache: string }[];
    expect(reqs.map((r) => r.url).sort()).toEqual(
      ['/apple-touch-icon.png', '/icon-192.png', '/icon-512.png', '/icon-maskable-512.png', '/manifest.webmanifest'],
    );
    expect(reqs.every((r) => r.cache === 'reload')).toBe(true);
  });

  it('on activate deletes the old v1 cache and every other cache, keeping only v2', async () => {
    const { listeners, deleted } = load();
    const w = waitUntil(); listeners.activate(w.e); await w.done();
    expect(deleted.sort()).toEqual(['lcars-static-v1', 'unrelated-cache']);
  });

  it('skips waiting and claims clients so the update applies promptly', async () => {
    const { listeners, self } = load();
    const a = waitUntil(); listeners.install(a.e); await a.done();
    const b = waitUntil(); listeners.activate(b.e); await b.done();
    expect(self.skipWaiting).toHaveBeenCalled();
    expect(self.clients.claim).toHaveBeenCalled();
  });

  it('failure path: a failed precache rejects the install, does not skip waiting, and removes the partial v2 cache (the working v1 cache is untouched)', async () => {
    const { listeners, self, deleted } = load({ addAllFails: true });
    const w = waitUntil(); listeners.install(w.e);
    await expect(w.done()).rejects.toThrow('precache failed');
    expect(self.skipWaiting).not.toHaveBeenCalled();
    expect(deleted).toEqual(['lcars-static-v2']);
  });

  it('does not intercept navigations or API requests', () => {
    const { listeners } = load();
    const respondWith = vi.fn();
    listeners.fetch({ request: { method: 'GET', url: 'https://hq.test/hub' }, respondWith });
    listeners.fetch({ request: { method: 'GET', url: 'https://hq.test/api/thing' }, respondWith });
    expect(respondWith).not.toHaveBeenCalled();
  });
});
