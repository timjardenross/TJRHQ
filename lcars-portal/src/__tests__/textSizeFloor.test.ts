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

// Bounds of this guard: it enforces the floor on SOURCE (typed, rem, em, clamp/min/max,
// CSS and inline forms). CSS generated at build time or set at runtime is not
// inspected here; that stays a visual/release gate.
//
// A length in px, rem or em. em is relative to the parent, so it is judged
// against a 16 px parent (conservative: flags em values below 0.75).
const toPx = (n: string, unit: string) => (unit === 'px' ? Number(n) : Number(n) * 16);
const LEN = /(\d+(?:\.\d+)?)(px|rem|em)\b/g;

// Tailwind arbitrary text sizes: text-[11px], text-[0.7rem], typed
// text-[length:11px], and function forms such as text-[clamp(10px,1vw,14px)] or
// text-[max(9px,1em)]. Colour forms (text-[#fff], text-[color:...], text-[var(--x)])
// are not sizes and are skipped.
const ARBITRARY = /text-\[([^\]]+)\]/g;
function arbitraryOffences(src: string): string[] {
  const out: string[] = [];
  for (const m of src.matchAll(ARBITRARY)) {
    const body = m[1];
    if (/^(#|color:|rgb|hsl|var\(--[a-z0-9-]*(color|ink|text)[a-z0-9-]*\))/i.test(body)) continue;
    const typed = body.replace(/^length:/, '');
    // any length literal inside the arbitrary value (covers clamp/min/max): every literal must meet the floor
    for (const l of typed.matchAll(LEN)) {
      if (toPx(l[1], l[2]) < FLOOR_PX) out.push(m[0]);
    }
    // a size built only from a variable or calc() cannot be judged statically
    if (/^(length:)?(var\(|calc\()/.test(body) && !LEN.test(typed)) out.push(`${m[0]} (unresolvable size)`);
    LEN.lastIndex = 0;
  }
  return out;
}

// Plain CSS font-size declarations and inline-style font sizes (numbers or strings).
function declarationOffences(src: string): string[] {
  const out: string[] = [];
  for (const m of src.matchAll(/font-size:\s*([^;}]+)/g)) {
    const v = m[1];
    for (const l of v.matchAll(LEN)) if (toPx(l[1], l[2]) < FLOOR_PX) out.push(`font-size ${v.trim()}`);
    if (/^(var\(|calc\()/.test(v.trim()) && !/(\d+(?:\.\d+)?)(px|rem|em)/.test(v)) out.push(`font-size ${v.trim()} (unresolvable size)`);
    LEN.lastIndex = 0;
  }
  for (const m of src.matchAll(/fontSize:\s*(?:(\d+(?:\.\d+)?)\b(?!\s*\*)|['"]([^'"]+)['"])/g)) {
    if (m[1] !== undefined) {
      if (Number(m[1]) < FLOOR_PX) out.push(`fontSize ${m[1]}`);
    } else {
      for (const l of m[2].matchAll(LEN)) if (toPx(l[1], l[2]) < FLOOR_PX) out.push(`fontSize '${m[2]}'`);
    }
    LEN.lastIndex = 0;
  }
  return out;
}

function offenders(): string[] {
  const out: string[] = [];
  for (const f of files) {
    const src = readFileSync(f, 'utf8');
    for (const o of [...arbitraryOffences(src), ...declarationOffences(src)]) out.push(`${rel(f)}: ${o}`);
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

  it('the matcher flags every supported way to write a sub-12 px size, and accepts 12 px and above', () => {
    const bad = [
      'text-[11px]', 'sm:text-[0.7rem]', 'text-[11.5px]', 'text-[length:11px]', 'text-[0.5em]',
      'text-[clamp(10px,1vw,14px)]', 'text-[max(9px,1em)]', 'text-[length:var(--x)]',
    ];
    for (const c of bad) expect(arbitraryOffences(`className="${c}"`).length, c).toBeGreaterThan(0);
    const good = [
      'text-[12px]', 'text-[12.5px]', 'text-[0.75rem]', 'text-[length:13px]', 'text-[clamp(12px,1vw,14px)]',
      'text-[#fff]', 'text-[color:#102B46]', 'text-[var(--wb-ink)]', 'text-[1em]',
    ];
    for (const c of good) expect(arbitraryOffences(`className="${c}"`), c).toEqual([]);
  });

  it('the declaration matcher flags sub-12 px CSS and inline sizes in every unit and form', () => {
    for (const c of ['font-size: 11px', 'font-size: 0.7rem', 'font-size: 0.5em', 'font-size: clamp(10px, 1vw, 14px)', 'font-size: var(--tiny)', "fontSize: '11px'", "fontSize: '0.7rem'", 'fontSize: 11']) {
      expect(declarationOffences(c).length, c).toBeGreaterThan(0);
    }
    for (const c of ['font-size: 12px', 'font-size: 1rem', 'font-size: 16px', "fontSize: '12px'", 'fontSize: 12', 'fontSize: 28']) {
      expect(declarationOffences(c), c).toEqual([]);
    }
  });
});
