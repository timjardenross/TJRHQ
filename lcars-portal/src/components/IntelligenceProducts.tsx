'use client';

// Intelligence page: the three repeatable products, each with the four labelled sections.
import { useEffect, useState } from 'react';
import { PRODUCT_SECTIONS, type IntelligenceProduct } from '@/lib/intelligenceProducts';

interface Payload {
  available: boolean;
  products: IntelligenceProduct[];
}

export default function IntelligenceProducts() {
  const [data, setData] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/intelligence-workbench/products')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'));
  }, []);

  if (error) return <p className="text-wb-body text-wb-ink2">Intelligence products could not be loaded ({error}).</p>;
  if (!data) return <p className="text-wb-body text-wb-ink2">Loading intelligence products…</p>;
  if (!data.available || data.products.length === 0) {
    return (
      <p className="text-wb-body text-wb-ink2">
        No intelligence products have been generated yet. They are produced weekly when the job is enabled
        (INTEL_PRODUCTS_ENABLED) and the intelligence_products table exists.
      </p>
    );
  }
  return (
    <div className="space-y-8">
      {data.products.map((p) => (
        <section key={p.product_key} id={p.product_key} aria-labelledby={`${p.product_key}-h`}>
          <h2 id={`${p.product_key}-h`} className="font-sans text-base font-bold text-wb-ink">
            {p.title}
          </h2>
          <p className="mt-1 text-wb-body text-wb-ink2">
            Generated for {p.generated_for}. {p.summary}
          </p>
          {PRODUCT_SECTIONS.map(([key, label]) => (
            <div key={key} className="mt-3">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-wb-ink">{label}</h3>
              {(p.sections?.[key] ?? []).length ? (
                <ul className="mt-1 list-disc space-y-1 pl-5 text-wb-body text-wb-ink2">
                  {p.sections[key].map((line, i) => (
                    <li key={i}>{line}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-wb-body text-wb-ink2">Nothing recorded.</p>
              )}
            </div>
          ))}
          <details className="mt-3">
            <summary className="cursor-pointer text-wb-body text-wb-sage-deep">Full report</summary>
            <pre className="mt-2 whitespace-pre-wrap text-xs text-wb-ink2">{p.body_md}</pre>
          </details>
        </section>
      ))}
    </div>
  );
}
