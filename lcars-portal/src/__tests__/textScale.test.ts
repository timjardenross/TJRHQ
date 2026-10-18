import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import postcss from 'postcss';
import tailwindcss from 'tailwindcss';
import { describe, expect, it } from 'vitest';
import config from '../../tailwind.config';

// Stage B: body copy uses the shared text scale, not ad-hoc pixel sizes.
const SCALE = { 'wb-label': '12px', 'wb-body': '14px', 'wb-lead': '16px', 'wb-title': '18px' };

function walk(dir: string, out: string[] = []): string[] {
  for (const n of readdirSync(dir)) {
    const p = path.join(dir, n);
    if (statSync(p).isDirectory()) {
      if (n !== '__tests__') walk(p, out);
    } else if (/\.(tsx?|css)$/.test(n) && !/\.test\./.test(n)) out.push(p);
  }
  return out;
}

describe('shared text scale', () => {
  it('each text-wb-* size compiles to its font-size, with no line-height', async () => {
    const r = await postcss([
      tailwindcss({ ...(config as object), content: [{ raw: Object.keys(SCALE).map((k) => `text-${k}`).join(' '), extension: 'html' }], corePlugins: { preflight: false } } as never),
    ]).process('@tailwind utilities;', { from: undefined });
    for (const [k, px] of Object.entries(SCALE)) {
      expect(r.css, k).toMatch(new RegExp(`\\.text-${k}\\s*\\{\\s*font-size:\\s*${px}\\s*;?\\s*\\}`));
    }
  });

  it('no source uses an arbitrary pixel text size from 12 to 18 px (use the scale)', () => {
    const bad: string[] = [];
    for (const f of walk(path.join(process.cwd(), 'src'))) {
      const s = readFileSync(f, 'utf8');
      for (const m of s.matchAll(/(?<![A-Za-z0-9_\[-])(?:[a-z0-9-]+:)*text-\[(\d+(?:\.\d+)?)px\]/g)) {
        const n = Number(m[1]);
        if (n >= 12 && n <= 18) bad.push(`${path.relative(process.cwd(), f)}: ${m[0]}`);
      }
    }
    expect(bad).toEqual([]);
  });
});
