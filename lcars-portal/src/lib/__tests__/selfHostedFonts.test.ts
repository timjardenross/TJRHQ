// @vitest-environment node
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const read = (rel: string) => readFileSync(join(__dirname, '..', '..', rel), 'utf8');

describe('fonts are self-hosted (no request to Google from the browser)', () => {
  it('globals.css does not import fonts from Google', () => {
    const css = read('app/globals.css');
    expect(css).not.toMatch(/fonts\.googleapis\.com|fonts\.gstatic\.com/);
  });

  it('the root layout loads all three families from local files through next/font/local and exposes them as CSS variables', () => {
    const layout = read('app/layout.tsx');
    expect(layout).not.toContain('next/font/google');
    expect(layout).toContain("from 'next/font/local'");
    for (const file of ['inter-latin-wght-normal.woff2', 'jetbrains-mono-latin-wght-normal.woff2', 'source-serif-4-latin-wght-normal.woff2']) {
      expect(layout).toContain(`./fonts/${file}`);
      expect(existsSync(join(__dirname, '..', '..', 'app', 'fonts', file))).toBe(true);
    }
    for (const v of ['--font-sans', '--font-mono', '--font-serif']) {
      expect(layout).toContain(v);
    }
  });

  it('the licence text travels with the font files', () => {
    for (const f of ['LICENSE-inter.txt', 'LICENSE-jetbrains-mono.txt', 'LICENSE-source-serif-4.txt']) {
      expect(read(`app/fonts/${f}`)).toMatch(/SIL OPEN FONT LICENSE/i);
    }
  });

  it('Tailwind families point at those variables', () => {
    const cfg = readFileSync(join(__dirname, '..', '..', '..', 'tailwind.config.ts'), 'utf8');
    expect(cfg).toMatch(/sans:\s*\['var\(--font-sans\)'/);
    expect(cfg).toMatch(/mono:\s*\['var\(--font-mono\)'/);
  });
});
