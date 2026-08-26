// Emergency Alert Hub — source health API (migration 0174).
//
// Reuses the platform's existing crawl-health mechanism (domain_heartbeats,
// migration 0071 — same one agent-status/route.ts reads) rather than a
// bespoke fetch_logs/crawl_runs table: every emergency_alert_* domain_key
// heartbeats through intelligence/emergency_alerts.py exactly like any
// other scheduled job. This route joins that real health data onto
// alert_sources so the workbench's own Source Health panel is genuinely
// live, not a link-out to the Agent/Job dashboard.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

// alert_sources.source_key -> domain_registry.domain_key (migration 0174).
const SOURCE_DOMAIN_KEYS: Record<string, string> = {
  nsw_rfs: 'emergency_alert_nsw_rfs',
  vic_emergency: 'emergency_alert_vic',
  qld_fire: 'emergency_alert_qld',
  sa_cfs: 'emergency_alert_sa',
  act_esa: 'emergency_alert_act',
  wa_dfes: 'emergency_alert_wa',
  tas_fire: 'emergency_alert_tas',
  nt_securent: 'emergency_alert_nt',
};

export interface EmergencyAlertSourceEntry {
  sourceKey: string;
  jurisdiction: string;
  sourceName: string;
  sourceType: string;
  baseUrl: string;
  feedUrl: string | null;
  active: boolean;
  fetchIntervalMinutes: number;
  notes: string | null;
  status: 'ok' | 'failed' | 'skipped' | 'unknown';
  lastRun: string | null;
  lastAction: string | null;
  alertCount: number;
}

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();

    const [sourcesRes, heartbeatsRes, countsRes] = await Promise.all([
      sb.from('alert_sources').select('*').order('jurisdiction', { ascending: true }),
      sb.from('domain_heartbeats_latest')
        .select('domain_key, status, detail, error_message, checked_at')
        .in('domain_key', Object.values(SOURCE_DOMAIN_KEYS)),
      sb.from('alerts').select('source_key').eq('is_active', true),
    ]);

    if (sourcesRes.error) throw sourcesRes.error;
    if (heartbeatsRes.error) throw heartbeatsRes.error;
    if (countsRes.error) throw countsRes.error;

    const heartbeatByDomainKey = new Map(
      (heartbeatsRes.data ?? []).map((row) => [row.domain_key, row])
    );
    const activeCountBySource = new Map<string, number>();
    for (const row of countsRes.data ?? []) {
      activeCountBySource.set(row.source_key, (activeCountBySource.get(row.source_key) ?? 0) + 1);
    }

    const sources: EmergencyAlertSourceEntry[] = (sourcesRes.data ?? []).map((src) => {
      const domainKey = SOURCE_DOMAIN_KEYS[src.source_key];
      const heartbeat = domainKey ? heartbeatByDomainKey.get(domainKey) : undefined;
      const rawStatus = heartbeat?.status;
      const status: EmergencyAlertSourceEntry['status'] =
        rawStatus === 'ok' || rawStatus === 'failed' || rawStatus === 'skipped' ? rawStatus : 'unknown';

      return {
        sourceKey: src.source_key,
        jurisdiction: src.jurisdiction,
        sourceName: src.source_name,
        sourceType: src.source_type,
        baseUrl: src.base_url,
        feedUrl: src.feed_url,
        active: src.active,
        fetchIntervalMinutes: src.fetch_interval_minutes,
        notes: src.notes,
        status,
        lastRun: heartbeat?.checked_at ?? null,
        lastAction: status === 'failed' ? (heartbeat?.error_message ?? heartbeat?.detail ?? null) : (heartbeat?.detail ?? null),
        alertCount: activeCountBySource.get(src.source_key) ?? 0,
      };
    });

    return NextResponse.json({ sources, fetchedAt: new Date().toISOString() });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Emergency alert source query failed', detail }, { status: 500 });
  }
}
