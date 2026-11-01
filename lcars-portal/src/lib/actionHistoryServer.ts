import { supabaseAdmin } from '@/lib/ai-actions';

/**
 * Server-side action-history logging for API route handlers (the actual
 * mutation boundary), as a direct insert into audit_events — same shape/
 * contract as POST /api/action-history (route.ts), just without the
 * self-fetch round trip a route handler would otherwise need to make to
 * call its own API. Mirrors src/lib/taskTelemetry.ts's client-side
 * trackTaskEvent() contract: { action, outcome, details } with details
 * kept to structured identifiers/state only — never secrets, credentials,
 * or raw user-entered free text (see ActionOutcome.tsx's capture-workbench
 * anti-pattern this deliberately avoids replicating).
 *
 * Best-effort: a logging failure never breaks the caller's real mutation.
 * record_id is a top-level details key by convention — briefs/[id]/route.ts
 * and other audit-trail readers filter on details->>record_id.
 */
export type ActionOutcome = 'success' | 'failed' | 'cancelled' | 'retry';

/** Deterministic JSON.stringify with recursively sorted object keys — a
 * naive JSON.stringify comparison against a value round-tripped through
 * Postgres JSONB breaks, because JSONB does not preserve insertion key
 * order. Used to compare a freshly built details object against one just
 * read back from audit_events for dedupe purposes. */
export function stableStringify(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  const keys = Object.keys(value as Record<string, unknown>).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify((value as Record<string, unknown>)[k])}`).join(',')}}`;
}

// Same collapse window as /api/action-history/route.ts's own dedupe: a
// retried call whose action+outcome+details are byte-identical to the
// most recent event within this window is the same idempotent attempt,
// not a new one, so it's collapsed onto the existing row rather than
// spamming a duplicate success event. A non-idempotent retry (e.g. a
// fresh insert with a new record_id) always differs in details and gets
// its own row automatically.
const DEDUPE_WINDOW_MS = 60_000;

export async function logActionHistory(params: {
  action: string;
  outcome: ActionOutcome;
  workbench: string;
  recordId?: string | null;
  details?: Record<string, unknown>;
  missionId?: string | null;
}): Promise<void> {
  try {
    const admin = supabaseAdmin();
    const details = {
      workbench: params.workbench,
      ...(params.recordId ? { record_id: params.recordId } : {}),
      ...(params.details ?? {}),
    };

    const since = new Date(Date.now() - DEDUPE_WINDOW_MS).toISOString();
    const { data: recent } = await admin
      .from('audit_events')
      .select('id,outcome,details')
      .eq('category', 'user_action')
      .eq('actor', 'captain')
      .eq('action', params.action)
      .gte('created_at', since)
      .order('created_at', { ascending: false })
      .limit(1);
    const last = recent?.[0];
    if (last && last.outcome === params.outcome && stableStringify(last.details ?? {}) === stableStringify(details)) {
      return;
    }

    await admin.from('audit_events').insert({
      category: 'user_action',
      actor: 'captain',
      action: params.action,
      outcome: params.outcome,
      details,
      mission_id: params.missionId ?? null,
    });
  } catch {
    // best-effort — never let telemetry failures break the real mutation
  }
}
