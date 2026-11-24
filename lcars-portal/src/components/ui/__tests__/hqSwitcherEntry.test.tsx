// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { WorkbenchShell } from '../WorkbenchShell';
import { resetHqEnabledCache } from '@/lib/hq/useHqEnabled';

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => <a href={href} {...props}>{children}</a>,
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: () => {}, replace: () => {} }),
  usePathname: () => '/test-workbench',
}));

const shell = () => render(<WorkbenchShell title="Test" tagline="t"><p>body</p></WorkbenchShell>);
const respond = (status: number, body: unknown) => vi.fn().mockImplementation(async (url: string) =>
  String(url).includes('/api/hq/status') ? { ok: status === 200, status, json: async () => body } : { ok: false, status: 404, json: async () => ({}) });

beforeEach(() => { resetHqEnabledCache(); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('existing workbench switcher: HQ entry', () => {
  it('is absent when HQ is off (the default)', async () => {
    const f = respond(200, { enabled: false });
    vi.stubGlobal('fetch', f);
    shell();
    await waitFor(() => expect(f.mock.calls.some((c) => String(c[0]).includes('/api/hq/status'))).toBe(true));
    expect(screen.queryByRole('link', { name: 'HQ' })).toBeNull();
  });
  it('appears, linking to /hq, only when HQ is on', async () => {
    vi.stubGlobal('fetch', respond(200, { enabled: true }));
    shell();
    const link = await screen.findByRole('link', { name: 'HQ' });
    expect(link.getAttribute('href')).toBe('/hq');
  });
  it('stays absent when the check fails (signed out, offline)', async () => {
    const f = respond(401, { error: 'Unauthorized' });
    vi.stubGlobal('fetch', f);
    shell();
    await waitFor(() => expect(f).toHaveBeenCalled());
    expect(screen.queryByRole('link', { name: 'HQ' })).toBeNull();
  });
  it('stays absent when fetch itself throws', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    shell();
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByRole('link', { name: 'HQ' })).toBeNull();
  });
});
