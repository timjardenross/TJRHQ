'use client';

// Human Systems Workbench — Trends.
//
// Split out from the main workbench page (2026-08-27, Captain direction):
// that page is a "what's happening right now" view; this one is the
// dedicated historical look-back — same split Readiness already has
// (readiness/history/page.tsx alongside its own today-focused tab).
//
// Every field here is backed by real, live-checked data (see
// app/api/human-systems/trends/route.ts's docstring for exactly what was
// checked and why sleep_quality/body_signal_clarity/predictability are
// excluded — 0 real rows for all three).

import { useEffect, useState } from 'react';
import { WorkbenchShell, Card } from '@/components/ui';
import { Sparkline } from '../_components/Sparkline';
import {
  STIMULATION_STATE_TREND_LABEL,
  PAIN_STATE_LABEL,
  REGULATION_STATE_LABEL,
  EXECUTIVE_FUNCTION_LABEL,
  COMPENSATION_LOAD_LABEL,
  EMOTIONAL_STATE_LABEL,
  SOCIAL_STATE_LABEL,
  CAPACITY_STATE_LABEL,
} from '../_components/types';
import type { TrendDayRow } from '@/app/api/human-systems/trends/route';

const TREND_ENERGY: Record<string, number> = { High: 3, Moderate: 2, Low: 1 };
// Ordinal maps — higher = better/more-resourced in every field below,
// consistent direction so the sparklines read the same way at a glance.
// Sourced from capacity_checkins' own CHECK constraints (migrations
// 0148/0152), not invented.
const TREND_NS: Record<string, number> = { dysregulated: 1, activated: 2, calm: 3 };
const TREND_CAPACITY: Record<string, number> = { red: 1, orange: 2, green: 3 };
const TREND_PAIN_STATE: Record<string, number> = { high: 1, elevated: 2, baseline: 3, low: 4 };
const TREND_REGULATION: Record<string, number> = { overloaded: 1, activated: 2, manageable: 3, settled: 4 };
const TREND_EXEC_FN: Record<string, number> = { very_difficult: 1, difficult: 2, strained: 3, good: 4 };
const TREND_COMPENSATION: Record<string, number> = { extreme: 1, high: 2, moderate: 3, low: 4 };
const TREND_EMOTIONAL: Record<string, number> = { overwhelming: 1, heavy: 2, moderate: 3, light: 4 };
const TREND_SOCIAL: Record<string, number> = { none: 1, limited: 2, some: 3, plenty: 4 };
// stimulation_state is NOT "higher = better" (both extremes are the
// problem, balanced is the goal) — positional only, not a goodness scale.
// Called out in its own tile's caption rather than mixed silently in with
// the others.
const TREND_STIMULATION_POSITION: Record<string, number> = { low: 1, balanced: 2, high: 3 };

interface TrendField {
  key: keyof TrendDayRow;
  label: string;
  map: Record<string, number> | null; // null = already numeric (pain_score)
  caption?: string;
}

const FIELDS: TrendField[] = [
  { key: 'energy', label: 'Energy', map: TREND_ENERGY },
  { key: 'pain_score', label: 'Pain (0-10)', map: null },
  { key: 'pain_state', label: 'Pain State', map: TREND_PAIN_STATE },
  { key: 'nervous_system_state', label: 'Nervous System', map: TREND_NS },
  { key: 'regulation_state', label: 'Regulation', map: TREND_REGULATION },
  { key: 'capacity_state', label: 'Capacity', map: TREND_CAPACITY },
  { key: 'executive_function', label: 'Executive Function', map: TREND_EXEC_FN },
  { key: 'compensation_load', label: 'Compensation Load', map: TREND_COMPENSATION },
  { key: 'emotional_state', label: 'Emotional Load', map: TREND_EMOTIONAL },
  { key: 'social_state', label: 'Social Resource', map: TREND_SOCIAL },
  {
    key: 'stimulation_state', label: 'Stimulation', map: TREND_STIMULATION_POSITION,
    caption: 'Not a goodness scale — both ends (too little, too much) are off; the middle (Balanced) is the goal.',
  },
];

