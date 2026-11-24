'use client';

import Link from 'next/link';
import { HqContext } from '@/lib/hq/HqProvider';
import { loadWork } from '@/lib/hq/data';
import { useAsync } from '@/lib/hq/useAsync';
import { ErrorLine, Loading, Notice } from '../../_components/ui';

const STATE_LABEL = { review: 'Ready for you', attention: 'Needs attention', progress: 'In progress', done: 'Completed' } as const;

export default function HqWorkItemPage({ params }: { params: { id: string } }) {
  const id = decodeURIComponent(params.id);
  const work = useAsync(loadWork);
  const w = work.data?.items.find((i) => i.id === id) ?? null;
  return (
    <>
      {w && <HqContext label={w.title} href={`/hq/work/${encodeURIComponent(w.id)}`} />}
      <Link href="/hq/work" className="hq-back">← Work</Link>
      {work.loading && <Loading what="this item" />}
      {work.error && <ErrorLine what="this item" detail={work.error} />}
      {!work.loading && !work.error && !w && <div className="hq-notice" role="status">This item is no longer in the active list.</div>}
      {w && (
        <>
          <div className="hq-head">
            <div className="hq-meta"><span className="hq-tag">{STATE_LABEL[w.state]}</span>{w.updatedAt && <span>Updated {new Date(w.updatedAt).toLocaleDateString()}</span>}</div>
            <h1>{w.title}</h1>
            <p className="hq-lead">{w.line}</p>
          </div>
          <section className="hq-sec" aria-labelledby="w-out">
            <div className="hq-sech"><h2 id="w-out">Outputs</h2></div>
            {w.outputs.length === 0 && <div className="hq-quiet">No outputs are recorded for this item. Missions do not track deliverables yet.</div>}
            {w.outputs.map((o) => (
              <div className="hq-plain" key={o}>
                {/^https?:\/\//.test(o) ? <a className="hq-link inline" href={o} target="_blank" rel="noopener noreferrer">{o}</a> : o}
              </div>
            ))}
          </section>
          <Notice>Status changes and approvals stay in the existing workbench in this version, so there is one place that records them.</Notice>
          <div className="hq-acts"><Link className="hq-btn" href={w.legacyHref}>Open in existing workbench</Link></div>
        </>
      )}
    </>
  );
}
