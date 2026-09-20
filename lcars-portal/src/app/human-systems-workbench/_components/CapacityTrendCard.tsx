'use client';

// Capacity Trend card — Overview tab, mockup panel 3 ("HUMAN SYSTEMS —
// FOCUS VIEW", mission USS-TJR-MSN-0394 §1.1: "Human Systems' 'Capacity
// Trend — Last 14 days' bar chart → the existing Sparkline component and
// TREND_GROUPS structure in the same file — a real, already-built chart,
// needs restyling not rebuilding"). Deferred from Phase 5's light-touch
// pass, picked back up per Phase 11 (Captain, 2026-09-20).
//
// Fetches the same /api/human-systems/trends endpoint the dedicated Trends
// page (../trends/page.tsx) already uses, and scores days with the shared
// TREND_CAPACITY map (./trendScoring.ts, split out of the Trends page
// specifically so this card and that page share one copy) — deliberately
// not a second computation of the same numbers. Last-14-days window
// matches the mockup's own label exactly (the Trends page's own window
// toggle defaults to 21d; this card always shows 14, independent of that
// toggle).

import { Card } from '@/components/ui';
import { useAbortEffect } from '@/hooks/useAbortEffect';
import { useState } from 'react';
import { CapacityTrendBars, type CapacityTrendBarDay } from './Sparkline';
import { TREND_CAPACITY } from './trendScoring';
import type { TrendDayRow } from '@/app/api/human-systems/trends/route';

const WINDOW_DAYS = 14;

const LEGEND: { key: 'green' | 'orange' | 'red'; label: string; dot: string }[] = [
  { key: 'green', label: 'Green', dot: 'bg-wb-ok' },
  { key: 'orange', label: 'Amber', dot: 'bg-wb-warn' },
  { key: 'red', label: 'Red', dot: 'bg-wb-crit' },
];

export function CapacityTrendCard() {
  const [trends, setTrends] = useState<TrendDayRow[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useAbortEffect((signal, alive) => {
    fetch('/api/human-systems/trends', { cache: 'no-store', signal })
      .then((r) => r.json())
      .then((data) => {
        if (data?.error) throw new Error(data.error);
        if (alive()) setTrends(data.trends ?? []);
      })
      .catch((err) => {
        if (alive() && !(err instanceof Error && err.name === 'AbortError')) {
          setLoadError(err instanceof Error ? err.message : 'Failed to load trend');
        }
      });
  }, []);

  const windowed = (trends ?? []).slice(-WINDOW_DAYS);
  const days: CapacityTrendBarDay[] = windowed.map((row) => {
    const raw = row.capacity_state;
    const key = typeof raw === 'string' ? raw.toLowerCase() : null;
    const score = key != null ? TREND_CAPACITY[key] ?? null : null;
    return { date: row.log_date, state: key, score };
  });

  return (
    <Card title="Capacity Trend" className="md:col-span-2">
      <p className="-mt-2 mb-3 text-[11px] uppercase tracking-[0.1em] text-wb-ink2">Last {WINDOW_DAYS} days</p>
      {loadError && <p className="text-[13px] text-wb-crit-on">Couldn&rsquo;t load the capacity trend: {loadError}</p>}
      {!loadError && trends === null && <p className="text-[13px] text-wb-ink2">Loading…</p>}
      {!loadError && trends !== null && days.length < 2 && (
        <p className="text-[13px] text-wb-ink2">Not enough recorded days yet for a trend.</p>
      )}
      {!loadError && trends !== null && days.length >= 2 && (
        <>
          <CapacityTrendBars days={days} />
          <div className="mt-2 flex flex-wrap gap-3">
            {LEGEND.map((l) => (
              <span key={l.key} className="inline-flex items-center gap-1.5 text-[11px] text-wb-ink2">
                <span className={`h-2 w-2 rounded-full ${l.dot}`} />
                {l.label}
              </span>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}
