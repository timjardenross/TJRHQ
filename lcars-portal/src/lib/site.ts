// Canonical production origin for metadata, sitemap, and robots generation.
// Order: an explicit NEXT_PUBLIC_SITE_URL; on a production build, the project's stable
// production domain (VERCEL_PROJECT_PRODUCTION_URL), so canonical links and share-card image
// URLs never point at a one-off deployment address; then Vercel's per-deployment URL, so
// preview builds never leak localhost into public surfaces; then localhost for local dev.
function origin(host: string | undefined): string | null {
  return host ? `https://${host}` : null;
}

export function resolveSiteUrl(env: Record<string, string | undefined>): string {
  return (
    env.NEXT_PUBLIC_SITE_URL ||
    (env.VERCEL_ENV === 'production' ? origin(env.VERCEL_PROJECT_PRODUCTION_URL) : null) ||
    origin(env.VERCEL_URL) ||
    'http://localhost:3100'
  ).replace(/\/$/, '');
}

export const SITE_URL = resolveSiteUrl(process.env);
