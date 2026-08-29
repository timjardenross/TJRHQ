import type { SupabaseClient } from '@supabase/supabase-js';

// Council follow-up 2026-08-29 (permissions/mission-approval-gates
// scoping): the live governed-approval routes (build-request AI-actions,
// health-OSINT curation; knowledge-library document decide deliberately
// excluded — see its own decideDocument(), which has a genuinely
// different two-tier eligibility shape and heavy domain side effects,
// not a fit for this) each independently hand-rolled the same
// fetch-row -> check-eligibility -> structured-error prefix before doing
// their actual (and legitimately different) mutation. This is that
// shared prefix, not a shared mutation - every caller still owns its own
// write.

export type GovernedFetchResult<T> =
  | { ok: true; row: T }
  | { ok: false; status: number; error: string };

export interface EligibilityCheck<T> {
  /** Return true if `row` is in a state eligible for the caller's action. */
  predicate: (row: T) => boolean;
  /** HTTP status to return when predicate() is false - typically 409
   * (wrong state) or 400 (not applicable to this row at all). */
  ineligibleStatus: number;
  ineligibleMessage: (row: T) => string;
}

/** Fetch one row by id and optionally check it's in an eligible state
 * before a caller proceeds to mutate it. Never throws - every failure
 * mode (lookup error, missing row, ineligible state) comes back as a
 * typed, structured result the caller maps to its own response shape. */
export async function fetchGovernedRow<T>(
  client: SupabaseClient,
  table: string,
  idColumn: string,
  id: string,
  select: string,
  eligibility?: EligibilityCheck<T>,
): Promise<GovernedFetchResult<T>> {
  const { data, error } = await client
    .from(table)
    .select(select)
    .eq(idColumn, id)
    .maybeSingle();

  if (error) {
    return { ok: false, status: 500, error: `Lookup failed: ${error.message}` };
  }
  if (!data) {
    return { ok: false, status: 404, error: 'Not found' };
  }

  const row = data as T;
  if (eligibility && !eligibility.predicate(row)) {
    return { ok: false, status: eligibility.ineligibleStatus, error: eligibility.ineligibleMessage(row) };
  }

  return { ok: true, row };
}
