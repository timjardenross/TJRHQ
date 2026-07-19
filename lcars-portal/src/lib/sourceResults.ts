// MSN-0351 (Operational Workbench Integrity) — honest multi-source fan-out.
//
// Timeline and Search each fetch several Supabase tables independently. When
// one source errors, its rows must not silently vanish into a "no results"
// state that looks identical to a genuine empty result. Each fetcher reports
// whether it succeeded; this helper collects the rows and the list of failed
// source labels so the page can surface a quiet, honest "couldn't check: …"
// note instead of pretending the failed source simply had nothing.

export interface SourceOutcome<T> {
  /** Human-readable source label, shown in the "couldn't check" note. */
  source: string;
  /** False when the underlying fetch errored or rejected. */
  ok: boolean;
  /** Rows returned (empty on failure). */
  items: T[];
}

export interface CollectedResults<T> {
  items: T[];
  /** Labels of sources that failed to load — empty when all succeeded. */
  failed: string[];
}

/**
 * Merge per-source outcomes into a flat item list plus the set of failed
 * source labels. Order of `items` is preserved as given; callers sort after.
 */
export function collectSourceOutcomes<T>(outcomes: SourceOutcome<T>[]): CollectedResults<T> {
  const items = outcomes.flatMap((o) => o.items);
  const failed = outcomes.filter((o) => !o.ok).map((o) => o.source);
  return { items, failed };
}
