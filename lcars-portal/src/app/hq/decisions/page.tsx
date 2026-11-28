'use client';

import Link from 'next/link';
import { Suspense, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { HqContext, useHq } from '@/lib/hq/HqProvider';
import { approveHqDecision, buildPackage, declineHqDecision, deferHqDecision, type HqActionResult } from '@/lib/hq/decisions';
import type { HqDecision } from '@/lib/hq/model';
import { ErrorLine, Loading } from '../_components/ui';

function DecisionDetail({ d, busy, onApprove, onDefer, onDecline }: {
  d: HqDecision; busy: boolean; onApprove: (option?: string) => void; onDefer: () => void; onDecline: () => void;
}) {
  const canDecline = d.source !== 'brief';
  const [option, setOption] = useState<string>('');
  const needsChoice = Boolean(d.options?.length);
  return (
    <div className="hq-panel">
      <div className="hq-meta"><span className="hq-tag">{d.sourceLabel}</span>{d.undoable && <span>Can be undone</span>}</div>
      <h2 style={{ fontSize: '1.05rem' }}>{d.title}</h2>
      <dl className="hq-kv">
        <dt>Requested</dt><dd>{d.request}</dd>
        <dt>Why it matters</dt><dd>{d.why}</dd>
        <dt>Recommended</dt><dd><strong>{d.recommendation}</strong></dd>
        <dt>If you approve</dt><dd>{d.ifApprove}</dd>
        <dt>If you defer</dt><dd>{d.ifDefer}</dd>
        <dt>Do you need to act?</dt><dd>{d.need}</dd>
      </dl>
      {d.options && d.options.length > 0 && (
        <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="hq-muted" style={{ fontSize: '.82rem', fontWeight: 600, padding: 0, marginBottom: 6 }}>Your decision</legend>
          <div className="hq-pkg">
            {d.options.map((o, i) => (
              <label key={o} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                <input type="radio" name={`opt-${d.id}`} value={o} checked={option === o} onChange={() => setOption(o)} id={`opt-${d.id}-${i}`} style={{ marginTop: 4, accentColor: 'var(--hq-accent)' }} />
                <span>{o}</span>
              </label>
            ))}
          </div>
        </fieldset>
      )}
      {d.evidence && d.evidence.length > 0 && (
        <details className="hq-details"><summary>Evidence carried from the item</summary>
          <ul style={{ margin: 0, paddingLeft: '1.1em' }}>{d.evidence.map((e, i) => <li key={i}><strong>{e.label}</strong>{e.detail ? `: ${e.detail}` : ''}</li>)}</ul>
        </details>
      )}
      {d.sourceItem && (
        <div className="hq-meta">
          <Link className="hq-link inline" href={d.sourceItem.hqHref}>Original intelligence item</Link>
          {d.sourceItem.url && <a className="hq-link inline" href={d.sourceItem.url} target="_blank" rel="noopener noreferrer">Original source</a>}
        </div>
      )}
      <div className="hq-acts">
        <button type="button" className="hq-btn primary" onClick={() => onApprove(option)} disabled={busy || (needsChoice && !option)} aria-disabled={busy || (needsChoice && !option)}>
          {busy ? 'Working…' : d.source === 'brief' && d.ifApprove.includes('published') ? 'Approve and publish' : 'Approve'}
        </button>
        <button type="button" className="hq-btn" onClick={onDefer} disabled={busy}>Defer</button>
        {canDecline && <button type="button" className="hq-btn quiet" onClick={onDecline} disabled={busy}>Decline</button>}
        <Link className="hq-link inline" href={d.legacyHref} style={{ alignSelf: 'center' }}>Open in existing workbench</Link>
      </div>
    </div>
  );
}

function Inner() {
  const router = useRouter();
  const params = useSearchParams();
  const { decisions, decisionsLoading, decisionErrors, reloadDecisions, toast } = useHq();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [deferred, setDeferred] = useState<Set<string>>(new Set());
  const [done, setDone] = useState<{ t: string; res: string }[]>([]);
  const [pkgSel, setPkgSel] = useState<Record<string, boolean>>({});

  const visible = useMemo(() => decisions.filter((d) => !deferred.has(d.id)), [decisions, deferred]);
  const { pkg, rest } = useMemo(() => buildPackage(visible), [visible]);
  const selectedId = params.get('id');
  const asked = selectedId ? (selectedId === pkg?.id ? pkg : visible.find((d) => d.id === selectedId) ?? null) : null;
  const first = pkg ?? rest[0] ?? null;
  // Wide screens always show a detail; on phones nothing is "selected" until chosen.
  const detailKey = asked ? asked.id : null;
  const current = asked ?? first;

  function select(id: string | null) {
    router.replace(id ? `/hq/decisions?id=${encodeURIComponent(id)}` : '/hq/decisions', { scroll: false });
  }

  async function settle(d: HqDecision, label: string, res: HqActionResult, verb: string) {
    if (res.ok) {
      setDone((x) => [...x, { t: d.title, res: verb }]);
      toast(`${label}: ${d.title}`, res.undo ? async () => {
        const u = await res.undo!();
        toast(u.ok ? 'Undone.' : `Could not undo. ${u.error ?? ''}`);
        await reloadDecisions();
      } : undefined);
    } else if (res.alreadyDecided) {
      toast('Already decided elsewhere. Nothing was changed.');
    } else {
      toast(res.error ?? 'That did not work. Nothing was changed.');
    }
    await reloadDecisions();
  }

  async function approve(d: HqDecision, option?: string) {
    setBusyId(d.id);
    const res = await approveHqDecision(d, option);
    await settle(d, d.source === 'brief' && d.ifApprove.includes('published') ? 'Approved and published' : 'Approved', res, 'approved');
    setBusyId(null);
    select(null);
  }
  async function decline(d: HqDecision) {
    setBusyId(d.id);
    const res = await declineHqDecision(d);
    await settle(d, 'Declined', res, 'declined');
    setBusyId(null);
    select(null);
  }
  async function defer(d: HqDecision) {
    setBusyId(d.id);
    const res = await deferHqDecision(d);
    setBusyId(null);
    if (res.ok) {
      setDeferred((s) => new Set(s).add(d.id));
      toast(`Deferred: ${d.title}`, () => setDeferred((s) => { const n = new Set(s); n.delete(d.id); return n; }));
      select(null);
    } else toast(res.error ?? 'Could not defer.');
  }

  async function approvePackage() {
    if (!pkg) return;
    const lines = pkg.lines.filter((l) => pkgSel[l.id] !== false);
    if (!lines.length) return;
    setBusyId(pkg.id);
    const undos: (() => Promise<{ ok: boolean; error?: string }>)[] = [];
    let ok = 0; let already = 0; let failed = 0;
    // Each line is approved through its own governed call, one at a time.
    for (const l of lines) {
      const r = await approveHqDecision(l);
      if (r.ok) { ok += 1; if (r.undo) undos.push(r.undo); setDone((x) => [...x, { t: l.title, res: 'approved' }]); }
      else if (r.alreadyDecided) already += 1; else failed += 1;
    }
    const parts = [`Approved ${ok}`, already ? `${already} already decided elsewhere` : '', failed ? `${failed} failed` : ''].filter(Boolean);
    toast(`${parts.join(', ')}. Each is recorded individually.`, undos.length ? async () => {
      for (const u of undos) await u();
      toast('Undone.');
      await reloadDecisions();
    } : undefined);
    await reloadDecisions();
    setBusyId(null);
    setPkgSel({});
    select(null);
  }

  return (
    <>
      {current && <HqContext label={current.title} href="/hq/decisions" />}
      <div className="hq-head">
        <h1>Decisions</h1>
        <p className="hq-lead" role="status">
          {decisionsLoading ? 'Loading…' : visible.length ? `${visible.length} waiting, most important first.` : 'Nothing is waiting for you.'}
        </p>
      </div>
      {decisionErrors.length > 0 && <ErrorLine what={decisionErrors.join(', ')} />}
      {decisionsLoading && <Loading what="decisions" />}

      {!decisionsLoading && (
        <div className="hq-split" data-detail={detailKey ? 'true' : 'false'}>
          <div className="hq-pane-list">
            <div className="hq-sec">
              {pkg && (
                <button type="button" className="hq-row" style={current?.id === pkg.id ? { background: 'var(--hq-accent-soft)' } : undefined} onClick={() => select(pkg.id)}>
                  <span className="t">{pkg.title}</span><span className="s">Build requests</span>
                </button>
              )}
              {rest.map((d) => (
                <button key={d.id} type="button" className="hq-row" style={current?.id === d.id ? { background: 'var(--hq-accent-soft)' } : undefined} onClick={() => select(d.id)}>
                  <span className="t">{d.title}</span><span className="s">{d.sourceLabel}</span>
                </button>
              ))}
              {!visible.length && <div className="hq-quiet">All clear.</div>}
            </div>
          </div>
          <div className="hq-pane-detail">
            <button type="button" className="hq-link inline hq-only-narrow" onClick={() => select(null)}>← All decisions</button>
            {current && current.id === pkg?.id && pkg && (
              <div className="hq-panel">
                <div className="hq-meta"><span className="hq-tag">Build requests</span><span>Each line can be undone</span></div>
                <h2 style={{ fontSize: '1.05rem' }}>{pkg.title}</h2>
                <dl className="hq-kv">
                  <dt>Requested</dt><dd>Approve small, reversible build requests that are not blocked.</dd>
                  <dt>Why it matters</dt><dd>They clear the queue and carry no live risk.</dd>
                  <dt>Do you need to act?</dt><dd>Required by policy, but no judgement call is involved.</dd>
                </dl>
                <ul className="hq-pkg">
                  {pkg.lines.map((l) => (
                    <li key={l.id}>
                      <input type="checkbox" id={`pk-${l.id}`} checked={pkgSel[l.id] !== false} onChange={(e) => setPkgSel((s) => ({ ...s, [l.id]: e.target.checked }))} />
                      <label htmlFor={`pk-${l.id}`}>{l.title} <span className="hq-muted">· {l.why}</span></label>
                    </li>
                  ))}
                </ul>
                <p className="hq-muted" style={{ fontSize: '.82rem' }}>Each line is approved and recorded individually.</p>
                <div className="hq-acts">
                  <button type="button" className="hq-btn primary" onClick={approvePackage} disabled={busyId === pkg.id || pkg.lines.every((l) => pkgSel[l.id] === false)}>
                    {busyId === pkg.id ? 'Working…' : `Approve ${pkg.lines.filter((l) => pkgSel[l.id] !== false).length}`}
                  </button>
                </div>
              </div>
            )}
            {current && current.id !== pkg?.id && 'source' in current && (
              <DecisionDetail key={current.id} d={current as HqDecision} busy={busyId === current.id} onApprove={(o) => approve(current as HqDecision, o)} onDefer={() => defer(current as HqDecision)} onDecline={() => decline(current as HqDecision)} />
            )}
            {!current && <div className="hq-quiet">Select a decision to review it.</div>}
          </div>
        </div>
      )}

      {deferred.size > 0 && <details className="hq-details"><summary>Deferred this session ({deferred.size})</summary>
        {[...deferred].map((id) => <div className="hq-plain" key={id}>{decisions.find((d) => d.id === id)?.title ?? id}{' '}
          <button type="button" className="hq-link inline" onClick={() => setDeferred((s) => { const n = new Set(s); n.delete(id); return n; })}>Reopen</button></div>)}
      </details>}
      {done.length > 0 && <details className="hq-details"><summary>Decided this session ({done.length})</summary>
        {done.map((x, i) => <div className="hq-plain" key={i}>{x.t} <span className="hq-muted">{x.res}</span></div>)}
      </details>}
    </>
  );
}

export default function HqDecisions() {
  return <Suspense fallback={<Loading what="decisions" />}><Inner /></Suspense>;
}
