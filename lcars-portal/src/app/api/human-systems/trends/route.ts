// Human Systems Workbench — Trends API.
//
// Separate from the main /api/human-systems route deliberately (Captain
// direction, 2026-08-27): the main route feeds "what's happening today"
// views; this one feeds the dedicated /human-systems-workbench/trends
// page — a longer, cross-field look-back, same split the Readiness domain
// already established (readiness/history/page.tsx alongside its own
// today-focused tab).
//
// Sources every field from real, live-checked columns only:
//   - capacity_checkins (checkin_type='capacity'): capacity_state,
//     stimulation_state, pain_state, pain_score, regulation_state,
//     executive_function, compensation_load, emotional_state, social_state
//     — confirmed live 2026-08-27 all reasonably populated (7-13 of the
//     last 16 check-ins) except emotional_state/social_state (7/16,
//     included anyway — still real, just sparser).
//   - analytics_health_daily: energy, nervous_system_state — the same two
//     fields the old Medical-tab sparklines used, moved here rather than
//     duplicated (see MedicalView.tsx's removed Trends section).
//
// sleep_quality, body_signal_clarity, and predictability are deliberately
// NOT included — checked live: 0 of 16 recent rows have any of the three
// populated (sleep_quality's writers are retired; the other two have never
// been written by anything). A sparkline for a field with zero real data
// would misrepresent it as "tracked" rather than "not currently captured."

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

const MAX_WINDOW_DAYS = 90;

// LLM summary (2026-08-27, Captain direction) — same Gemini->Mistral chain
// core/llm/provider_chain.py uses server-side, called directly here (plain
// REST, no SDK) since this route runs in the Next.js server process, not
// Python. Summarizes the last 30 days regardless of the page's own window
// toggle — a stable "how have things been trending" read, not something
// that changes every time the Captain clicks 7d/30d/90d.
//
// Improved 2026-09-06: the model used to be handed only the raw per-day
// lines and asked to eyeball state counts, volatility, and "what's driving
// it" itself — exactly the kind of arithmetic-over-noisy-categoricals task
// a small fast model (gemini-3.5-flash-lite / mistral-small) gets wrong or
// overclaims on. It now gets a Computed statistics block built from real
// counts/averages (see computeSummaryStats/formatStatsBlock) and is told
// those numbers are ground truth; naming a "driver" field is restricted to
// whatever computeSummaryStats's coverage threshold actually surfaced, so
// the summary can't cite a field (e.g. social_state) that only has 2 of 30
// days recorded as if it were a confident pattern.
const SUMMARY_SYSTEM_PROMPT =
  'You are summarizing 30 days of Captain TJR\'s own capacity/regulation/recovery ' +
  'check-in data for the Captain to read at the top of the Trends page. Plain ' +
  'language, 2-3 short sentences, no medical claims or diagnosis — describe the ' +
  'pattern in the data (improving, worsening, stable, volatile) and name which ' +
  'field(s) are driving it. You will be given a "Computed statistics" block — ' +
  'treat every count, average, and percentage in it as ground truth and do not ' +
  'recompute or restate a different number of your own. Only name a field as a ' +
  '"driver" if it appears in that block\'s Candidate drivers list; if that list ' +
  'is empty, describe the pattern without naming a specific cause. The raw daily ' +
  'log below the stats block is for qualitative color only (wording, timing), ' +
  'not for counting. Never invent a value not present in the data. If there is ' +
  'too little data to say anything meaningful, say so plainly instead of guessing.';

// Fields eligible to be named as a "driver" of the pattern, and what counts
// as a concerning value for each — mirrors the "worse" end of the buckets
// the Trends page itself scores each field on (see page.tsx's TREND_* maps)
// so the summary's notion of "concerning" matches what the Captain sees
// colored/scored on the page, not a separately-invented scale.
const DRIVER_FIELDS: {
  key: keyof TrendDayRow;
  label: string;
  concerning: (v: string) => boolean;
}[] = [
  { key: 'energy', label: 'energy', concerning: (v) => v.toLowerCase() === 'low' },
  { key: 'nervous_system_state', label: 'nervous system regulation', concerning: (v) => v !== 'calm' },
  { key: 'regulation_state', label: 'regulation', concerning: (v) => v === 'activated' || v === 'overloaded' },
  { key: 'stimulation_state', label: 'stimulation balance', concerning: (v) => v !== 'balanced' },
  { key: 'pain_state', label: 'pain', concerning: (v) => v === 'high' || v === 'elevated' },
  { key: 'executive_function', label: 'executive function', concerning: (v) => v === 'very_difficult' || v === 'difficult' },
  { key: 'compensation_load', label: 'compensation load', concerning: (v) => v === 'extreme' || v === 'high' },
  { key: 'emotional_state', label: 'emotional load', concerning: (v) => v === 'overwhelming' || v === 'heavy' },
  { key: 'social_state', label: 'social resource', concerning: (v) => v === 'none' || v === 'limited' },
];

