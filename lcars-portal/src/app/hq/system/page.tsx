'use client';

import Link from 'next/link';
import { useHq } from '@/lib/hq/HqProvider';
import { getJson } from '@/lib/hq/data';
import { useAsync } from '@/lib/hq/useAsync';
import { ErrorLine, Loading } from '../_components/ui';

interface Overview {
  posture: 'normal' | 'degraded' | 'attention' | 'unknown';
  headline: string;
  narrative: { impact: string | null; next: string | null; actionRequired: boolean; actionNote: string };
  materialDegradations: string[];
  attentionItems: { title: string; detail: string }[];
  jobsSummary: { scheduled: number; healthy: number; attention: number };
}

const SETTINGS = [
  ['Appearance', '/settings/appearance'], ['AI and automation', '/settings/ai-automation'], ['Connections', '/settings/connections'],
  ['Data and privacy', '/settings/data-privacy'], ['Follow-through', '/settings/follow-through'], ['HQ behaviour', '/settings/hq-behaviour'], ['Intelligence', '/settings/intelligence'],
] as const;

export default function HqSystem() {
  const { materialProblem } = useHq();
  const ov = useAsync(async () => {
    const r = await getJson<Overview>('/api/agent-status-workbench/overview');
    if (!r.ok) throw new Error(r.error);
    return r.data;
  });
  const o = ov.data;
  return (
    <>
      <div className="hq-head">
        <h1>System and settings</h1>
        <p className="hq-lead">Technical health and configuration. Only material problems appear on Home.</p>
      </div>
      {ov.loading && <Loading what="system health" />}
      {ov.error && <ErrorLine what="system health" detail={ov.error} />}
      {o && (
        <>
          <section className="hq-sec" aria-labelledby="s-act">
            <div className="hq-sech"><h2 id="s-act">Needs action</h2></div>
            {o.posture === 'normal' && <div className="hq-quiet">Nothing needs action. {o.headline}</div>}
            {o.posture !== 'normal' && (
              <div className="hq-panel">
                <strong>{o.headline}</strong>
                <dl className="hq-kv">
                  {o.narrative.impact && <><dt>Affects</dt><dd>{o.narrative.impact}</dd></>}
                  {o.materialDegradations.length > 0 && <><dt>Capabilities</dt><dd>{o.materialDegradations.join(', ')}</dd></>}
                  {o.attentionItems.map((a) => <div key={a.title} style={{ display: 'contents' }}><dt>{a.title}</dt><dd>{a.detail}</dd></div>)}
                  {o.narrative.next && <><dt>Next</dt><dd>{o.narrative.next}</dd></>}
                </dl>
                <div className="hq-acts"><Link className="hq-btn primary" href="/agent-status-workbench">Open HQ Status to investigate</Link></div>
                <p className="hq-muted" style={{ fontSize: '.82rem' }}>Retrying and repairs are done in HQ Status. HQ does not run them itself.</p>
              </div>
            )}
          </section>
          <section className="hq-sec" aria-labelledby="s-rt">
            <div className="hq-sech"><h2 id="s-rt">Routine health</h2></div>
            <div className="hq-plain">Jobs: {o.jobsSummary.healthy} of {o.jobsSummary.scheduled} healthy{o.jobsSummary.attention ? `, ${o.jobsSummary.attention} need a look` : ''}.</div>
            <details className="hq-details"><summary>Technical detail</summary>
              <p className="hq-muted">Job history, sources, pipeline quality and model telemetry are in the existing screens.</p>
              <div className="hq-acts"><Link className="hq-link inline" href="/agent-status-workbench">HQ Status</Link><Link className="hq-link inline" href="/model-crew">Model Crew</Link></div>
            </details>
          </section>
        </>
      )}
      {!o && !ov.loading && materialProblem && <div className="hq-notice" role="alert">A problem needs attention. <Link href="/agent-status-workbench">Open HQ Status</Link>.</div>}
      <section className="hq-sec" aria-labelledby="s-set">
        <div className="hq-sech"><h2 id="s-set">Settings</h2></div>
        {SETTINGS.map(([label, href]) => <Link key={href} className="hq-row" href={href}><span className="t">{label}</span><span className="s">Opens the existing settings page.</span></Link>)}
      </section>
    </>
  );
}
