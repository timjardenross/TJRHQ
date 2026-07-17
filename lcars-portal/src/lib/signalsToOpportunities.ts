// Phase 1C Communications — signal -> opportunity batch conversion.
// Pure/testable core for POST /api/content/signals-to-opportunities.
// Mirrors core/content/signal_opportunity_converter.py (the CLI/cron
// entry point for the same logic); the two must stay behaviourally
// identical. Kept here, not inline in the route, so it can be unit
// tested against a mocked Supabase client — matches the lib/ +
// route.ts split used by decide.ts, engineering-queue.ts, etc.

export type SignalRow = {
  id?: string;
  event_id_text: string | null;
  raw_title: string | null;
  pillar_key: string | null;
  rank_score?: number;
  domain: string | null;
  suggested_angle: string | null;
};

export type OpportunityRow = {
  title: string;
  pillar: string | null;
  source_kind: 'signal';
  source_ref: string;
  signal_source_id: string;
  classification: 'publishable';
  status: 'opportunity';
  format: string;
  notes: string | null;
};

export const DOMAIN_FORMAT_DEFAULT: Record<string, string> = {
  health: 'case_study',
  operational: 'executive_insight',
};

export interface BatchResult {
  domain: string | null;
  min_rank_score: number;
  status: 'no_signals' | 'failed' | 'completed';
  requested: number;
  created: number;
  signal_ids: string[];
  opportunity_ids: string[];
  error?: string;
}

/**
 * Validate a candidate signal batch and build the comms_content rows to
 * insert. Pure — no I/O. All-or-nothing: any invalid signal produces a
 * non-empty `errors` array and the caller must abort the whole batch
 * rather than insert the valid subset.
 */
export function buildOpportunityRows(signals: SignalRow[]): {
  rows: OpportunityRow[];
  errors: string[];
  signalIds: string[];
} {
  const errors: string[] = [];
  const rows: OpportunityRow[] = [];
  const signalIds: string[] = [];

  for (const s of signals) {
    if (!s.raw_title || !s.event_id_text) {
      errors.push(`signal ${s.id ?? '?'}: missing raw_title or event_id_text`);
      continue;
    }
    rows.push({
      title: s.raw_title,
      pillar: s.pillar_key,
      source_kind: 'signal',
      source_ref: s.event_id_text,
      signal_source_id: s.event_id_text,
      classification: 'publishable',
      status: 'opportunity',
      format: DOMAIN_FORMAT_DEFAULT[s.domain ?? ''] ?? 'executive_insight',
      notes: s.suggested_angle,
    });
    signalIds.push(s.event_id_text);
  }

  return { rows, errors, signalIds };
}

// Minimal shape of the Supabase-js query builder methods this module needs —
// lets tests supply a lightweight mock instead of the real client.
export interface SupabaseLike {
  from(table: string): {
    select(cols: string): any;
    insert(rows: unknown[]): any;
  };
}

export interface CreateOpportunitiesParams {
  signalIds?: string[] | null;
  limit?: number;
  minRankScore?: number;
  domain?: 'health' | 'operational' | null;
}

export async function createOpportunitiesFromSignals(
  sb: SupabaseLike,
  { signalIds = null, limit = 5, minRankScore = 0.7, domain = null }: CreateOpportunitiesParams,
): Promise<BatchResult> {
  const base = { domain, min_rank_score: minRankScore };

  let query = sb
    .from('content_signals')
    .select('id,event_id_text,raw_title,pillar_key,rank_score,domain,suggested_angle')
    .eq('suppressed', false);

  if (signalIds && signalIds.length > 0) {
    query = query.in('event_id_text', signalIds);
  } else {
    query = query.gte('rank_score', minRankScore).order('rank_score', { ascending: false }).limit(limit);
    if (domain) query = query.eq('domain', domain);
  }

  const { data: signals, error: fetchErr } = await query;
  if (fetchErr) throw fetchErr;

  if (signalIds && signalIds.length > 0 && signals && signals.length !== signalIds.length) {
    // Some selected signals were suppressed/removed since the UI loaded them — abort
    // rather than silently create a partial batch of a different size than requested.
    return {
      ...base,
      status: 'failed',
      requested: signalIds.length,
      created: 0,
      signal_ids: [],
      opportunity_ids: [],
      error: `${signalIds.length - (signals?.length ?? 0)} selected signal(s) are no longer eligible (suppressed or removed) — batch not created`,
    };
  }

  if (!signals || signals.length === 0) {
    return { ...base, status: 'no_signals', requested: 0, created: 0, signal_ids: [], opportunity_ids: [] };
  }

  const { rows, errors, signalIds: writtenSignalIds } = buildOpportunityRows(signals);

  if (errors.length > 0) {
    return {
      ...base,
      status: 'failed',
      requested: signals.length,
      created: 0,
      signal_ids: [],
      opportunity_ids: [],
      error: errors.join('; '),
    };
  }

  const { data: created, error: insertErr } = await sb.from('comms_content').insert(rows).select('id');

  if (insertErr) {
    return {
      ...base,
      status: 'failed',
      requested: signals.length,
      created: 0,
      signal_ids: writtenSignalIds,
      opportunity_ids: [],
      error: `batch insert failed — 0 opportunities created, entire batch rolled back: ${insertErr.message}`,
    };
  }

  return {
    ...base,
    status: 'completed',
    requested: signals.length,
    created: created?.length ?? 0,
    signal_ids: writtenSignalIds,
    opportunity_ids: (created ?? []).map((r: { id: string }) => r.id),
  };
}
