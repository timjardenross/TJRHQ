/**
 * HSF-001 — Human Systems Framework (dashboard layer).
 *
 * A lightweight TypeScript mirror of the Python framework engine
 * (slack-bot/lib/human_systems/framework.py). Derives a four-domain energy
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

function scanEscalation(text: string | null | undefined): string | null {
  if (!text) return null;
  const hits = RED_FLAGS.filter((f) => f.test.test(text));
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

/** Fetch recent rows from human_systems_daily. Returns [] when unavailable. */
export async function fetchHumanSystemsRows(days = 7): Promise<HealthRow[]> {
  if (!supabase) return [];
  try {
    const { data, error } = await supabase
      .from('human_systems_daily')
      .select('*')
      .gte('log_date', daysAgo(days))
      .order('log_date', { ascending: false });
    if (error || !data) return [];
    return data as HealthRow[];
  } catch {
    return [];
  }
}

export interface HumanSystemsData {
  snapshot: CapacitySnapshot;
  debt: RecoveryDebt;
  isLive: boolean;
}

/** Load the panel's data, degrading gracefully to a neutral no-data snapshot. */
export async function loadHumanSystems(): Promise<HumanSystemsData> {
  const rows = await fetchHumanSystemsRows(7);
  const todayRow = rows.find((r) => String(r.log_date) === today()) ?? rows[0] ?? null;
  return {
    snapshot: interpretCapacity(todayRow),
    debt: recoveryDebt(rows),
    isLive: rows.length > 0
  };
}
