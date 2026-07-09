/**
 * HSF-001 — Human Systems Framework (dashboard layer).
 *
 * A lightweight TypeScript mirror of the Python framework engine
 * (platform-runtime/lib/human_systems/framework.py). Derives a four-domain energy
 * snapshot + daily capacity score from a daily health row, and fetches that
 * row from the Supabase `human_systems_daily` view. When Supabase is absent or
 * a query fails, callers fall back to a neutral mock so the panel always renders.
 *
 * Evidence-informed, non-diagnostic. Bands: good | moderate | limited | depleted.
 */

import { supabase } from './supabase';
import type { StatusTone } from './types';

export type EnergyBand = 'good' | 'moderate' | 'limited' | 'depleted';
export type DomainKey = 'physical' | 'cognitive' | 'emotional' | 'social';

export interface EnergyDomain {
  key: DomainKey;
  label: string;
  band: EnergyBand;
  score: number;
  driver: string;
}

export interface CapacitySnapshot {
  domains: EnergyDomain[];
  overallBand: EnergyBand;
  overallScore: number;
  dataAvailable: boolean;
  headline: string;
  /** A single recommended next step, doctrine-compliant. */
  topRecommendation: string;
  /** Red-flag escalation banner text, when present. */
  escalation: string | null;
  sleepHours: number | null;
  painScore: number | null;
  movementCompleted: boolean | null;
}

export interface HealthRow {
  log_date?: string;
  energy?: string | null;
  mood?: string | null;
  nervous_system_state?: string | null;
  sleep_hours?: number | null;
  sleep_quality?: string | null;
  pain_score?: number | null;
  sitting_tolerance_minutes?: number | null;
  captain_capacity_rating?: string | null;
  movement_completed?: boolean | null;
  notes?: string | null;
}

const clamp = (v: number) => Math.max(0, Math.min(100, v));

function bandFromScore(score: number): EnergyBand {
  if (score >= 75) return 'good';
  if (score >= 55) return 'moderate';
  if (score >= 35) return 'limited';
  return 'depleted';
}

export const BAND_TONE: Record<EnergyBand, StatusTone> = {
  good: 'status',
  moderate: 'command',
  limited: 'operations',
  depleted: 'medical'
};

export const BAND_LABEL: Record<EnergyBand, string> = {
  good: 'Good',
  moderate: 'Moderate',
  limited: 'Limited',
  depleted: 'Depleted'
};

function norm(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  const s = String(v).trim().toLowerCase();
  return s || null;
}

function sleepScore(row: HealthRow): number {
  const hours = row.sleep_hours;
  const quality = norm(row.sleep_quality);
  if (hours === null || hours === undefined) {
    if (!quality) return 50;
  }
  let score = 50;
  if (hours !== null && hours !== undefined && !Number.isNaN(Number(hours))) {
    score = clamp((Number(hours) / 7.5) * 70);
  }
  if (quality === 'good') score += 20;
  else if (quality === 'fair') score += 8;
  else if (quality === 'poor') score -= 12;
  return clamp(score);
}

// ── Red-flag scan (mirror of safety.scan_red_flags, condensed) ────────────────

const RED_FLAGS: { test: RegExp; urgent: boolean; message: string }[] = [
  {
    test: /suicid|kill myself|want to die|self[- ]?harm|can'?t keep (myself|me) safe/i,
    urgent: true,
    message:
      'This is the priority over everything else — please call 999, the Samaritans on 116 123, or a crisis line now. You do not have to manage this alone.'
  },
  {
    test: /chest pain|chest tight|can'?t breathe|short(ness)? of breath/i,
    urgent: true,
    message:
      'Chest pain or breathing difficulty should be treated as an emergency — please call 999 now.'
  },
  {
    test: /new (numbness|weakness)|bladder (control|incontinen)|bowel (control|incontinen)|saddle/i,
    urgent: true,
    message:
      'New or worsening neurological symptoms warrant urgent assessment — contact your GP today, or A&E / 999 if rapidly worsening.'
  },
  {
    test: /\bfever\b|infection/i,
    urgent: false,
    message: 'Signs of fever or infection are worth checking the same day — contact your GP or NHS 111.'
  }
];

