// @vitest-environment jsdom
import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

let pathname = '/missions';
vi.mock('next/navigation', () => ({ usePathname: () => pathname }));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => <a href={href} {...rest}>{children}</a>,
}));
vi.mock('@/components/ui/WorkbenchShell', () => ({
  WorkbenchShell: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <div data-testid="shell" data-title={title}>{children}</div>
  ),
}));
import { LegacyFrame, OWN_SHELL } from '../LegacyFrame';
import MedicalPage from '../../medical/page';

describe('LegacyFrame', () => {
  beforeEach(() => { pathname = '/missions'; });
  afterEach(cleanup);

  it('puts legacy routes in the workbench shell with the compatibility note', () => {
    render(<LegacyFrame><p>content</p></LegacyFrame>);
    expect(screen.getByTestId('shell')).toBeTruthy();
    expect(screen.getByRole('note').getAttribute('data-route-family')).toBe('legacy-compatibility');
    expect(screen.getByText('content')).toBeTruthy();
  });

  it.each(['/decisions', '/decisions/'])('does not nest a second shell on %s (page brings its own)', (p) => {
    pathname = p;
    render(<LegacyFrame><p>content</p></LegacyFrame>);
    expect(screen.queryByTestId('shell')).toBeNull();
    expect(screen.getByText('content')).toBeTruthy();
  });

  it.each(['/medical', '/medical/', '/medical/pulse'])('frames the real Medical page in exactly one shell on %s', (p) => {
    pathname = p;
    render(<LegacyFrame><MedicalPage /></LegacyFrame>);
    expect(screen.getAllByTestId('shell')).toHaveLength(1);
    expect(screen.getByText('Medical Bay')).toBeTruthy();
  });

  it('OWN_SHELL is exactly the set of (app) pages that render their own <WorkbenchShell>', () => {
    const root = path.join(process.cwd(), 'src/app/(app)');
    const own: string[] = [];
    const walk = (dir: string) => {
      for (const n of readdirSync(dir)) {
        const f = path.join(dir, n);
        if (statSync(f).isDirectory()) { if (n !== '_components') walk(f); continue; }
        if (n !== 'page.tsx') continue;
        if (/<WorkbenchShell[\s>]/.test(readFileSync(f, 'utf8'))) {
          own.push('/' + path.relative(root, path.dirname(f)).split(path.sep).join('/'));
        }
      }
    };
    walk(root);
    expect([...OWN_SHELL].sort()).toEqual(own.sort());
  });
});
