import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: {
    absolute: 'Command Access | TJR HQ',
  },
  description: 'Secure command access for TJR HQ.',
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
