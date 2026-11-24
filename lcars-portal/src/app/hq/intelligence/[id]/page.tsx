'use client';

import Link from 'next/link';
import { useState } from 'react';
import { HqContext, useHq } from '@/lib/hq/HqProvider';
import { loadIntel } from '@/lib/hq/data';
import { hqMission } from '@/lib/hq/actions';
import { useAsync } from '@/lib/hq/useAsync';
import { ErrorLine, EvidenceBar, Loading, RiskPill } from '../../_components/ui';

export default function HqIntelItemPage({ params }: { params: { id: string } }) {
  const id = decodeURIComponent(params.id);
  const { toast, openNew } = useHq();
  const intel = useAsync(loadIntel);
  const [busy, setBusy] = useState(false);
  const [started, setStarted] = useState(false);
  const item = intel.data?.items.find((i) => i.id === id) ?? null;

  async function startMission() {
    if (!item || busy || started) return; // one click, one mission: promote has no duplicate guard
    setBusy(true);
    const r = await hqMission(`Assess: ${item.title}`, { label: item.title, href: `/hq/intelligence/${encodeURIComponent(item.id)}` });
    setBusy(false);
    if (r.ok) { setStarted(true); toast('Mission candidate created with this item attached. It needs your review in Missions.'); }
    else if (r.partial) { setStarted(true); toast(`${r.error} Your idea is saved in Capture.`); }
    else toast(r.error ?? 'Could not create the mission.');
  }

  return (
    <>
      {item && <HqContext label={item.title} href={`/hq/intelligence/${encodeURIComponent(item.id)}`} />}
      <Link href="/hq/intelligence" className="hq-back">← Intelligence</Link>
      {intel.loading && <Loading what="this item" />}
      {intel.error && <ErrorLine what="this item" detail={intel.error} />}
      {!intel.loading && !intel.error && !item && <div className="hq-notice" role="status">This item is no longer in the current list. It may have been resolved or aged out.</div>}
      {item && (
        <>
          <div className="hq-head">
            <div className="hq-meta"><span className="hq-tag">{item.kind}</span>{item.when && <span>{new Date(item.when).toLocaleString()}</span>}</div>
            <h1>{item.title}</h1>
            <div className="hq-meta"><RiskPill risk={item.risk} /><EvidenceBar evidence={item.evidence} /></div>
          </div>
          <div className="hq-panel">
            <dl className="hq-kv">
              <dt>What happened</dt><dd>{item.summary}</dd>
              {item.why && <><dt>Why it matters</dt><dd>{item.why}</dd></>}
              {item.youNeedTo && <><dt>Suggested</dt><dd>{item.youNeedTo}</dd></>}
              {item.corroboration !== null && <><dt>Corroboration</dt><dd>{item.corroboration} {item.corroboration === 1 ? 'source' : 'sources'}</dd></>}
              {item.sourceName && <><dt>Source</dt><dd>{item.sourceName}</dd></>}
            </dl>
            {item.url && <a className="hq-link inline" href={item.url} target="_blank" rel="noopener noreferrer">Open the original source</a>}
          </div>
          <div className="hq-panel">
            <h2 style={{ fontSize: '.95rem' }}>What next?</h2>
            <p className="hq-muted" style={{ fontSize: '.88rem' }}>Either keeps this item attached, so nothing needs re-entering.</p>
            <div className="hq-acts">
              <button type="button" className="hq-btn primary" onClick={startMission} disabled={busy || started} aria-disabled={busy || started}>{started ? 'Mission requested' : busy ? 'Working…' : 'Start mission'}</button>
              <button type="button" className="hq-btn" onClick={() => openNew({ type: 'capture', context: { label: item.title, href: `/hq/intelligence/${encodeURIComponent(item.id)}` } })}>Capture a follow-up</button>
              <Link className="hq-btn quiet" href={item.legacyHref}>Open in existing workbench</Link>
            </div>
          </div>
        </>
      )}
    </>
  );
}
