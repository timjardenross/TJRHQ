'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useHq } from '@/lib/hq/HqProvider';
import { loadWork } from '@/lib/hq/data';
import { loadActivity } from '@/lib/hq/activity';
import { inboxDismiss, inboxMakeMission, inboxMarkReviewed, loadInbox, type HqInboxItem } from '@/lib/hq/inbox';
import { RESEARCH_NO_RUNNER, researchStatus } from '@/lib/hq/research';
import { useAsync } from '@/lib/hq/useAsync';
import type { HqWorkItem, HqWorkState } from '@/lib/hq/model';
import { ErrorLine, Loading, Notice } from '../_components/ui';

const GROUPS: { state: HqWorkState; label: string }[] = [
  { state: 'review', label: 'Ready for you' },
  { state: 'attention', label: 'Needs attention' },
  { state: 'progress', label: 'In progress' },
  { state: 'done', label: 'Completed this week' },
];

export default function HqWork() {
  const { toast } = useHq();
  const work = useAsync(loadWork);
  const inbox = useAsync(loadInbox);
  const activity = useAsync(() => loadActivity(14));
  const [busy, setBusy] = useState<string | null>(null);

  const all = work.data?.items ?? [];
  const research = all.filter((w) => w.kind === 'research');
  const items = all.filter((w) => w.kind !== 'research');

  const row = (w: HqWorkItem) => (
    <Link key={w.id} href={`/hq/work/${encodeURIComponent(w.id)}`} className="hq-row">
      <span className="t">{w.title}</span><span className="s">{w.line}</span>
      <span className="r">
        {w.outputs.length > 0 && <span className="hq-pill info">{w.outputs.length} {w.outputs.length === 1 ? 'output' : 'outputs'}</span>}
        {w.state === 'review' && <span className="hq-pill green">Review</span>}
        {w.state === 'attention' && <span className="hq-pill amber">Blocked</span>}
      </span>
    </Link>
  );

  async function act(item: HqInboxItem, kind: 'mission' | 'reviewed' | 'dismiss') {
    setBusy(item.id);
    const res = kind === 'mission' ? await inboxMakeMission(item.id) : kind === 'reviewed' ? await inboxMarkReviewed(item.id) : await inboxDismiss(item.id);
    setBusy(null);
    if (res.ok) {
      toast(kind === 'mission' ? 'Mission candidate created. It needs your review in Missions.' : kind === 'reviewed' ? 'Marked reviewed.' : 'Dismissed.');
      await Promise.all([inbox.reload(), work.reload()]);
    } else toast('error' in res && res.error ? res.error : 'That did not work. Nothing was changed.');
  }

  return (
    <>
      <div className="hq-head">
        <h1>Work</h1>
        <p className="hq-lead">Missions, research, hand-offs, captured items and recent activity in one place.</p>
      </div>
      {work.loading && <Loading what="work" />}
      {work.error && <ErrorLine what="work" detail={work.error} />}
      {work.data && work.data.unavailable.length > 0 && <ErrorLine what={work.data.unavailable.join(', ')} />}
      {work.data && all.length === 0 && <div className="hq-quiet">No active work.</div>}

      {research.length > 0 && (
        <section className="hq-sec" aria-labelledby="w-research">
          <div className="hq-sech"><h2 id="w-research">Research ({research.length})</h2></div>
          <Notice>{RESEARCH_NO_RUNNER}</Notice>
          {research.map((r) => {
            const rs = researchStatus(r.rawStatus ?? 'Idea');
            return (
              <Link key={r.id} href={`/hq/work/${encodeURIComponent(r.id)}`} className="hq-row">
                <span className="t">{r.title}</span>
                <span className="s">{r.updatedAt ? `Updated ${new Date(r.updatedAt).toLocaleDateString()}` : 'Research item'}</span>
                <span className="r"><span className={`hq-pill ${rs.tone === 'amber' ? 'amber' : rs.tone === 'green' ? 'green' : 'info'}`}>{rs.label}</span></span>
              </Link>
            );
          })}
        </section>
      )}

      {GROUPS.map((g) => {
        const rows = items.filter((w) => w.state === g.state);
        if (!rows.length) return null;
        return (
          <section className="hq-sec" key={g.state} aria-labelledby={`w-${g.state}`}>
            <div className="hq-sech"><h2 id={`w-${g.state}`}>{g.label} ({rows.length})</h2></div>
            {rows.map(row)}
          </section>
        );
      })}

      <section className="hq-sec" aria-labelledby="w-inbox">
        <div className="hq-sech"><h2 id="w-inbox">Captured, needs sorting{inbox.data ? ` (${inbox.data.length})` : ''}</h2></div>
        {inbox.loading && <Loading what="captures" />}
        {inbox.error && <ErrorLine what="captures" detail={inbox.error} />}
        {inbox.data && inbox.data.length === 0 && <div className="hq-quiet">Nothing is waiting to be sorted.</div>}
        {inbox.data?.map((c) => (
          <div className="hq-plain" key={c.id}>
            <div style={{ fontWeight: 600 }}>{c.title}</div>
            <div className="hq-meta" style={{ margin: '2px 0 6px' }}>Captured {new Date(c.capturedAt).toLocaleDateString()} · {c.importance} importance</div>
            <div className="hq-acts">
              <button type="button" className="hq-btn small primary" disabled={busy === c.id} onClick={() => act(c, 'mission')}>Make a mission</button>
              <button type="button" className="hq-btn small" disabled={busy === c.id} onClick={() => act(c, 'reviewed')}>Mark reviewed</button>
              <button type="button" className="hq-btn small quiet" disabled={busy === c.id} onClick={() => act(c, 'dismiss')}>Dismiss</button>
            </div>
          </div>
        ))}
        <div className="hq-quiet">Classification, routing and AI enrichment stay in the <Link href="/capture-workbench" className="hq-link inline">Capture workbench</Link>.</div>
      </section>

      <details className="hq-details">
        <summary>Recent activity{activity.data ? ` (${activity.data.items.length})` : ''}</summary>
        {activity.loading && <Loading what="activity" />}
        {activity.data && activity.data.unavailable.length > 0 && <ErrorLine what={activity.data.unavailable.join(', ')} />}
        {activity.data?.items.map((a) => (
          <div className="hq-plain" key={a.id}>
            {a.title}{a.detail ? ` · ${a.detail}` : ''} <span className="hq-muted">· {new Date(a.at).toLocaleString()}</span>
            {a.needsAction && <> <span className="hq-pill amber">Needs a look</span></>}
          </div>
        ))}
        {activity.data && activity.data.items.length === 0 && <div className="hq-quiet">No activity in the last 14 days.</div>}
        <div className="hq-quiet">Mission changes and execution events only. Personal check-ins and journal entries are not shown in HQ.</div>
      </details>
    </>
  );
}
