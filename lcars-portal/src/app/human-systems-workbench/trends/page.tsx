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

// Ordinal maps — higher = better/more-resourced in every field below,
// consistent 0-100 range so every sparkline reads on the same axis.
//
// Four fields (energy, capacity, nervous_system, regulation) use the
// platform's own REAL canonical scoring, not an invented scale — pulled
// directly from compute_recovery_score() (migration
// 0150_capacity_checkins_recovery_integration.sql), the same weighted
// formula that already powers the Recovery Score elsewhere in this app.
// regulation_state is collapsed to the same 3-bucket scale
// nervous_system_state uses (settled/manageable -> calm, activated ->
// activated, overloaded -> dysregulated) exactly as that SQL function
// does, so the two fields' numbers stay directly comparable.
// Lowercase keys, matching fieldValues()/latestLabel()/latestScore()'s own
// raw.toLowerCase() lookup — energy's actual values (High/Moderate/Low,
// from analytics_health_daily and the energyFromCapacityState() backfill)
// arrive Title Case. This was the real cause of Energy showing "Not
// enough data" despite real backfilled rows existing: every other field's
// map already used lowercase keys, so only this one silently missed on
// every lookup. Found and fixed 2026-08-27.
const TREND_ENERGY: Record<string, number> = { high: 90, moderate: 60, low: 25 };
const TREND_NS: Record<string, number> = { calm: 90, activated: 55, dysregulated: 20 };
const TREND_CAPACITY: Record<string, number> = { green: 85, orange: 55, red: 20 };
const TREND_REGULATION: Record<string, number> = { settled: 90, manageable: 90, activated: 55, overloaded: 20 };

// The remaining fields have no canonical platform score (compute_recovery_
// score() doesn't weight them) — evenly spaced across the same 0-100 range
// for visual consistency with the four above, not claiming the same
// precision. Sourced from capacity_checkins' own CHECK constraints
// (migrations 0148/0152), not invented.
const TREND_PAIN_STATE: Record<string, number> = { high: 15, elevated: 45, baseline: 70, low: 95 };
const TREND_EXEC_FN: Record<string, number> = { very_difficult: 15, difficult: 45, strained: 70, good: 95 };
const TREND_COMPENSATION: Record<string, number> = { extreme: 15, high: 45, moderate: 70, low: 95 };
const TREND_EMOTIONAL: Record<string, number> = { overwhelming: 15, heavy: 45, moderate: 70, light: 95 };
const TREND_SOCIAL: Record<string, number> = { none: 15, limited: 45, some: 70, plenty: 95 };
// stimulation_state is NOT "higher = better" (both extremes are the
// problem, balanced is the goal) — positional only, not a goodness scale.
// Called out in its own tile's caption rather than mixed silently in with
// the others.
const TREND_STIMULATION_POSITION: Record<string, number> = { low: 25, balanced: 75, high: 25 };

interface TrendField {
  key: keyof TrendDayRow;
  label: string;
  map: Record<string, number> | null; // null = already numeric (pain_score)
  caption?: string;
}

// Phase 9 (Human Systems redesign, 2026-09-06) — grouped into 4 buckets
// instead of one flat list of equally-prominent tiles, so the page reads
// as "here's how capacity, regulation, load, and recovery resources have
// each moved" rather than 11 undifferentiated cards. Purely a display/
// grouping change — every field, its scoring map, and the underlying
// trends query are unchanged from before this phase.
interface TrendGroup {
  key: string;
  label: string;
  blurb: string;
  fields: TrendField[];
}

const TREND_GROUPS: TrendGroup[] = [
  {
    key: 'capacity',
    label: 'Capacity',
    blurb: 'How much the system has had available to work with.',
    fields: [
      { key: 'energy', label: 'Energy', map: TREND_ENERGY },
      { key: 'capacity_state', label: 'Capacity', map: TREND_CAPACITY },
    ],
  },
  {
    key: 'regulation',
    label: 'Regulation',
    blurb: 'Nervous-system state and sensory input balance.',
    fields: [
      { key: 'nervous_system_state', label: 'Nervous System', map: TREND_NS },
      { key: 'regulation_state', label: 'Regulation', map: TREND_REGULATION },
      {
        key: 'stimulation_state', label: 'Stimulation', map: TREND_STIMULATION_POSITION,
        caption: 'Not a goodness scale — both ends (too little, too much) are off; the middle (Balanced) is the goal.',
      },
    ],
  },
  {
    key: 'load',
    label: 'Load',
    blurb: 'What has been costing effort or asking more of the system than usual.',
    fields: [
      { key: 'pain_score', label: 'Pain (0-10)', map: null },
      { key: 'pain_state', label: 'Pain State', map: TREND_PAIN_STATE },
      { key: 'executive_function', label: 'Executive Function', map: TREND_EXEC_FN },
      { key: 'compensation_load', label: 'Compensation Load', map: TREND_COMPENSATION },
    ],
  },
  {
    key: 'recovery',
    label: 'Recovery',
    blurb: 'Resources available for restoring capacity.',
    fields: [
      { key: 'emotional_state', label: 'Emotional Load', map: TREND_EMOTIONAL },
      { key: 'social_state', label: 'Social Resource', map: TREND_SOCIAL },
    ],
  },
];

// Flat list retained for the code that operates across every field
// regardless of grouping (recordedDays count, etc.) — unchanged logic,
// just derived from the grouped structure instead of duplicated.
const FIELDS: TrendField[] = TREND_GROUPS.flatMap((g) => g.fields);

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

