'use client';

import Link from 'next/link';
import { Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { getJson, loadIntel } from '@/lib/hq/data';
import { useAsync } from '@/lib/hq/useAsync';
import { loadIntelExtras } from '@/lib/hq/intelExtras';
import { normaliseRisk } from '@/lib/hq/vocab';
import type { HqIntelItem } from '@/lib/hq/model';
import { LENSES, filterIntel, type Lens } from '@/lib/hq/intelFilter';
import { ErrorLine, EvidenceBar, Loading, Notice, RiskPill } from '../_components/ui';

interface BriefHead { brief_id: string; generated_at: string; approval_status: string | null; overall_risk: string | null; bottom_line?: string | null; executive_snapshot: string | null }

function Inner() {
  const router = useRouter();
  const params = useSearchParams();
  const raw = params.get('lens');
  const lens: Lens = (LENSES as readonly string[]).includes(raw ?? '') ? (raw as Lens) : 'All';
  const intel = useAsync(loadIntel);
  const brief = useAsync(async () => {
    const r = await getJson<{ briefs: BriefHead[] }>('/api/briefs');
    return r.ok ? r.data.briefs[0] ?? null : null;
  });
  const items = intel.data ? filterIntel(intel.data.items, lens) : [];
  const needs = items.filter((i) => i.needsYou);
  const others = items.filter((i) => !i.needsYou);
  const extras = useAsync(loadIntelExtras);

  const row = (i: HqIntelItem) => (
    <Link key={i.id} href={`/hq/intelligence/${encodeURIComponent(i.id)}`} className="hq-row">
      <span className="t">{i.title}</span>
      <span className="s">{i.kind}{i.when ? ` · ${new Date(i.when).toLocaleDateString()}` : ''}{i.summary ? ` · ${i.summary}` : ''}</span>
      <span className="r"><RiskPill risk={i.risk} /><EvidenceBar evidence={i.evidence} /></span>
    </Link>
  );

  return (
    <>
      <div className="hq-head">
        <h1>Intelligence</h1>
        <p className="hq-lead">Signals, alerts, briefs and research in one list.</p>
      </div>

      {brief.data && (
        <Link href={`/hq/intelligence/brief/${encodeURIComponent(brief.data.brief_id)}`} className="hq-row" style={{ background: 'var(--hq-surface2)', borderRadius: 8, border: '1px solid var(--hq-line)' }}>
          <span className="t">Latest brief · {brief.data.brief_id}</span>
          <span className="s">{(brief.data.bottom_line ?? brief.data.executive_snapshot ?? 'No summary recorded.').slice(0, 160)}</span>
          <span className="r"><RiskPill risk={normaliseRisk(brief.data.overall_risk)} /><span className="hq-pill info">{(brief.data.approval_status ?? 'Unknown').replace('_', ' ')}</span></span>
        </Link>
      )}

      <div className="hq-chips" role="group" aria-label="Filter">
        {LENSES.map((l) => (
          <button key={l} type="button" className="hq-chip" aria-pressed={lens === l}
            onClick={() => router.replace(l === 'All' ? '/hq/intelligence' : `/hq/intelligence?lens=${encodeURIComponent(l)}`, { scroll: false })}>{l}</button>
        ))}
      </div>

      {intel.loading && <Loading what="intelligence" />}
      {intel.error && <ErrorLine what="intelligence" detail={intel.error} />}
      {intel.data && intel.data.unavailable.length > 0 && <ErrorLine what={intel.data.unavailable.join(', ')} />}
      {intel.data && items.length === 0 && <div className="hq-quiet">Nothing in this view.</div>}
      {needs.length > 0 && <section className="hq-sec" aria-labelledby="i-need"><div className="hq-sech"><h2 id="i-need">Needs you</h2></div>{needs.map(row)}</section>}
      {others.length > 0 && <section className="hq-sec" aria-labelledby="i-else"><div className="hq-sech"><h2 id="i-else">{needs.length ? 'Everything else' : 'Items'}</h2></div>{others.map(row)}</section>}

      {extras.data && (
        <>
          {extras.data.products.state === 'ok' && extras.data.products.products.length > 0 && (
            <section className="hq-sec" aria-labelledby="i-prod">
              <div className="hq-sech"><h2 id="i-prod">Intelligence products</h2><Link href="/intelligence-workbench?tab=products">Open in Intelligence workbench</Link></div>
              {extras.data.products.products.map((p) => (
                <Link key={p.product_key} href={`/intelligence-workbench?tab=products#${encodeURIComponent(p.product_key)}`} className="hq-row">
                  <span className="t">{p.title}</span><span className="s">{p.summary}</span>
                  <span className="r"><span className="hq-pill info">{new Date(p.as_of).toLocaleDateString()}</span></span>
                </Link>
              ))}
            </section>
          )}
          {extras.data.coverage.state === 'ok' && extras.data.coverage.counts && (
            <section className="hq-sec" aria-labelledby="i-cov">
              <div className="hq-sech"><h2 id="i-cov">Source coverage</h2><Link href="/intelligence-workbench?tab=sources">Open in Intelligence workbench</Link></div>
              <div className="hq-plain">
                {Object.entries(extras.data.coverage.counts).map(([k, v]) => `${v} ${k.toLowerCase()}`).join(' · ')}
              </div>
              {extras.data.coverage.limitationsLine && <div className="hq-quiet">{extras.data.coverage.limitationsLine}</div>}
              {extras.data.coverage.notHealthy.slice(0, 5).map((s) => (
                <div className="hq-plain" key={s.source_name}>{s.source_name} <span className={`hq-pill ${s.state === 'BROKEN' ? 'red' : 'amber'}`}>{s.state.toLowerCase()}</span> <span className="hq-muted">· {s.reason}</span></div>
              ))}
            </section>
          )}
          {(extras.data.incidents.state !== 'ok' || extras.data.products.state !== 'ok') && (
            <Notice>
              {extras.data.incidents.state === 'off' && 'Incident clustering is switched off in this environment. '}
              {extras.data.incidents.state === 'unavailable' && 'Incidents are not available yet (the snapshot is not published). '}
              {extras.data.products.state !== 'ok' && 'Intelligence products are not available yet (their migration is not applied). '}
              These come from the Intelligence programme and appear here once it activates them.
            </Notice>
          )}
        </>
      )}
    </>
  );
}

export default function HqIntelligence() {
  return <Suspense fallback={<Loading what="intelligence" />}><Inner /></Suspense>;
}
