// Builds one SourceRow per registry source from the same three tables as
// SOURCE_ROWS_SQL in intelligence/source_effectiveness.py (registry, events,
// source health), via the supabase client the other workbench routes use.
// Read-only. Rows are paged because PostgREST caps a response at 1000 rows.

import type { SourceRow } from '@/lib/sourceEffectiveness';

const PAGE = 1000;
const MAX_PAGES = 30;

async function fetchAll(build: (from: number, to: number) => PromiseLike<{ data: any[] | null; error: { message: string } | null }>, label: string): Promise<any[]> {
  const out: any[] = [];
  for (let p = 0; p < MAX_PAGES; p++) {
    const { data, error } = await build(p * PAGE, p * PAGE + PAGE - 1);
    if (error) throw new Error(`Failed to fetch ${label}: ${error.message}`);
    out.push(...(data ?? []));
    if (!data || data.length < PAGE) break;
  }
  return out;
}

export async function loadSourceRows(sb: any, now: Date = new Date()): Promise<SourceRow[]> {
  const since30 = new Date(now.getTime() - 30 * 86_400_000).toISOString();
  const since7 = new Date(now.getTime() - 7 * 86_400_000).toISOString();

  const registry = await fetchAll(
    (a, b) => sb.from('intelligence_source_registry').select('source_id, source_name, source_type, active').order('source_id').range(a, b),
    'source registry',
  );
  const events = await fetchAll(
    (a, b) => sb.from('intelligence_events').select('event_id, source_id, collected_at').gte('collected_at', since30).order('event_id').range(a, b),
    'source events',
  );
  const health = await fetchAll(
    (a, b) => sb.from('intelligence_source_health').select('source_id, status, checked_at').gte('checked_at', since7).order('checked_at').range(a, b),
    'source health',
  );

  const ev = new Map<string, { n30: number; n7: number; last: string | null }>();
  for (const e of events) {
    const cur = ev.get(e.source_id) ?? { n30: 0, n7: 0, last: null };
    cur.n30++;
    if (e.collected_at >= since7) cur.n7++;
    if (!cur.last || e.collected_at > cur.last) cur.last = e.collected_at;
    ev.set(e.source_id, cur);
  }
  const h = new Map<string, { checks7: number; bad7: number; last: string | null; lastOk: string | null }>();
  for (const r of health) {
    const cur = h.get(r.source_id) ?? { checks7: 0, bad7: 0, last: null, lastOk: null };
    cur.checks7++;
    if (r.status !== 'ok') cur.bad7++;
    if (!cur.last || r.checked_at > cur.last) cur.last = r.checked_at;
    if (r.status === 'ok' && (!cur.lastOk || r.checked_at > cur.lastOk)) cur.lastOk = r.checked_at;
    h.set(r.source_id, cur);
  }

  return registry
    .map((s: any): SourceRow => ({
      source_name: s.source_name,
      source_type: s.source_type,
      active: Boolean(s.active),
      n7: ev.get(s.source_id)?.n7 ?? 0,
      n30: ev.get(s.source_id)?.n30 ?? 0,
      last_event: ev.get(s.source_id)?.last ?? null,
      checks7: h.get(s.source_id)?.checks7 ?? 0,
      bad7: h.get(s.source_id)?.bad7 ?? 0,
      last_check: h.get(s.source_id)?.last ?? null,
      last_ok: h.get(s.source_id)?.lastOk ?? null,
    }))
    .sort((a, b) => Number(b.active) - Number(a.active) || a.source_name.localeCompare(b.source_name));
}
