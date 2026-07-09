import type { Metadata } from 'next';

// Overrides the root layout's site-wide noindex: /login is the only route
// that isn't gated by src/middleware.ts, so it's the sole page allowed
// into search results (see src/app/sitemap.ts, src/app/robots.ts).
export const metadata: Metadata = {
  robots: {
    index: true,
    follow: true
  },
  alternates: {
    canonical: '/login'
  }
};

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