const LABEL_MAPS: Partial<Record<keyof TrendDayRow, Record<string, string>>> = {
  capacity_state: CAPACITY_STATE_LABEL,
  stimulation_state: STIMULATION_STATE_TREND_LABEL,
  pain_state: PAIN_STATE_LABEL,
  regulation_state: REGULATION_STATE_LABEL,
  executive_function: EXECUTIVE_FUNCTION_LABEL,
  compensation_load: COMPENSATION_LOAD_LABEL,
  emotional_state: EMOTIONAL_STATE_LABEL,
  social_state: SOCIAL_STATE_LABEL,
};

const WINDOWS = [
  { key: '7d', label: '7 days', days: 7 },
  { key: '30d', label: '30 days', days: 30 },
  { key: '90d', label: '90 days', days: 90 },
] as const;

function fieldValues(trends: TrendDayRow[], field: TrendField): (number | null)[] {
  return trends.map((t) => {
    const raw = t[field.key];
    if (raw == null) return null;
    if (field.map === null) return typeof raw === 'number' ? raw : null;
    const key = typeof raw === 'string' ? raw.toLowerCase() : String(raw);
    return field.map[key] ?? null;
  });
}

function latestLabel(trends: TrendDayRow[], field: TrendField): string {
  for (let i = trends.length - 1; i >= 0; i--) {
    const raw = trends[i][field.key];
    if (raw == null) continue;
    if (field.map === null) return String(raw);
    const labelMap = LABEL_MAPS[field.key];
    const key = typeof raw === 'string' ? raw.toLowerCase() : String(raw);
    return labelMap?.[key] ?? String(raw);
  }
  return 'Not recorded';
}

export default function TrendsPage() {
  const [trends, setTrends] = useState<TrendDayRow[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [windowKey, setWindowKey] = useState<(typeof WINDOWS)[number]['key']>('30d');

  useEffect(() => {
    fetch('/api/human-systems/trends', { cache: 'no-store' })
      .then((r) => r.json())
      .then((data) => {
        if (data?.error) throw new Error(data.error);
        setTrends(data.trends ?? []);
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : 'Failed to load trends'));
  }, []);

  const activeWindow = WINDOWS.find((w) => w.key === windowKey)!;
  const windowed = trends ? trends.slice(-activeWindow.days) : [];
  const recordedDays = windowed.filter((t) =>
    FIELDS.some((f) => t[f.key] != null)
  ).length;

  return (
    <WorkbenchShell
      title="Human Systems — Trends"
      eyebrow="Capacity, Regulation & Recovery"
      tagline="USS TJR · How things have been moving over time, not just today"
      back={{ href: '/human-systems-workbench', label: 'Human Systems Workbench' }}
    >
      <div className="flex flex-col gap-4">
        <Card>
          <div className="flex items-center justify-between">
            <p className="text-[13px] text-wb-ink2">
              {trends === null && !loadError ? 'Loading…' : `${recordedDays} of ${windowed.length} day(s) in this window have at least one recorded field.`}
            </p>
            <div className="flex overflow-hidden rounded-md border border-wb-line text-[11px]">
              {WINDOWS.map((w) => (
                <button
                  key={w.key}
                  onClick={() => setWindowKey(w.key)}
                  className={`px-2.5 py-1 ${windowKey === w.key ? 'bg-wb-sage-deep text-white' : 'text-wb-ink2 hover:bg-wb-line/40'}`}
                >
                  {w.label}
                </button>
              ))}
            </div>
          </div>
        </Card>

        {loadError && (
          <div className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-4 text-[13px] text-wb-crit-on">
            Couldn&rsquo;t load trends: {loadError}
          </div>
        )}

        {trends && !loadError && (
          <Card>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {FIELDS.map((field) => (
                <div key={field.key} className="rounded-md border border-wb-line bg-wb-bg p-3">
                  <div className="text-[11px] uppercase tracking-wide text-wb-ink2">{field.label}</div>
                  <div className="mt-1 text-[13px] font-medium text-wb-ink">{latestLabel(windowed, field)}</div>
                  <div className="mt-2">
                    <Sparkline values={fieldValues(windowed, field)} />
                  </div>
                  {field.caption && <p className="mt-1 text-[10px] italic text-wb-ink2">{field.caption}</p>}
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    </WorkbenchShell>
  );
}