// A field needs at least this many recorded days in the window before the
// summary is allowed to call it a "driver" — matches the spirit of the
// route's existing "sparse fields shouldn't be presented as tracked"
// stance (see the module-level docstring re: emotional_state/social_state).
const MIN_DRIVER_COVERAGE = 5;
const CAPACITY_STATES = ['green', 'orange', 'red'] as const;

async function callGemini(prompt: string): Promise<string | null> {
  const key = process.env.GEMINI_API_KEY;
  if (!key) {
    console.warn('[human-systems/trends] GEMINI_API_KEY not set in this process env');
    return null;
  }
  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key=${key}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        system_instruction: { parts: [{ text: SUMMARY_SYSTEM_PROMPT }] },
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: { maxOutputTokens: 512, temperature: 0.3 },
      }),
    }
  );
  if (!res.ok) {
    console.warn('[human-systems/trends] Gemini call failed:', res.status, await res.text().catch(() => ''));
    return null;
  }
  const data = await res.json();
  return data?.candidates?.[0]?.content?.parts?.[0]?.text?.trim() || null;
}

async function callMistral(prompt: string): Promise<string | null> {
  const key = process.env.MISTRAL_API_KEY;
  if (!key) {
    console.warn('[human-systems/trends] MISTRAL_API_KEY not set in this process env');
    return null;
  }
  const res = await fetch('https://api.mistral.ai/v1/chat/completions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: 'mistral-small-latest',
      messages: [
        { role: 'system', content: SUMMARY_SYSTEM_PROMPT },
        { role: 'user', content: prompt },
      ],
      max_tokens: 512,
      temperature: 0.3,
    }),
  });
  if (!res.ok) return null;
  const data = await res.json();
  return data?.choices?.[0]?.message?.content?.trim() || null;
}

function hasAnyField(t: TrendDayRow): boolean {
  return Object.values(t).some((v, i) => i > 0 && v != null);
}

export interface DriverStat {
  label: string;
  coverage: number;
  concerningCount: number;
  rate: number;
}

export interface SummaryStats {
  totalDays: number;
  recordedDays: number;
  capacityCounts: Record<(typeof CAPACITY_STATES)[number], number>;
  capacityRecorded: number;
  capacityTransitions: number;
  painValues: number[];
  drivers: DriverStat[];
}

// Pulled out of buildSummaryPrompt so the numbers the model is told to
// treat as ground truth are computed once, in plain code, rather than left
// for the model to derive from the raw per-day lines itself.
export function computeSummaryStats(windowed: TrendDayRow[]): SummaryStats {
  const capacityCounts = { green: 0, orange: 0, red: 0 };
  let capacityTransitions = 0;
  let prevCapacity: string | null = null;
  for (const t of windowed) {
    if (t.capacity_state && (CAPACITY_STATES as readonly string[]).includes(t.capacity_state)) {
      capacityCounts[t.capacity_state as (typeof CAPACITY_STATES)[number]]++;
      if (prevCapacity && prevCapacity !== t.capacity_state) capacityTransitions++;
      prevCapacity = t.capacity_state;
    }
  }
  const capacityRecorded = capacityCounts.green + capacityCounts.orange + capacityCounts.red;

  const painValues = windowed
    .map((t) => t.pain_score)
    .filter((v): v is number => v != null);

  const drivers: DriverStat[] = DRIVER_FIELDS.map((d) => {
    const values = windowed
      .map((t) => t[d.key])
      .filter((v): v is string => typeof v === 'string');
    const coverage = values.length;
    const concerningCount = values.filter(d.concerning).length;
    return { label: d.label, coverage, concerningCount, rate: coverage ? concerningCount / coverage : 0 };
  })
    .filter((d) => d.coverage >= MIN_DRIVER_COVERAGE && d.concerningCount > 0)
    .sort((a, b) => b.rate - a.rate)
    .slice(0, 3);

  return {
    totalDays: windowed.length,
    recordedDays: windowed.filter(hasAnyField).length,
    capacityCounts,
    capacityRecorded,
    capacityTransitions,
    painValues,
    drivers,
  };
}

