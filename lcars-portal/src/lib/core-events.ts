import type { SupabaseClient } from '@supabase/supabase-js';
import { createSupabaseServiceRoleClient } from '@/lib/supabase-service-role';

/**
 * Thin client for core/platform/event_bus.py's publish_event() contract
 * (core_events table, migration 0055) — MSN-0328 Wave 2. Mirrors the
 * Python function's schema and non-blocking/never-throws behaviour
 * exactly, so TS and Python callers produce indistinguishable rows for
 * the same canonical Captain Brief pipeline to consume.
 *
 * core_events has RLS with zero anon/authenticated policies — only a
 * service-role client can actually write a row. publishEvent()/
 * publishMissionEvent() below accept whatever client the caller passes
 * (kept for callers that already hold a service-role client, e.g. a
 * Python-style server context), but every route in this app should call
 * publishEventServerSide()/publishMissionEventServerSide() instead, which
 * build the service-role client internally so callers can't accidentally
 * pass an anon/SSR client that gets silently denied (the exact bug found
 * in Physical Readiness, mission-lifecycle, and knowledge-library — none
 * of core_events' 20 call sites across this codebase were exempt except
 * the Python ones, which already default to service-role).
 */
export interface PublishEventArgs {
  eventType: string;
  domain: string;
  source: string;
  linkedMissions?: string[];
  linkedDocuments?: string[];
  recommendedAction?: string | null;
  metrics?: Record<string, unknown>;
}

export interface PublishEventResult {
  ok: boolean;
  error?: string;
}

/** Structured, greppable failure log — the thing the old bare `catch {}` never gave anyone. */
function logPublishFailure(args: PublishEventArgs, error: string) {
  console.error('[core-events] publish_event failed', {
    event_type: args.eventType,
    domain: args.domain,
    source: args.source,
    error,
  });
}

/**
 * Insert one core_events row using the given client. Never throws (matches
 * publish_event()'s contract) but now returns a result instead of silently
 * discarding failures, and logs every failure via logPublishFailure() so a
 * denied/misconfigured write is observable in server logs instead of
 * vanishing with no trace.
 */
export async function publishEvent(supabase: SupabaseClient, args: PublishEventArgs): Promise<PublishEventResult> {
  try {
    const { error } = await supabase.from('core_events').insert({
      event_type: args.eventType,
      domain: args.domain,
      source: args.source,
      linked_missions: args.linkedMissions ?? [],
      linked_entities: [],
      linked_documents: args.linkedDocuments ?? [],
      recommended_action: args.recommendedAction ?? null,
      // MSN-0330: optional, matching publish_event()'s own Optional[dict]
      // contract — omitted entirely (not sent as {}) when the caller has
      // nothing structured to add; core_events.metrics defaults to {}
      // server-side (migration 0061).
      ...(args.metrics !== undefined && { metrics: args.metrics }),
    });
    if (error) {
      logPublishFailure(args, error.message);
      return { ok: false, error: error.message };
    }
    return { ok: true };
  } catch (exc) {
    const message = exc instanceof Error ? exc.message : String(exc);
    logPublishFailure(args, message);
    return { ok: false, error: message };
  }
}

/** Convenience wrapper — kept for callers that already hold a service-role (or equivalent) client. */
export async function publishMissionEvent(
  supabase: SupabaseClient,
  args: { eventType: string; missionId: string; fromStatus?: string | null; toStatus: string; source: string },
): Promise<PublishEventResult> {
  return publishEvent(supabase, {
    eventType: args.eventType,
    domain: 'mission-lifecycle',
    source: args.source,
    linkedMissions: [args.missionId],
    recommendedAction: args.fromStatus ? `${args.fromStatus} -> ${args.toStatus}` : args.toStatus,
  });
}

/**
 * Preferred entry point for every Next.js server context (API route,
 * server action). Builds its own service-role client so the caller never
 * has to think about which client is RLS-safe for core_events — and if
 * SUPABASE_SERVICE_ROLE_KEY is missing, that failure is logged too instead
 * of throwing into the caller's primary business logic.
 */
export async function publishEventServerSide(args: PublishEventArgs): Promise<PublishEventResult> {
  let supabase: SupabaseClient;
  try {
    supabase = createSupabaseServiceRoleClient();
  } catch (exc) {
    const message = exc instanceof Error ? exc.message : String(exc);
    logPublishFailure(args, message);
    return { ok: false, error: message };
  }
  return publishEvent(supabase, args);
}

/** publishMissionEvent, but building its own service-role client like publishEventServerSide(). */
export async function publishMissionEventServerSide(
  args: { eventType: string; missionId: string; fromStatus?: string | null; toStatus: string; source: string },
): Promise<PublishEventResult> {
  return publishEventServerSide({
    eventType: args.eventType,
    domain: 'mission-lifecycle',
    source: args.source,
    linkedMissions: [args.missionId],
    recommendedAction: args.fromStatus ? `${args.fromStatus} -> ${args.toStatus}` : args.toStatus,
  });
}
