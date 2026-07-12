'use client';

// Phase B — the 7-day Capture analytics, re-expressed as the workbench KPI
// strip (Human Systems' KpiDashboard role). Ported from CaptureAnalyticsPanel.
// Reuses fetchCaptureAnalytics() and SOURCE_BADGE from lib/capture unchanged;
// clicking a stat/chip jumps to the Inbox domain pre-filtered.

import { Card } from '@/components/ui';
import { SOURCE_BADGE, type CaptureAnalytics } from '@/lib/capture';
import type { InboxFilter } from './types';

const CLASS_LABELS: Record<string, string> = {
  mission: 'Mission', personal: 'Health', research: 'Idea', decision: 'Decision',
  reference: 'Note', unclassified: 'Unclassified',
};

const SOURCE_TO_FILTER: Record<string, InboxFilter> = {
  'lcars-mobile-quick-capture': 'portal',
  'telegram-xo-voice-capture': 'telegram-voice',
};

const CLASS_TO_FILTER: Record<string, InboxFilter> = {
  mission: 'mission',
  personal: 'health',
  research: 'research',
  decision: 'decision',
  unclassified: 'unclassified',
};

function Stat({ label, value, onClick, tone = 'ink' }: { label: string; value: number; onClick?: () => void; tone?: 'ink' | 'ok' | 'warn' }) {
  const valueTone = tone === 'warn' ? 'text-wb-warn-on' : tone === 'ok' ? 'text-wb-ok-on' : 'text-wb-ink';
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      className={`flex flex-col items-start rounded-md px-1 text-left ${onClick ? 'transition hover:opacity-70 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep' : 'cursor-default'}`}
    >
      <span className={`font-serif text-2xl ${valueTone}`}>{value}</span>
      <span className="text-[10px] uppercase tracking-[0.14em] text-wb-ink2">{label}{onClick ? ' ↓' : ''}</span>
    </button>
  );
}

export function KpiDashboard({
  stats,
  loading,
  onFilter,
}: {
  stats: CaptureAnalytics | null;
  loading: boolean;
  onFilter: (f: InboxFilter) => void;
}) {
  if (loading && !stats) {
    return (
      <Card className="mb-6">
        <p className="text-[11px] uppercase tracking-[0.14em] text-wb-ink2">Capture · last 7 days</p>
        <p className="mt-2 text-[13px] text-wb-ink2">Loading…</p>
      </Card>
    );
  }
  if (!stats) return null;

  const topSources = Object.entries(stats.by_source).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const topClasses = Object.entries(stats.by_classification).sort((a, b) => b[1] - a[1]).slice(0, 6);

  return (
    <Card className="mb-6">
      <p className="mb-3 text-[11px] uppercase tracking-[0.14em] text-wb-ink2">Capture · last 7 days</p>
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Today" value={stats.today} />
        <Stat label="This week" value={stats.this_week} />
        <Stat label="Pending" value={stats.pending} tone={stats.pending > 0 ? 'warn' : 'ok'} onClick={() => onFilter('all')} />
      </div>

      {topSources.length > 0 && (
        <div className="mt-4">
          <p className="mb-1.5 text-[10px] uppercase tracking-[0.14em] text-wb-ink2">By source</p>
          <div className="flex flex-wrap gap-2">
            {topSources.map(([ch, n]) => {
              const filter = SOURCE_TO_FILTER[ch];
              return (
                <button
                  key={ch}
                  type="button"
                  onClick={() => filter && onFilter(filter)}
                  disabled={!filter}
                  className={`flex items-center gap-1 text-[11px] ${filter ? 'text-wb-ink2 transition hover:text-wb-ink' : 'cursor-default text-wb-ink2'}`}
                >
                  <span className="font-semibold text-wb-ink">{n}</span>
                  {SOURCE_BADGE[ch]?.label ?? ch}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {topClasses.length > 0 && (
        <div className="mt-3">
          <p className="mb-1.5 text-[10px] uppercase tracking-[0.14em] text-wb-ink2">By classification</p>
          <div className="flex flex-wrap gap-2">
            {topClasses.map(([cl, n]) => {
              const filter = CLASS_TO_FILTER[cl];
              return (
                <button
                  key={cl}
                  type="button"
                  onClick={() => filter && onFilter(filter)}
                  disabled={!filter}
                  className={`flex items-center gap-1 text-[11px] ${filter ? 'text-wb-ink2 transition hover:text-wb-ink' : 'cursor-default text-wb-ink2'}`}
                >
                  <span className="font-semibold text-wb-ink">{n}</span>
                  {CLASS_LABELS[cl] ?? cl}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </Card>
  );
}
