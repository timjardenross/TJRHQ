// Source Health API (Agent & Job Status workbench, Phase 3 uplift).
//
// This workbench is the SOLE owner of source-health diagnostics — Technical
// OSINT and Health OSINT link here instead of duplicating this view.
//
// Technical (intelligence) sources: intelligence_source_registry +
// intelligence_source_health. The health table has no "latest per source"
// view, so we pull the most recent ~1500 rows ordered by checked_at desc
// and reduce to one row per source_id in JS — confirmed against the live
// data (2026-09-06) that only ~106 of 163 registered sources appear even
// in the most recent 1000 rows, so anything not in this window is reported
// as "no recent health check" rather than fabricated as healthy.
//
// Health (health_signals) sources: health_source_registry +
// health_source_fetch_config. Only 11 of 308 registered health sources have
// a fetch_config row (confirmed live) — the rest are manually-curated/seed
// sources with no automated cadence at all. Those are reported in a
// separate `uncadenced` bucket, not silently counted as healthy or hidden.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

export type SourceStatus = 'healthy' | 'degraded' | 'delayed' | 'failing' | 'unknown';

export interface TechnicalSourceRow {
  sourceId: string;
  sourceName: string;
  sourceType: string;
  category: string;
  pipeline: 'technical';
  status: SourceStatus;
  lastCheckedAt: string | null;
  errorMessage: string | null;
  active: boolean;
}

export interface HealthSourceRow {
  sourceId: string;
  sourceName: string;
  sourceType: string | null;
  pipeline: 'health';
  status: SourceStatus;
  cadence: string | null;
  lastFetch: string | null;
  lastFetchStatus: string | null;
  lastFetchMessage: string | null;
  hasFetchConfig: boolean;
  active: boolean;
}

/** Cadence label -> maximum acceptable gap before we call it "delayed".
 *  Generous (2x cadence) so a job running a few hours late doesn't flap. */
const CADENCE_THRESHOLD_MS: Record<string, number> = {
  daily: 2 * 24 * 3600_000,
  '2x/week': 4 * 24 * 3600_000,
  '3x/week': 3 * 24 * 3600_000,
  weekly: 10 * 24 * 3600_000,
};

function technicalStatus(raw: string | undefined): SourceStatus {
  switch (raw) {
    case 'ok': return 'healthy';
    case 'stale': return 'delayed';
    case 'degraded': return 'degraded';
    case 'skipped': return 'degraded';
    case 'failed': return 'failing';
    default: return 'unknown';
  }
}

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();

    // ── Technical (intelligence) sources ──────────────────────────────────
    const { data: technicalRegistry, error: regErr } = await sb
      .from('intelligence_source_registry')
      .select('source_id, source_name, source_type, category, active')
      .order('source_name', { ascending: true });
    if (regErr) throw regErr;

    const { data: recentHealth, error: healthErr } = await sb
      .from('intelligence_source_health')
      .select('source_id, status, checked_at, error_message')
      .order('checked_at', { ascending: false })
      .limit(1500);
    if (healthErr) throw healthErr;

    const latestBySource = new Map<string, { status: string; checked_at: string; error_message: string | null }>();
    for (const row of recentHealth ?? []) {
      if (!latestBySource.has(row.source_id)) latestBySource.set(row.source_id, row);
    }

    const technical: TechnicalSourceRow[] = (technicalRegistry ?? []).map((s: any) => {
      const latest = latestBySource.get(s.source_id);
      return {
        sourceId: s.source_id,
        sourceName: s.source_name,
        sourceType: s.source_type,
        category: s.category,
        pipeline: 'technical',
        status: latest ? technicalStatus(latest.status) : 'unknown',
        lastCheckedAt: latest?.checked_at ?? null,
        errorMessage: latest?.error_message ?? null,
        active: s.active,
      };
    });

    // ── Health sources ─────────────────────────────────────────────────────
    const { data: healthRegistry, error: hRegErr } = await sb
      .from('health_source_registry')
      .select('source_id, source_name, source_type')
      .order('source_name', { ascending: true });
    if (hRegErr) throw hRegErr;

    const { data: fetchConfigs, error: fcErr } = await sb
      .from('health_source_fetch_config')
      .select('source_id, cadence, last_fetch, last_fetch_status, last_fetch_message, active');
    if (fcErr) throw fcErr;

    const fetchConfigBySource = new Map<string, any>();
    for (const row of fetchConfigs ?? []) fetchConfigBySource.set(row.source_id, row);

    const health: HealthSourceRow[] = (healthRegistry ?? []).map((s: any) => {
      const cfg = fetchConfigBySource.get(s.source_id);
      if (!cfg) {
        return {
          sourceId: s.source_id,
          sourceName: s.source_name,
          sourceType: s.source_type,
          pipeline: 'health',
          status: 'unknown',
          cadence: null,
          lastFetch: null,
          lastFetchStatus: null,
          lastFetchMessage: null,
          hasFetchConfig: false,
          active: true,
        };
      }

      let status: SourceStatus;
      if (cfg.last_fetch_status === 'failed') {
        status = 'failing';
      } else if (!cfg.last_fetch) {
        status = 'unknown';
      } else {
        const ageMs = Date.now() - new Date(cfg.last_fetch).getTime();
        const threshold = CADENCE_THRESHOLD_MS[cfg.cadence] ?? CADENCE_THRESHOLD_MS.weekly;
        status = ageMs > threshold ? 'delayed' : 'healthy';
      }

      return {
        sourceId: s.source_id,
        sourceName: s.source_name,
        sourceType: s.source_type,
        pipeline: 'health',
        status,
        cadence: cfg.cadence ?? null,
        lastFetch: cfg.last_fetch ?? null,
        lastFetchStatus: cfg.last_fetch_status ?? null,
        lastFetchMessage: cfg.last_fetch_message ?? null,
        hasFetchConfig: true,
        active: cfg.active ?? true,
      };
    });

    const summarize = (rows: Array<{ status: SourceStatus }>) => ({
      healthy: rows.filter((r) => r.status === 'healthy').length,
      degraded: rows.filter((r) => r.status === 'degraded' || r.status === 'delayed').length,
      failing: rows.filter((r) => r.status === 'failing').length,
      unknown: rows.filter((r) => r.status === 'unknown').length,
      total: rows.length,
    });

    return NextResponse.json({
      fetchedAt: new Date().toISOString(),
      technical,
      health: health.filter((h) => h.hasFetchConfig),
      healthUncadenced: health.filter((h) => !h.hasFetchConfig).length,
      summary: {
        technical: summarize(technical),
        health: summarize(health.filter((h) => h.hasFetchConfig)),
      },
      note: `${health.filter((h) => !h.hasFetchConfig).length} of ${health.length} registered health sources have no automated fetch cadence tracked (health_source_fetch_config) — they are manually curated/seed sources, not shown as failing or healthy.`,
    });
  } catch (err) {
    console.error('[agent-status-workbench/sources] read failed:', err);
    return NextResponse.json(
      { error: 'sources_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
