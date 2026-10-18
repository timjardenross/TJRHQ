import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';

// Design uplift Stage A2a: no text below 12 px anywhere in HQ's source.
const FLOOR_PX = 12;
const root = path.join(process.cwd(), 'src');

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = path.join(dir, name);
    if (statSync(p).isDirectory()) {
      if (name === '__tests__' || name === 'node_modules') continue;
      walk(p, out);
    } else if (/\.(tsx?|css)$/.test(name) && !/\.(test|stories)\./.test(name)) {
      out.push(p);
    }
  }
  return out;
}

const files = walk(root);
const rel = (p: string) => path.relative(process.cwd(), p);

// Tailwind arbitrary sizes in px or rem (1rem = 16px), e.g. text-[11px], sm:text-[0.7rem]
const ARBITRARY = /text-\[(\d+(?:\.\d+)?)(px|rem)\]/g;

function offenders(): string[] {
  const out: string[] = [];
  for (const f of files) {
    const src = readFileSync(f, 'utf8');
    for (const m of src.matchAll(ARBITRARY)) {
      const px = m[2] === 'rem' ? Number(m[1]) * 16 : Number(m[1]);
      if (px < FLOOR_PX) out.push(`${rel(f)}: ${m[0]}`);
    }
    // plain CSS and inline-style font sizes
    for (const m of src.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)) {
      if (Number(m[1]) < FLOOR_PX) out.push(`${rel(f)}: font-size ${m[1]}px`);
    }
    for (const m of src.matchAll(/fontSize:\s*(\d+(?:\.\d+)?)\b(?!\s*\*)/g)) {
      if (Number(m[1]) < FLOOR_PX) out.push(`${rel(f)}: fontSize ${m[1]}`);
    }
  }
  return out;
}

describe('text size floor (design uplift Stage A2a)', () => {
  it('scans a meaningful number of source files', () => {
    expect(files.length).toBeGreaterThan(300);
  });

  it('no text class, font-size declaration or inline fontSize is below 12 px', () => {
    expect(offenders()).toEqual([]);
  });

  it('the Tailwind config adds no sub-12 px text size', () => {
    const cfg = readFileSync(path.join(process.cwd(), 'tailwind.config.ts'), 'utf8');
    expect(cfg).not.toMatch(/fontSize:\s*\{[^}]*['"]?(2xs|3xs)['"]?\s*:/);
  });

  it('the matcher itself works: it flags 11px, 0.7rem and 11.5px, and accepts 12px, 12.5px and 0.75rem', () => {
    const flagged = (s: string) => [...s.matchAll(ARBITRARY)].some((m) => (m[2] === 'rem' ? Number(m[1]) * 16 : Number(m[1])) < FLOOR_PX);
    expect(flagged('text-[11px]')).toBe(true);
    expect(flagged('sm:text-[0.7rem]')).toBe(true);
    expect(flagged('text-[11.5px]')).toBe(true);
    expect(flagged('text-[12px]')).toBe(false);
    expect(flagged('text-[12.5px]')).toBe(false);
    expect(flagged('text-[0.75rem]')).toBe(false);
  });
});
