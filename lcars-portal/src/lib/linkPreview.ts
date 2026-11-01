/**
 * Pure HTML meta-tag extraction for the Shopping List "paste a URL" assist
 * (POST /api/shopping-list/preview). Split out from the route handler so
 * the parsing logic is unit-testable without a real network fetch — the
 * route owns the fetch (timeout, size cap, SSRF check); this just reads a
 * string of HTML already in hand.
 */

export interface LinkPreviewDraft {
  product_name: string | null;
  image_url: string | null;
  cost: number | null;
  currency: string | null;
  vendor: string;
}

function metaContent(html: string, attr: 'property' | 'name', key: string): string | null {
  const re = new RegExp(
    `<meta[^>]+${attr}=["']${key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}["'][^>]+content=["']([^"']*)["']`,
    'i',
  );
  const altRe = new RegExp(
    `<meta[^>]+content=["']([^"']*)["'][^>]+${attr}=["']${key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}["']`,
    'i',
  );
  const match = html.match(re) ?? html.match(altRe);
  return match ? decodeHtmlEntities(match[1].trim()) : null;
}

function decodeHtmlEntities(s: string): string {
  return s
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>');
}

function titleTag(html: string): string | null {
  const match = html.match(/<title[^>]*>([^<]*)<\/title>/i);
  return match ? decodeHtmlEntities(match[1].trim()) : null;
}

/** Extracts product_name/image_url/cost/currency suggestions from raw HTML,
 * plus vendor from the hostname. Checks both `og:price:amount` and
 * `product:price:amount` (and their currency counterparts) since sites
 * vary in which they emit — often neither. Never throws; missing tags just
 * come back null so the frontend form falls back to manual entry. */
export function extractLinkPreview(html: string, hostname: string): LinkPreviewDraft {
  const ogTitle = metaContent(html, 'property', 'og:title');
  const product_name = ogTitle ?? titleTag(html);

  const ogImage = metaContent(html, 'property', 'og:image');
  const image_url = ogImage;

  const priceAmount =
    metaContent(html, 'property', 'og:price:amount') ??
    metaContent(html, 'property', 'product:price:amount');
  const priceCurrency =
    metaContent(html, 'property', 'og:price:currency') ??
    metaContent(html, 'property', 'product:price:currency');

  const cost = priceAmount !== null && priceAmount !== '' && !Number.isNaN(Number(priceAmount))
    ? Number(priceAmount)
    : null;
  const currency = priceCurrency || null;

  return {
    product_name,
    image_url,
    cost,
    currency,
    vendor: hostname.replace(/^www\./i, ''),
  };
}
