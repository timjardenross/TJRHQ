// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkbenchShell } from '../WorkbenchShell';
import { ActionOutcome } from '../../ActionOutcome';
import { EvidenceMeta } from '../../EvidenceMeta';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/test-workbench',
}));

describe('formal accessibility regression contract', () => {
  it('provides a keyboard skip target and native focusable primary controls', () => {
    render(<WorkbenchShell title="Test" tagline="Test"><button type="button">Primary action</button></WorkbenchShell>);
    const skip = screen.getByRole('link', { name: /skip to content/i });
    expect(skip.getAttribute('href')).toBe('#wb-main');
    expect(screen.getByRole('button', { name: 'Primary action' }).getAttribute('tabindex')).not.toBe('-1');
    expect(document.querySelector('#wb-main')).toBeTruthy();
  });

  it('announces action outcomes and exposes evidence metadata to screen readers', () => {
    render(<><ActionOutcome message="Saved" tone="success" /><EvidenceMeta source="Task registry" observedAt="2026-09-21T00:00:00Z" confidence="high" state="stale" /></>);
    expect(screen.getByRole('status').getAttribute('aria-live')).toBe('polite');
    expect(screen.getByLabelText('Evidence metadata').textContent).toMatch(/Source: Task registry/);
    expect(screen.getByLabelText('Evidence metadata').textContent).toMatch(/State: stale/);
  });

  it('keeps status semantics textual rather than relying on colour alone', () => {
    render(<ActionOutcome message="Action failed" tone="error" />);
    expect(screen.getAllByRole('status').some((node) => node.textContent?.includes('Action failed'))).toBe(true);
  });

  it('keeps the mobile/zoom contract based on fluid layout primitives', () => {
    const { container } = render(<WorkbenchShell title="Zoom test" tagline="A long but readable tagline"><p>Content</p></WorkbenchShell>);
    const main = document.querySelector('#wb-main');
    expect(main).toBeTruthy();
    expect(main?.className).toMatch(/mx-auto/);
    expect(main?.className).toMatch(/px-4/);
  });
});
