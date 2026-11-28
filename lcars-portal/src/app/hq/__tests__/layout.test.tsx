import { afterEach, describe, expect, it, vi } from 'vitest';

// notFound() throws in Next; model that so the test can see it was called.
class NotFound extends Error {}
vi.mock('next/navigation', () => ({ notFound: () => { throw new NotFound('NEXT_NOT_FOUND'); } }));
vi.mock('../_components/HqShell', () => ({ HqShell: ({ children }: { children: unknown }) => children }));
vi.mock('../hq.css', () => ({}));

import HqLayout, { dynamic } from '../layout';

const original = process.env.HQ_WORKBENCH_ENABLED;
afterEach(() => { if (original === undefined) delete process.env.HQ_WORKBENCH_ENABLED; else process.env.HQ_WORKBENCH_ENABLED = original; });

describe('/hq is gated by HQ_WORKBENCH_ENABLED', () => {
  it('returns the standard 404 when the flag is unset (default off)', () => {
    delete process.env.HQ_WORKBENCH_ENABLED;
    expect(() => HqLayout({ children: null })).toThrow(NotFound);
  });
  it('returns 404 when explicitly disabled', () => {
    process.env.HQ_WORKBENCH_ENABLED = 'false';
    expect(() => HqLayout({ children: null })).toThrow(NotFound);
  });
  it('renders when enabled', () => {
    process.env.HQ_WORKBENCH_ENABLED = 'true';
    expect(() => HqLayout({ children: null })).not.toThrow();
  });
  it('reads the flag per request, never at build time', () => {
    expect(dynamic).toBe('force-dynamic');
  });
});
