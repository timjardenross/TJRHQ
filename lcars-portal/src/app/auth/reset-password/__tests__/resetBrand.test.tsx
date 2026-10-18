// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ResetPasswordPage from '../page';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock('@/lib/supabase-browser', () => ({
  createSupabaseBrowserClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: null } }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
      exchangeCodeForSession: async () => ({ error: null }),
    },
  }),
}));

afterEach(cleanup);

describe('reset-password heading brand (brand Stage 3), rendered', () => {
  it('shows the dark-surface mark as a decorative image beside plain "TJR HQ" and the page heading', () => {
    const { container } = render(<ResetPasswordPage />);
    const img = container.querySelector('img');
    expect(img).not.toBeNull();
    expect(img).toHaveAttribute('src', '/brand/hq-icon-dark.svg');
    expect(img).toHaveAttribute('alt', '');
    expect(img).toHaveAttribute('width', '48');
    expect(screen.getByText('TJR HQ')).toBeInTheDocument();
    expect(screen.queryByText(/endeavour 27/i)).toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: 'Reset password' })).toBeInTheDocument();
  });
});
