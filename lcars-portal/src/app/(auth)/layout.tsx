import type { Metadata } from 'next';

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false
  },
  alternates: {
    canonical: '/login'
  }
};

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
