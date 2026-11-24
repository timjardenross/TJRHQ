// Clustered, tiered incident view (backend: intelligence/incident_clustering.py + delivery_tiers.py, published as read-only snapshot rows by
// tools/intelligence/publish_incident_snapshot.py into intelligence_incident_snapshots - draft migration, NOT applied).
//
// One incident = one entry everywhere. `incident_key` (= tiered_brief.incident_id: 'inc-' + sha1(earliest report id | its subject)[:10]) is the shared dedupe key: the
// Telegram alert payload (intelligence/alert_dispatcher.py), Home's needs-attention, the Decisions inbox and the Intelligence page all use it,
// so the same incident is never shown twice as a different entity. Telegram stays the timely channel; these are the durable, repeatable views.
//
// Flag: INCIDENT_VIEW_V1 (env, read per request, default OFF). Read-only: nothing here writes, acknowledges or sends.

export type IncidentTier = 'IMMEDIATE_ALERT' | 'SCHEDULED_BRIEF' | 'MONITOR' | 'CONTEXT' | 'REFERENCE_RETAIN';
export type IncidentRelation = 'NEW' | 'SUBSEQUENT' | 'RESTORATION_UPDATE' | 'RELATED' | 'HISTORICAL_REFERENCE';

export interface IncidentReport {
  relation: IncidentRelation;
  event_id: string;
  title: string;
  published_at: string | null;
  restoration?: 'full' | 'partial' | null;
}

export interface IncidentRow {
  incident_key: string;
  headline: string;
  tier: IncidentTier;
  restoration_status: string;
  n_reports: number;
  why: string;
  reports: IncidentReport[];
  material_exception: boolean;
  snapshot_at: string;
  last_report_at: string | null;
}

export const INCIDENT_COLUMNS =
  'incident_key,headline,tier,restoration_status,n_reports,why,reports,material_exception,snapshot_at,last_report_at';

export function incidentViewEnabled(env: Record<string, string | undefined> = process.env): boolean {
  return ['1', 'true', 'yes', 'on'].includes((env.INCIDENT_VIEW_V1 ?? '').trim().toLowerCase());
}

/** Needs the Captain's eye: an alert-level incident, or a material exception (material but not alert-fresh, still live). */
export function needsAttention(r: IncidentRow): boolean {
  return r.tier === 'IMMEDIATE_ALERT' || (r.material_exception && r.tier === 'SCHEDULED_BRIEF');
}

/** One entry per incident_key (a re-published snapshot must not duplicate an incident); newest snapshot wins. */
export function dedupeIncidents(rows: IncidentRow[]): IncidentRow[] {
  const byKey = new Map<string, IncidentRow>();
  for (const r of rows) {
    const prev = byKey.get(r.incident_key);
    if (!prev || new Date(r.snapshot_at).getTime() >= new Date(prev.snapshot_at).getTime()) byKey.set(r.incident_key, r);
  }
  const order: Record<string, number> = { IMMEDIATE_ALERT: 0, SCHEDULED_BRIEF: 1, MONITOR: 2, CONTEXT: 3, REFERENCE_RETAIN: 4 };
  return [...byKey.values()].sort(
    (a, b) => (order[a.tier] ?? 9) - (order[b.tier] ?? 9) || (b.last_report_at ?? '').localeCompare(a.last_report_at ?? ''),
  );
}

export function lifecycleSummary(r: IncidentRow): string {
  const n = (rel: IncidentRelation) => r.reports.filter((x) => x.relation === rel).length;
  return [`${n('NEW')} new`, `${n('SUBSEQUENT')} subsequent`, `${n('RESTORATION_UPDATE')} restoration`, `${n('RELATED')} related`].join(' · ');
}

export interface IncidentDecisionItem {
  id: string; // 'inc:<incident_key>'
  incidentKey: string;
  title: string;
  detail: string;
  href: string;
}

export function toDecisionItem(r: IncidentRow): IncidentDecisionItem {
  return {
    id: `inc:${r.incident_key}`,
    incidentKey: r.incident_key,
    title: r.headline,
    detail: `${r.tier === 'IMMEDIATE_ALERT' ? 'Alert-level' : 'Material exception'} · ${r.restoration_status.replace(/_/g, ' ')} · ${r.n_reports} reports`,
    href: `/intelligence#${r.incident_key}`,
  };
}

/** Server side: latest rows from the snapshot table. A missing table or any error is "unavailable", never a thrown 500 and never an empty all-clear. */
export async function fetchIncidentSnapshot(
  sb: { from: (t: string) => any },
  opts: { attentionOnly?: boolean; sinceHours?: number; limit?: number } = {},
): Promise<{ available: boolean; incidents: IncidentRow[] }> {
  try {
    const since = new Date(Date.now() - (opts.sinceHours ?? 72) * 3_600_000).toISOString();
    const { data, error } = await sb
      .from('intelligence_incident_snapshots')
      .select(INCIDENT_COLUMNS)
      .gte('snapshot_at', since)
      .order('snapshot_at', { ascending: false })
      .limit(opts.limit ?? 200);
    if (error) return { available: false, incidents: [] };
    let rows = dedupeIncidents((data ?? []) as IncidentRow[]);
    if (opts.attentionOnly) rows = rows.filter(needsAttention);
    return { available: true, incidents: rows };
  } catch {
    return { available: false, incidents: [] };
  }
}
