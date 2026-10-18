// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { WorkbenchShell } from '../WorkbenchShell';
import { Sidebar } from '../Sidebar';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/test-workbench',
}));

afterEach(cleanup);

const src = (f: string) => readFileSync(path.join(process.cwd(), 'src', f), 'utf8');

describe('TJR HQ brand mark in the app chrome (brand Stage 2)', () => {
  it('header: the home link keeps its accessible name and holds a decorative mark', () => {
    render(<WorkbenchShell title="Test" tagline="t"><p>c</p></WorkbenchShell>);
    const link = screen.getByRole('link', { name: 'Workbenches home' });
    const img = link.querySelector('img');
    expect(img).not.toBeNull();
    expect(img).toHaveAttribute('alt', '');
    expect(img).toHaveAttribute('width', '36');
    expect(link.textContent).toBe('');
  });

  it('header: dark modes use the inverted tile, Read mode the navy tile', () => {
    const tile = (mode: 'focus' | 'command' | 'read') => {
      const { unmount } = render(<WorkbenchShell title="T" tagline="t" mode={mode}><p>c</p></WorkbenchShell>);
      const s = screen.getByRole('link', { name: 'Workbenches home' }).querySelector('img')!.getAttribute('src');
      unmount();
      return s;
    };
    expect(tile('focus')).toBe('/brand/hq-icon-dark.svg');
    expect(tile('command')).toBe('/brand/hq-icon-dark.svg');
    expect(tile('read')).toBe('/brand/hq-icon-light.svg');
  });

  it('sidebar: inverted-tile mark and the name "TJR HQ" with no "Endeavour 27" sub-label', () => {
    render(<Sidebar />);
    const link = screen.getByRole('link', { name: 'TJR HQ home' });
    expect(link).toHaveAttribute('href', '/hub');
    expect(link.querySelector('img')).toHaveAttribute('src', '/brand/hq-icon-dark.svg');
    expect(link.querySelector('img')).toHaveAttribute('alt', '');
    expect(link.textContent).toBe('TJR HQ');
    expect(screen.queryByText(/endeavour 27/i)).toBeNull();
  });

  it('the triangle glyph and its style are gone from the chrome', () => {
    for (const f of ['components/ui/WorkbenchShell.tsx', 'components/ui/Sidebar.tsx', 'app/globals.css']) {
      const text = src(f);
      expect(text, f).not.toContain('△');
      expect(text, f).not.toContain('endeavour-brand-mark');
    }
  });

  it('login heading uses the mark and plain "TJR HQ" (no descriptor line)', () => {
    const login = src('app/(auth)/login/page.tsx');
    expect(login).toContain("import { BrandMark } from '@/components/brand'");
    expect(login).toContain('<BrandMark surface="dark" size={48} />');
    expect(login).not.toContain('ENDEAVOUR 27');
  });
});
