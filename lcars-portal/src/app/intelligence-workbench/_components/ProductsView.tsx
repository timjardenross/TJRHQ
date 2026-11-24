'use client';

import { useEffect } from 'react';
import IntelligenceProducts from '@/components/IntelligenceProducts';

// Products tab of /intelligence-workbench: recurring provider, systemic and forward watch, each with the four labelled sections.
// Deep links are /intelligence-workbench?tab=products#<product_key>; the sections render after a fetch, so re-scroll once they exist.
export function ProductsView() {
  useEffect(() => {
    if (typeof window === 'undefined' || !window.location.hash) return;
    const id = decodeURIComponent(window.location.hash.slice(1));
    const t = window.setTimeout(() => document.getElementById(id)?.scrollIntoView({ block: 'start' }), 600);
    return () => window.clearTimeout(t);
  }, []);
  return (
    <section aria-labelledby="products-heading">
      <h2 id="products-heading" className="font-sans text-wb-label font-bold uppercase tracking-[0.25em] text-wb-sand-deep">
        Intelligence products
      </h2>
      <div className="mt-3">
        <IntelligenceProducts />
      </div>
    </section>
  );
}
