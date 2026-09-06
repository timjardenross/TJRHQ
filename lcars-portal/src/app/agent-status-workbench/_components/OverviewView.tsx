'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card } from '@/components/ui';
import { stateToneClasses } from '@/lib/departments';
import { stageToneGlyph } from './shared';
import type { StageTone } from './shared';

interface StageResult {
  key: string;
  label: string;
  tone: StageTone;
  detail: string;
}

interface AttentionCard {
  kind: 'job' | 'source';
  pipeline?: 'technical' | 'health';
  title: string;
  detail: string;
  href: string;
}

interface OverviewData {
  fetchedAt: string;
  allClear: boolean;
  attention: AttentionCard[];
  pipelines: {
    technical: { stages: StageResult[]; day: string | null };
    health: { stages: StageResult[]; day: string | null };
  };
  sourcesSummary: {
    technical: { healthy: number; degraded: number; failing: number };
    health: { healthy: number; delayed: number; failing: number };
  };
  jobsSummary: { scheduled: number; healthy: number; attention: number };
}

function StageRow({ stage }: { stage: StageResult }) {
  const classes = stateToneClasses(stage.tone);
  return (
    <li className="flex items-start gap-2 py-1.5" title={stage.detail}>
      <span className={`mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${classes.bg} ${classes.on}`} aria-hidden>
        {stageToneGlyph(stage.tone)}
      </span>
      <div className="min-w-0">
        <p className="text-[12px] font-medium text-wb-ink">
          {stage.label}
          <span className="sr-only"> — {stage.tone === 'ok' ? 'healthy' : stage.tone === 'warn' ? 'needs review' : stage.tone === 'crit' ? 'unhealthy' : 'unknown'}</span>
        </p>
        <p className="truncate text-[11px] text-wb-ink2">{stage.detail}</p>
      </div>
    </li>
  );
}

export function OverviewView({ onNavigate }: { onNavigate: (tab: 'sources' | 'pipeline' | 'jobs') => void }) {
  const [data, setData] = useState<OverviewData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch('/api/agent-status-workbench/overview', { cache: 'no-store' });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body?.error ?? `HTTP ${res.status}`);
        }
        const json = await res.json();
        if (!cancelled) setData(json);
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : 'Failed to load system health');
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  if (isLoading) {
    return <Card><p className="text-[13px] italic text-wb-ink2">Loading system health…</p></Card>;
  }

  if (loadError || !data) {
    return (
      <Card>
        <div className="rounded-md border border-wb-crit/40 bg-wb-crit/10 px-4 py-3">
          <p className="text-[13px] font-semibold text-wb-crit-on">System health unavailable</p>
          <p className="mt-1 text-[12px] text-wb-ink2">{loadError ?? 'No data returned.'}</p>
        </div>
      </Card>
    );
  }

  const actionableCount = data.attention.length;

  return (
    <div className="flex flex-col gap-4">
      {/* Headline verdict */}
      <Card>
        {data.allClear ? (
          <p className="text-[15px] font-semibold text-state-ok-on">
            ✓ HQ background systems are healthy
          </p>
        ) : (
          <p className="text-[15px] font-semibold text-state-warn-on">
            {actionableCount} minor issue{actionableCount !== 1 ? 's' : ''} need review
          </p>
        )}
        <p className="mt-1 text-[11px] text-wb-ink2">
          Updated moments ago · covers Technical OSINT + Health OSINT ingestion, all scheduled platform jobs, and every governed source.
        </p>
      </Card>

      {/* Needs Attention */}
      {data.attention.length > 0 && (
        <Card>
          <h2 className="mb-3 font-serif text-lg text-wb-ink">Needs Attention</h2>
          <ul className="flex flex-col gap-2">
            {data.attention.slice(0, 8).map((card, i) => (
              <li key={i} className="rounded-md border border-wb-line bg-wb-bg p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[13px] font-semibold text-wb-ink">{card.title}</p>
                    <p className="mt-0.5 text-[12px] text-wb-ink2">{card.detail}</p>
                  </div>
                  <Link href={card.href} className="shrink-0 text-[12px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep">
                    Investigate →
                  </Link>
                </div>
              </li>
            ))}
          </ul>
          {data.attention.length > 8 && (
            <p className="mt-2 text-[11px] text-wb-ink2">+{data.attention.length - 8} more — see Source Health / Jobs tabs.</p>
          )}
        </Card>
      )}

      {/* Pipeline health */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-serif text-lg text-wb-ink">Technical OSINT Pipeline</h2>
            <Link href="/intelligence-workbench" className="text-[11px] text-wb-sage-deep hover:underline">
              Open Technical OSINT →
            </Link>
          </div>
          <ul>
            {data.pipelines.technical.stages.map((s) => <StageRow key={s.key} stage={s} />)}
          </ul>
          <button type="button" onClick={() => onNavigate('pipeline')} className="mt-2 text-[12px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep">
            View pipeline health details →
          </button>
        </Card>
        <Card>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-serif text-lg text-wb-ink">Health OSINT Pipeline</h2>
            <Link href="/health-osint" className="text-[11px] text-wb-sage-deep hover:underline">
              Open Health OSINT →
            </Link>
          </div>
          <ul>
            {data.pipelines.health.stages.map((s) => <StageRow key={s.key} stage={s} />)}
          </ul>
          <button type="button" onClick={() => onNavigate('pipeline')} className="mt-2 text-[12px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep">
            View pipeline health details →
          </button>
        </Card>
      </div>

      {/* Sources + Jobs summaries */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <h2 className="mb-2 font-serif text-lg text-wb-ink">Sources</h2>
          <p className="text-[13px] text-wb-ink2">
            Technical: {data.sourcesSummary.technical.healthy} healthy, {data.sourcesSummary.technical.degraded} degraded, {data.sourcesSummary.technical.failing} failing
          </p>
          <p className="text-[13px] text-wb-ink2">
            Health: {data.sourcesSummary.health.healthy} healthy, {data.sourcesSummary.health.failing} failing
          </p>
          <button type="button" onClick={() => onNavigate('sources')} className="mt-2 text-[12px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep">
            View source health →
          </button>
        </Card>
        <Card>
          <h2 className="mb-2 font-serif text-lg text-wb-ink">Jobs</h2>
          <p className="text-[13px] text-wb-ink2">
            {data.jobsSummary.scheduled} scheduled, {data.jobsSummary.healthy} healthy, {data.jobsSummary.attention} require attention
          </p>
          <button type="button" onClick={() => onNavigate('jobs')} className="mt-2 text-[12px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep">
            View jobs →
          </button>
        </Card>
      </div>
    </div>
  );
}
