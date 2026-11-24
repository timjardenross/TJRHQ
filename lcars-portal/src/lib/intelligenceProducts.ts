// Intelligence products (recurring provider, systemic view, forward watch): types and pure helpers.
// Rows come from public.intelligence_products (DRAFT migration docs/migration-drafts/0261_intelligence_products.DRAFT.sql),
// written by intelligence/intel_products_job.py. Until that table exists the API reports `available: false`.

import { productHref } from './intelligenceLinks';

export const PRODUCT_SECTIONS = [
  ['confirmed_evidence', 'Confirmed evidence'],
  ['analytical_inference', 'Analytical inference'],
  ['potential_exposure', 'Potential exposure'],
  ['unknowns', 'Unknowns'],
] as const;

export type SectionKey = (typeof PRODUCT_SECTIONS)[number][0];

export interface ProductException {
  dedupe_key: string;
  title: string;
  detail: string;
  severity: string;
  evidence_ids?: string[];
  due_date?: string;
}

export interface IntelligenceProduct {
  product_key: string;
  generated_for: string;
  as_of: string;
  title: string;
  summary: string;
  sections: Record<SectionKey, string[]>;
  exceptions: ProductException[];
  body_md: string;
}

export interface ProductException2 extends ProductException {
  product_key: string;
  product_title: string;
  generated_for: string;
  href: string;
}

/** A dated forward-watch exception expires once its due_date (YYYY-MM-DD, UTC) is before today. */
export function isExpiredForwardWatch(productKey: string, e: ProductException, now: Date = new Date()): boolean {
  if (productKey !== 'forward_watch' || !e?.due_date) return false;
  const due = String(e.due_date).slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(due) && due < now.toISOString().slice(0, 10);
}

/**
 * Flatten exceptions across products, one entry per stable dedupe_key (first occurrence wins).
 * Dated forward-watch exceptions are dropped after their due_date: weekly generation would otherwise keep a passed
 * deadline on the attention list until the next run.
 */
export function collectExceptions(products: IntelligenceProduct[], now: Date = new Date()): ProductException2[] {
  const seen = new Set<string>();
  const out: ProductException2[] = [];
  for (const p of products) {
    for (const e of p.exceptions ?? []) {
      if (!e?.dedupe_key || seen.has(e.dedupe_key)) continue;
      if (isExpiredForwardWatch(p.product_key, e, now)) continue;
      seen.add(e.dedupe_key);
      out.push({
        ...e,
        product_key: p.product_key,
        product_title: p.title,
        generated_for: p.generated_for,
        href: productHref(p.product_key),
      });
    }
  }
  return out;
}

/** Latest row per product_key from rows ordered by generated_for descending. */
export function latestPerProduct(rows: IntelligenceProduct[]): IntelligenceProduct[] {
  const seen = new Set<string>();
  return rows.filter((r) => (seen.has(r.product_key) ? false : (seen.add(r.product_key), true)));
}

/** Postgres undefined_table (42P01) or PostgREST schema-cache miss: the draft migration has not been applied. */
export function isMissingTable(err: { code?: string; message?: string } | null | undefined): boolean {
  return !!err && (err.code === '42P01' || err.code === 'PGRST205' || /does not exist|schema cache/i.test(err.message ?? ''));
}

export async function fetchLatestProducts(sb: any): Promise<{ available: boolean; products: IntelligenceProduct[] }> {
  const { data, error } = await sb
    .from('intelligence_products')
    .select('product_key, generated_for, as_of, title, summary, sections, exceptions, body_md')
    .order('generated_for', { ascending: false })
    .limit(30);
  if (error) {
    if (isMissingTable(error)) return { available: false, products: [] };
    throw new Error(`Failed to read intelligence products: ${error.message}`);
  }
  return { available: true, products: latestPerProduct((data ?? []) as IntelligenceProduct[]) };
}
