import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';

// Contrast guard for the HQ colour tokens (design uplift Stage A). Parses the
// real values from globals.css, so editing a token without checking its
// pairings fails here. WCAG 2.x relative luminance; text needs 4.5:1.
const css = readFileSync(path.join(process.cwd(), 'src', 'app', 'globals.css'), 'utf8');

const noComments = css.replace(/\/\*[\s\S]*?\*\//g, '');

// Merge every rule whose selector list ends with `selector` (a file can hold
// several :root blocks).
function block(selector: string): Record<string, string> {
  const out: Record<string, string> = {};
  const re = new RegExp(`(?:^|\\n)([^{}]*${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})\\s*\\{([^}]*)\\}`, 'g');
  for (const rule of noComments.matchAll(re)) {
    for (const m of rule[2].matchAll(/--wb-([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})/g)) out[m[1]] = m[2];
  }
  if (!Object.keys(out).length) throw new Error(`no tokens found for ${selector}`);
  return out;
}

const lum = (hex: string) => {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const ratio = (a: string, b: string) => {
  const [x, y] = [lum(a), lum(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
};

const light = block(':root');
// The dark block's selector list ends with the mode selector; read it by that.
const dark = block("[data-wb-mode='dark']");

describe.each([
  ['light (default)', light],
  ['dark (chrome and mode="dark")', dark],
])('%s token set', (_name, t) => {
  it('defines every token the system uses', () => {
    for (const k of ['bg', 'surface', 'surface-raised', 'line', 'ink', 'ink2', 'sage', 'sage-deep', 'sand', 'sand-deep']) {
      expect(t[k], k).toMatch(/^#[0-9A-Fa-f]{6}$/);
    }
  });

  it('body and secondary text pass 4.5:1 on bg, surface and raised surfaces', () => {
    for (const fg of ['ink', 'ink2']) {
      for (const bg of ['bg', 'surface', 'surface-raised']) {
        expect(ratio(t[fg], t[bg]), `${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it('the interactive blue and the text-safe sand pass 4.5:1 as text on bg, surface and raised surfaces', () => {
    for (const fg of ['sage', 'sand-deep']) {
      for (const bg of ['bg', 'surface', 'surface-raised']) {
        expect(ratio(t[fg], t[bg]), `${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it('white text on the fill blue (sage-deep) passes 4.5:1, so buttons stay legible', () => {
    expect(ratio('#FFFFFF', t['sage-deep'])).toBeGreaterThanOrEqual(4.5);
  });
});

describe('light set specifics', () => {
  it('sage-deep is also text-safe on every light surface (links, pressed state)', () => {
    for (const bg of ['bg', 'surface', 'surface-raised']) expect(ratio(light['sage-deep'], light[bg]), bg).toBeGreaterThanOrEqual(4.5);
  });

  it('the status text colours (-on) stay legible on every light surface', () => {
    for (const t of ['ok', 'warn', 'crit']) {
      for (const bg of ['bg', 'surface', 'surface-raised']) {
        expect(ratio(light[`${t}-on`], light[bg]), `${t}-on on ${bg}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });
});

describe('dark scopes', () => {
  it('set their own text colour, so chrome never inherits the light page ink', () => {
    const m = noComments.match(/\[data-wb-chrome='dark'\],\s*\[data-wb-mode='dark'\]\s*\{([^}]*)\}/);
    expect(m).not.toBeNull();
    expect(m![1]).toMatch(/color:\s*var\(--wb-ink\)/);
  });
});

describe('documented non-text tokens', () => {
  it('records that dark sage-deep is a fill (white text on top), not a text colour', () => {
    expect(css).toMatch(/Not a text colour, by design: `--wb-sage-deep` in the dark set/);
    expect(css).toMatch(/fill-only on dark/);
  });
});

// Status pills: `bg-state-X/15 text-state-X-on` (and /10) on bg, surface and raised.
describe('status pills stay legible in both sets', () => {
  const tones = ['ok', 'warn', 'crit', 'unknown', 'info'] as const;
  const rootVars = (() => {
    const out: Record<string, string> = {};
    for (const m of noComments.matchAll(/--(state-[a-z]+(?:-soft|-on)?):\s*(#[0-9A-Fa-f]{6})/g)) out[m[1]] = m[2];
    return out;
  })();
  const darkVars = (() => {
    const m = noComments.match(/\[data-wb-chrome='dark'\],\s*\[data-wb-mode='dark'\]\s*\{([^}]*)\}/)!;
    const out: Record<string, string> = {};
    for (const v of m[1].matchAll(/--(state-[a-z]+-on|wb-(?:ok|warn|crit)-on):\s*(#[0-9A-Fa-f]{6})/g)) out[v[1]] = v[2];
    return out;
  })();
  const mix = (fg: string, bg: string, a: number) => {
    const f = [1, 3, 5].map((i) => parseInt(fg.slice(i, i + 2), 16));
    const b = [1, 3, 5].map((i) => parseInt(bg.slice(i, i + 2), 16));
    return '#' + f.map((c, i) => Math.round(c * a + b[i] * (1 - a)).toString(16).padStart(2, '0')).join('');
  };

  it.each(tones)('state-%s: the on-shade passes 4.5:1 on its 10 and 15 percent tint in the light set', (tone) => {
    for (const bg of ['bg', 'surface', 'surface-raised']) {
      for (const a of [0.1, 0.15]) {
        expect(ratio(rootVars[`state-${tone}-on`], mix(rootVars[`state-${tone}`], light[bg], a)), `${tone} ${bg} ${a}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it.each(tones)('state-%s: the dark-scope on-shade passes 4.5:1 on its 10 and 15 percent tint in the dark set', (tone) => {
    const on = darkVars[`state-${tone}-on`];
    expect(on, `dark override for ${tone}`).toMatch(/^#[0-9A-Fa-f]{6}$/);
    for (const bg of ['bg', 'surface', 'surface-raised']) {
      for (const a of [0.1, 0.15]) {
        expect(ratio(on, mix(rootVars[`state-${tone}`], dark[bg], a)), `${tone} ${bg} ${a}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it('the wb ok, warn and crit text shades also have dark overrides that pass on dark surfaces', () => {
    for (const t of ['ok', 'warn', 'crit']) {
      const on = darkVars[`wb-${t}-on`];
      expect(on, t).toMatch(/^#[0-9A-Fa-f]{6}$/);
      for (const bg of ['bg', 'surface', 'surface-raised']) expect(ratio(on, dark[bg]), `${t} on ${bg}`).toBeGreaterThanOrEqual(4.5);
    }
  });
});
