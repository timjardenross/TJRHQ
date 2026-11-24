// Activity history in HQ Work: recent mission state changes and execution events, read from
// the same tables the Timeline workbench reads (RLS applies). Personal sources (check-ins, the
// journal, personal captures) are deliberately excluded.
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

export interface HqActivity { id: string; title: string; detail: string | null; at: string; needsAction: boolean }

interface Transition { id: string | number; mission_id: string; from_state: string | null; to_state: string; actor: string | null; created_at: string }
interface ExecEvent { id: string | number; status: string; mission_id: string | null; created_at: string }

const ACTION_WORDS = new Set(['blocked', 'failed', 'error', 'pending', 'review', 'queued']);

export const mapTransition = (t: Transition): HqActivity => ({
  id: `mst-${t.id}`, title: `${t.mission_id}: ${t.from_state ?? '?'} to ${t.to_state}`, detail: t.actor ? `by ${t.actor}` : null,
  at: t.created_at, needsAction: ACTION_WORDS.has(t.to_state.toLowerCase()),
});
export const mapExecEvent = (e: ExecEvent): HqActivity => ({
  id: `ev-${e.id}`, title: `${e.mission_id ?? 'System'}: ${e.status}`, detail: null, at: e.created_at, needsAction: ACTION_WORDS.has(e.status.toLowerCase()),
});

export function mergeActivity(a: HqActivity[], b: HqActivity[], limit = 30): HqActivity[] {
  return [...a, ...b].sort((x, y) => (x.at < y.at ? 1 : -1)).slice(0, limit);
}

export async function loadActivity(days = 14): Promise<{ items: HqActivity[]; unavailable: string[] }> {
  const sb = createSupabaseBrowserClient();
  const since = new Date(Date.now() - days * 86_400_000).toISOString();
  const unavailable: string[] = [];
  const [tr, ev] = await Promise.all([
    sb.from('mission_state_transitions').select('id, mission_id, from_state, to_state, actor, created_at').gte('created_at', since).order('created_at', { ascending: false }).limit(30),
    sb.from('mission_execution_events').select('id, status, mission_id, created_at').gte('created_at', since).order('created_at', { ascending: false }).limit(20),
  ]);
  if (tr.error) unavailable.push('Mission changes');
  if (ev.error) unavailable.push('Execution events');
  return {
    items: mergeActivity(((tr.data ?? []) as Transition[]).map(mapTransition), ((ev.data ?? []) as ExecEvent[]).map(mapExecEvent)),
    unavailable,
  };
}
