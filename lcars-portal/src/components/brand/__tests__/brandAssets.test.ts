import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { brandMarkSrc } from '../BrandMark';
import { brandWordmarkSrc, WORDMARK_ASPECT } from '../BrandWordmark';

const DIR = path.join(process.cwd(), 'public', 'brand');
const EXPECTED = [
  'hq-icon-light.svg', 'hq-icon-dark.svg', 'hq-icon-mono-navy.svg', 'hq-icon-mono-white.svg',
  'hq-wordmark-primary-light.svg', 'hq-wordmark-primary-dark.svg',
  'hq-wordmark-horizontal-light.svg', 'hq-wordmark-horizontal-dark.svg',
  'hq-wordmark-compact-light.svg', 'hq-wordmark-compact-dark.svg',
  'hq-wordmark-mono-navy.svg', 'hq-wordmark-mono-white.svg',
  'hq-favicon-16.svg', 'hq-favicon-32.svg', 'hq-favicon-adaptive.svg', 'hq-app-icon-fullbleed.svg',
];

describe('public/brand assets', () => {
  it('ships exactly the 16 specified SVGs', () => {
    const svgs = readdirSync(DIR).filter((f) => f.endsWith('.svg')).sort();
    expect(svgs).toEqual([...EXPECTED].sort());
  });

  it.each(EXPECTED)('%s has no live text, a viewBox, and an accessible title', (f) => {
    const svg = readFileSync(path.join(DIR, f), 'utf8');
    expect(svg).not.toMatch(/<text[\s>]/);
    expect(svg).toMatch(/viewBox="[^"]+"/);
    expect(svg).toMatch(/<title id="t">TJR HQ<\/title>/);
  });

  it('every file a component can request exists', () => {
    const wanted = new Set<string>();
    for (const surface of ['light', 'dark'] as const) {
      for (const mono of [false, true]) for (const size of [16, 24, 32, 36, 48]) wanted.add(brandMarkSrc(surface, mono, size));
      for (const layout of ['primary', 'horizontal', 'compact'] as const) {
        for (const mono of [false, true]) wanted.add(brandWordmarkSrc(layout, surface, mono));
      }
    }
    for (const url of wanted) expect(existsSync(path.join(process.cwd(), 'public', url)), url).toBe(true);
  });

  it('the aspect ratios in code match the SVG viewBoxes', () => {
    for (const layout of ['primary', 'horizontal', 'compact'] as const) {
      const svg = readFileSync(path.join(DIR, `hq-wordmark-${layout}-light.svg`), 'utf8');
      const [, , w, h] = svg.match(/viewBox="([\d. -]+)"/)![1].trim().split(/\s+/).map(Number);
      expect(WORDMARK_ASPECT[layout]).toBeCloseTo(w / h, 2);
    }
  });
});
