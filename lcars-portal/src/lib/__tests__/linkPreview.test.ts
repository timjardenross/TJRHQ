import { describe, it, expect } from 'vitest';
import { extractLinkPreview } from '@/lib/linkPreview';

describe('extractLinkPreview', () => {
  it('extracts og:title, og:image, og:price:amount/currency', () => {
    const html = `
      <html><head>
        <meta property="og:title" content="Widget 3000" />
        <meta property="og:image" content="https://example.com/widget.jpg" />
        <meta property="og:price:amount" content="49.95" />
        <meta property="og:price:currency" content="AUD" />
        <title>Fallback Title</title>
      </head></html>
    `;
    const draft = extractLinkPreview(html, 'www.example.com');
    expect(draft.product_name).toBe('Widget 3000');
    expect(draft.image_url).toBe('https://example.com/widget.jpg');
    expect(draft.cost).toBe(49.95);
    expect(draft.currency).toBe('AUD');
    expect(draft.vendor).toBe('example.com');
  });

  it('falls back to product:price:amount/currency when og:price is absent', () => {
    const html = `
      <meta property="product:price:amount" content="120" />
      <meta property="product:price:currency" content="USD" />
    `;
    const draft = extractLinkPreview(html, 'shop.example.com');
    expect(draft.cost).toBe(120);
    expect(draft.currency).toBe('USD');
  });

  it('falls back to <title> when og:title is missing', () => {
    const html = `<title>Plain Title Only</title>`;
    const draft = extractLinkPreview(html, 'example.com');
    expect(draft.product_name).toBe('Plain Title Only');
  });

  it('returns nulls for cost/currency/product_name/image when no matching tags exist at all', () => {
    const html = `<html><head></head><body>no meta tags here</body></html>`;
    const draft = extractLinkPreview(html, 'example.com');
    expect(draft.product_name).toBeNull();
    expect(draft.image_url).toBeNull();
    expect(draft.cost).toBeNull();
    expect(draft.currency).toBeNull();
    expect(draft.vendor).toBe('example.com');
  });

  it('strips a leading www. from the vendor suggestion', () => {
    const draft = extractLinkPreview('', 'www.retailer.com.au');
    expect(draft.vendor).toBe('retailer.com.au');
  });

  it('decodes HTML entities in extracted text', () => {
    const html = `<meta property="og:title" content="Bill&#39;s &amp; Ted&#39;s Widget" />`;
    const draft = extractLinkPreview(html, 'example.com');
    expect(draft.product_name).toBe("Bill's & Ted's Widget");
  });

  it('does not crash on a non-numeric price amount', () => {
    const html = `<meta property="og:price:amount" content="Contact us" />`;
    const draft = extractLinkPreview(html, 'example.com');
    expect(draft.cost).toBeNull();
  });
});
