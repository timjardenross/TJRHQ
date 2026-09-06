// HQ Status interpreted-overview API (backs the "Status" tab).
//
// This is the HQ HEALTH INTERPRETER layer (spec §29) wired to live data:
// domain_heartbeats_latest (via lib/agentStatusJobs) for job health, plus
// the Phase 26 pipeline-quality views and intelligence/health source-health
// views for two capabilities (Technical/Health Intelligence) where job
// heartbeats alone don't see a stalled pipeline stage or a failing source.
// All three signal sources are read-only and already governed elsewhere in
// this workbench (Automations/Sources tabs) — this route does not invent a
// fourth. Posture math itself lives in lib/hqStatusInterpreter.ts and is
// unit-tested there without a DB; this route's only job is to gather
// signals and hand them to that pure function.
//
// 2026-09-06 HQ Status uplift: replaces the old allClear/attention-list
// shape (which showed a flat "Needs Attention" list of every failed job or
// source) with an interpreted capability posture — NORMAL/DEGRADED/
// ATTENTION/UNKNOWN — plus a small Captain's-Chair-ready summary. Retired
// sources (active=false) and non-live jobs are still excluded from signal
// computation for the same reason as before: a permanently-retired item's
// last-known state must never render as an ongoing problem.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { fetchAgentStatusEntries } from '@/lib/agentStatusJobs';
import {
  computeCapabilities,
  applyCapabilitySignal,
  interpretHQStatus,
  buildCaptainChairSummary,
  type CapabilityTone,
} from '@/lib/hqStatusInterpreter';

type StageTone = 'ok' | 'warn' | 'crit' | 'unknown';

interface StageResult {
  key: string;
  label: string;
  tone: StageTone;
  detail: string;
}

/** Tri-state for one pipeline stage: 'crit' if a feeding job has failed,
 *  'unknown' if there's simply no data for today yet, else 'ok'/'warn'
 *  based on whether the mapped view counts are flowing. Unchanged from the
 *  prior overview route — still used to feed both the Sources tab's
 *  Pipeline Health view and (new) the two intelligence capabilities below. */
