import type { MetadataRoute } from 'next';
import { SITE_URL } from '@/lib/site';
import { INDEXABLE_PUBLIC_PATHS, PRIVATE_ROBOTS_DISALLOWS } from '@/lib/public-site';

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: [...INDEXABLE_PUBLIC_PATHS, '/login'],
        disallow: [...PRIVATE_ROBOTS_DISALLOWS],
      },
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
