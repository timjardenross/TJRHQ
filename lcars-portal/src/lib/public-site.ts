import type { Metadata } from 'next';

export const PUBLIC_SITE_NAME = 'TJR Mind & Body';

export const PUBLIC_PAGES = [
  {
    path: '/',
    title: 'TJR Mind & Body | Practical Resilience Coaching and Education',
    description:
      'Practical resilience coaching and education for people navigating pressure, burnout, chronic pain, disruption, and steady rebuilding.',
    priority: 1,
    changeFrequency: 'monthly' as const,
  },
  {
    path: '/founder-story',
    title: 'Founder Story | TJR Mind & Body',
    description:
      'Why TJR Mind & Body exists: Tim Jarden-Ross on operational resilience, chronic pain, rebuilding, and practical support that works in real life.',
    priority: 0.8,
    changeFrequency: 'monthly' as const,
  },
  {
    path: '/contact',
    title: 'Contact | TJR Mind & Body',
    description:
      'Contact TJR Mind & Body to enquire about support, coaching, education, or a discovery conversation.',
    priority: 0.7,
    changeFrequency: 'monthly' as const,
  },
] as const;

export const PUBLIC_PATHS = PUBLIC_PAGES.map((page) => page.path);

export const PUBLIC_ROUTE_ALLOWLIST = new Set([
  ...PUBLIC_PATHS,
  '/login',
  '/robots.txt',
  '/sitemap.xml',
]);

export const PRIVATE_ROBOTS_DISALLOWS = [
  '/api/',
  '/auth/',
  '/captains-chair',
  '/advisory-council',
  '/knowledge',
  '/knowledge-library',
  '/search',
  '/timeline',
  '/capture',
  '/engineering-queue',
  '/engineering',
  '/intelligence',
  '/comms',
  '/alerts',
  '/missions',
  '/medical',
  '/operations',
  '/captains-log',
  '/captains-notebook',
  '/captains-brief',
  '/delivery',
  '/automation-centre',
  '/model-crew',
  '/physical-readiness',
  '/human-systems',
  '/recovery-brief',
  '/stage-progression',
  '/operating-model',
  '/decisions',
  '/decide',
  '/ask',
] as const;

export function buildPublicMetadata({
  path,
  title,
  description,
}: {
  path: string;
  title: string;
  description: string;
}): Metadata {
  return {
    title,
    description,
    robots: {
      index: true,
      follow: true,
    },
    alternates: {
      canonical: path,
    },
    openGraph: {
      title,
      description,
      url: path,
      siteName: PUBLIC_SITE_NAME,
      type: 'website',
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
    },
  };
}
