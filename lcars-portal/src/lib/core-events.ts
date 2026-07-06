import type { SupabaseClient } from '@supabase/supabase-js';

/**
 * Thin client for core/platform/event_bus.py's publish_event() contract
 * (core_events table, migration 0055) — MSN-0328 Wave 2. Mirrors the
 * Python function's schema and non-blocking/never-throws behaviour
 * exactly, so TS and Python callers produce indistinguishable rows for
 * the same canonical Captain Brief pipeline to consume.
 */
export interface PublishEventArgs {
  eventType: string;
  domain: string;
  source: string;
  linkedMissions?: string[];
  recommendedAction?: string | null;
}

export async function publishEvent(supabase: SupabaseClient, args: PublishEventArgs): Promise<void> {
  try {
    await supabase.from('core_events').insert({
      event_type: args.eventType,
      domain: args.domain,
      source: args.source,
      linked_missions: args.linkedMissions ?? [],
      linked_entities: [],
      linked_documents: [],
      recommended_action: args.recommendedAction ?? null,
    });
  } catch {
    /* non-blocking — matches publish_event()'s own never-raises contract */
  }
}

/** Convenience wrapper for the one domain this Wave actually wires — mission lifecycle. */
export async function publishMissionEvent(
  supabase: SupabaseClient,
  args: { eventType: string; missionId: string; fromStatus?: string | null; toStatus: string; source: string },
): Promise<void> {
  return publishEvent(supabase, {
    eventType: args.eventType,
    domain: 'mission-lifecycle',
    source: args.source,
    linkedMissions: [args.missionId],
    recommendedAction: args.fromStatus ? `${args.fromStatus} -> ${args.toStatus}` : args.toStatus,
  });
}
