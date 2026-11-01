import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { metadata as authMetadata } from '../app/(auth)/layout';
import { metadata as appMetadata } from '../app/(app)/layout';

const src = (f: string) => readFileSync(path.join(process.cwd(), 'src', f), 'utf8');

describe('"Endeavour 27" no longer appears in user-visible strings (brand Stage 3)', () => {
  it('page metadata', () => {
    for (const m of [authMetadata, appMetadata]) {
      expect(String(m.description)).not.toMatch(/endeavour 27/i);
    }
  });

  it('visible JSX text in the app chrome and auth surfaces', () => {
    const visible = [
      'app/(app)/layout.tsx',
      'app/(auth)/login/page.tsx',
      'app/auth/reset-password/page.tsx',
      'components/ui/Sidebar.tsx',
    ];
    for (const f of visible) {
      // strip comments, then look for the wording in what remains (JSX text and strings)
      const code = src(f).replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
      expect(code, f).not.toMatch(/endeavour 27/i);
    }
  });
});
