'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card } from '@/components/ui';
import { stateToneClasses } from '@/lib/departments';
import { stageToneGlyph } from './shared';
import type { StageTone } from './shared';

interface StageResult { key: string; label: string; tone: StageTone; detail: string }

interface OverviewData {
  pipelines: {
    technical: { stages: StageResult[]; day: string | null };
    health: { stages: StageResult[]; day: string | null };
  };
}

interface QualityData {
  technical: Array<Record<string, any>>;
  health: Array<Record<string, any>>;
  note: string;
}

function StageChecklist({ stages }: { stages: StageResult[] }) {
  return (
    <ul className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
      {stages.map((s) => {
        const classes = stateToneClasses(s.tone);
        return (
          <li key={s.key} className="flex items-start gap-2" title={s.detail}>
            <span className={`mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${classes.bg} ${classes.on}`} aria-hidden>
              {stageToneGlyph(s.tone)}
            </span>
            <div className="min-w-0">
              <p className="text-[12px] font-medium text-wb-ink">{s.label}</p>
              <p className="truncate text-[11px] text-wb-ink2">{s.detail}</p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

const TECH_COLS: Array<[string, string]> = [
  ['discovered', 'Discovered'], ['suppressed', 'Hard-filtered'], ['deduplicated', 'Deduplicated'],
  ['relevant', 'Relevant'], ['watch', 'Watching'], ['brief', 'Briefed'], ['escalate', 'Escalated'], ['human_overrides', 'Human overrides'],
];
const HEALTH_COLS: Array<[string, string]> = [
  ['discovered', 'Discovered'], ['not_relevant', 'Irrelevant'], ['deduplicated', 'Duplicate'],
  ['evidence_contribution_scored', 'Evidence contributors'], ['pending_curation', 'Curation required'],
  ['safety_flagged', 'Safety escalations'], ['human_overrides', 'Human overrides'],
];

function QualityTable({ rows, cols }: { rows: Array<Record<string, any>>; cols: Array<[string, string]> }) {
  if (rows.length === 0) {
    return <p className="text-[12px] italic text-wb-ink2">No daily rows yet.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-wb-line">
            <th className="pb-2 pr-3 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Day</th>
            {cols.map(([key, label]) => (
              <th key={key} className="pb-2 pr-3 text-right text-[10px] uppercase tracking-wider text-wb-ink2">{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.day} className="border-b border-wb-line last:border-0">
              <td className="py-2 pr-3 text-[12px] text-wb-ink">{new Date(r.day).toLocaleDateString('en-AU', { day: '2-digit', month: 'short' })}</td>
              {cols.map(([key]) => (
                <td key={key} className="py-2 pr-3 text-right text-[12px] tabular-nums text-wb-ink2">{r[key] ?? 0}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PipelineHealthView() {
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [quality, setQuality] = useState<QualityData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [ovRes, qRes] = await Promise.all([
          fetch('/api/agent-status-workbench/overview', { cache: 'no-store' }),
          fetch('/api/agent-status-workbench/pipeline-quality', { cache: 'no-store' }),
        ]);
        if (!ovRes.ok || !qRes.ok) throw new Error('Failed to load pipeline health');
        const [ov, q] = await Promise.all([ovRes.json(), qRes.json()]);
        if (!cancelled) { setOverview(ov); setQuality(q); }
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : 'Failed to load pipeline health');
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  if (isLoading) return <Card><p className="text-[13px] italic text-wb-ink2">Loading pipeline health…</p></Card>;
  if (loadError || !overview || !quality) {
    return (
      <Card>
        <div className="rounded-md border border-wb-crit/40 bg-wb-crit/10 px-4 py-3">
          <p className="text-[13px] font-semibold text-wb-crit-on">Pipeline health unavailable</p>
          <p className="mt-1 text-[12px] text-wb-ink2">{loadError ?? 'No data returned.'}</p>
        </div>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-serif text-lg text-wb-ink">Technical OSINT Pipeline</h2>
          <Link href="/intelligence-workbench" className="text-[11px] text-wb-sage-deep hover:underline">Open Technical OSINT →</Link>
        </div>
        <StageChecklist stages={overview.pipelines.technical.stages} />
        <h3 className="mb-2 mt-4 text-[11px] font-semibold uppercase tracking-wide text-wb-ink2">Last 14 days</h3>
        <QualityTable rows={quality.technical} cols={TECH_COLS} />
      </Card>

      <Card>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-serif text-lg text-wb-ink">Health OSINT Pipeline</h2>
          <Link href="/health-osint" className="text-[11px] text-wb-sage-deep hover:underline">Open Health OSINT →</Link>
        </div>
        <StageChecklist stages={overview.pipelines.health.stages} />
        <h3 className="mb-2 mt-4 text-[11px] font-semibold uppercase tracking-wide text-wb-ink2">Last 14 days</h3>
        <QualityTable rows={quality.health} cols={HEALTH_COLS} />
      </Card>

      <p className="text-[11px] text-wb-ink2">{quality.note}</p>
    </div>
  );
}
