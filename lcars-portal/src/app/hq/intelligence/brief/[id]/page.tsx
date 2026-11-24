'use client';

import Link from 'next/link';
import { useState } from 'react';
import { HqContext, useHq } from '@/lib/hq/HqProvider';
import { getJson } from '@/lib/hq/data';
import { actOnBrief } from '@/lib/hq/decisionSources';
import { useAsync } from '@/lib/hq/useAsync';
import { normaliseRisk } from '@/lib/hq/vocab';
import { ErrorLine, Loading, Notice, RiskPill } from '../../../_components/ui';

interface TopEvent { event_id?: string; title: string; risk_rating: string | null; summary?: string | null; so_what?: string | null; canonical_url?: string | null }
interface Brief {
  brief_id: string; generated_at: string; approval_status: 'IN_REVIEW' | 'QA_PASSED' | 'PUBLISHED' | null; overall_risk: string | null;
  executive_snapshot: string | null; bottom_line?: string | null; top_events?: TopEvent[] | null; known_unknowns?: string[] | null;
  coverage?: { degraded?: boolean; reason?: string | null; failed?: number; missing_sources?: string[] } | null;
}

export default function HqBriefPage({ params }: { params: { id: string } }) {
  const id = decodeURIComponent(params.id);
  const { toast, reloadDecisions } = useHq();
  const brief = useAsync(async () => {
    const r = await getJson<{ brief: Brief | null }>(`/api/briefs/${encodeURIComponent(id)}`);
    if (!r.ok) throw new Error(r.error);
    return r.data.brief;
  }, [id]);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const b = brief.data;

  async function gate() {
    if (!b || busy || (b.approval_status !== 'IN_REVIEW' && b.approval_status !== 'QA_PASSED')) return;
    setBusy(true);
    const res = await actOnBrief({ kind: 'brief', briefId: b.brief_id, status: b.approval_status });
    setBusy(false);
    setConfirm(false);
    toast(res.ok ? (b.approval_status === 'QA_PASSED' ? 'Brief published. This cannot be undone.' : 'Brief marked QA passed.') : (res.error ?? 'Nothing was changed.'));
    await Promise.all([brief.reload(), reloadDecisions()]);
  }

  const status = b?.approval_status ?? null;
  return (
    <>
      <HqContext label={`Brief ${id}`} href={`/hq/intelligence/brief/${encodeURIComponent(id)}`} />
      <Link href="/hq/intelligence" className="hq-back">← Intelligence</Link>
      {brief.loading && <Loading what="the brief" />}
      {brief.error && <ErrorLine what="the brief" detail={brief.error} />}
      {!brief.loading && !brief.error && !b && <div className="hq-notice" role="status">No brief with that id.</div>}
      {b && (
        <>
          <div className="hq-head">
            <div className="hq-meta"><span className="hq-tag">Brief</span><span>{new Date(b.generated_at).toLocaleString()}</span><span className="hq-pill info">{(status ?? 'Unknown').replace('_', ' ')}</span></div>
            <h1>Brief {b.brief_id}</h1>
            <div className="hq-meta"><RiskPill risk={normaliseRisk(b.overall_risk)} /></div>
          </div>
          {b.coverage?.degraded && <Notice>Coverage was reduced for this brief{b.coverage.reason ? `: ${b.coverage.reason}` : ''}.{b.coverage.missing_sources?.length ? ` Missing: ${b.coverage.missing_sources.join(', ')}.` : ''}</Notice>}
          <div className="hq-panel">
            <p>{b.bottom_line ?? b.executive_snapshot ?? 'No summary was recorded for this brief.'}</p>
          </div>
          {(b.top_events?.length ?? 0) > 0 && (
            <section className="hq-sec" aria-labelledby="b-ev">
              <div className="hq-sech"><h2 id="b-ev">Top items</h2></div>
              {b.top_events!.map((e, i) => (
                <div className="hq-plain" key={e.event_id ?? i}>
                  <strong>{e.title}</strong> <RiskPill risk={normaliseRisk(e.risk_rating)} />
                  {e.so_what && <div className="hq-muted" style={{ fontSize: '.86rem' }}>{e.so_what}</div>}
                  {e.canonical_url && <div><a className="hq-link inline" href={e.canonical_url} target="_blank" rel="noopener noreferrer">Original source</a></div>}
                </div>
              ))}
            </section>
          )}
          {(b.known_unknowns?.length ?? 0) > 0 && (
            <details className="hq-details"><summary>What this brief does not know</summary>
              <ul style={{ margin: 0, paddingLeft: '1.1em' }}>{b.known_unknowns!.map((u, i) => <li key={i}>{u}</li>)}</ul>
            </details>
          )}
          {(status === 'IN_REVIEW' || status === 'QA_PASSED') && (
            <div className="hq-panel">
              <h2 style={{ fontSize: '.95rem' }}>{status === 'QA_PASSED' ? 'Ready to publish' : 'In review'}</h2>
              <p className="hq-muted" style={{ fontSize: '.88rem' }}>
                {status === 'QA_PASSED' ? 'Publishing sends the notification and cannot be undone. Only an executive approval can do this.' : 'Mark it QA passed when you are satisfied with its quality.'}
              </p>
              {!confirm ? (
                <div className="hq-acts"><button type="button" className="hq-btn primary" onClick={() => (status === 'QA_PASSED' ? setConfirm(true) : void gate())} disabled={busy}>{status === 'QA_PASSED' ? 'Publish' : 'Mark QA passed'}</button></div>
              ) : (
                <div className="hq-acts" role="alertdialog" aria-label="Confirm publish">
                  <button type="button" className="hq-btn primary" onClick={gate} disabled={busy}>{busy ? 'Publishing…' : 'Yes, publish now'}</button>
                  <button type="button" className="hq-btn quiet" onClick={() => setConfirm(false)}>Cancel</button>
                </div>
              )}
            </div>
          )}
          <Link className="hq-link inline" href={`/briefs/${encodeURIComponent(b.brief_id)}`}>Open in existing Briefs</Link>
        </>
      )}
    </>
  );
}