function formatStatsBlock(stats: SummaryStats): string {
  const lines: string[] = [`Recorded days: ${stats.recordedDays} of ${stats.totalDays} in this window.`];

  if (stats.capacityRecorded > 0) {
    const { green, orange, red } = stats.capacityCounts;
    lines.push(
      `Capacity state counts: green=${green}, orange=${orange}, red=${red} ` +
      `(${stats.capacityRecorded} days recorded). Day-to-day changes in capacity ` +
      `state: ${stats.capacityTransitions} of ${Math.max(stats.capacityRecorded - 1, 0)} possible transitions.`
    );
  }

  if (stats.painValues.length > 0) {
    const max = Math.max(...stats.painValues);
    const avg = stats.painValues.reduce((a, b) => a + b, 0) / stats.painValues.length;
    lines.push(`Pain score (0-10): ${stats.painValues.length} day(s) recorded, average ${avg.toFixed(1)}, max ${max}.`);
  }

  if (stats.drivers.length > 0) {
    lines.push('Candidate drivers (only these may be named as driving the pattern, ranked by how often each was in a concerning state):');
    for (const d of stats.drivers) {
      lines.push(`- ${d.label}: concerning on ${d.concerningCount} of ${d.coverage} recorded days`);
    }
  } else {
    lines.push('Candidate drivers: none — no field has enough recorded days to confidently name as a driver.');
  }

  return lines.join('\n');
}

export function buildSummaryPrompt(trends: TrendDayRow[]): string {
  const recorded = trends.filter(hasAnyField);
  const lines = recorded.map((t) => {
    const fields = [
      t.capacity_state && `capacity=${t.capacity_state}`,
      t.stimulation_state && `stimulation=${t.stimulation_state}`,
      t.pain_state && `pain=${t.pain_state}`,
      t.pain_score != null && `pain_score=${t.pain_score}`,
      t.regulation_state && `regulation=${t.regulation_state}`,
      t.executive_function && `executive_function=${t.executive_function}`,
      t.compensation_load && `compensation_load=${t.compensation_load}`,
      t.emotional_state && `emotional=${t.emotional_state}`,
      t.social_state && `social=${t.social_state}`,
      t.energy && `energy=${t.energy}`,
      t.nervous_system_state && `nervous_system=${t.nervous_system_state}`,
    ].filter(Boolean);
    return `${t.log_date}: ${fields.join(', ')}`;
  });
  const statsBlock = formatStatsBlock(computeSummaryStats(trends));
  return (
    `Computed statistics (ground truth — use these for any counts, percentages, ` +
    `or named drivers; never state a number that isn't in this block):\n${statsBlock}\n\n` +
    `Raw daily log (${recorded.length} recorded day(s), for qualitative color only — ` +
    `not for counting):\n${lines.join('\n')}`
  );
}

// Last 30 *calendar* days, not the last 30 rows with any data — trends is
// sparse (only dates with a row in either source table get an entry at
// all), so a plain array slice(-30) could silently reach back well past 30
// calendar days whenever there are gap days in between. That would make
// the page's own "(last 30 days)" heading inaccurate to whatever data
// actually got fed to the model.
function last30CalendarDays(trends: TrendDayRow[]): TrendDayRow[] {
  const cutoff = daysAgo(29);
  return trends.filter((t) => t.log_date >= cutoff);
}

async function generateSummary(trends: TrendDayRow[]): Promise<string | null> {
  const windowed = last30CalendarDays(trends);
  const recordedCount = windowed.filter(hasAnyField).length;
  if (recordedCount < 2) return null;
  const prompt = buildSummaryPrompt(windowed);
  try {
    return (await callGemini(prompt)) ?? (await callMistral(prompt));
  } catch (err) {
    console.error('[human-systems/trends] summary generation failed:', err);
    return null;
  }
}

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

