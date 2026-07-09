# XML Sitemap and Search Discovery

## Current public surface

The LCARS portal now uses a hybrid architecture:

- Public, indexable pages:
  - `/`
  - `/founder-story`
  - `/contact`
- Public but intentionally non-indexed utility/auth page:
  - `/login`
- Public metadata routes:
  - `/sitemap.xml`
  - `/robots.txt`

Everything else remains part of the private LCARS command-centre and is still protected by middleware authentication.

## Sitemap policy

`src/app/sitemap.ts` includes only the intentional public marketing pages:

- `https://tjrmindbody.com/`
- `https://tjrmindbody.com/founder-story`
- `https://tjrmindbody.com/contact`

Private LCARS routes are never emitted into the sitemap, and `/login` is excluded so search engines do not treat the authentication entry point as a landing page.

## Robots policy

`src/app/robots.ts` now:

- allows the public marketing pages
- blocks `/api/*`
- blocks private LCARS route prefixes such as `/captains-chair`, `/medical`, `/missions`, `/intelligence`, and the rest of the internal application surface
- references the production sitemap URL

This keeps crawl budget focused on the public TJR Mind & Body experience while reducing the chance of accidental discovery of private app routes.

## Metadata strategy

The root app layout keeps the safe default:

- `index: false`
- `follow: false`

Each intentional public page overrides that default with page-level metadata:

- canonical URL
- `index: true`
- `follow: true`
- title
- description
- Open Graph metadata

This means new private routes inherit `noindex` unless they are explicitly designed and reviewed as public pages.

## Middleware policy

`src/middleware.ts` allows unauthenticated access only to:

- `/`
- `/founder-story`
- `/contact`
- `/login`

The metadata routes `/sitemap.xml` and `/robots.txt` are excluded from middleware matching so crawlers can fetch them without authentication redirects.

All other UI routes still redirect unauthenticated users to `/login`.

## Production URL safety

`src/lib/site.ts` continues to resolve the canonical site URL with the following priority:

1. `NEXT_PUBLIC_SITE_URL`
2. `https://tjrmindbody.com` in production
3. Vercel preview URL outside production
4. localhost fallback for local development

This prevents production sitemap and robots output from leaking localhost URLs when deployed correctly.
