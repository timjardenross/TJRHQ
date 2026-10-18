import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import postcss from 'postcss';
import tailwindcss from 'tailwindcss';
import config from '../../tailwind.config';

// Design uplift Stage A2b: opacity modifiers on token colours must generate CSS.
// Collects every modifier class on a token colour that appears in source, compiles
// them with the project's real Tailwind config, and asserts each one has a rule.
const root = path.join(process.cwd(), 'src');
function walk(dir: string, out: string[] = []): string[] {
  for (const n of readdirSync(dir)) {
    const p = path.join(dir, n);
    if (statSync(p).isDirectory()) { if (n !== '__tests__') walk(p, out); }
    else if (/\.(tsx?|css)$/.test(n) && !/\.(test|stories)\./.test(n)) out.push(p);
  }
  return out;
}

const TOKEN_GROUPS = '(?:wb|state|lcars|brand|command|engineering|operations|medical|science|status|space|panel|edge)';
const UTIL = '(?:bg|text|border|ring|from|to|via|divide|placeholder|outline|fill|stroke|decoration|accent|caret)';
const CLASS_RE = new RegExp(`(?<![A-Za-z0-9_\\[-])((?:[a-z0-9-]+:)*${UTIL}-${TOKEN_GROUPS}(?:-[a-z0-9]+)*\\/[0-9]{1,3})(?![A-Za-z0-9_])`, 'g');

const used = (() => {
  const set = new Set<string>();
  for (const f of walk(root)) for (const m of readFileSync(f, 'utf8').matchAll(CLASS_RE)) set.add(m[1]);
  return [...set].sort();
})();

const esc = (c: string) => c.replace(/([:/])/g, '\\$1');

async function compile(classes: string[], cfg: any = config) {
  const r = await postcss([tailwindcss({ ...cfg, content: [{ raw: classes.join(' '), extension: 'html' }], corePlugins: { preflight: false } })]).process(
    '@tailwind utilities;',
    { from: undefined },
  );
  return r.css;
}

describe('opacity modifiers on token colours (design uplift Stage A2b)', () => {
  it('finds the modifier classes the app uses', () => {
    expect(used.length).toBeGreaterThan(100);
  });

  it('every modifier class used in source generates a CSS rule', async () => {
    const css = await compile(used);
    const missing = used.filter((c) => !css.includes('.' + esc(c)));
    expect(missing).toEqual([]);
  });

  it('modifiers mix the token with transparency, and unmodified classes keep the exact token', async () => {
    const css = await compile(['bg-wb-crit/10', 'text-wb-ink2/70', 'border-wb-sage-deep/40', 'bg-wb-bg', 'text-state-ok-on']);
    expect(css).toMatch(/\.bg-wb-crit\\\/10\s*\{\s*background-color:\s*color-mix\(in srgb, var\(--wb-crit\) calc\(0\.1 \* 100%\), transparent\)/);
    expect(css).toMatch(/\.text-wb-ink2\\\/70\s*\{\s*color:\s*color-mix\(in srgb, var\(--wb-ink2\) calc\(0\.7 \* 100%\), transparent\)/);
    // no modifier: opacity variable defaults to 1, so the colour is the token itself
    expect(css).toMatch(/\.bg-wb-bg\s*\{\s*--tw-bg-opacity:\s*1;\s*background-color:\s*color-mix\(in srgb, var\(--wb-bg\) calc\(var\(--tw-bg-opacity\) \* 100%\), transparent\)/);
    expect(css).toMatch(/var\(--state-ok-on\)/);
  });

  it('the harness would catch the old bug: a plain var() colour generates nothing for a modifier', async () => {
    const old = { ...config, theme: { ...config.theme, extend: { ...config.theme?.extend, colors: { wb: { crit: 'var(--wb-crit)' } } }, colors: undefined } } as any;
    const css = await compile(['bg-wb-crit/10'], old);
    expect(css).not.toContain('bg-wb-crit\\/10');
  });
});
