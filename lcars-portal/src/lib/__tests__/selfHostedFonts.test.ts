// @vitest-environment node
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const read = (rel: string) => readFileSync(join(__dirname, '..', '..', rel), 'utf8');

describe('fonts are self-hosted (no request to Google from the browser)', () => {
  it('globals.css does not import fonts from Google', () => {
    const css = read('app/globals.css');
    expect(css).not.toMatch(/fonts\.googleapis\.com|fonts\.gstatic\.com/);
  });

  it('the root layout loads all three families through next/font and exposes them as CSS variables', () => {
    const layout = read('app/layout.tsx');
    for (const family of ['Inter', 'JetBrains_Mono', 'Source_Serif_4']) {
      expect(layout).toMatch(new RegExp(`${family}\\(\\{`));
    }
    for (const v of ['--font-sans', '--font-mono', '--font-serif']) {
      expect(layout).toContain(v);
    }
  });

  it('Tailwind families point at those variables', () => {
    const cfg = readFileSync(join(__dirname, '..', '..', '..', 'tailwind.config.ts'), 'utf8');
    expect(cfg).toMatch(/sans:\s*\['var\(--font-sans\)'/);
    expect(cfg).toMatch(/mono:\s*\['var\(--font-mono\)'/);
  });
});
