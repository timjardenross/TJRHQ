'use client';

// Situation (MSN-0364) — replaces Signal Snapshot's 3 raw source cards
// with domain-grouped read-only awareness (Personal/Environment/Systems),
// routing to authoritative workbenches rather than duplicating them. Only
// renders a domain when it has material content — no fixed card count.

import Link from 'next/link';
import { WorkbenchPanel } from '@/components/WorkbenchPanel';
import { stateToneClasses, capacityStateToTone } from '@/lib/departments';
import { CAPACITY_STATE_LABEL, RISK_STATE_TONE } from '@/lib/captainsChairData';
import type { StateTone } from '@/lib/types';

interface SituationDomainProps {
  title: string;
  lines: string[];
  tone: StateTone;
  href: string;
  linkLabel: string;
}

function SituationDomain({ title, lines, tone, href, linkLabel }: SituationDomainProps) {
  const c = stateToneClasses(tone);
  return (
    <div className={`rounded-lg border ${c.border} ${c.bg} p-3`}>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-wb-ink2">{title}</p>
      {lines.map((line, i) => (
        <p key={i} className={`mt-0.5 text-sm ${i === 0 ? `font-semibold ${c.text}` : 'text-wb-ink/80'}`}>{line}</p>
      ))}
      <Link href={href} className="mt-2 inline-block text-[11px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
        {linkLabel} →
      </Link>
    </div>
  );
}

export interface SituationInputs {
  capacityState: string | null;
  postureMessage: string | null;
  topHealthSignal: { title: string; severity: string } | null;
  emergencyCount: number;
  emergencyWorstHeadline: string | null;
  emergencyTone: StateTone;
  /** HQ V1 Integration QA §24: 'stale' means the last successful collection
   *  cycle is older than the Hub's own staleness threshold — surfaced so
   *  "Clear" is never confused with "we stopped checking a while ago." */
  emergencyFreshness: 'fresh' | 'stale';
  topOsintSignal: { title: string; risk_rating: string } | null;
  agentFailedCount: number;
  agentWorstLabel: string | null;
}

export function Situation({ data, loading }: { data: SituationInputs; loading: boolean }) {
  if (loading) {
    return (
      <WorkbenchPanel title="Situation">
        <p className="text-sm text-wb-ink2 animate-pulse">Loading…</p>
      </WorkbenchPanel>
    );
  }

  const personalLines = [
    data.capacityState ? (CAPACITY_STATE_LABEL[data.capacityState] ?? data.capacityState) : 'No data',
    ...(data.postureMessage ? [data.postureMessage] : []),
    ...(data.topHealthSignal ? [`${data.topHealthSignal.title} (${data.topHealthSignal.severity})`] : []),
  ];

  const environmentLines = data.emergencyCount > 0
    ? [`${data.emergencyCount} active alert${data.emergencyCount === 1 ? '' : 's'}`, ...(data.emergencyWorstHeadline ? [data.emergencyWorstHeadline] : [])]
    : ['Clear — no relevant local alerts'];
  if (data.emergencyFreshness === 'stale') {
    environmentLines.push('Last check is overdue — may not reflect the latest alerts');
  }

  const systemsLines = data.agentFailedCount > 0
    ? [`${data.agentFailedCount} degraded`, ...(data.agentWorstLabel ? [data.agentWorstLabel] : [])]
    : data.topOsintSignal
      ? [data.topOsintSignal.risk_rating, data.topOsintSignal.title]
      : ['Nominal — no significant degradation'];

  const systemsTone: StateTone = data.agentFailedCount > 0
    ? 'crit'
    : data.topOsintSignal
      ? (RISK_STATE_TONE[data.topOsintSignal.risk_rating] ?? 'unknown')
      : 'ok';

  return (
    <WorkbenchPanel title="Situation" eyebrow="Domain awareness, not a dashboard">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <SituationDomain
          title="Personal"
          lines={personalLines}
          tone={capacityStateToTone(data.capacityState)}
          href="/human-systems-workbench"
          linkLabel="Human Systems"
        />
        <SituationDomain
          title="Environment"
          lines={environmentLines}
          tone={data.emergencyTone}
          href="/emergency-alert-hub-workbench"
          linkLabel="Alerts"
        />
        <SituationDomain
          title="Systems"
          lines={systemsLines}
          tone={systemsTone}
          href={data.agentFailedCount > 0 ? '/agent-status-workbench' : '/intelligence-workbench'}
          linkLabel={data.agentFailedCount > 0 ? 'Agent Status' : 'Technical OSINT'}
        />
      </div>
      {data.topHealthSignal && data.topHealthSignal.severity !== 'ok' && (
        <p className="mt-2 text-[11px] text-wb-ink2">
          <Link href="/health-osint" className="text-wb-sage-deep hover:underline">Health OSINT →</Link>
        </p>
      )}
    </WorkbenchPanel>
  );
}
