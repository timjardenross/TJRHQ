// Weekly Review for HQ Home. The existing review is built from ~15 tables,
// including personal-health and personal-task sections, and its summary counts
// and narrative are summed over every section. HQ therefore never receives that
// payload: the server route below sanitises it first, keeps ONLY non-personal
// sections, recomputes the counts from what is kept, and drops the narrative.

export interface RawSignal { key: string; label: string; count: number; tone: 'ok' | 'warn' | 'crit' | 'neutral'; items?: { id: string; title: string; href?: string; meta?: string }[]; unavailable?: boolean }
export interface RawSection { key: string; title: string; href?: string; signals: RawSignal[] }
export interface RawWeeklyReview {
  summary?: { weekStart?: string; weekEnd?: string; lastCompletedAt?: string | null; reviewDebtDays?: number | null };
  workbenches?: RawSection[];
}

/** Sections that carry personal data (or free-text personal questions). */
export const PERSONAL_SECTIONS = new Set(['human-systems', 'ready-room', 'advisory']);
/** Individual signals inside kept sections that list capture or notebook text. */
export const PERSONAL_SIGNALS = new Set(['chair:unreviewed', 'chair:notes']);

export interface HqWeeklyItem { title: string; href?: string; section: string; tone: 'warn' | 'crit' }
export interface HqWeeklyReview {
  weekStart: string | null;
  weekEnd: string | null;
  lastCompletedAt: string | null;
  reviewDebtDays: number | null;
  looks: number;
  urgent: number;
  items: HqWeeklyItem[];
  /** Section titles that were left out and why, so the omission is visible. */
  excluded: string[];
}

export function sanitiseWeeklyReview(raw: RawWeeklyReview, maxItems = 6): HqWeeklyReview {
  const kept: RawSection[] = [];
  for (const s of raw.workbenches ?? []) {
    if (PERSONAL_SECTIONS.has(s.key)) continue;
    kept.push({ ...s, signals: s.signals.filter((g) => !PERSONAL_SIGNALS.has(`${s.key}:${g.key}`)) });
  }
  let looks = 0;
  let urgent = 0;
  const items: HqWeeklyItem[] = [];
  for (const s of kept) {
    for (const g of s.signals) {
      if (g.unavailable) continue;
      if (g.tone === 'warn') looks += g.count;
      if (g.tone === 'crit') urgent += g.count;
      if (g.tone === 'warn' || g.tone === 'crit') {
        for (const it of g.items ?? []) items.push({ title: it.title, href: it.href, section: s.title, tone: g.tone });
      }
    }
  }
  items.sort((a, b) => (a.tone === b.tone ? 0 : a.tone === 'crit' ? -1 : 1));
  return {
    weekStart: raw.summary?.weekStart ?? null,
    weekEnd: raw.summary?.weekEnd ?? null,
    lastCompletedAt: raw.summary?.lastCompletedAt ?? null,
    reviewDebtDays: raw.summary?.reviewDebtDays ?? null,
    looks,
    urgent,
    items: items.slice(0, maxItems),
    excluded: ['Personal health and personal tasks', 'Advisory questions'],
  };
}
