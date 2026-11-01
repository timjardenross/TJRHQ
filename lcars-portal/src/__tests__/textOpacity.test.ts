import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

// Opacity modifiers on token colours now take effect (tailwind.config.ts withAlpha),
// so a text-wb-*/NN class lowers contrast below the tested token pairs.
// Text must use the solid token. Disabled controls are exempt from WCAG 1.4.3.
const ALLOWED = new Map<string, number>([['components/ui/Sidebar.tsx', 2]]);
const PATTERN =
  /(?<![A-Za-z0-9_\[-])(?:[a-z0-9-]+:)*text-(?:wb|state|lcars|brand|command|engineering|operations|medical|science|status)[a-z0-9-]*\/[0-9]{1,3}(?![A-Za-z0-9_])/g;

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) {
      if (name !== '__tests__') walk(p, out);
    } else if (/\.(tsx|ts|css)$/.test(name) && !/\.(test|stories)\./.test(name)) out.push(p);
  }
  return out;
}

describe('text colour opacity', () => {
  it('no token text class carries an opacity modifier (except disabled cues)', () => {
    const root = join(process.cwd(), 'src');
    const bad: string[] = [];
    for (const file of walk(root)) {
      const rel = file.slice(root.length + 1);
      const n = (readFileSync(file, 'utf8').match(PATTERN) ?? []).length;
      if (n !== (ALLOWED.get(rel) ?? 0)) bad.push(`${rel}: ${n}`);
    }
    expect(bad).toEqual([]);
  });
});