// analytics_health_daily.energy is COALESCE(captains_log_entries.energy,
// health_daily_logs.energy) (migration 0017) — both writers are already
// retired (Captain's Log 2026-08-10; health_daily_logs replaced by
// capacity_checkins the same day). Captain confirmed 2026-08-27: nothing
// captures fresh data for that field anymore, so backfill from
// capacity_checkins.capacity_state — the live signal, same mapping the
// main /api/human-systems route's energyFromCapacityState() already uses.
function energyFromCapacityState(state: string | null): string | null {
  return ({ green: 'High', orange: 'Moderate', red: 'Low' } as Record<string, string>)[state ?? ''] ?? null;
}

export interface TrendDayRow {
  log_date: string;
  energy: string | null;
  nervous_system_state: string | null;
  capacity_state: string | null;
  stimulation_state: string | null;
  pain_state: string | null;
  pain_score: number | null;
  regulation_state: string | null;
  executive_function: string | null;
  compensation_load: string | null;
  emotional_state: string | null;
  social_state: string | null;
}

export async function GET(request: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    const since = daysAgo(MAX_WINDOW_DAYS - 1);
    const until = today();

    // Captain-flagged 2026-08-27: a garbage row (log_date='2099-01-01',
    // energy='Moderate') in analytics_health_daily was sorting as the
    // "latest" day — since only a lower bound was applied here, the fake
    // future date passed straight through and got picked as the tile's
    // displayed value while the real most-recent reading (2026-08-21) sat
    // buried. The main /api/human-systems route has always applied this
    // same .lte('log_date', today()) upper bound (see its buildMedical());
    // this route just never had it. Added to both queries.
    const [{ data: dailyRows, error: dailyErr }, { data: checkinRows, error: checkinErr }] = await Promise.all([
      sb.from('analytics_health_daily')
        .select('log_date,energy,nervous_system_state')
        .gte('log_date', since)
        .lte('log_date', until)
        .order('log_date', { ascending: true }),
      sb.from('capacity_checkins')
        .select('log_date,captured_at,capacity_state,stimulation_state,pain_state,pain_score,regulation_state,executive_function,compensation_load,emotional_state,social_state')
        .eq('checkin_type', 'capacity')
        .gte('log_date', since)
        .lte('log_date', until)
        .order('captured_at', { ascending: true }),
    ]);
    if (dailyErr) throw dailyErr;
    if (checkinErr) throw checkinErr;

    const byDate = new Map<string, TrendDayRow>();
    for (const r of (dailyRows ?? []) as any[]) {
      byDate.set(r.log_date, {
        log_date: r.log_date,
        energy: r.energy ?? null,
        nervous_system_state: r.nervous_system_state ?? null,
        capacity_state: null, stimulation_state: null, pain_state: null, pain_score: null,
        regulation_state: null, executive_function: null, compensation_load: null,
        emotional_state: null, social_state: null,
      });
    }
    // Last write per log_date wins (ascending captured_at order), same
    // priority rule the main route's own backfill already uses.
    for (const r of (checkinRows ?? []) as any[]) {
      const existing = byDate.get(r.log_date) ?? {
        log_date: r.log_date, energy: null, nervous_system_state: null,
        capacity_state: null, stimulation_state: null, pain_state: null, pain_score: null,
        regulation_state: null, executive_function: null, compensation_load: null,
        emotional_state: null, social_state: null,
      };
      byDate.set(r.log_date, {
        ...existing,
        energy: existing.energy ?? energyFromCapacityState(r.capacity_state),
        capacity_state: r.capacity_state ?? existing.capacity_state,
        stimulation_state: r.stimulation_state ?? existing.stimulation_state,
        pain_state: r.pain_state ?? existing.pain_state,
        pain_score: r.pain_score ?? existing.pain_score,
        regulation_state: r.regulation_state ?? existing.regulation_state,
        executive_function: r.executive_function ?? existing.executive_function,
        compensation_load: r.compensation_load ?? existing.compensation_load,
        emotional_state: r.emotional_state ?? existing.emotional_state,
        social_state: r.social_state ?? existing.social_state,
      });
    }

    const trends = Array.from(byDate.values()).sort((a, b) => a.log_date.localeCompare(b.log_date));
    const summary = await generateSummary(trends);
    return NextResponse.json({ trends, window_days: MAX_WINDOW_DAYS, summary });
  } catch (err) {
    console.error('[human-systems/trends] read failed:', err);
    return NextResponse.json({ error: 'trends_read_failed' }, { status: 500 });
  }
}
