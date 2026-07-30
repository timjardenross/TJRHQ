import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: {
    absolute: 'Login | TJR Mind & Body',
  },
  description: 'Secure login for the private TJR Mind & Body LCARS command centre.',
  robots: {
    index: false,
    follow: false,
  },
  alternates: {
    canonical: '/login',
  },
};

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
