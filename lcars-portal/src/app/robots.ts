import type { MetadataRoute } from 'next';
import { SITE_URL } from '@/lib/site';

// This app is a private, auth-gated command centre (see src/middleware.ts) —
// only /login is reachable without a session. Disallow everything else so
// crawlers don't waste budget on redirect chains or risk indexing an
// authenticated URL that later becomes public without a deliberate review.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: ['/login'],
        disallow: ['/']
      }
    ],
    sitemap: `${SITE_URL}/sitemap.xml`
  };
}
