'use client';

// Per-domain detail page (Briefs/Captain's Brief consolidation follow-up —
// BRIEFS_CAPTAINS_BRIEF_CONSOLIDATION.md §13 "deliberately not built in
// this pass"). Phase 5 retired /captains-brief-workbench?domain=... with
// no replacement, judged an acceptable simplification at the time since
// the Domains tab's own card already showed more than the old per-domain
// filter view did. This restores a stable, bookmarkable per-domain URL —
// intelligence/brief/domains_view.py's event-bus DomainSummary.detail_href
// now points here instead of the flat /briefs link.
//
// Reuses the same /api/briefs/domains endpoint and the same DomainCard
// component the Domains tab renders — no new backend capability, no new
// data shape, just a dedicated destination for one domain's already-
// computed picture. Read-only, matching the tab's own convention: no
// approve/reject/execute affordances.

import { useParams } from 'next/navigation';
import { useState } from 'react';
import { useAbortEffect } from '@/hooks/useAbortEffect';
import { Card, WorkbenchShell } from '@/components/ui';
import type { DomainsDocument } from '@/lib/domainsShared';
import { DomainCard } from '../../_components/DomainsView';

export default function DomainDetailPage() {
  const params = useParams<{ key: string }>();
  const key = params.key;

  const [doc, setDoc] = useState<DomainsDocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useAbortEffect((signal, alive) => {
    fetch('/api/briefs/domains', { signal })
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw new Error(d?.error || 'Failed to load domains');
        if (alive()) { setDoc(d); setError(null); }
      })
      .catch((e) => {
        if (alive() && !(e instanceof Error && e.name === 'AbortError')) {
          setError(e instanceof Error ? e.message : 'Failed to load domains');
        }
      })
      .finally(() => { if (alive()) setLoading(false); });
  }, []);

  const domain = doc?.domains.find((d) => d.key === key) ?? null;

  return (
    <WorkbenchShell
      title={domain?.label ?? 'Domain'}
      eyebrow="Briefs · Domain Detail"
      tagline="USS TJR · One domain's synthesized picture — posture, what changed, what matters, watch, evidence"
      back={{ href: '/briefs', label: 'Briefs' }}
    >
      {loading && <p className="text-sm text-wb-ink2 animate-pulse">Assembling domain picture…</p>}

      {!loading && error && (
        <Card title="Domains">
          <p className="text-sm text-wb-crit-on">{error}</p>
        </Card>
      )}

      {!loading && !error && !domain && (
        <Card title="Domain not found">
          <p className="text-sm text-wb-ink2">
            No domain with key &ldquo;{key}&rdquo; in the current cross-domain picture. It may have been renamed,
            or may simply have no data this cycle — check the{' '}
            <a href="/briefs" className="text-wb-sage-deep underline">
              Briefs Domains tab
            </a>{' '}
            for the current list.
          </p>
        </Card>
      )}

      {!loading && !error && domain && (
        <div className="max-w-2xl">
          <DomainCard domain={domain} />
        </div>
      )}
    </WorkbenchShell>
  );
}