/**
 * Negation markers that, when they immediately precede a red-flag phrase,
 * mean the phrase is being denied rather than reported ("no chest pain",
 * "denies suicidal ideation", "negative for fever", "ruled out infection").
 */
const NEGATION_MARKERS =
  /\b(no|not|never|none|without|negative(?:\s+for)?|denies|denied|deny|ruled?\s+out|rules?\s+out|free\s+of|absence\s+of|absent)\b/i;

/**
 * True when the red-flag phrase at `matchIndex` is negated by a marker in the
 * short window of text immediately preceding it (~4 words). This is a
 * deliberately simple preceding-text check, not full NLP — it is scoped to
 * catch the common denial forms a check-in note actually uses. A pure,
 * testable function so both the true-positive and negated paths are covered.
 */
export function isNegated(text: string, matchIndex: number): boolean {
  if (matchIndex <= 0) return false;
  const preceding = text.slice(0, matchIndex);
  const words = preceding.split(/\s+/).filter(Boolean);
  // Look back ~4 tokens (enough for "negative for", "ruled out", "no ... of").
  const window = words.slice(-4).join(' ');
  return NEGATION_MARKERS.test(window);
}

export function scanEscalation(text: string | null | undefined): string | null {
  if (!text) return null;
  const hits = RED_FLAGS.filter((f) => {
    // A flag only counts if at least one of its matches is NOT negated by the
    // text immediately preceding it. Iterate every match (global copy of the
    // pattern) so "no chest pain but chest tightness now" still escalates.
    const flags = f.test.flags.includes('g') ? f.test.flags : f.test.flags + 'g';
    const re = new RegExp(f.test.source, flags);
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      if (!isNegated(text, m.index)) return true;
      if (m.index === re.lastIndex) re.lastIndex++; // guard against zero-width loops
    }
    return false;
  });
  if (!hits.length) return null;
  hits.sort((a, b) => Number(b.urgent) - Number(a.urgent));
  return hits.map((h) => h.message).join(' ');
}

// ── Capacity interpretation ───────────────────────────────────────────────────

