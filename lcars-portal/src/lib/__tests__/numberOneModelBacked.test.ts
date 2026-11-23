// #664 Codex P1: with modelBacked:false, "I'm stuck" must not call the decompose model (no fetch at all).
import { describe, it, expect } from 'vitest';



describe('intent-router decompose gating', () => {
  it('source: decompose is only reachable when modelBacked !== false', async () => {
    const { readFileSync } = await import('node:fs');
    const { resolve } = await import('node:path');
    const src = readFileSync(resolve(__dirname, '../number-one/intent-router.ts'), 'utf8');
    expect(src).toMatch(/options\.modelBacked === false \? null : await decompose\(/);
    expect(src.match(/await decompose\(/g)).toHaveLength(1);
  });
});
