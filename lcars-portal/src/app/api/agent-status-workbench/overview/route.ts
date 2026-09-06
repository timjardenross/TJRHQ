// System Health overview API (Agent & Job Status workbench, Phase 3 uplift).
//
// Backs the workbench's default landing tab: a single "is HQ's machinery
// okay" verdict plus the three summary strips (Sources / Pipeline / Jobs)
// that link into the deeper tabs. Combines three already-governed sources
// of truth, all read-only:
//   - domain_heartbeats_latest (via lib/agentStatusJobs) for job health
//   - intelligence_source_health_latest (migration 0190) / health_source_fetch_config for source health
//   - the Phase 26 views (migration 0187) for per-pipeline-stage health
//
// 2026-09-06 fix: technical source health now reads the exact latest-per-
// source view instead of a top-1500-rows-deduped-in-JS approach, which
// could silently drop a failing source from Needs Attention if its most
// recent check fell outside that window. Retired sources (active=false in
// intelligence_source_registry) are also excluded from Needs Attention —
// their last-known status before retirement would otherwise generate a
// permanent, un-actionable "failing" card.
//
// No new scoring logic: pipeline stage health below is a pragmatic
// tri-state derived from the same counts humans would read off the Phase 26
// views by eye, not a new algorithm layered on top of disposition.py.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { fetchAgentStatusEntries, NON_LIVE_DOMAIN_KEYS, type AgentStatusEntry } from '@/lib/agentStatusJobs';

type StageTone = 'ok' | 'warn' | 'crit' | 'unknown';

interface StageResult {
  key: string;
  label: string;
  tone: StageTone;
  detail: string;
}

interface NeedsAttentionCard {
  kind: 'job' | 'source';
  pipeline?: 'technical' | 'health';
  title: string;
  detail: string;
  href: string;
}

function jobStatusByKey(jobs: AgentStatusEntry[]): Map<string, AgentStatusEntry> {
  const m = new Map<string, AgentStatusEntry>();
  for (const j of jobs) m.set(j.domainKey, j);
  return m;
}

/** Tri-state for one pipeline stage: 'crit' if a feeding job has failed,
 *  'unknown' if there's simply no data for today yet, else 'ok'/'warn'
 *  based on whether the mapped view counts are flowing. */
