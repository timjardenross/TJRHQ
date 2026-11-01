// Human Systems Workbench — Clinician Report content.
//
// Backs /human-systems-workbench/report: a fixed 14-day, print-ready
// summary meant to be handed to an external reader (Captain's psychologist)
// ahead of a session — distinct from the Trends page's own "What Changed"
// card, which is written for the Captain themselves and covers a rolling
// 30 days. Same grounding discipline as trends/summary.ts (a computed
// statistics block the model must treat as ground truth, never its own
// arithmetic over the raw log) but asks for three short, clearly-labelled
// sections instead of one paragraph, and is written in first person
// ("I've...") since the Captain is the one sending it, not the system
// describing them in the third person.
//
// Split out from route.ts for the same reason trends/summary.ts is split
// out of trends/route.ts: Next.js's route-export validation only allows a
// route.ts file to export recognized handler/config names, so anything
// that needs unit testing lives here instead.

import { computeSummaryStats, type SummaryStats, type TrendDayRow } from '../trends/summary';

export const REPORT_WINDOW_DAYS = 14;

export const REPORT_SYSTEM_PROMPT =
  'You are helping Captain TJR prepare a short written update to send their psychologist ' +
  'ahead of tomorrow\'s appointment, built from the last 14 days of their own capacity/' +
  'regulation/recovery check-in data. Write in first person, as the Captain, plain everyday ' +
  'language — no clinical jargon, no diagnosis, no medical claims. You will be given a ' +
  '"Computed statistics" block — treat every count, average, and percentage in it as ground ' +
  'truth and never state a different number of your own. Only name a field as a driver of a ' +
  'pattern if it appears in that block\'s Candidate drivers list. The raw daily log is for ' +
  'qualitative color only (wording, timing), not for counting. Never invent something that ' +
  'isn\'t in the data. Respond with ONLY a JSON object, no other text, of the exact shape ' +
  '{"highlights": string[], "changes": string[], "focus": string[]} — 2 to 4 short items ' +
  '(under ~20 words each) per array. "highlights" = what went well or stayed steady this ' +
  'fortnight. "changes" = what moved, and roughly when, compared to the pattern before it. ' +
  '"focus" = what would be worth raising or working on in the session. If there is too little ' +
  'data to say something for a section, return an empty array for it rather than guessing.';

export interface ReportContent {
  highlights: string[];
  changes: string[];
  focus: string[];
}

function last14CalendarDays(trends: TrendDayRow[]): TrendDayRow[] {
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - (REPORT_WINDOW_DAYS - 1));
  const cutoffStr = cutoff.toISOString().slice(0, 10);
  return trends.filter((t) => t.log_date >= cutoffStr);
}

/** Same stats-block format as trends/summary.ts's formatStatsBlock, kept as
 *  a private copy rather than exported/reused directly — the two prompts'
 *  wording around the block differs enough (this one is grounding a
 *  3-section JSON reply, not a single paragraph) that sharing the function
 *  itself would couple two independent prompts for no real benefit. The
 *  numbers themselves still come from the one shared computeSummaryStats. */
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
    lines.push('Candidate drivers (only these may be named as driving a pattern, ranked by how often each was in a concerning state):');
    for (const d of stats.drivers) {
      lines.push(`- ${d.label}: concerning on ${d.concerningCount} of ${d.coverage} recorded days`);
    }
  } else {
    lines.push('Candidate drivers: none — no field has enough recorded days to confidently name as a driver.');
  }

  return lines.join('\n');
}

export function buildReportPrompt(trends: TrendDayRow[]): { prompt: string; stats: SummaryStats; windowed: TrendDayRow[] } {
  const windowed = last14CalendarDays(trends);
  const stats = computeSummaryStats(windowed);
  const recorded = windowed.filter((t) => Object.values(t).some((v, i) => i > 0 && v != null));
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
  const statsBlock = formatStatsBlock(stats);
  const prompt =
    `Computed statistics (ground truth — use these for any counts, percentages, ` +
    `or named drivers; never state a number that isn't in this block):\n${statsBlock}\n\n` +
    `Raw daily log (${recorded.length} recorded day(s), for qualitative color only — ` +
    `not for counting):\n${lines.join('\n')}`;
  return { prompt, stats, windowed };
}

/** Parses the model's JSON reply, tolerating a stray code fence (some
 *  providers wrap JSON in ```json ... ``` even when told not to) and
 *  validates the shape strictly — anything malformed is treated as "no
 *  report" rather than shown half-broken. */
export function parseReportResponse(raw: string): ReportContent | null {
  const cleaned = raw.trim().replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/, '').trim();
  try {
    const data = JSON.parse(cleaned);
    const isStringArray = (v: unknown): v is string[] => Array.isArray(v) && v.every((x) => typeof x === 'string');
    if (isStringArray(data?.highlights) && isStringArray(data?.changes) && isStringArray(data?.focus)) {
      return { highlights: data.highlights, changes: data.changes, focus: data.focus };
    }
  } catch {
    // fall through — malformed JSON is handled by the caller's fallback
  }
  return null;
}

/** Deterministic fallback built directly from computeSummaryStats — used
 *  whenever no LLM key is configured or the call fails/returns something
 *  malformed, so the report is never empty the night before an appointment
 *  just because a third-party API had a bad moment. Every line here is a
 *  plain restatement of a number already in `stats`, nothing inferred. */
export function buildFallbackReport(stats: SummaryStats): ReportContent {
  const highlights: string[] = [];
  const changes: string[] = [];
  const focus: string[] = [];

  if (stats.recordedDays === 0) {
    highlights.push('No check-ins recorded in this window yet.');
    return { highlights, changes, focus };
  }

  highlights.push(`Recorded a check-in on ${stats.recordedDays} of the last ${stats.totalDays} days.`);

  if (stats.capacityRecorded > 0) {
    const { green, orange, red } = stats.capacityCounts;
    highlights.push(`Capacity: ${green} sustainable day(s), ${orange} stretched, ${red} depleted (of ${stats.capacityRecorded} recorded).`);
    changes.push(`Capacity state changed day-to-day ${stats.capacityTransitions} time(s) across ${stats.capacityRecorded} recorded days.`);
  }

  if (stats.painValues.length > 0) {
    const max = Math.max(...stats.painValues);
    const avg = stats.painValues.reduce((a, b) => a + b, 0) / stats.painValues.length;
    changes.push(`Pain averaged ${avg.toFixed(1)}/10 over ${stats.painValues.length} recorded day(s), peaking at ${max}/10.`);
  }

  if (stats.drivers.length > 0) {
    for (const d of stats.drivers) {
      focus.push(`${d.label[0].toUpperCase()}${d.label.slice(1)} was in a concerning state on ${d.concerningCount} of ${d.coverage} recorded days.`);
    }
  } else {
    focus.push('No single field stood out as a recurring concern this fortnight.');
  }

  return { highlights, changes, focus };
}
