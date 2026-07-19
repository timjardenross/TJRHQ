// Canonical production origin for metadata, sitemap, and robots generation.
// Falls back through Vercel's preview-deployment URL so non-production
// builds never leak localhost/preview URLs into public SEO surfaces.
export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL ||
  (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : null) ||
  'http://localhost:3100'
).replace(/\/$/, '');
