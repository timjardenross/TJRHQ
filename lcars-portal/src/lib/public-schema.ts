import { SITE_URL } from '@/lib/site';
import {
  CONTACT_RESPONSE_TIME,
  PUBLIC_SITE_DESCRIPTION,
  PUBLIC_SITE_NAME,
  SUPPORT_EMAIL,
  buildBreadcrumbs,
  getPublicPage,
} from './public-site';

export interface JsonLdObject {
  [key: string]: unknown;
}

export function buildPublicSchemaSet(path: string): JsonLdObject[] {
  const page = getPublicPage(path);
  const pageUrl = `${SITE_URL}${page.path}`;
  const breadcrumbs = buildBreadcrumbs(path);

  const organization: JsonLdObject = {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    '@id': `${SITE_URL}#organization`,
    name: PUBLIC_SITE_NAME,
    url: SITE_URL,
    email: SUPPORT_EMAIL,
    logo: `${SITE_URL}/icon-512.png`,
    image: `${SITE_URL}/icon-512.png`,
    description: PUBLIC_SITE_DESCRIPTION,
    founder: { '@id': `${SITE_URL}#person` },
    contactPoint: [
      {
        '@type': 'ContactPoint',
        contactType: 'customer support',
        email: SUPPORT_EMAIL,
        areaServed: 'AU',
        availableLanguage: ['en'],
      },
    ],
  };

  const person: JsonLdObject = {
    '@context': 'https://schema.org',
    '@type': 'Person',
    '@id': `${SITE_URL}#person`,
    name: 'Tim Jarden-Ross',
    url: `${SITE_URL}/founder-story`,
    email: SUPPORT_EMAIL,
    jobTitle: 'Founder',
    image: `${SITE_URL}/icon-512.png`,
    worksFor: { '@id': `${SITE_URL}#organization` },
    description:
      'Founder of TJR Mind & Body, combining operational resilience leadership with lived experience of chronic pain, setbacks, and rebuilding.',
    knowsAbout: [
      'Operational resilience',
      'Business continuity',
      'Chronic pain self-management',
      'Practical resilience',
      'Coaching and education',
    ],
  };

  const website: JsonLdObject = {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    '@id': `${SITE_URL}#website`,
    name: PUBLIC_SITE_NAME,
    url: SITE_URL,
    description: PUBLIC_SITE_DESCRIPTION,
    inLanguage: 'en-AU',
    publisher: { '@id': `${SITE_URL}#organization` },
  };

  const webPage: JsonLdObject = {
    '@context': 'https://schema.org',
    '@type': page.schemaType,
    '@id': `${pageUrl}#webpage`,
    url: pageUrl,
    name: page.title,
    description: page.description,
    inLanguage: 'en-AU',
    isPartOf: { '@id': `${SITE_URL}#website` },
    publisher: { '@id': `${SITE_URL}#organization` },
    breadcrumb: path === '/' ? undefined : { '@id': `${pageUrl}#breadcrumb` },
    about:
      path === '/founder-story' || path === '/about'
        ? { '@id': `${SITE_URL}#person` }
        : { '@id': `${SITE_URL}#organization` },
    mainEntity:
      path === '/contact'
        ? {
            '@type': 'ContactPoint',
            contactType: 'customer support',
            email: SUPPORT_EMAIL,
            description: CONTACT_RESPONSE_TIME,
          }
        : undefined,
  };

  const breadcrumbList: JsonLdObject | null =
    path === '/'
      ? null
      : {
          '@context': 'https://schema.org',
          '@type': 'BreadcrumbList',
          '@id': `${pageUrl}#breadcrumb`,
          itemListElement: breadcrumbs.map((crumb, index) => ({
            '@type': 'ListItem',
            position: index + 1,
            name: crumb.name,
            item: `${SITE_URL}${crumb.path}`,
          })),
        };

  return [organization, person, website, webPage, breadcrumbList].filter(
    (entry): entry is JsonLdObject => entry != null
  );
}
