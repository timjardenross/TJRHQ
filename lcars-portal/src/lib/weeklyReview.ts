'use client';

/**
 * Weekly Review — types + client fetch wrapper.
 *
 * All computation happens server-side in /api/weekly-review (GET), which
 * queries each existing workbench's own tables directly — no mirror/staging
 * tables. This file only holds the shared shape + a thin fetch/complete
 * wrapper, mirroring lib/capture.ts and lib/personalTasks.ts.
 */

export type SignalTone = 'ok' | 'warn' | 'crit' | 'neutral';

export interface SignalItem {
  id: string;
  title: string;
  href?: string;
  meta?: string;
}

export interface Signal {
  key: string;
  label: string;
  count: number;
  tone: SignalTone;
  items: SignalItem[];
  /** True if this signal's data source couldn't be queried (schema drift,
   * table renamed, etc) — shown as "unavailable" rather than a false zero. */
  unavailable?: boolean;
}

export interface WorkbenchSection {
  key: string;
  title: string;
  href: string;
  signals: Signal[];
}

export interface SystemSummary {
  weekStart: string;
  weekEnd: string;
  openLoops: number;
  waitingOn: number;
  urgentThisWeek: number;
  newlyImportant: number;
  noiseToIgnore: number;
  reviewDebtDays: number | null;
  lastCompletedAt: string | null;
}

export interface WeeklyReviewData {
  summary: SystemSummary;
  workbenches: WorkbenchSection[];
}

export async function fetchWeeklyReview(): Promise<WeeklyReviewData | null> {
  try {
    const resp = await fetch('/api/weekly-review', { cache: 'no-store' });
    if (!resp.ok) return null;
    return (await resp.json()) as WeeklyReviewData;
  } catch {
    return null;
  }
}

export interface CompleteResult {
  ok: boolean;
  error?: string;
}

export async function completeWeeklyReview(notes: string, summary: SystemSummary): Promise<CompleteResult> {
  try {
    const resp = await fetch('/api/weekly-review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes, summary }),
    });
    const json = await resp.json();
    if (!resp.ok) return { ok: false, error: json?.error ?? `HTTP ${resp.status}` };
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Failed to complete review.' };
  }
}