function stageHealth(
  key: string,
  label: string,
  feedingJobKeys: string[],
  jobs: Map<string, AgentStatusEntry>,
  observedCount: number | null,
  discoveredToday: number,
  notObservable = false,
): StageResult {
  const failedJob = feedingJobKeys.map((k) => jobs.get(k)).find((j) => j?.status === 'failed');
  if (failedJob) {
    return { key, label, tone: 'crit', detail: `Feeding job "${failedJob.label}" is failing: ${failedJob.lastAction ?? 'no detail'}` };
  }
  if (notObservable) {
    return { key, label, tone: 'unknown', detail: 'Not exposed by the Phase 26 observability views yet — job health only.' };
  }
  if (discoveredToday === 0) {
    return { key, label, tone: 'unknown', detail: 'No items discovered today yet.' };
  }
  if (observedCount === null || observedCount === 0) {
    return { key, label, tone: 'warn', detail: 'Discovery is flowing but this stage shows zero today — may be pre-rollout NULL or a real stall, worth a look.' };
  }
  return { key, label, tone: 'ok', detail: `${observedCount} today.` };
}

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();

    const [jobs, techQuality, healthQuality, techSources, activeTechSourceIds, healthFetchConfigs] = await Promise.all([
      fetchAgentStatusEntries(sb),
      sb.from('intelligence_ingestion_quality_daily').select('*').order('day', { ascending: false }).limit(1),
      sb.from('health_ingestion_quality_daily').select('*').order('day', { ascending: false }).limit(1),
      sb.from('intelligence_source_health_latest').select('source_id, status, checked_at, error_message'),
      sb.from('intelligence_source_registry').select('source_id').eq('active', true),
      sb.from('health_source_fetch_config').select('source_id, cadence, last_fetch, last_fetch_status, last_fetch_message, health_source_registry(source_name)'),
    ]);

    if (techQuality.error) throw techQuality.error;
    if (healthQuality.error) throw healthQuality.error;
    if (techSources.error) throw techSources.error;
    if (activeTechSourceIds.error) throw activeTechSourceIds.error;
    if (healthFetchConfigs.error) throw healthFetchConfigs.error;

    const jobsByKey = jobStatusByKey(jobs);
    const t = techQuality.data?.[0] ?? null;
    const h = healthQuality.data?.[0] ?? null;

    // ── Pipeline health stages ────────────────────────────────────────────
    const technicalStages: StageResult[] = [
      stageHealth('discovery', 'Discovery', ['intelligence_collection', 'intraday_status_collection'], jobsByKey, t?.discovered ?? null, t?.discovered ?? 0),
      stageHealth('parsing', 'Parsing', ['intelligence_collection', 'intraday_status_collection'], jobsByKey, t?.discovered ?? null, t?.discovered ?? 0, true),
      stageHealth('relevance_gate', 'Relevance Gate', ['intelligence_suppression_audit'], jobsByKey, (t?.not_relevant ?? 0) + (t?.low_confidence ?? 0) + (t?.relevant ?? 0), t?.discovered ?? 0),
      stageHealth('deduplication', 'Deduplication', [], jobsByKey, t?.deduplicated ?? null, t?.discovered ?? 0),
      stageHealth('scoring', 'Scoring', ['evolved_captain_insight_generation'], jobsByKey, (t?.relevant ?? 0) + (t?.not_relevant ?? 0) + (t?.low_confidence ?? 0), t?.discovered ?? 0),
      stageHealth('disposition', 'Disposition', [], jobsByKey, (t?.escalate ?? 0) + (t?.brief ?? 0) + (t?.watch ?? 0) + (t?.reference ?? 0) + (t?.suppress ?? 0), t?.discovered ?? 0),
    ];

    const healthStages: StageResult[] = [
      stageHealth('discovery', 'Discovery', ['health_osint_weekly_fetch'], jobsByKey, h?.discovered ?? null, h?.discovered ?? 0),
      stageHealth('parsing', 'Parsing', ['health_osint_weekly_fetch'], jobsByKey, h?.discovered ?? null, h?.discovered ?? 0, true),
      stageHealth('relevance_gate', 'Relevance Gate', [], jobsByKey, (h?.not_relevant ?? 0) + (h?.low_confidence ?? 0) + (h?.relevant ?? 0), h?.discovered ?? 0),
      stageHealth('study_clustering', 'Study Clustering', [], jobsByKey, null, h?.discovered ?? 0, true),
      stageHealth('evidence_scoring', 'Evidence Scoring', [], jobsByKey, h?.evidence_contribution_scored ?? null, h?.discovered ?? 0),
      stageHealth('curation', 'Curation', ['health_osint_auto_curation'], jobsByKey, null, h?.discovered ?? 0, true),
    ];

    // ── Needs Attention ────────────────────────────────────────────────────
    const attention: NeedsAttentionCard[] = [];

    for (const j of jobs) {
      if (j.status !== 'failed' || NON_LIVE_DOMAIN_KEYS.has(j.domainKey)) continue;
      attention.push({
        kind: 'job',
        title: j.label,
        detail: j.lastAction ?? 'Failed — no detail recorded.',
        href: '/agent-status-workbench?tab=jobs',
      });
    }

    // Retired sources (active=false) are excluded — their last-known status
    // before retirement would otherwise generate a permanent, un-actionable
    // "failing" card and inflate the source-health summary strip forever.
    const activeIds = new Set((activeTechSourceIds.data ?? []).map((r) => r.source_id));
    const latestTechBySource = new Map<string, { status: string; checked_at: string; error_message: string | null }>();
    for (const row of techSources.data ?? []) {
      if (activeIds.has(row.source_id)) latestTechBySource.set(row.source_id, row);
    }
    const failingTechByMessage = new Map<string, number>();
    for (const row of latestTechBySource.values()) {
      if (row.status !== 'failed') continue;
      const msg = row.error_message ?? 'Unknown error';
      failingTechByMessage.set(msg, (failingTechByMessage.get(msg) ?? 0) + 1);
    }
    for (const [msg, count] of failingTechByMessage.entries()) {
      attention.push({
        kind: 'source',
        pipeline: 'technical',
        title: count > 1 ? `${count} technical sources failing` : '1 technical source failing',
        detail: msg,
        href: '/agent-status-workbench?tab=sources',
      });
    }

    for (const row of healthFetchConfigs.data ?? []) {
      if (row.last_fetch_status !== 'failed') continue;
      const name = (row as any).health_source_registry?.source_name ?? 'Unknown source';
      attention.push({
        kind: 'source',
        pipeline: 'health',
        title: `${name} — FAILING`,
        detail: `${row.last_fetch_message ?? 'No detail recorded'}. Last attempt: ${row.last_fetch ?? 'never'}.`,
        href: '/agent-status-workbench?tab=sources',
      });
    }

    // ── Summary strips ──────────────────────────────────────────────────────
    const technicalSourceStatuses = Array.from(latestTechBySource.values()).map((r) => r.status);
    const sourcesSummary = {
      technical: {
        healthy: technicalSourceStatuses.filter((s) => s === 'ok').length,
        degraded: technicalSourceStatuses.filter((s) => s === 'degraded' || s === 'stale' || s === 'skipped').length,
        failing: technicalSourceStatuses.filter((s) => s === 'failed').length,
      },
      health: {
        healthy: (healthFetchConfigs.data ?? []).filter((r) => r.last_fetch_status !== 'failed' && r.last_fetch).length,
        delayed: 0, // computed cheaply here as "unknown/never fetched"; full detail lives in /sources
        failing: (healthFetchConfigs.data ?? []).filter((r) => r.last_fetch_status === 'failed').length,
      },
    };

    const liveJobs = jobs.filter((j) => !NON_LIVE_DOMAIN_KEYS.has(j.domainKey));
    const jobsSummary = {
      scheduled: liveJobs.length,
      healthy: liveJobs.filter((j) => j.status === 'ok').length,
      attention: liveJobs.filter((j) => j.status === 'failed' || j.status === 'unknown').length,
    };

    const isAllClear = attention.length === 0
      && technicalStages.every((s) => s.tone !== 'crit')
      && healthStages.every((s) => s.tone !== 'crit');

    return NextResponse.json({
      fetchedAt: new Date().toISOString(),
      allClear: isAllClear,
      attention,
      pipelines: {
        technical: { stages: technicalStages, day: t?.day ?? null },
        health: { stages: healthStages, day: h?.day ?? null },
      },
      sourcesSummary,
      jobsSummary,
    });
  } catch (err) {
    console.error('[agent-status-workbench/overview] read failed:', err);
    return NextResponse.json(
      { error: 'overview_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
