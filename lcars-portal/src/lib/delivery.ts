/**
 * EDO delivery dashboard data (MSN-EDO-002 QW1).
 *
 * Reads the `mission_delivery` + `mission_delivery_metrics` views (migration
 * 0023). When Supabase is unavailable, returns empty/zero so the panel renders
 * a graceful "no data" state. Bottleneck detection mirrors the Python engine
 * (lib/delivery/analysis.py).
 */

import { createSupabaseBrowserClient } from './supabase-browser';
import type { StatusTone } from './types';

// Session-aware client (2026-07-18): mission_delivery/mission_delivery_metrics
// have never granted anon any privilege at all (checked live via
// information_schema.table_privileges - only authenticated/postgres/
// service_role) - this file's queries never worked through the plain anon
// client, on any night, independent of tonight's RLS changes elsewhere.
// Same fix as lib/ros-data.ts/lib/human-systems.ts. Constructed fresh per
// call, matching every other caller in this codebase.
function client() {
  return createSupabaseBrowserClient();
}

export interface DeliveryRow {
  title: string;
  delivery_state: string;
  age_days: number;
  pr_url: string | null;
  priority_norm: string;
  task_type_norm: string;
}

export interface DeliveryMetrics {
  total: number;
  open_count: number;
  closed_count: number;
  blocked_count: number;
  with_pr: number;
  with_outcome: number;
  rework_count: number;
  avg_cycle_days: number | null;
}

export interface Bottleneck {
  title: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  detail: string;
}

export const OPEN_STATES = ['proposed', 'planned', 'in_progress', 'in_review', 'validated', 'blocked'];

export const STATE_TONE: Record<string, StatusTone> = {
  proposed: 'neutral',
  planned: 'command',
  in_progress: 'medical',
  in_review: 'command',
  validated: 'status',
  blocked: 'operations',
  closed: 'status',
  archived: 'neutral'
};

export async function fetchDeliveryRows(): Promise<DeliveryRow[]> {
  const supabase = client();
  try {
    const { data, error } = await supabase
      .from('mission_delivery')
      .select('title, delivery_state, age_days, pr_url, priority_norm, task_type_norm')
      .order('age_days', { ascending: false });
    if (error || !data) return [];
    return data as DeliveryRow[];
  } catch {
    return [];
  }
}

export async function fetchDeliveryMetrics(): Promise<DeliveryMetrics | null> {
  const supabase = client();
  try {
    const { data, error } = await supabase.from('mission_delivery_metrics').select('*').limit(1);
    if (error || !data || !data.length) return null;
    return data[0] as DeliveryMetrics;
  } catch {
    return null;
  }
}

/** Mirror of analysis.detect_bottlenecks (condensed). */
export function detectBottlenecks(rows: DeliveryRow[]): Bottleneck[] {
  const out: Bottleneck[] = [];
  for (const r of rows) {
    const st = r.delivery_state;
    const age = r.age_days ?? 0;
    if (st === 'closed' || st === 'archived') continue;
    if (st === 'blocked') out.push({ title: r.title, severity: 'critical', detail: `Blocked for ${age}d.` });
    else if (st === 'planned' && age > 3)
      out.push({ title: r.title, severity: age > 7 ? 'high' : 'medium', detail: `Planned, not started for ${age}d.` });
    else if (st === 'in_progress' && age > 6)
      out.push({ title: r.title, severity: 'high', detail: `In progress ${age}d without review.` });
    else if (st === 'in_review' && age > 1)
      out.push({ title: r.title, severity: 'medium', detail: `Awaiting review ${age}d.` });
    else if (st === 'validated' && age > 1)
      out.push({ title: r.title, severity: 'medium', detail: `Validated, awaiting closure ${age}d.` });
    if (st === 'in_review' && !(r.pr_url ?? '').trim())
      out.push({ title: r.title, severity: 'high', detail: 'In review with no PR/evidence.' });
  }
  const order = { critical: 0, high: 1, medium: 2, low: 3 };
  return out.sort((a, b) => order[a.severity] - order[b.severity]);
}

// ── Control Tower (MSN-EDO-003 WP2) — risk, capacity, constraint ──────────────

export interface MissionRisk {
  title: string;
  score: number;
  level: 'high' | 'medium' | 'low';
}

const STATE_BASE: Record<string, number> = {
  blocked: 80, in_review: 50, in_progress: 40, planned: 30, validated: 25, proposed: 20
};

export function deliveryRisk(r: DeliveryRow): MissionRisk {
  const st = r.delivery_state;
  const age = r.age_days ?? 0;
  let score = STATE_BASE[st] ?? 20;
  if (age > 14) score += 30;
  else if (age > 7) score += 20;
  if ((st === 'in_progress' || st === 'in_review') && !(r.pr_url ?? '').trim()) score += 15;
  if (['p0', 'p1'].includes((r.priority_norm ?? '').toLowerCase())) score += 10;
  score = Math.max(0, Math.min(100, score));
  return { title: r.title, score, level: score >= 70 ? 'high' : score >= 40 ? 'medium' : 'low' };
}

export interface ControlTower {
  topRisks: MissionRisk[];
  highRiskCount: number;
  constraint: string | null;
  constraintCount: number;
  engWip: number;
}

export function controlTower(rows: DeliveryRow[]): ControlTower {
  const open = rows.filter((r) => OPEN_STATES.includes(r.delivery_state));
  const risks = open.map(deliveryRisk).sort((a, b) => b.score - a.score);
  const counts: Record<string, number> = {};
  open.forEach((r) => (counts[r.delivery_state] = (counts[r.delivery_state] ?? 0) + 1));
  const constraint = Object.keys(counts).sort((a, b) => counts[b] - counts[a])[0] ?? null;
  const engWip = rows.filter(
    (r) => /engineer/.test(r.task_type_norm ?? '') && ['in_progress', 'in_review'].includes(r.delivery_state)
  ).length;
  return {
    topRisks: risks.slice(0, 5),
    highRiskCount: risks.filter((r) => r.level === 'high').length,
    constraint,
    constraintCount: constraint ? counts[constraint] : 0,
    engWip
  };
}

export interface DeliveryData {
  rows: DeliveryRow[];
  metrics: DeliveryMetrics | null;
  bottlenecks: Bottleneck[];
  tower: ControlTower;
  isLive: boolean;
}

export async function loadDelivery(): Promise<DeliveryData> {
  const [rows, metrics] = await Promise.all([fetchDeliveryRows(), fetchDeliveryMetrics()]);
  return {
    rows,
    metrics,
    bottlenecks: detectBottlenecks(rows),
    tower: controlTower(rows),
    isLive: rows.length > 0
  };
}
