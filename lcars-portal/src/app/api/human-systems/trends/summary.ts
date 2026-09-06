// Trends "What Changed" LLM summary — prompt construction and the stats it
// grounds itself in.
//
// Split out of route.ts (2026-09-06): Next.js's App Router validates that a
// route.ts file exports nothing but the recognized handler/config names
// (GET, POST, the runtime/revalidate config, etc.) — any other real
// (non-type) export fails the build with "X is not a valid Route export
// field". computeSummaryStats/buildSummaryPrompt need to be exported for
// unit testing, so they live here instead and route.ts just imports them.

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
export const SUMMARY_SYSTEM_PROMPT =
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
// stance (see route.ts's module-level docstring re: emotional_state/
// social_state).
const MIN_DRIVER_COVERAGE = 5;
const CAPACITY_STATES = ['green', 'orange', 'red'] as const;

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
