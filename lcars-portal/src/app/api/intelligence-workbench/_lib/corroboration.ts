// Shared corroboration-count lookup — same signal_corroboration query
// pattern already used by credibility/route.ts and source-network/route.ts,
// factored out so today/route.ts, watching/route.ts and library/route.ts
// don't each reimplement it.

export async function fetchCorroborationCounts(sb: any, eventIds: string[]): Promise<Map<string, number>> {
  const counts = new Map<string, number>();
  if (!eventIds.length) return counts;

  const { data, error } = await sb
    .from('signal_corroboration')
    .select('signal_id, corroborating_signal_id')
    .or(`signal_id.in.(${eventIds.join(',')}),corroborating_signal_id.in.(${eventIds.join(',')})`);

  if (error) throw new Error(`Failed to fetch corroborations: ${error.message}`);

  (data ?? []).forEach((c: any) => {
    counts.set(c.signal_id, (counts.get(c.signal_id) || 0) + 1);
    counts.set(c.corroborating_signal_id, (counts.get(c.corroborating_signal_id) || 0) + 1);
  });
  return counts;
}
