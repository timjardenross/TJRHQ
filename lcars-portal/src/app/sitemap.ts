import type { MetadataRoute } from 'next';
import { SITE_URL } from '@/lib/site';

// USS-TJR-MSN-XML-SITEMAP: everything under middleware auth (see
// src/middleware.ts) redirects unauthenticated requests to /login before
// rendering, so /login is the only URL a crawler can actually retrieve
// content from today. Add entries here only as routes are deliberately
// carved out of the auth gate for public access.
export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: `${SITE_URL}/login`,
      lastModified: new Date(),
      changeFrequency: 'yearly',
      priority: 0.5
    }
  ];
}