export function interpretCapacity(row: HealthRow | null): CapacitySnapshot {
  if (!row) {
    return {
      domains: (['physical', 'cognitive', 'emotional', 'social'] as DomainKey[]).map((key) => ({
        key,
        label: key.charAt(0).toUpperCase() + key.slice(1),
        band: 'moderate' as EnergyBand,
        score: 60,
        driver: 'no data logged'
      })),
      overallBand: 'moderate',
      overallScore: 60,
      dataAvailable: false,
      headline: 'No check-in logged yet today. A quick check-in would calibrate the day.',
      topRecommendation: 'Consider a quick health check-in so the system can read today.',
      escalation: null,
      sleepHours: null,
      painScore: null,
      movementCompleted: null
    };
  }

  const energy = norm(row.energy);
  const ns = norm(row.nervous_system_state);
  const mood = norm(row.mood);
  const cap = norm(row.captain_capacity_rating);
  const sleepS = sleepScore(row);

  const energyScore = ({ high: 90, moderate: 60, low: 28 } as Record<string, number>)[energy ?? ''] ?? 55;
  const nsScore = ({ calm: 90, activated: 52, dysregulated: 22 } as Record<string, number>)[ns ?? ''] ?? 60;
  const moodScore =
    ({ positive: 85, high: 85, stable: 62, moderate: 62, low: 30 } as Record<string, number>)[mood ?? ''] ?? 58;

  let painPenalty = 0;
  if (row.pain_score !== null && row.pain_score !== undefined && !Number.isNaN(Number(row.pain_score))) {
    painPenalty = Math.min(25, Number(row.pain_score) * 2.5);
  }

  let phys = 0.45 * sleepS + 0.45 * energyScore + 0.1 * 60 - painPenalty;
  if (row.sitting_tolerance_minutes != null && !Number.isNaN(Number(row.sitting_tolerance_minutes))) {
    phys += (Math.min(Number(row.sitting_tolerance_minutes), 180) - 120) / 12;
  }
  phys = clamp(phys);
  const cog = clamp(0.5 * sleepS + 0.5 * nsScore);
  const emo = clamp(0.55 * nsScore + 0.45 * moodScore);
  const soc = clamp(0.5 * moodScore + 0.5 * nsScore);

  const domains: EnergyDomain[] = [
    { key: 'physical', label: 'Physical', band: bandFromScore(phys), score: Math.round(phys), driver: `${energy ?? 'unknown'} energy` },
    { key: 'cognitive', label: 'Cognitive', band: bandFromScore(cog), score: Math.round(cog), driver: `nervous system ${ns ?? 'unknown'}` },
    { key: 'emotional', label: 'Emotional', band: bandFromScore(emo), score: Math.round(emo), driver: `mood ${mood ?? 'unknown'}` },
    { key: 'social', label: 'Social', band: bandFromScore(soc), score: Math.round(soc), driver: 'estimated from mood + state' }
  ];

  let overall = domains.reduce((a, d) => a + d.score, 0) / domains.length;
  if (cap === 'green' || cap === 'amber' || cap === 'red') {
    const self = ({ green: 82, amber: 55, red: 25 } as Record<string, number>)[cap];
    overall = 0.6 * overall + 0.4 * self;
  }
  const overallBand = bandFromScore(overall);
  const limited = domains.filter((d) => d.band === 'limited' || d.band === 'depleted');

  let headline: string;
  let topRecommendation: string;
  if (overallBand === 'good') {
    headline = 'Capacity looks available today. A steady, sustainable load fits.';
    topRecommendation = 'Consider banking a small recovery anchor while capacity is good.';
  } else if (overallBand === 'moderate') {
    headline = 'Moderate capacity. Pace the day and protect the afternoon.';
    topRecommendation = 'A practical next step could be choosing one anchor and pacing the rest.';
  } else if (overallBand === 'limited') {
    const names = limited.map((d) => d.label.toLowerCase()).join(', ') || 'several domains';
    headline = `Limited capacity (${names}). This is a signal to lighten load today.`;
    topRecommendation = 'Consider a low-capacity day shape: one anchor only, short blocks, real breaks.';
  } else {
    headline = 'Capacity is low today. Rest and protection are the priority.';
    topRecommendation = 'Rest is the priority. Defer non-urgent decisions where you can.';
  }

  return {
    domains,
    overallBand,
    overallScore: Math.round(overall),
    dataAvailable: true,
    headline,
    topRecommendation,
    escalation: scanEscalation(row.notes),
    sleepHours: row.sleep_hours ?? null,
    painScore: row.pain_score ?? null,
    movementCompleted: row.movement_completed ?? null
  };
}

// ── Recovery-debt signal across recent days ───────────────────────────────────

export interface RecoveryDebt {
  level: 'none' | 'building' | 'high';
  message: string;
}

export function recoveryDebt(rows: HealthRow[]): RecoveryDebt {
  if (!rows.length) return { level: 'none', message: 'No recent data to assess recovery debt.' };
  const recent = [...rows].slice(0, 3);
  const bands = recent.map((r) => interpretCapacity(r).overallBand);
  const lowRun = bands.every((b) => b === 'limited' || b === 'depleted');
  const sleepVals = recent.map((r) => r.sleep_hours).filter((v): v is number => v != null);
  const sleepDebt = sleepVals.length > 0 && sleepVals.reduce((a, b) => a + b, 0) / sleepVals.length < 6;
  if (lowRun && sleepDebt) return { level: 'high', message: 'Several low-capacity days with short sleep — a real recovery window is worth protecting.' };
  if (lowRun || sleepDebt) return { level: 'building', message: 'Recovery debt may be building. Consider lightening load before it costs more.' };
  return { level: 'none', message: 'No significant recovery debt signal.' };
}

// ── Fetch ─────────────────────────────────────────────────────────────────────

function today(): string {
  return new Date().toISOString().slice(0, 10);
}
function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

export interface RecoveryPulse {
  log_date: string;
  pulse_type: string;
  captured_at: string;
  energy: string | null;
  mood: string | null;
  stress: string | null;
  readiness: string | null;
  pain_score: number | null;
  notes: string | null;
}

/** Map stress → nervous_system_state for capacity scoring. */
function stressToNsState(stress: string | null): string | null {
  if (!stress) return null;
  return ({ low: 'calm', moderate: 'activated', high: 'dysregulated' } as Record<string, string>)[stress] ?? null;
}

