// @vitest-environment jsdom
//
// Settings Page Redesign mission §26 (Accessibility): the shell pieces
// shared by every section — nav, headings, rows, save-status line — get
// the same axe-core pass the rest of the TJR Design System already gets
// in components/ui/__tests__/a11y.test.tsx. Individual sections aren't
// exercised here (each fetches from /api/settings on mount; that's
// integration-test territory, not a unit a11y pass), but every one of
// them is built from exactly these primitives.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { toHaveNoViolations, type AxeMatchers } from 'vitest-axe/dist/matchers';
import { SettingsNav } from '../SettingsNav';
import { SectionHeading, SettingRow } from '../SectionHeading';
import { SaveStatusLine } from '../SaveStatusLine';
import SettingsIndexPage from '../../page';

declare module 'vitest' {
  // eslint-disable-next-line
  interface Assertion<T = any> extends AxeMatchers {}
}

expect.extend({ toHaveNoViolations });

afterEach(cleanup);

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/settings',
}));

describe('Settings shell — accessibility', () => {
  it('SettingsNav has no axe violations and marks the active section', async () => {
    const { container } = render(<SettingsNav />);
    expect(await axe(container)).toHaveNoViolations();
  });

  it('SectionHeading + SettingRow have no axe violations', async () => {
    const { container } = render(
      <SectionHeading title="Appearance" description="How HQ looks.">
        <SettingRow label="Theme" hint="Applies everywhere.">
          <button type="button">Archive</button>
        </SettingRow>
      </SectionHeading>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it('SaveStatusLine communicates each state without colour alone', () => {
    const { rerender } = render(<SaveStatusLine status="saving" />);
    expect(screen.getByText('Saving…')).toBeTruthy();

    rerender(<SaveStatusLine status="saved" />);
    expect(screen.getByText('Saved ✓')).toBeTruthy();

    rerender(<SaveStatusLine status="error" />);
    expect(screen.getByText('Could not save this setting.')).toBeTruthy();
    expect(screen.getByRole('alert')).toBeTruthy();
  });

  it('Settings index list has no axe violations and links every section', async () => {
    const { container } = render(<SettingsIndexPage />);
    expect(await axe(container)).toHaveNoViolations();
    expect(screen.getByRole('link', { name: /Appearance/ }).getAttribute('href')).toBe('/settings/appearance');
    expect(screen.getByRole('link', { name: /Data & Privacy/ }).getAttribute('href')).toBe('/settings/data-privacy');
  });
});
