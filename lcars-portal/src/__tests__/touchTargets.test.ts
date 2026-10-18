import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const css = readFileSync(join(process.cwd(), 'src/app/globals.css'), 'utf8');
const block = css.slice(css.indexOf('@media (pointer: coarse)'));

describe('touch targets (A2c)', () => {
  it('coarse-pointer rule gives controls a 44px minimum', () => {
    expect(block).toMatch(/button:not\(\[data-wb-dense\]\)/);
    expect(block).toMatch(/select:not\(\[data-wb-dense\]\)/);
    expect(block).toMatch(/min-height:\s*44px/);
  });
  it('keeps an explicit dense opt-out', () => {
    expect(block).toMatch(/data-wb-dense/);
  });
  it('shared Button sizes already clear 44px (py-2.5/py-3 + text)', () => {
    const src = readFileSync(join(process.cwd(), 'src/components/ui/Button.tsx'), 'utf8');
    expect(src).toMatch(/sm: 'px-3 py-2\.5/);
    expect(src).toMatch(/md: 'px-4 py-3/);
  });
});
