// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({ useSearchParams: () => new URLSearchParams('') }));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => <a href={href} {...rest}>{children}</a>,
}));
vi.mock('@/components/MobileCommandBar', () => ({ MobileCommandBar: () => null }));
import InvestigatePage from '../page';

describe('/investigate with no type or reason', () => {
  afterEach(cleanup);

  it('explains how the page is reached without naming screens that no longer exist, and links to Today and Decisions', async () => {
    const { findByText, container } = render(<InvestigatePage />);
    await findByText(/needs a specific starting point/);
    expect(container.textContent).not.toMatch(/Home or Recommended/);
    expect(screen.getByText('Go to Today').getAttribute('href')).toBe('/captains-chair-workbench');
    expect(screen.getByText('Go to Decisions').getAttribute('href')).toBe('/decisions');
  });
});
