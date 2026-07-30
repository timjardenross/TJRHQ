'use client';

import { Card } from '@/components/ui';

export function ArchitectureIndex() {
  const ADR_LIST = [
    'ADR-001 — Supabase as primary data store',
    'ADR-002 — Next.js 14 App Router for LCARS Portal',
    'ADR-003 — Python FastAPI for Command Centre backend',
    'ADR-004 — SQLite for local mission state (missions.db)',
    'ADR-005 — Slack as primary push notification channel',
    'ADR-006 — Captain Brief delivered via Slack + Dashy',
    'ADR-007 — Context assembly pipeline (WP-A through WP-D)',
    'ADR-008 — LLM synthesis for weekly intelligence (v2.0)',
    'ADR-009 — 30-day rolling baselines for health/capacity',
    'ADR-010 — Separate health_daily_logs and captains_log_entries',
    'ADR-011 — lessons_learned table for organisational memory',
    'ADR-012 — outcome_quality field on commander_decisions',
    'ADR-013 — Readiness history accumulation pattern',
    'ADR-014 — Captain Profile Memory Bank (captain_profile.txt)',
    'ADR-015 — Engineering handoff advisory-only read model',
    'ADR-016 — 5-status lifecycle (Pending Triage → Completed)',
    'ADR-017 — Universal Search across all tables (Phase 3A)',
    'ADR-018 — Unified Timeline with cross-domain interleaving',
    'ADR-019 — Notification engine single push source (WP-6)',
    'ADR-020 — Mission lifecycle CLI commands',
    'ADR-021 — Proactive scheduler for mission triggers',
    'ADR-022 — Engineering governance review cadence',
    'ADR-023 — P0 security action tracking',
    'ADR-024 — ADR approval workflow (Captain sign-off)',
    'ADR-025 — D-series decision numbering convention',
    'ADR-026 — MSN numbering and phase gate convention',
  ];

  return (
    <Card className="border-wb-line bg-wb-bg/30 p-4 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <p className="text-[13px] font-sans font-semibold text-wb-ink">ADR Index</p>
        <span className="text-[11px] px-1.5 py-0.5 rounded border border-wb-line text-wb-ink2">
          Static reference · not live
        </span>
      </div>
      <p className="text-xs text-wb-ink2">
        A hand-maintained list of architecture decision titles for quick orientation. This is not a
        queryable registry and is not guaranteed complete or current — some entries record decisions
        still awaiting Captain approval. Treat it as a static index, not a source of record.
      </p>
      <div className="space-y-1.5 text-xs text-wb-ink2 font-mono">
        {ADR_LIST.map((adr) => (
          <div key={adr} className="flex gap-2">
            <span className="text-wb-ink shrink-0">&rsaquo;</span>
            <span>{adr}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}
