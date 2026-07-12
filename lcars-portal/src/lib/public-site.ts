import type { Metadata } from 'next';

export const PUBLIC_SITE_NAME = 'TJR Mind & Body';
export const PUBLIC_SITE_DESCRIPTION =
  'Practical resilience coaching and education for people navigating pressure, burnout, chronic pain, disruption, and steady rebuilding.';
export const SUPPORT_EMAIL = 'support@tjrmindbody.com';
export const PUBLIC_SOCIAL_IMAGE_PATH = '/opengraph-image';
export const CONTACT_RESPONSE_TIME = 'We aim to reply within 2 business days.';

export interface PublicPageConfig {
  path: string;
  title: string;
  description: string;
  navLabel: string;
  priority: number;
  changeFrequency: 'daily' | 'weekly' | 'monthly' | 'yearly' | 'always' | 'hourly' | 'never';
  schemaType: 'WebPage' | 'AboutPage' | 'ContactPage';
}

export const INDEXABLE_PUBLIC_PAGES: PublicPageConfig[] = [
  {
    path: '/',
    title: 'TJR Mind & Body | Practical Resilience Coaching and Education',
    description: PUBLIC_SITE_DESCRIPTION,
    navLabel: 'Home',
    priority: 1,
    changeFrequency: 'monthly',
    schemaType: 'WebPage',
  },
  {
    path: '/about',
    title: 'About | TJR Mind & Body',
    description:
      'Learn about TJR Mind & Body, the practical resilience coaching and education approach, and who this work is designed to support.',
    navLabel: 'About',
    priority: 0.9,
    changeFrequency: 'monthly',
    schemaType: 'AboutPage',
  },
  {
    path: '/founder-story',
    title: 'Founder Story | TJR Mind & Body',
    description:
      'Why TJR Mind & Body exists: Tim Jarden-Ross on operational resilience, chronic pain, rebuilding, and practical support that works in real life.',
    navLabel: 'Founder Story',
    priority: 0.8,
    changeFrequency: 'monthly',
    schemaType: 'AboutPage',
  },
  {
    path: '/contact',
    title: 'Contact | TJR Mind & Body',
    description:
      'Contact TJR Mind & Body to enquire about support, coaching, education, or a discovery conversation.',
    navLabel: 'Contact',
    priority: 0.8,
    changeFrequency: 'monthly',
    schemaType: 'ContactPage',
  },
  {
    path: '/privacy-policy',
    title: 'Privacy Policy | TJR Mind & Body',
    description:
      'Read how TJR Mind & Body collects, uses, stores, and protects personal information submitted through this website.',
    navLabel: 'Privacy Policy',
    priority: 0.5,
    changeFrequency: 'yearly',
    schemaType: 'WebPage',
  },
  {
    path: '/terms-conditions',
    title: 'Terms & Conditions | TJR Mind & Body',
    description:
      'Review the terms that govern use of the TJR Mind & Body website, content, and enquiry process.',
    navLabel: 'Terms & Conditions',
    priority: 0.5,
    changeFrequency: 'yearly',
    schemaType: 'WebPage',
  },
  {
    path: '/disclaimer',
    title: 'Website Disclaimer | TJR Mind & Body',
    description:
      'Important website disclaimer for TJR Mind & Body, including educational scope, coaching focus, and medical advice limitations.',
    navLabel: 'Disclaimer',
    priority: 0.5,
    changeFrequency: 'yearly',
    schemaType: 'WebPage',
  },
  {
    path: '/cookie-policy',
    title: 'Cookie Policy | TJR Mind & Body',
    description:
      'Understand how TJR Mind & Body uses cookies and similar technologies, including essential authentication-related cookies.',
    navLabel: 'Cookie Policy',
    priority: 0.4,
    changeFrequency: 'yearly',
    schemaType: 'WebPage',
  },
];

export const PRIMARY_PUBLIC_NAV = [
  { href: '/', label: 'Home' },
  { href: '/about', label: 'About' },
  { href: '/founder-story', label: 'Founder Story' },
  { href: '/contact', label: 'Contact' },
  { href: '/login', label: 'Login' },
] as const;

export const FOOTER_PUBLIC_NAV = [
  { href: '/about', label: 'About' },
  { href: '/founder-story', label: 'Founder Story' },
  { href: '/contact', label: 'Contact' },
  { href: '/privacy-policy', label: 'Privacy Policy' },
  { href: '/terms-conditions', label: 'Terms & Conditions' },
  { href: '/disclaimer', label: 'Disclaimer' },
  { href: '/cookie-policy', label: 'Cookie Policy' },
] as const;

export const INDEXABLE_PUBLIC_PATHS = INDEXABLE_PUBLIC_PAGES.map((page) => page.path);

export const PUBLIC_ROUTE_ALLOWLIST = new Set([
  ...INDEXABLE_PUBLIC_PATHS,
  '/login',
  '/robots.txt',
  '/sitemap.xml',
  PUBLIC_SOCIAL_IMAGE_PATH,
]);

export const PRIVATE_ROBOTS_DISALLOWS = [
  '/api/',
  '/auth/',
  '/captains-chair',
  '/advisory-council',
  '/advisory-workbench',
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
  '/home',
  '/recommended',
  '/investigate',
  '/comms-studio',
] as const;

export function getPublicPage(path: string): PublicPageConfig {
  const page = INDEXABLE_PUBLIC_PAGES.find((entry) => entry.path === path);
  if (!page) {
    throw new Error(`Unknown public page path: ${path}`);
  }
  return page;
}

export function buildBreadcrumbs(path: string) {
  const page = getPublicPage(path);
  if (path === '/') return [{ name: 'Home', path: '/' }];
  return [
    { name: 'Home', path: '/' },
    { name: page.navLabel, path: page.path },
  ];
}

export function buildPublicMetadata(path: string): Metadata {
  const page = getPublicPage(path);

  return {
    title: {
      absolute: page.title,
    },
    description: page.description,
    robots: {
      index: true,
      follow: true,
    },
    alternates: {
      canonical: page.path,
    },
    openGraph: {
      title: page.title,
      description: page.description,
      url: page.path,
      siteName: PUBLIC_SITE_NAME,
      type: 'website',
      images: [
        {
          url: PUBLIC_SOCIAL_IMAGE_PATH,
          width: 1200,
          height: 630,
          alt: 'TJR Mind & Body social sharing image',
        },
      ],
    },
    twitter: {
      card: 'summary_large_image',
      title: page.title,
      description: page.description,
      images: [PUBLIC_SOCIAL_IMAGE_PATH],
    },
  };
}
