import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import postcss from 'postcss';
import { describe, expect, it } from 'vitest';

const css = readFileSync(join(process.cwd(), 'src/app/globals.css'), 'utf8');

/** Declarations that apply, inside @media (pointer: coarse), to a selector list containing `sel`. */
function coarseDecls(sel: string): Record<string, string> {
  const out: Record<string, string> = {};
  postcss.parse(css).walkAtRules('media', (at) => {
    if (!/pointer:\s*coarse/.test(at.params)) return;
    at.walkRules((rule) => {
      if (!rule.selectors.some((s) => s.trim() === sel)) return;
      rule.walkDecls((d) => {
        out[d.prop] = d.value;
      });
    });
  });
  return out;
}

describe('touch targets (A2c) - rule structure', () => {
  it('buttons and role=button get 44px in both dimensions on coarse pointers', () => {
    for (const sel of ["button:not([data-wb-dense])", "[role='button']:not([data-wb-dense])"]) {
      expect(coarseDecls(sel)['min-height'], sel).toBe('44px');
      expect(coarseDecls(sel)['min-width'], sel).toBe('44px');
    }
  });
  it('select and summary get a 44px height', () => {
    expect(coarseDecls('select:not([data-wb-dense])')['min-height']).toBe('44px');
    expect(coarseDecls('summary:not([data-wb-dense])')['min-height']).toBe('44px');
  });
  it('checkbox and radio get 24px, not 44px', () => {
    for (const t of ['checkbox', 'radio']) {
      const d = coarseDecls(`input[type='${t}']:not([data-wb-dense])`);
      expect([d['min-height'], d['min-width']]).toEqual(['24px', '24px']);
    }
  });
  it('nothing in the rule applies outside the coarse-pointer media query', () => {
    const outside: string[] = [];
    postcss.parse(css).walkRules((r) => {
      if (r.parent?.type === 'atrule' && /pointer:\s*coarse/.test((r.parent as postcss.AtRule).params)) return;
      r.walkDecls(/^min-(height|width)$/, (d) => {
        if (d.value === '44px') outside.push(`${r.selector} { ${d.prop} }`);
      });
    });
    expect(outside).toEqual([]);
  });
});

// Rendered check: real Chromium with the production CSS rule, coarse (touch) vs fine (mouse).
const chromium = (() => {
  const base = process.env.PLAYWRIGHT_BROWSERS_PATH ?? '/opt/pw-browsers';
  try {
    const d = readdirSync(base).find((n) => n.startsWith('chromium-'));
    const p = d && join(base, d, 'chrome-linux', 'chrome');
    return process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ?? (p && existsSync(p) ? p : undefined);
  } catch {
    return process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
  }
})();

describe.skipIf(!chromium)('touch targets (A2c) - rendered in Chromium', () => {
  const rule = css.slice(css.indexOf('@media (pointer: coarse)'));
  const html = `<style>${rule}</style>
    <div id="bar" style="display:flex;align-items:flex-start;gap:4px;width:360px;flex-wrap:nowrap">
      <button id="txt" style="padding:2px">OK</button>
      <button id="glyph" class="p-1" style="padding:4px">✕</button>
      <button id="icon" style="padding:0"><svg width="10" height="10"></svg></button>
      <button id="dense" data-wb-dense style="padding:0">d</button>
    </div>
    <select id="sel"><option>a</option></select><input id="txtin" type="text">
    <input id="cb" type="checkbox"><input id="hid" type="hidden"><button id="gone" style="display:none">x</button>`;
  async function measure(touch: boolean) {
    const { chromium: pw } = await import('playwright');
    const browser = await pw.launch({ executablePath: chromium });
    try {
      const ctx = await browser.newContext({ hasTouch: touch, isMobile: touch, viewport: { width: 400, height: 800 } });
      const page = await ctx.newPage();
      await page.setContent(html);
      return await page.evaluate(() => {
        const r = (id: string) => {
          const b = document.getElementById(id)!.getBoundingClientRect();
          return [Math.round(b.width), Math.round(b.height)];
        };
        return Object.fromEntries(['txt', 'glyph', 'icon', 'dense', 'sel', 'txtin', 'cb', 'hid', 'gone'].map((i) => [i, r(i)]));
      });
    } finally {
      await browser.close();
    }
  }
  it('coarse pointer: buttons (incl. glyph-only and svg-only) are >=44x44, select/input >=44 high, dense and checkbox as specified', async () => {
    const m = await measure(true);
    for (const id of ['txt', 'glyph', 'icon']) {
      expect(m[id][0], `${id} width`).toBeGreaterThanOrEqual(44);
      expect(m[id][1], `${id} height`).toBeGreaterThanOrEqual(44);
    }
    expect(m.sel[1]).toBeGreaterThanOrEqual(44);
    expect(m.txtin[1]).toBeGreaterThanOrEqual(44);
    expect(m.dense[1]).toBeLessThan(44);
    expect(m.cb[0]).toBeGreaterThanOrEqual(24);
    expect(m.hid).toEqual([0, 0]);
    expect(m.gone).toEqual([0, 0]);
  }, 60000);
  it('fine pointer: nothing is enlarged', async () => {
    const m = await measure(false);
    for (const id of ['txt', 'glyph', 'icon', 'sel', 'txtin']) expect(m[id][1], id).toBeLessThan(44);
  }, 60000);
});
