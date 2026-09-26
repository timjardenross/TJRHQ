// EvidenceMeta coverage regression (Work Package 2, 2026-09-21).
//
// Guards against a route regaining/gaining material data-bearing claims
// with no evidence metadata at all — the exact gap this WP closed (Weekly
// Review, Shopping List, Engineering Handoffs, HQ Status, HQ Evolution
// findings, Emergency Alerts, Human Systems, Physical Readiness, Hub,
// Captain's Chair). This is a narrower, mechanically-checkable proxy for
// "every material claim has EvidenceMeta nearby" (a true semantic check
// isn't statically decidable): it asserts that somewhere in each priority
// route's own file tree (page.tsx plus its _components), the real
// `EvidenceMeta` component from '@/components/EvidenceMeta' is imported —
// not a parallel/ad-hoc evidence-text pattern. It intentionally does not
// check every individual claim within a route; see the WP2 report for the
// specific fields wired per route.
//
// If this test starts failing for a route you're actively building, that's
// the signal to wire EvidenceMeta into the new surface before merging, not
// to loosen this list.

import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'fs';
import { join } from 'path';

const APP_DIR = join(__dirname, '..');

const PRIORITY_ROUTES = [
  'hub',
  'captains-chair-workbench',
  'weekly-review',
  'shopping-list-workbench',
  'engineering-handoffs',
  'agent-status-workbench',
  'self-improvement-findings',
  'emergency-alert-hub-workbench',
  'human-systems-workbench',
  'physical-readiness',
];

function collectTsxFiles(dir: string): string[] {
  let out: string[] = [];
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const entry of entries) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      out = out.concat(collectTsxFiles(full));
    } else if (/\.tsx?$/.test(entry) && !entry.includes('__tests__')) {
      out.push(full);
    }
  }
  return out;
}

function importsEvidenceMeta(filePath: string): boolean {
  const content = readFileSync(filePath, 'utf8');
  return /from ['"]@\/components\/EvidenceMeta['"]/.test(content);
}

describe('EvidenceMeta coverage — priority routes', () => {
  for (const route of PRIORITY_ROUTES) {
    it(`${route} imports the real EvidenceMeta component somewhere in its tree`, () => {
      const routeDir = join(APP_DIR, route);
      const files = collectTsxFiles(routeDir);
      expect(files.length, `expected route directory to exist and contain files: ${routeDir}`).toBeGreaterThan(0);
      const hit = files.some(importsEvidenceMeta);
      expect(hit, `no file under ${route} imports EvidenceMeta from '@/components/EvidenceMeta'`).toBe(true);
    });
  }

  it('lib/captainsChairData.ts HqStatusSummary carries a real observedAt field (backs Hub + System Status EvidenceMeta)', () => {
    const content = readFileSync(join(APP_DIR, '..', 'lib', 'captainsChairData.ts'), 'utf8');
    expect(content).toMatch(/observedAt:\s*string \| null/);
  });
});
