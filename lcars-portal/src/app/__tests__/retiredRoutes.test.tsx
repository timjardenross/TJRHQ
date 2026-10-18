// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const redirect = vi.fn();
vi.mock('next/navigation', () => ({ redirect: (u: string) => redirect(u), usePathname: () => '/x' }));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => <a href={href} {...rest}>{children}</a>,
}));
vi.mock('@/components/ui/WorkbenchShell', () => ({
  WorkbenchShell: ({ children, title }: { children: React.ReactNode; title: string }) => <div data-testid="shell" data-title={title}>{children}</div>,
}));
import FocusRetired from '../focus-workbench/page';
import PhysicalReadinessRetired from '../physical-readiness/page';
import PhysicalReadinessHistoryRetired from '../physical-readiness/history/page';
import PhysicalReadinessStartRetired from '../physical-readiness/start/page';
import PhysicalReadinessSessionRetired from '../physical-readiness/session/[id]/page';
import ExerciseLibraryRedirect from '../physical-readiness/library/page';

describe('retired routes (owner decisions, 2026-10-18)', () => {
  afterEach(() => { cleanup(); redirect.mockClear(); });

  it.each([
    ['Physical Readiness', PhysicalReadinessRetired],
    ['Physical Readiness history', PhysicalReadinessHistoryRetired],
    ['Physical Readiness start', PhysicalReadinessStartRetired],
    ['Physical Readiness session', PhysicalReadinessSessionRetired],
  ])('%s answers with a notice that points at Knowledge Exercises', (_n, Page) => {
    render(<Page />);
    expect(screen.getByText(/retired from HQ/)).toBeTruthy();
    expect(screen.getByText(/Knowledge · Exercises/).closest('a')?.getAttribute('href')).toBe('/knowledge-workbench?tab=exercises');
  });

  it('Focus answers with a notice that points at Today and Ready Room', () => {
    render(<FocusRetired />);
    expect(screen.getByText(/Go to Today/).closest('a')?.getAttribute('href')).toBe('/captains-chair-workbench');
    expect(screen.getByText(/Go to Ready Room/).closest('a')?.getAttribute('href')).toBe('/ready-room');
  });

  it('the old exercise library URL redirects to the Knowledge Exercises tab', () => {
    ExerciseLibraryRedirect();
    expect(redirect).toHaveBeenCalledWith('/knowledge-workbench?tab=exercises');
  });
});
