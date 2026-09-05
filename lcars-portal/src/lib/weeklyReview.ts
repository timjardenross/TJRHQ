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

// "Newly important" and "Safe to ignore" were removed 2026-09-05 (Weekly
// Review synthesis mission) — the former was a byte-for-byte duplicate of
// urgentThisWeek's computation (no actual week-over-week "newly" logic ever
// existed), the latter counted how many neutral-tone signals returned zero,
// not an evidence-backed ignorable-item count. Both are superseded by
// WeeklyReviewSynthesis's whatChanged/youCanIgnore below, which are
// evidence-backed. openLoops/waitingOn/urgentThisWeek remain as secondary
// diagnostics (brief §21 explicitly permits this), no longer the opening
// experience.
export interface SystemSummary {
  weekStart: string;
  weekEnd: string;
  openLoops: number;
  waitingOn: number;
  urgentThisWeek: number;
  reviewDebtDays: number | null;
  lastCompletedAt: string | null;
}

// ── Synthesis layer (2026-09-05, Weekly Review redesign) ────────────────────
// Everything below is interpretation built server-side (route.ts) on top of
// the existing section/signal data above — no new source-of-truth tables.
// Deterministic/rule-based (mirrors deriveSystemPosture/computeStrategicPosture's
// own no-LLM discipline), not an LLM call — brief allows AI assist but
// doesn't require it.

export type DeltaGlyph = 'down' | 'flat' | 'up' | 'warn' | 'ok';

export interface WeekInReviewLine {
  key: string;
  label: string;
  glyph: DeltaGlyph;
  detail: string;
}

export interface WeekInReview {
  narrative: string;
  lines: WeekInReviewLine[];
}

export interface ChangeItem {
  key: string;
  label: string;
  glyph: DeltaGlyph;
  detail: string;
  /** True when no prior week's data exists to compare against — rendered
   * distinctly from "no change" (brief §29 — never silently convert missing
   * comparison data into reassurance). */
  noHistory: boolean;
}

export interface MatteredItem {
  key: string;
  title: string;
  why: string;
  tone: SignalTone;
  href?: string;
}

export interface LearnedItem {
  key: string;
  title: string;
  lesson: string;
}

/** A carry-forward item can either wrap one specific signal item (reuses the
 * existing "→ Ready Room" createTask() action already wired in SignalRow) or
 * stand alone with its own recommendation text (e.g. the capacity-posture
 * item, which isn't a single record). */
export interface CarryForwardItem {
  key: string;
  title: string;
  detail: string;
  recommendation: string;
  href?: string;
  /** Present only when this item wraps a real signal item — lets the UI
   * reuse the existing SignalRow/ItemRow "→ Ready Room" action verbatim
   * instead of inventing a second action path. */
  signalItem?: SignalItem & { sourceLabel: string; signalLabel: string; tone: SignalTone };
}

export interface WatchItem {
  key: string;
  label: string;
  detail: string;
  /** False when the underlying data genuinely isn't computable yet (e.g.
   * Known Unknowns / Evidence Gaps aren't DB-backed today) — rendered as an
   * honest gap, never a fabricated "no gaps" claim (brief §12/§31). */
  available: boolean;
}

export interface NextWeekPosture {
  posture: string;
  message: string;
  priorities: string[];
  avoid?: string;
}

export interface DomainSynthesis {
  headline: string;
  noActionRequired: boolean;
  detail: string;
}

export interface WeeklyReviewSynthesis {
  weekInReview: WeekInReview;
  whatChanged: ChangeItem[];
  whatMattered: MatteredItem[];
  learned: LearnedItem[];
  carryForward: CarryForwardItem[];
  youCanIgnore: string[];
  watchNextWeek: WatchItem[];
  nextWeek: NextWeekPosture;
  technical: DomainSynthesis;
  health: DomainSynthesis;
}

export interface WeeklyReviewData {
  summary: SystemSummary;
  workbenches: WorkbenchSection[];
  synthesis: WeeklyReviewSynthesis;
  /** Flattened `${sectionKey}:${signalKey}` -> count, for this run — sent
   * back to POST on "Close the Week" so next week's GET can diff against it
   * (see route.ts's fetchStrategicPosture/buildSynthesis doc comments). */
  signalCounts: Record<string, number>;
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

export async function completeWeeklyReview(
  notes: string, summary: SystemSummary, signalCounts: Record<string, number>, nextWeekPostureAccepted: boolean,
): Promise<CompleteResult> {
  try {
    const resp = await fetch('/api/weekly-review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes, summary, signalCounts, nextWeekPostureAccepted }),
    });
    const json = await resp.json();
    if (!resp.ok) return { ok: false, error: json?.error ?? `HTTP ${resp.status}` };
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Failed to complete review.' };
  }
}
