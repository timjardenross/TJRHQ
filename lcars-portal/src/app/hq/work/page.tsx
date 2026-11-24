'use client';

import Link from 'next/link';
import { loadWork } from '@/lib/hq/data';
import { useAsync } from '@/lib/hq/useAsync';
import { RESEARCH_NOT_RUNNING, loadResearchRequests } from '@/lib/hq/research';
import type { HqWorkItem, HqWorkState } from '@/lib/hq/model';
import { ErrorLine, Loading } from '../_components/ui';

const GROUPS: { state: HqWorkState; label: string }[] = [
  { state: 'review', label: 'Ready for you' },
  { state: 'attention', label: 'Needs attention' },
  { state: 'progress', label: 'In progress' },
  { state: 'done', label: 'Completed this week' },
];

export default function HqWork() {
  const work = useAsync(loadWork);
  const research = useAsync(loadResearchRequests);
  const items = work.data?.items ?? [];
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
  return (
    <>
      <div className="hq-head">
        <h1>Work</h1>
        <p className="hq-lead">Missions and engineering hand-offs: what is ready, blocked, and moving.</p>
      </div>
      {work.loading && <Loading what="work" />}
      {work.error && <ErrorLine what="work" detail={work.error} />}
      {work.data && work.data.unavailable.length > 0 && <ErrorLine what={work.data.unavailable.join(', ')} />}
      {work.data && items.length === 0 && <div className="hq-quiet">No active work.</div>}
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
      {research.data && research.data.length > 0 && (
        <section className="hq-sec" aria-labelledby="w-research">
          <div className="hq-sech"><h2 id="w-research">Research requests, not running ({research.data.length})</h2></div>
          <div className="hq-notice" role="note">{RESEARCH_NOT_RUNNING}</div>
          {research.data.map((r) => (
            <Link key={r.id} href={r.legacyHref} className="hq-row">
              <span className="t">{r.title}</span>
              <span className="s">Captured {new Date(r.requestedAt).toLocaleDateString()}. Waiting for review in Capture.</span>
              <span className="r"><span className="hq-pill info">Requested, not running</span></span>
            </Link>
          ))}
        </section>
      )}
      <div className="hq-quiet">Individual agent steps and build notifications are not listed here. Status changes are made in Missions for now.</div>
    </>
  );
}
