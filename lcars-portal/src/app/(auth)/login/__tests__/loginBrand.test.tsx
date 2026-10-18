// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import LoginPage from '../page';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock('@/lib/supabase-browser', () => ({ createSupabaseBrowserClient: () => ({}) }));

afterEach(cleanup);

describe('login page brand heading (brand Stage 2), rendered', () => {
  it('shows the dark-surface mark as a decorative image beside plain "TJR HQ" and the page heading', () => {
    const { container } = render(<LoginPage />);
    const img = container.querySelector('img');
    expect(img).not.toBeNull();
    expect(img).toHaveAttribute('src', '/brand/hq-icon-dark.svg');
    expect(img).toHaveAttribute('alt', '');
    expect(img).toHaveAttribute('width', '48');
    expect(screen.getByText('TJR HQ')).toBeInTheDocument();
    expect(screen.queryByText(/endeavour 27/i)).toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: 'Command access' })).toBeInTheDocument();
  });

  it('keeps the sign-in form: the mark did not displace the controls', () => {
    render(<LoginPage />);
    expect(document.querySelector('form')).not.toBeNull();
    expect(screen.getAllByRole('button').length).toBeGreaterThan(0);
    expect(document.querySelector('input[type="email"]')).not.toBeNull();
  });
});