// Aligned to therapy session frequency (Captain-directed 2026-08-27) —
// weekly multiples rather than calendar-month buckets, so a window
// boundary lines up with "since my last session" / "since 3 sessions ago"
// instead of an arbitrary 30/90-day cut.
const WINDOWS = [
  { key: '7d', label: '7 days', days: 7 },
  { key: '14d', label: '14 days', days: 14 },
  { key: '21d', label: '21 days', days: 21 },
  { key: '35d', label: '35 days', days: 35 },
  { key: '49d', label: '49 days', days: 49 },
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

/** The number actually driving the sparkline for this field's latest
 *  recorded day — shown alongside the label since a category name alone
 *  ("Strained") doesn't show where it sits on the scale the way "70/100"
 *  does. null for pain_score (already numeric, shown as the label itself)
 *  and when nothing's recorded. */
function latestScore(trends: TrendDayRow[], field: TrendField): number | null {
  if (field.map === null) return null;
  for (let i = trends.length - 1; i >= 0; i--) {
    const raw = trends[i][field.key];
    if (raw == null) continue;
    const key = typeof raw === 'string' ? raw.toLowerCase() : String(raw);
    return field.map[key] ?? null;
  }
  return null;
}

export default function TrendsPage() {
  const [trends, setTrends] = useState<TrendDayRow[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [windowKey, setWindowKey] = useState<(typeof WINDOWS)[number]['key']>('21d');
  const [summary, setSummary] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);

  useEffect(() => {
    fetch('/api/human-systems/trends', { cache: 'no-store' })
      .then((r) => r.json())
      .then((data) => {
        if (data?.error) throw new Error(data.error);
        setTrends(data.trends ?? []);
        setSummary(data.summary ?? null);
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : 'Failed to load trends'))
      .finally(() => setSummaryLoading(false));
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
      back={{ href: '/human-systems-workbench', label: 'Human Systems' }}
    >
      {/* Single-page print target (Captain-directed 2026-08-27): tight
       *  @page margins, compact padding, and page-break-inside: avoid on
       *  every tile so a tile never splits across a page boundary — with
       *  11 fields the natural flow already fits one page once the
       *  screen-sized padding/gaps are trimmed for print. */}
      <style>{`
        @media print {
          @page { size: auto; margin: 8mm; }
          .print-compact { padding: 0.5rem !important; }
          .print-tile { break-inside: avoid; page-break-inside: avoid; }
        }
      `}</style>
      <div className="flex flex-col gap-4 print:gap-2">
        <Card className="print-compact">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-wb-ink2">What Changed (last 30 days)</div>
          <p className="mt-1 text-[13px] text-wb-ink">
            {summaryLoading
              ? 'Generating summary…'
              : summary ?? 'Not enough recorded days yet for a summary.'}
          </p>
          <p className="mt-2 text-[11px] text-wb-ink2">
            Built only from what was actually recorded — never a value it doesn&rsquo;t have.
          </p>
        </Card>

        <Card className="print:hidden">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[13px] text-wb-ink2">
              {trends === null && !loadError ? 'Loading…' : `${recordedDays} of ${windowed.length} day(s) in this window have at least one recorded field.`}
            </p>
            <div className="flex items-center gap-2">
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
              <button
                onClick={() => window.print()}
                className="rounded-md border border-wb-line px-3 py-1 text-[11px] font-medium text-wb-ink transition hover:border-wb-sage-deep"
              >
                Download PDF
              </button>
            </div>
          </div>
        </Card>

        {/* Print-only header — the WorkbenchShell chrome and window-toggle
         *  controls above are hidden via print:hidden; this line gives the
         *  PDF its own context (which window, when generated) since the
         *  interactive toggle buttons obviously don't survive onto paper. */}
        <p className="hidden text-[11px] text-wb-ink2 print:block">
          Human Systems — Trends · {activeWindow.label} window · generated {new Date().toLocaleString('en-AU')}
        </p>

        {loadError && (
          <div className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-4 text-[13px] text-wb-crit-on">
            Couldn&rsquo;t load trends: {loadError}
          </div>
        )}

        {trends && !loadError && (
          <div className="flex flex-col gap-4 print:gap-2">
            {TREND_GROUPS.map((group) => (
              <Card key={group.key} className="print-compact print-tile">
                <div className="flex items-baseline justify-between gap-3">
                  <div className="text-[12px] font-semibold uppercase tracking-[0.12em] text-wb-ink">{group.label}</div>
                  <div className="text-[11px] text-wb-ink2">{group.blurb}</div>
                </div>
                <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 print:grid-cols-3 print:gap-2">
                  {group.fields.map((field) => {
                    const score = latestScore(windowed, field);
                    return (
                      <div key={field.key} className="print-tile rounded-md border border-wb-line bg-wb-bg p-3 print:p-1.5">
                        <div className="text-[11px] uppercase tracking-wide text-wb-ink2">{field.label}</div>
                        <div className="mt-1 flex items-baseline gap-2">
                          <span className="text-[13px] font-medium text-wb-ink">{latestLabel(windowed, field)}</span>
                          {score != null && <span className="text-[12px] tabular-nums text-wb-ink2">{score}/100</span>}
                        </div>
                        <div className="mt-2">
                          <Sparkline values={fieldValues(windowed, field)} />
                        </div>
                        {field.caption && <p className="mt-1 text-[10px] italic text-wb-ink2">{field.caption}</p>}
                      </div>
                    );
                  })}
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </WorkbenchShell>
  );
}
