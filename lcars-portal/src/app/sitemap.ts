import type { MetadataRoute } from 'next';
import { SITE_URL } from '@/lib/site';
import { PUBLIC_PAGES } from '@/lib/public-site';

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();

  return PUBLIC_PAGES.map((page) => ({
    url: `${SITE_URL}${page.path}`,
    lastModified,
    changeFrequency: page.changeFrequency,
    priority: page.priority,
  }));
}
