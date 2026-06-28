'use client';

import { useState, useEffect } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

type DecisionRecord = {
  id: string;
  decision_title: string;
  decision_summary: string | null;
  source: string | null;
  route: string | null;
  created_at: string;
};

type LessonRecord = {
  id: string;
  title: string;
  lesson_text: string | null;
  context: string | null;
  source: string | null;
  mission_id: string | null;
  created_at: string;
};

type TabId = 'decisions' | 'lessons' | 'architecture' | 'all';

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

function snippet(text: string | null, len: number): string {
  if (!text) return '';
  return text.length > len ? text.slice(0, len) + '…' : text;
}

const TABS: { id: TabId; label: string }[] = [
  { id: 'decisions', label: 'Decisions' },
  { id: 'lessons', label: 'Lessons' },
  { id: 'architecture', label: 'Architecture' },
  { id: 'all', label: 'All' },
];

type AllRecord =
  | ({ _source: 'decision' } & DecisionRecord)
  | ({ _source: 'lesson' } & LessonRecord);

export default function KnowledgePage() {
  const [activeTab, setActiveTab] = useState<TabId>('all');
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [lessons, setLessons] = useState<LessonRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(searchQuery), 200);
    return () => clearTimeout(t);
  }, [searchQuery]);

  useEffect(() => {
    const supabase = createSupabaseBrowserClient();
    Promise.all([
      supabase
        .from('commander_decisions')
        .select('id, decision_title, decision_summary, source, route, created_at')
        .order('created_at', { ascending: false })
        .limit(50),
      supabase
        .from('lessons_learned')
        .select('id, title, lesson_text, context, source, created_at, mission_id')
        .order('created_at', { ascending: false })
        .limit(50),
    ]).then(([d, l]) => {
      setDecisions((d.data as DecisionRecord[]) ?? []);
      setLessons((l.data as LessonRecord[]) ?? []);
      setLoading(false);
    });
  }, []);

  const q = debouncedQuery.toLowerCase();

  const filteredDecisions = decisions.filter((r) => {
    if (q && !r.decision_title?.toLowerCase().includes(q) && !r.decision_summary?.toLowerCase().includes(q)) return false;
    return true;
  });

  const filteredLessons = lessons.filter((r) => {
    if (q && !r.title?.toLowerCase().includes(q) && !r.lesson_text?.toLowerCase().includes(q) && !r.context?.toLowerCase().includes(q)) return false;
    return true;
  });

  const allRecords: AllRecord[] = [
    ...filteredDecisions.map((r) => ({ _source: 'decision' as const, ...r })),
    ...filteredLessons.map((r) => ({ _source: 'lesson' as const, ...r })),
  ].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

  const totalRecords = decisions.length + lessons.length;

  return (
    <div className="space-y-4">
      <LCARSPanel
        title="Knowledge Hub"
        accent="science"
        eyebrow="MSN-3D-002 · Organisational Memory"
      >
        <div className="space-y-3">
          <input
            type="text"
            placeholder="Search records…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-foreground placeholder:text-lcars-muted focus:border-science focus:outline-none"
          />
          <p className="text-xs text-lcars-muted">
            {loading ? 'Loading…' : `${totalRecords} records`}
          </p>
        </div>
      </LCARSPanel>

      {/* Tab bar — Health Centre style */}
      <div className="flex border-b border-edge overflow-x-auto mb-4">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-xs uppercase tracking-[0.15em] whitespace-nowrap transition-colors ${
              activeTab === tab.id
                ? 'border-b-2 border-science text-science font-semibold -mb-px'
                : 'text-lcars-muted hover:text-lcars-text'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <p className="text-sm text-lcars-muted">Loading knowledge records…</p>
      ) : (
        <>
          {/* DECISIONS */}
          {activeTab === 'decisions' && (
            <div className="space-y-2">
              {filteredDecisions.length === 0 ? (
                <p className="text-sm text-lcars-muted">No decision records found.</p>
              ) : (
                filteredDecisions.map((r) => (
                  <div key={r.id} className="rounded-lcars border border-edge bg-panel/60 p-3 flex flex-col gap-1">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm font-medium text-foreground">{r.decision_title}</span>
                      <span className="text-[9px] text-lcars-muted shrink-0">{relativeTime(r.created_at)}</span>
                    </div>
                    <div className="flex gap-1.5 flex-wrap">
                      {r.route && (
                        <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-command text-command">
                          {r.route}
                        </span>
                      )}
                      {r.source && (
                        <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-edge text-lcars-muted">
                          {r.source}
                        </span>
                      )}
                    </div>
                    {r.decision_summary && (
                      <p className="text-xs text-lcars-muted">{snippet(r.decision_summary, 120)}</p>
                    )}
                  </div>
                ))
              )}
            </div>
          )}

          {/* LESSONS */}
          {activeTab === 'lessons' && (
            <div className="space-y-2">
              {filteredLessons.length === 0 ? (
                <p className="text-sm text-lcars-muted">No lesson records found.</p>
              ) : (
                filteredLessons.map((r) => (
                  <div key={r.id} className="rounded-lcars border border-edge bg-panel/60 p-3 flex flex-col gap-1">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm font-medium text-foreground">{r.title}</span>
                      <span className="text-[9px] text-lcars-muted shrink-0">{relativeTime(r.created_at)}</span>
                    </div>
                    <div className="flex gap-1.5 flex-wrap">
                      {r.source && (
                        <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-science text-science">
                          {r.source}
                        </span>
                      )}
                      {r.mission_id && (
                        <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-edge text-lcars-muted">
                          {r.mission_id}
                        </span>
                      )}
                    </div>
                    {(r.lesson_text ?? r.context) && (
                      <p className="text-xs text-lcars-muted">{snippet(r.lesson_text ?? r.context, 120)}</p>
                    )}
                  </div>
                ))
              )}
            </div>
          )}

          {/* ARCHITECTURE */}
          {activeTab === 'architecture' && (
            <div className="rounded-lcars border border-engineering bg-panel/60 p-4 space-y-3">
              <p className="text-[9px] uppercase tracking-[0.15em] text-engineering font-lcars">ADR Registry</p>
              <p className="text-xs text-lcars-muted">
                Architecture Decision Records — query the Engineering tab for full detail and status.
              </p>
              <div className="space-y-1.5 text-xs text-lcars-muted font-mono">
                {[
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
                ].map((adr) => (
                  <div key={adr} className="flex gap-2">
                    <span className="text-engineering shrink-0">&rsaquo;</span>
                    <span>{adr}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ALL */}
          {activeTab === 'all' && (
            <div className="space-y-2">
              {allRecords.length === 0 ? (
                <p className="text-sm text-lcars-muted">No records found.</p>
              ) : (
                allRecords.map((r) => {
                  if (r._source === 'decision') {
                    const rec = r as { _source: 'decision' } & DecisionRecord;
                    return (
                      <div key={`d-${rec.id}`} className="rounded-lcars border border-edge bg-panel/60 p-3 flex flex-col gap-1">
                        <div className="flex items-start justify-between gap-2">
                          <span className="text-sm font-medium text-foreground">{rec.decision_title}</span>
                          <span className="text-[9px] text-lcars-muted shrink-0">{relativeTime(rec.created_at)}</span>
                        </div>
                        <div className="flex gap-1.5 flex-wrap">
                          <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-command text-command">
                            Decision
                          </span>
                          {rec.route && (
                            <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-edge text-lcars-muted">
                              {rec.route}
                            </span>
                          )}
                          {rec.source && (
                            <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-edge text-lcars-muted">
                              {rec.source}
                            </span>
                          )}
                        </div>
                        {rec.decision_summary && (
                          <p className="text-xs text-lcars-muted">{snippet(rec.decision_summary, 100)}</p>
                        )}
                      </div>
                    );
                  }
                  // lesson
                  const rec = r as { _source: 'lesson' } & LessonRecord;
                  return (
                    <div key={`l-${rec.id}`} className="rounded-lcars border border-edge bg-panel/60 p-3 flex flex-col gap-1">
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-sm font-medium text-foreground">{rec.title}</span>
                        <span className="text-[9px] text-lcars-muted shrink-0">{relativeTime(rec.created_at)}</span>
                      </div>
                      <div className="flex gap-1.5 flex-wrap">
                        <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-science text-science">
                          Lesson
                        </span>
                        {rec.source && (
                          <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-edge text-lcars-muted">
                            {rec.source}
                          </span>
                        )}
                        {rec.mission_id && (
                          <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-edge text-lcars-muted">
                            {rec.mission_id}
                          </span>
                        )}
                      </div>
                      {(rec.lesson_text ?? rec.context) && (
                        <p className="text-xs text-lcars-muted">{snippet(rec.lesson_text ?? rec.context, 100)}</p>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