function stageHealth(
  key: string,
  label: string,
  feedingJobKeys: string[],
  jobFailed: (domainKey: string) => { label: string; lastAction: string | null } | undefined,
  observedCount: number | null,
  discoveredToday: number,
  notObservable = false,
): StageResult {
  const failedJob = feedingJobKeys.map((k) => jobFailed(k)).find((j) => j !== undefined);
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

function worstStageTone(stages: StageResult[]): StageTone {
  if (stages.some((s) => s.tone === 'crit')) return 'crit';
  if (stages.some((s) => s.tone === 'warn')) return 'warn';
  if (stages.some((s) => s.tone === 'unknown')) return 'unknown';
  return 'ok';
}

function stageToneToCapabilitySignal(tone: StageTone, reason: string): { tone: CapabilityTone; reason: string } | null {
  switch (tone) {
    case 'crit': return { tone: 'unavailable', reason };
    case 'warn': return { tone: 'degraded', reason };
    case 'unknown': return { tone: 'unknown', reason };
    case 'ok': return null; // healthy is the capability's own default — no need to force it
  }
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

    const failedJobByKey = new Map(jobs.filter((j) => j.status === 'failed').map((j) => [j.domainKey, { label: j.label, lastAction: j.lastAction }]));
    const jobFailed = (domainKey: string) => failedJobByKey.get(domainKey);

    const t = techQuality.data?.[0] ?? null;
    const h = healthQuality.data?.[0] ?? null;

    // ── Pipeline health stages (unchanged math, now also feeds capabilities below) ──
    const technicalStages: StageResult[] = [
      stageHealth('discovery', 'Discovery', ['intelligence_collection', 'intraday_status_collection'], jobFailed, t?.discovered ?? null, t?.discovered ?? 0),
      stageHealth('parsing', 'Parsing', ['intelligence_collection', 'intraday_status_collection'], jobFailed, t?.discovered ?? null, t?.discovered ?? 0, true),
      stageHealth('relevance_gate', 'Relevance Gate', ['intelligence_suppression_audit'], jobFailed, (t?.not_relevant ?? 0) + (t?.low_confidence ?? 0) + (t?.relevant ?? 0), t?.discovered ?? 0),
      stageHealth('deduplication', 'Deduplication', [], jobFailed, t?.deduplicated ?? null, t?.discovered ?? 0),
      stageHealth('scoring', 'Scoring', ['evolved_captain_insight_generation'], jobFailed, (t?.relevant ?? 0) + (t?.not_relevant ?? 0) + (t?.low_confidence ?? 0), t?.discovered ?? 0),
      stageHealth('disposition', 'Disposition', [], jobFailed, (t?.escalate ?? 0) + (t?.brief ?? 0) + (t?.watch ?? 0) + (t?.reference ?? 0) + (t?.suppress ?? 0), t?.discovered ?? 0),
    ];

    const healthStages: StageResult[] = [
      stageHealth('discovery', 'Discovery', ['health_osint_weekly_fetch'], jobFailed, h?.discovered ?? null, h?.discovered ?? 0),
      stageHealth('parsing', 'Parsing', ['health_osint_weekly_fetch'], jobFailed, h?.discovered ?? null, h?.discovered ?? 0, true),
      stageHealth('relevance_gate', 'Relevance Gate', [], jobFailed, (h?.not_relevant ?? 0) + (h?.low_confidence ?? 0) + (h?.relevant ?? 0), h?.discovered ?? 0),
      stageHealth('study_clustering', 'Study Clustering', [], jobFailed, null, h?.discovered ?? 0, true),
      stageHealth('evidence_scoring', 'Evidence Scoring', [], jobFailed, h?.evidence_contribution_scored ?? null, h?.discovered ?? 0),
      stageHealth('curation', 'Curation', [], jobFailed, null, h?.discovered ?? 0, true),
    ];

    // Retired sources (active=false) are excluded — their last-known status
    // before retirement would otherwise generate a permanent, un-actionable
    // "failing" signal.
    const activeIds = new Set((activeTechSourceIds.data ?? []).map((r) => r.source_id));
    const latestTechBySource = new Map<string, { status: string; checked_at: string; error_message: string | null }>();
    for (const row of techSources.data ?? []) {
      if (activeIds.has(row.source_id)) latestTechBySource.set(row.source_id, row);
    }
    const technicalSourceStatuses = Array.from(latestTechBySource.values()).map((r) => r.status);
    const techFailing = technicalSourceStatuses.filter((s) => s === 'failed').length;
    const techDegraded = technicalSourceStatuses.filter((s) => s === 'degraded' || s === 'stale' || s === 'skipped').length;

    const healthConfigs = healthFetchConfigs.data ?? [];
    const healthFailing = healthConfigs.filter((r) => r.last_fetch_status === 'failed').length;

    // ── Capability posture (the interpreter) ──────────────────────────────
    let capabilities = computeCapabilities(jobs);

    const techStageTone = worstStageTone(technicalStages);
    const techSignal = stageToneToCapabilitySignal(
      techStageTone,
      techStageTone === 'crit' || techStageTone === 'warn'
        ? `Technical OSINT pipeline stage issue: ${technicalStages.find((s) => s.tone === techStageTone)?.detail ?? 'see Sources tab.'}`
        : techFailing > 0
          ? `${techFailing} technical source${techFailing === 1 ? '' : 's'} failing.`
          : 'No technical pipeline telemetry for today yet.',
    );
    if (techSignal) capabilities = applyCapabilitySignal(capabilities, 'technical_intelligence', techSignal);
    if (techFailing > 0) {
      capabilities = applyCapabilitySignal(capabilities, 'technical_intelligence', { tone: 'degraded', reason: `${techFailing} technical source${techFailing === 1 ? '' : 's'} failing.` });
    }

    const healthStageTone = worstStageTone(healthStages);
    const healthSignal = stageToneToCapabilitySignal(
      healthStageTone,
      healthStageTone === 'crit' || healthStageTone === 'warn'
        ? `Health OSINT pipeline stage issue: ${healthStages.find((s) => s.tone === healthStageTone)?.detail ?? 'see Sources tab.'}`
        : 'No health pipeline telemetry for today yet.',
    );
    if (healthSignal) capabilities = applyCapabilitySignal(capabilities, 'health_intelligence', healthSignal);
    if (healthFailing > 0) {
      capabilities = applyCapabilitySignal(capabilities, 'health_intelligence', { tone: 'degraded', reason: `${healthFailing} health source${healthFailing === 1 ? '' : 's'} failing.` });
    }

    const interpretation = interpretHQStatus(capabilities);
    const fetchedAt = new Date().toISOString();
    const captainSummary = buildCaptainChairSummary(interpretation, fetchedAt);

    // ── Secondary raw counts (spec §43: kept, but never primary) ──────────
    const sourcesSummary = {
      technical: { healthy: technicalSourceStatuses.filter((s) => s === 'ok').length, degraded: techDegraded, failing: techFailing },
      health: { healthy: healthConfigs.filter((r) => r.last_fetch_status !== 'failed' && r.last_fetch).length, delayed: 0, failing: healthFailing },
    };
    const liveJobs = jobs.filter((j) => j.status !== 'retired' && j.status !== 'disabled');
    const jobsSummary = {
      scheduled: liveJobs.length,
      healthy: liveJobs.filter((j) => j.status === 'ok').length,
      attention: liveJobs.filter((j) => j.status === 'failed' || j.status === 'unknown').length,
    };

    return NextResponse.json({
      fetchedAt,
      posture: interpretation.posture,
      headline: interpretation.headline,
      narrative: interpretation.narrative,
      capabilities: interpretation.capabilities,
      materialDegradations: interpretation.materialDegradations,
      unknownMaterialAreas: interpretation.unknownMaterialAreas,
      attentionItems: interpretation.attentionItems,
      needsAttentionCount: interpretation.needsAttentionCount,
      unknownMaterialCount: interpretation.unknownMaterialCount,
      captainSummary,
      // Secondary detail for progressive disclosure — Automations/Sources
      // tabs are still the canonical home for the full picture.
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
      {
        error: 'overview_read_failed',
        detail: err instanceof Error ? err.message : 'Unknown error',
        // Honest failure shape (spec §49): the caller must never assume
        // NORMAL when this route itself can't determine health.
        posture: 'unknown',
      },
      { status: 500 },
    );
  }
}
