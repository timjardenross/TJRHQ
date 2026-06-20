/**
 * EDO delivery dashboard data (MSN-EDO-002 QW1).
 *
 * Reads the `mission_delivery` + `mission_delivery_metrics` views (migration
 * 0023). When Supabase is unavailable, returns empty/zero so the panel renders
 * a graceful "no data" state. Bottleneck detection mirrors the Python engine
 * (lib/delivery/analysis.py).
 */

import { supabase } from './supabase';
import type { StatusTone } from './types';

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
  if (!supabase) return [];
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
  if (!supabase) return null;
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

export interface DeliveryData {
  rows: DeliveryRow[];
  metrics: DeliveryMetrics | null;
  bottlenecks: Bottleneck[];
  isLive: boolean;
}

export async function loadDelivery(): Promise<DeliveryData> {
  const [rows, metrics] = await Promise.all([fetchDeliveryRows(), fetchDeliveryMetrics()]);
  return { rows, metrics, bottlenecks: detectBottlenecks(rows), isLive: rows.length > 0 };
}
