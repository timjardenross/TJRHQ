import type { MetadataRoute } from 'next';
import { SITE_URL } from '@/lib/site';
import { PRIVATE_ROBOTS_DISALLOWS, PUBLIC_PATHS } from '@/lib/public-site';

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: [...PUBLIC_PATHS, '/login'],
        disallow: [...PRIVATE_ROBOTS_DISALLOWS],
      },
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
