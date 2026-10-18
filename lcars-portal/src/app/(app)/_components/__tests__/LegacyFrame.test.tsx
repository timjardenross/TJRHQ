// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

let pathname = '/missions';
vi.mock('next/navigation', () => ({ usePathname: () => pathname }));
vi.mock('@/components/ui/WorkbenchShell', () => ({
  WorkbenchShell: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <div data-testid="shell" data-title={title}>{children}</div>
  ),
}));
import { LegacyFrame } from '../LegacyFrame';

describe('LegacyFrame', () => {
  beforeEach(() => { pathname = '/missions'; });
  afterEach(cleanup);

  it('puts legacy routes in the workbench shell with the compatibility note', () => {
    render(<LegacyFrame><p>content</p></LegacyFrame>);
    expect(screen.getByTestId('shell')).toBeTruthy();
    expect(screen.getByRole('note').getAttribute('data-route-family')).toBe('legacy-compatibility');
    expect(screen.getByText('content')).toBeTruthy();
  });

  it.each(['/medical', '/decisions', '/decisions/'])('does not nest a second shell on %s (page brings its own)', (p) => {
    pathname = p;
    render(<LegacyFrame><p>content</p></LegacyFrame>);
    expect(screen.queryByTestId('shell')).toBeNull();
    expect(screen.getByText('content')).toBeTruthy();
  });

  it('still frames medical sub-pages that have no shell of their own', () => {
    pathname = '/medical/pulse';
    render(<LegacyFrame><p>content</p></LegacyFrame>);
    expect(screen.getByTestId('shell')).toBeTruthy();
  });
});
