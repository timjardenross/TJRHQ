'use client';

import Link from 'next/link';
import { useState, type FormEvent } from 'react';
import { HqContext, useHq } from '@/lib/hq/HqProvider';
import { loadIntel } from '@/lib/hq/data';
import { hqMission } from '@/lib/hq/actions';
import { useAsync } from '@/lib/hq/useAsync';
import { ErrorLine, EvidenceBar, Loading, RiskPill } from '../../_components/ui';

export default function HqIntelItemPage({ params }: { params: { id: string } }) {
  const id = decodeURIComponent(params.id);
  const { toast, openNew, reloadDecisions } = useHq();
  const intel = useAsync(loadIntel);
  const [busy, setBusy] = useState(false);
  const [started, setStarted] = useState(false);
  const [asking, setAsking] = useState(false);
  const [requested, setRequested] = useState<{ existing: boolean } | null>(null);
  const [reqBusy, setReqBusy] = useState(false);
  const [question, setQuestion] = useState('');
  const [reason, setReason] = useState('');
  const [optionsText, setOptionsText] = useState('Start a mission to assess\nKeep watching\nNo action');
  const [recommendation, setRecommendation] = useState('');
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

  function openRequest() {
    if (!item) return;
    setQuestion(`How should we respond to “${item.title}”?`);
    setReason(item.why ?? item.summary);
    setAsking(true);
  }

  async function sendRequest(e: FormEvent) {
    e.preventDefault();
    if (!item || reqBusy) return;
    setReqBusy(true);
    const evidence = [
      { label: 'What happened', detail: item.summary },
      { label: 'Evidence quality', detail: item.evidence },
      ...(item.corroboration !== null ? [{ label: 'Corroboration', detail: `${item.corroboration} source${item.corroboration === 1 ? '' : 's'}` }] : []),
      ...(item.sourceName ? [{ label: 'Source', detail: item.sourceName }] : []),
      ...(item.risk ? [{ label: 'Risk', detail: item.risk }] : []),
    ];
    try {
      const resp = await fetch('/api/hq/decisions/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sourceId: item.id, sourceTitle: item.title, sourceUrl: item.url, sourceLens: item.lens,
          question, reason, options: optionsText.split('\n').map((o) => o.trim()).filter(Boolean),
          recommendation: recommendation || null, evidence,
        }),
      });
      const json = (await resp.json().catch(() => ({}))) as { error?: string; existing?: boolean };
      if (!resp.ok) { toast(json.error ?? 'Could not create the request.'); }
      else {
        setRequested({ existing: Boolean(json.existing) });
        setAsking(false);
        await reloadDecisions();
        toast(json.existing ? 'A decision was already requested for this item.' : 'Sent to Decisions for you.');
      }
    } finally { setReqBusy(false); }
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
              {requested
                ? <Link className="hq-btn" href="/hq/decisions">{requested.existing ? 'Decision already requested: open Decisions' : 'Decision requested: open Decisions'}</Link>
                : <button type="button" className="hq-btn" onClick={openRequest} aria-expanded={asking}>Ask me to decide</button>}
              <Link className="hq-btn quiet" href={item.legacyHref}>Open in existing workbench</Link>
            </div>
          </div>
          {asking && !requested && (
            <form className="hq-panel" onSubmit={sendRequest} aria-label="Request a decision">
              <h2 style={{ fontSize: '.95rem' }}>Request a decision</h2>
              <p className="hq-muted" style={{ fontSize: '.86rem' }}>This puts one decision in your Decisions inbox. The item, its evidence, your reason and the options travel with it. Nothing happens until you choose.</p>
              <label htmlFor="dr-q" className="hq-muted" style={{ fontSize: '.84rem' }}>What needs to be decided</label>
              <textarea id="dr-q" className="hq-input" value={question} onChange={(e) => setQuestion(e.target.value)} required maxLength={300} />
              <label htmlFor="dr-r" className="hq-muted" style={{ fontSize: '.84rem' }}>Why a decision is needed</label>
              <textarea id="dr-r" className="hq-input" value={reason} onChange={(e) => setReason(e.target.value)} required maxLength={1000} />
              <label htmlFor="dr-o" className="hq-muted" style={{ fontSize: '.84rem' }}>Options, one per line (2 to 5)</label>
              <textarea id="dr-o" className="hq-input" value={optionsText} onChange={(e) => setOptionsText(e.target.value)} required />
              <label htmlFor="dr-rec" className="hq-muted" style={{ fontSize: '.84rem' }}>Recommendation (leave blank if there is no evidence-supported recommendation)</label>
              <select id="dr-rec" className="hq-input" value={recommendation} onChange={(e) => setRecommendation(e.target.value)}>
                <option value="">No recommendation</option>
                {optionsText.split('\n').map((o) => o.trim()).filter(Boolean).map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
              <div className="hq-acts">
                <button type="submit" className="hq-btn primary" disabled={reqBusy} aria-disabled={reqBusy}>{reqBusy ? 'Sending…' : 'Send to Decisions'}</button>
                <button type="button" className="hq-btn quiet" onClick={() => setAsking(false)}>Cancel</button>
              </div>
            </form>
          )}
        </>
      )}
    </>
  );
}
