import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

// SEC-01 Option B: every LCARS route that proxies the self-improvement dashboard
// must call requireSiOwner() before any upstream request. Source-order check.
const ROUTES = [
  'self-improvement/findings/route.ts',
  'self-improvement/opportunities/route.ts',
  'self-improvement/evolution-summary/route.ts',
  'self-improvement/mission-dispatch-status/route.ts',
  'self-improvement/decide/route.ts',
  'self-improvement/opportunities/decide/route.ts',
  'engineering-handoffs/route.ts',
  'engineering-handoffs/artifact/route.ts',
];

describe('owner gate precedes every upstream call (SEC-01)', () => {
  const base = join(__dirname, '..');
  for (const rel of ROUTES) {
    it(`${rel}: imports and calls requireSiOwner() before the first fetch`, () => {
      const src = readFileSync(join(base, rel), 'utf8');
      expect(src).toContain("from '@/lib/selfImprovementAuth'");
      expect(src).not.toContain("from '@/lib/supabase-server'");
      const gate = src.indexOf('await requireSiOwner()');
      const fetchAt = src.indexOf('await fetch(');
      expect(gate).toBeGreaterThan(-1);
      expect(fetchAt).toBeGreaterThan(-1);
      expect(gate).toBeLessThan(fetchAt);
    });
  }
});