/** Map readiness → captain_capacity_rating. */
function readinessToCapacity(readiness: string | null): string | null {
  if (!readiness) return null;
  return ({ high: 'green', moderate: 'amber', low: 'red' } as Record<string, string>)[readiness] ?? null;
}

/**
 * Merge a Captain's Log row with the most-recent pulse for that day.
 * Pulse wins on energy/mood/pain/nervous_system_state — they are more current.
 * Log wins on sleep_hours/movement_completed/sitting_tolerance — pulses don't carry these.
 */
function mergeWithPulse(log: HealthRow | null, pulse: RecoveryPulse | null): HealthRow | null {
  if (!pulse && !log) return null;
  if (!pulse) return log;
  const base: HealthRow = log ?? { log_date: pulse.log_date };
  return {
    ...base,
    energy: pulse.energy ?? base.energy,
    mood: pulse.mood ?? base.mood,
    pain_score: pulse.pain_score ?? base.pain_score,
    nervous_system_state: stressToNsState(pulse.stress) ?? base.nervous_system_state,
    captain_capacity_rating: readinessToCapacity(pulse.readiness) ?? base.captain_capacity_rating,
    notes: pulse.notes ?? base.notes,
  };
}

/**
 * Result of a source fetch. `failed` is true ONLY when the query genuinely
 * errored or threw — never when Supabase is simply unconfigured or the query
 * succeeded with no rows. This lets callers distinguish "checked, nothing
 * there" from "could not check", which matters for the red-flag banner.
 */
interface FetchResult<T> {
  rows: T[];
  failed: boolean;
}

/** Fetch recent rows from human_systems_daily. */
async function fetchLogRows(days: number): Promise<FetchResult<HealthRow>> {
  if (!supabase) return { rows: [], failed: false };
  try {
    const { data, error } = await supabase
      .from('human_systems_daily')
      .select('*')
      .gte('log_date', daysAgo(days))
      .order('log_date', { ascending: false });
    if (error) return { rows: [], failed: true };
    return { rows: (data ?? []) as HealthRow[], failed: false };
  } catch {
    return { rows: [], failed: true };
  }
}

/** Fetch recent recovery pulses — most recent per day returned. */
async function fetchPulseRows(days: number): Promise<FetchResult<RecoveryPulse>> {
  if (!supabase) return { rows: [], failed: false };
  try {
    const { data, error } = await supabase
      .from('recovery_pulses')
      .select('log_date,pulse_type,captured_at,energy,mood,stress,readiness,pain_score,notes')
      .gte('log_date', daysAgo(days))
      .order('captured_at', { ascending: false });
    if (error) return { rows: [], failed: true };
    return { rows: (data ?? []) as RecoveryPulse[], failed: false };
  } catch {
    return { rows: [], failed: true };
  }
}

/**
 * Merge log rows with pulse data.
 * Priority: recovery_pulses (real-time) take precedence over log fields for
 * energy/mood/pain/stress. Log provides sleep, movement, sitting tolerance.
 * Days with pulses but no log still produce a usable row.
 */
export async function fetchHumanSystemsRowsWithStatus(
  days = 7
): Promise<{ rows: HealthRow[]; failed: boolean }> {
  const [logRes, pulseRes] = await Promise.all([fetchLogRows(days), fetchPulseRows(days)]);

  // Latest pulse per day (pulses already ordered desc by captured_at)
  const latestPulseByDate = new Map<string, RecoveryPulse>();
  for (const p of pulseRes.rows) {
    if (!latestPulseByDate.has(p.log_date)) {
      latestPulseByDate.set(p.log_date, p);
    }
  }

  // All dates represented across both sources
  const allDates = new Set<string>([
    ...logRes.rows.map((r) => String(r.log_date)),
    ...latestPulseByDate.keys(),
  ]);

  const logByDate = new Map(logRes.rows.map((r) => [String(r.log_date), r]));

  const rows = Array.from(allDates)
    .sort((a, b) => b.localeCompare(a)) // newest first
    .map((date) => mergeWithPulse(logByDate.get(date) ?? null, latestPulseByDate.get(date) ?? null))
    .filter((r): r is HealthRow => r !== null);

  return { rows, failed: logRes.failed || pulseRes.failed };
}

