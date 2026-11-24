'use client';

// HQ Home. Part of the parallel HQ workbench: gated by HQ_WORKBENCH_ENABLED in hq/layout.tsx
// (default off) and deliberately NOT listed in LIVE_WORKBENCHES, so the existing hub, switcher and
// generated docs are unchanged. Capability status: docs/HQ-CAPABILITY-CHECKLIST.md.

import Link from 'next/link';
import { useHq } from '@/lib/hq/HqProvider';
import { useHqNeedsYou } from '@/lib/hq/home';
import { getJson, loadWork } from '@/lib/hq/data';
import { useAsync } from '@/lib/hq/useAsync';
import { ErrorLine, Loading, RiskPill } from './_components/ui';
import { normaliseRisk } from '@/lib/hq/vocab';
import { toHqHref } from '@/lib/hq/home';
import type { HqWeeklyReview } from '@/lib/hq/weeklyReview';

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}

interface BriefHead { brief_id: string; generated_at: string; executive_snapshot: string | null; bottom_line?: string | null; overall_risk: string | null }

export default function HqHome() {
  const { decisions, decisionsLoading, decisionErrors, hqStatus, materialProblem } = useHq();
  const { items: needsYou, loading: needsLoading, errors: needsErrors } = useHqNeedsYou(hqStatus);
  const brief = useAsync(async () => {
    const r = await getJson<{ briefs: BriefHead[] }>('/api/briefs');
    if (!r.ok) throw new Error(r.error);
    return r.data.briefs[0] ?? null;
  });
  const work = useAsync(loadWork);
  const week = useAsync(async () => {
    const r = await getJson<HqWeeklyReview>('/api/hq/weekly-review');
    if (!r.ok) throw new Error(r.error);
    return r.data;
  });

  const attentionCount = needsYou.length;
  const waiting = decisions.length;
  const loadingAll = needsLoading || decisionsLoading;
  const summary = loadingAll
    ? 'Checking what needs you…'
    : attentionCount || waiting
      ? `${attentionCount} ${attentionCount === 1 ? 'thing needs' : 'things need'} attention and ${waiting} ${waiting === 1 ? 'decision is' : 'decisions are'} waiting.`
      : 'Nothing needs you right now.';

  const review = work.data?.items.filter((w) => w.kind !== 'research' && w.state === 'review').length ?? 0;
  const progress = work.data?.items.filter((w) => w.kind !== 'research' && w.state === 'progress').length ?? 0;
  const researchPending = work.data?.items.filter((w) => w.kind === 'research' && w.rawStatus === 'Idea').length ?? 0;
  const blockedCount = work.data?.items.filter((w) => w.kind !== 'research' && w.state === 'attention').length ?? 0;

  const snapshot = brief.data?.bottom_line ?? brief.data?.executive_snapshot ?? null;

  return (
    <>
      <div className="hq-head">
        <h1>{greeting()}</h1>
        <p className="hq-lead" role="status">{summary}</p>
      </div>

      <section className="hq-sec" aria-labelledby="h-attn">
        <div className="hq-sech"><h2 id="h-attn">Needs your attention</h2></div>
        {needsLoading && <Loading what="attention items" />}
        {!needsLoading && needsYou.length === 0 && !materialProblem && (
          <div className="hq-quiet">Nothing is waiting on you. Intelligence and work are on track.</div>
        )}
        {needsYou.map((i) => (
          <Link key={i.id} href={i.hqHref} className="hq-row">
            <span className="t">{i.title}</span>
            <span className="s">{i.detail}{i.external ? ' Opens the existing workbench.' : ''}</span>
            <span className="r"><span className="hq-pill info">{i.actionLabel}</span></span>
          </Link>
        ))}
        {needsErrors.length > 0 && <ErrorLine what={needsErrors.join(', ')} />}
      </section>

      <section className="hq-sec" aria-labelledby="h-dec">
        <div className="hq-sech"><h2 id="h-dec">Decisions waiting</h2><Link href="/hq/decisions">Review all</Link></div>
        {decisionsLoading && <Loading what="decisions" />}
        {!decisionsLoading && waiting === 0 && <div className="hq-quiet">No decisions waiting.</div>}
        {decisions.slice(0, 2).map((d) => (
          <Link key={d.id} href={`/hq/decisions?id=${encodeURIComponent(d.id)}`} className="hq-row">
            <span className="t">{d.title}</span><span className="s">{d.recommendation}</span>
            <span className="r"><span className="hq-pill info">{d.sourceLabel}</span></span>
          </Link>
        ))}
        {waiting > 2 && <div className="hq-quiet">and {waiting - 2} more</div>}
        {decisionErrors.length > 0 && <ErrorLine what={decisionErrors.join(', ')} />}
      </section>

      <section className="hq-sec" aria-labelledby="h-know">
        <div className="hq-sech"><h2 id="h-know">What I know</h2><Link href="/hq/intelligence">Open Intelligence</Link></div>
        {brief.loading && <Loading what="the latest brief" />}
        {brief.error && <ErrorLine what="the latest brief" />}
        {!brief.loading && !brief.error && !brief.data && <div className="hq-quiet">No brief has been generated yet.</div>}
        {brief.data && (
          <div className="hq-plain">
            <div className="hq-meta" style={{ marginBottom: 4 }}>
              <span>Latest brief {brief.data.brief_id}</span>
              <RiskPill risk={normaliseRisk(brief.data.overall_risk)} />
            </div>
            {snapshot ?? 'No summary was recorded for this brief.'}
            {' '}<Link className="hq-link inline" href={`/hq/intelligence/brief/${encodeURIComponent(brief.data.brief_id)}`}>Read the brief</Link>
          </div>
        )}
      </section>

      <section className="hq-sec" aria-labelledby="h-week">
        <div className="hq-sech"><h2 id="h-week">This week</h2><Link href="/weekly-review">Open Weekly Review</Link></div>
        {week.loading && <Loading what="the weekly review" />}
        {week.error && <ErrorLine what="the weekly review" />}
        {week.data && (
          <>
            <div className="hq-plain">
              {week.data.lastCompletedAt
                ? `Last weekly review ${week.data.reviewDebtDays ?? 0} ${week.data.reviewDebtDays === 1 ? 'day' : 'days'} ago.`
                : 'No weekly review has been completed yet.'}
              {' '}{week.data.looks} {week.data.looks === 1 ? 'item' : 'items'} to look at{week.data.urgent ? `, ${week.data.urgent} urgent` : ''}.
            </div>
            {week.data.items.slice(0, 4).map((it, i) => {
              const m = it.href ? toHqHref(it.href) : null;
              return m ? (
                <Link key={i} href={m.href} className="hq-row"><span className="t">{it.title}</span><span className="s">{it.section}{m.external ? ' · opens the existing workbench' : ''}</span><span className="r"><span className={`hq-pill ${it.tone === 'crit' ? 'red' : 'amber'}`}>{it.tone === 'crit' ? 'Urgent' : 'Look'}</span></span></Link>
              ) : (
                <div key={i} className="hq-plain">{it.title} <span className="hq-muted">· {it.section}</span></div>
              );
            })}
            <div className="hq-quiet">Completing the review stays in the Weekly Review workbench. Personal health and personal tasks are not included here.</div>
          </>
        )}
      </section>

      <section className="hq-sec" aria-labelledby="h-work">
        <div className="hq-sech"><h2 id="h-work">Happening on your behalf</h2><Link href="/hq/work">Open Work</Link></div>
        {work.loading && <Loading what="work" />}
        {work.data && (
          <div className="hq-plain">
            {review} {review === 1 ? 'item is' : 'items are'} ready for you to review. {progress} {progress === 1 ? 'is' : 'are'} in progress.{blockedCount > 0 ? ` ${blockedCount} ${blockedCount === 1 ? 'is' : 'are'} blocked.` : ''}{researchPending > 0 ? ` ${researchPending} research ${researchPending === 1 ? 'item is' : 'items are'} requested and not running.` : ''}
          </div>
        )}
        {work.error && <ErrorLine what="work" />}
        {work.data && work.data.unavailable.length > 0 && <ErrorLine what={work.data.unavailable.join(', ')} />}
      </section>

      <div className="hq-quiet">
        {materialProblem ? 'A system problem needs attention. ' : 'Everything else is quiet. Routine jobs are not listed here. '}
        <Link href="/hq/system" className="hq-link inline">See system</Link>
      </div>
    </>
  );
}
