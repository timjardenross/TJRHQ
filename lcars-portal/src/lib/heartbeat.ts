import type { SupabaseClient } from '@supabase/supabase-js';
import { createSupabaseServiceRoleClient } from '@/lib/supabase-service-role';

/**
 * TypeScript port of core/platform/heartbeat.py::record_heartbeat().
 *
 * Ported because 3 domains (captains_log, physical_readiness,
 * advisory_sessions) are written from this Next.js app, not Python, and had
 * no TS equivalent of the helper — every domain registered in
 * domain_registry (migration 0071) is supposed to write here on each run
 * attempt (STARSHIP-REDESIGN.md §4), but these 3 never could. See
 * .claude/skills/bot-reviews/fixes-2026-08-09/monitoring-fixes.md, "Not
 * fixed — real write points exist, but in TypeScript" section.
 *
 * domain_heartbeats has RLS restricted to service_role writes only
 * (policy `domain_heartbeats_service_write`, `auth.role() = 'service_role'`)
 * — same reason core_events needs createSupabaseServiceRoleClient(), see
 * core-events.ts. Every caller of recordHeartbeatServerSide() must be a
 * server context (API route handler), never a 'use client' component
 * directly — the browser only ever has the anon key.
 */

export type HeartbeatStatus = 'ok' | 'failed' | 'skipped';

export interface RecordHeartbeatArgs {
  domainKey: string;
  status?: HeartbeatStatus;
  detail?: string | null;
  errorMessage?: string | null;
  latencyMs?: number | null;
}

export interface RecordHeartbeatResult {
  ok: boolean;
  error?: string;
}

/** Structured, greppable failure log — mirrors core-events.ts's logPublishFailure(). */
function logHeartbeatFailure(args: RecordHeartbeatArgs, error: string) {
  console.error('[heartbeat] record_heartbeat failed', {
    domain_key: args.domainKey,
    status: args.status ?? 'ok',
    error,
  });
}

/**
 * Insert one domain_heartbeats row using the given (service-role) client.
 * Never throws — matches record_heartbeat()'s "a heartbeat write must
 * never be able to break the job it's attached to" contract — but returns
 * a result instead of silently discarding failures, and logs every
 * failure so a denied/misconfigured write is observable in server logs.
 */
export async function recordHeartbeat(
  supabase: SupabaseClient,
  args: RecordHeartbeatArgs,
): Promise<RecordHeartbeatResult> {
  const status: HeartbeatStatus = args.status ?? 'ok';
  try {
    const { error } = await supabase.from('domain_heartbeats').insert({
      domain_key: args.domainKey,
      status,
      detail: args.detail ?? null,
      error_message: args.errorMessage ?? null,
      latency_ms: args.latencyMs ?? null,
    });
    if (error) {
      logHeartbeatFailure(args, error.message);
      return { ok: false, error: error.message };
    }
    return { ok: true };
  } catch (exc) {
    const message = exc instanceof Error ? exc.message : String(exc);
    logHeartbeatFailure(args, message);
    return { ok: false, error: message };
  }
}

/** Convenience wrapper matching Python's record_heartbeat_ok(). */
export async function recordHeartbeatOk(
  supabase: SupabaseClient,
  domainKey: string,
  detail?: string | null,
  latencyMs?: number | null,
): Promise<RecordHeartbeatResult> {
  return recordHeartbeat(supabase, { domainKey, status: 'ok', detail, latencyMs });
}

/**
 * Preferred entry point for every Next.js server context (API route,
 * server action) — builds its own service-role client so the caller never
 * has to think about which client is RLS-safe for domain_heartbeats, and if
 * SUPABASE_SERVICE_ROLE_KEY is missing, that failure is logged instead of
 * throwing into the caller's primary business logic. Mirrors
 * publishEventServerSide() in core-events.ts exactly.
 */
export async function recordHeartbeatServerSide(args: RecordHeartbeatArgs): Promise<RecordHeartbeatResult> {
  let supabase: SupabaseClient;
  try {
    supabase = createSupabaseServiceRoleClient();
  } catch (exc) {
    const message = exc instanceof Error ? exc.message : String(exc);
    logHeartbeatFailure(args, message);
    return { ok: false, error: message };
  }
  return recordHeartbeat(supabase, args);
}