export async function fetchHumanSystemsRows(days = 7): Promise<HealthRow[]> {
  return (await fetchHumanSystemsRowsWithStatus(days)).rows;
}

// ── HSF-002 decision layer (compact mirror of decision.py) ────────────────────

const TERMINAL_STATUSES = ['closed', 'archived'];
const SUSTAINABLE_ACTIVE: Record<EnergyBand, number> = {
  good: 2,
  moderate: 1,
  limited: 0,
  depleted: 0
};

/** Count open (in-flight) missions. Returns null when Supabase is unavailable. */
export async function fetchOpenMissionCount(): Promise<number | null> {
  if (!supabase) return null;
  try {
    const { data, error } = await supabase.from('missions').select('status');
    if (error || !data) return null;
    return data.filter(
      (r: { status?: string }) => !TERMINAL_STATUSES.includes(String(r.status ?? '').toLowerCase())
    ).length;
  } catch {
    return null;
  }
}

export interface Decision {
  highestLeverage: string;
  focus: string[];
  defer: string[];
  missionLoadNote: string | null;
}

/** Single highest-leverage action + focus/defer, mirroring the Python engine. */
export function decide(snapshot: CapacitySnapshot, openMissions: number | null): Decision {
  const band = snapshot.overallBand;

  // Highest-leverage action.
  let highestLeverage: string;
  if (snapshot.escalation) {
    highestLeverage = 'Involve a clinician — see the escalation note above.';
  } else if (band === 'limited' || band === 'depleted') {
    highestLeverage =
      'Protect capacity today: pick one anchor, defer the rest, and schedule one genuine recovery block now.';
  } else if (band === 'moderate') {
    highestLeverage =
      'Spend your best window on the highest priority, then protect a recovery block. Hold everything below it.';
  } else {
    highestLeverage =
      'Capacity is available — apply it to what matters most, and bank a small recovery anchor.';
  }

  // Focus / defer.
  let focus: string[];
  let defer: string[];
  if (band === 'limited' || band === 'depleted') {
    focus = ['Recovery', 'One must-do only'];
    defer = ['New initiatives', 'Low-priority research', 'Additional commitments'];
  } else if (band === 'moderate') {
    focus = ['Top priority', 'A protected recovery block'];
    defer = ['New initiatives beyond the top priority', 'P3+ backlog'];
  } else {
    focus = ['Top priorities', 'Bank a recovery anchor'];
    defer = ['P3+ backlog', 'New commitments'];
  }

  // Mission-load note.
  let missionLoadNote: string | null = null;
  if (openMissions !== null) {
    const sustainable = SUSTAINABLE_ACTIVE[band];
    const overloaded = band === 'limited' || band === 'depleted' || openMissions > 5;
    missionLoadNote = overloaded
      ? `${openMissions} open missions exceed ${band} capacity — consider pausing new intake; progress ${Math.max(sustainable, 1)} today.`
      : `${openMissions} open missions sit within ${band} capacity — up to ${sustainable} to progress today.`;
  }

  return { highestLeverage, focus, defer, missionLoadNote };
}

export interface HumanSystemsData {
  snapshot: CapacitySnapshot;
  debt: RecoveryDebt;
  decision: Decision;
  isLive: boolean;
  /**
   * True only when the health-source fetch that feeds the red-flag scan
   * genuinely failed (query error / thrown), so `snapshot.escalation` is
   * unreliable — distinct from a successful "no red flag" result. Surfaces
   * on both /human-systems and /medical must render an honest "could not
   * check" state rather than an all-clear when this is true.
   */
  escalationCheckFailed: boolean;
}

/** Load the panel's data, degrading gracefully to a neutral no-data snapshot. */
export async function loadHumanSystems(): Promise<HumanSystemsData> {
  const [{ rows, failed }, openMissions] = await Promise.all([
    fetchHumanSystemsRowsWithStatus(7),
    fetchOpenMissionCount()
  ]);
  const todayRow = rows.find((r) => String(r.log_date) === today()) ?? rows[0] ?? null;
  const snapshot = interpretCapacity(todayRow);
  return {
    snapshot,
    debt: recoveryDebt(rows),
    decision: decide(snapshot, openMissions),
    isLive: rows.length > 0,
    escalationCheckFailed: failed
  };
}
