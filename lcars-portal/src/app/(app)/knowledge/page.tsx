'use client';

import { useState, useEffect, useCallback } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

type DecisionRecord = {
  id: string;
  title: string;
  decision_type: string | null;
  status: string | null;
  created_at: string;
  description: string | null;
};

type LessonRecord = {
  id: string;
  title: string;
  lesson_type: string | null;
  domain: string | null;
  created_at: string;
  description: string | null;
};

type BriefRecord = {
  brief_id: string;
  executive_snapshot: string | null;
  bottom_line: string | null;
  overall_risk: string | null;
  generated_at: string;
  period_end: string | null;
};

type TabId = 'decisions' | 'lessons' | 'intelligence' | 'architecture' | 'all';

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

function decisionTypeAccent(type: string | null): string {
  switch (type?.toLowerCase()) {
    case 'architectural': return 'border-engineering text-engineering';
    case 'operational': return 'border-command text-command';
    case 'strategic': return 'border-science text-science';
    default: return 'border-medical text-medical';
  }
}

const TABS: { id: TabId; label: string }[] = [
  { id: 'decisions', label: 'Decisions' },
  { id: 'lessons', label: 'Lessons' },
  { id: 'intelligence', label: 'Intelligence' },
  { id: 'architecture', label: 'Architecture' },
  { id: 'all', label: 'All' },
];

type AllRecord =
  | ({ _source: 'decision' } & DecisionRecord)
  | ({ _source: 'lesson' } & LessonRecord)
  | ({ _source: 'brief' } & BriefRecord);

export default function KnowledgePage() {
  const [activeTab, setActiveTab] = useState<TabId>('all');
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [lessons, setLessons] = useState<LessonRecord[]>([]);
  const [briefs, setBriefs] = useState<BriefRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [domainFilter, setDomainFilter] = useState('');

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(searchQuery), 200);
    return () => clearTimeout(t);
  }, [searchQuery]);

  useEffect(() => {
    const supabase = createSupabaseBrowserClient();
    Promise.all([
      supabase
        .from('commander_decisions')
        .select('id, title, decision_type, status, created_at, description')
        .order('created_at', { ascending: false })
        .limit(50),
      supabase
        .from('lessons_learned')
        .select('id, title, lesson_type, domain, created_at, description')
        .order('created_at', { ascending: false })
        .limit(50),
      supabase
        .from('intelligence_briefs')
        .select('brief_id, executive_snapshot, bottom_line, overall_risk, generated_at, period_end')
        .order('generated_at', { ascending: false })
        .limit(50),
    ]).then(([d, l, b]) => {
      setDecisions((d.data as DecisionRecord[]) ?? []);
      setLessons((l.data as LessonRecord[]) ?? []);
      setBriefs((b.data as BriefRecord[]) ?? []);
      setLoading(false);
    });
  }, []);

  const q = debouncedQuery.toLowerCase();

  const filteredDecisions = decisions.filter((r) => {
    if (q && !r.title?.toLowerCase().includes(q) && !r.description?.toLowerCase().includes(q)) return false;
    return true;
  });

  const filteredLessons = lessons.filter((r) => {
    if (q && !r.title?.toLowerCase().includes(q) && !r.description?.toLowerCase().includes(q) && !r.domain?.toLowerCase().includes(q)) return false;
    if (domainFilter && r.domain !== domainFilter) return false;
    return true;
  });

  const filteredBriefs = briefs.filter((r) => {
    if (q && !r.executive_snapshot?.toLowerCase().includes(q) && !r.bottom_line?.toLowerCase().includes(q)) return false;
    return true;
  });

  const allRecords: AllRecord[] = [
    ...filteredDecisions.map((r) => ({ _source: 'decision' as const, ...r })),
    ...filteredLessons.map((r) => ({ _source: 'lesson' as const, ...r })),
    ...filteredBriefs.map((r) => ({ _source: 'brief' as const, ...r })),
  ].sort((a, b) => {
    const aDate = ('created_at' in a ? a.created_at : (a as any).generated_at) ?? '';
    const bDate = ('created_at' in b ? b.created_at : (b as any).generated_at) ?? '';
    return new Date(bDate).getTime() - new Date(aDate).getTime();
  });

  const uniqueDomains = Array.from(new Set(lessons.map((l) => l.domain).filter(Boolean))) as string[];

  const totalRecords = decisions.length + lessons.length + briefs.length;
  const totalDomains = uniqueDomains.length;

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
          {uniqueDomains.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              <button
                onClick={() => setDomainFilter('')}
                className={`text-[9px] uppercase tracking-[0.15em] px-2 py-0.5 rounded border transition-colors ${
                  domainFilter === ''
                    ? 'bg-science text-space border-science'
                    : 'border-edge text-lcars-muted hover:text-science hover:border-science'
                }`}
              >
                All
              </button>
              {uniqueDomains.map((d) => (
                <button
                  key={d}
                  onClick={() => setDomainFilter(domainFilter === d ? '' : d)}
                  className={`text-[9px] uppercase tracking-[0.15em] px-2 py-0.5 rounded border transition-colors ${
                    domainFilter === d
                      ? 'bg-science text-space border-science'
                      : 'border-edge text-lcars-muted hover:text-science hover:border-science'
                  }`}
                >
                  {d}
                </button>
              ))}
            </div>
          )}
          <p className="text-xs text-lcars-muted">
            {loading ? 'Loading…' : `${totalRecords} records across ${totalDomains} domains`}
          </p>
        </div>
      </LCARSPanel>

      {/* Tab bar */}
      <div className="flex gap-1 flex-wrap">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`text-xs px-3 py-1.5 rounded-lcars border transition-colors font-lcars uppercase tracking-[0.1em] ${
              activeTab === tab.id
                ? 'bg-science text-space border-science'
                : 'border-edge text-lcars-muted hover:text-science hover:border-science'
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
                      <span className="text-sm font-medium text-foreground">{r.title}</span>
                      <span className="text-[9px] text-lcars-muted shrink-0">{relativeTime(r.created_at)}</span>
                    </div>
                    <div className="flex gap-1.5 flex-wrap">
                      {r.decision_type && (
                        <span className={`text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border ${decisionTypeAccent(r.decision_type)}`}>
                          {r.decision_type}
                        </span>
                      )}
                      {r.status && (
                        <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-edge text-lcars-muted">
                          {r.status}
                        </span>
                      )}
                    </div>
                    {r.description && (
                      <p className="text-xs text-lcars-muted">{snippet(r.description, 100)}</p>
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
              ) : domainFilter === '' ? (
                // Group by domain
                (() => {
                  const grouped: Record<string, LessonRecord[]> = {};
                  filteredLessons.forEach((r) => {
                    const key = r.domain ?? 'Uncategorised';
                    if (!grouped[key]) grouped[key] = [];
                    grouped[key].push(r);
                  });
                  return Object.entries(grouped).map(([domain, items]) => (
                    <div key={domain} className="space-y-1.5">
                      <p className="text-[9px] uppercase tracking-[0.15em] text-science font-lcars">{domain}</p>
                      {items.map((r) => (
                        <div key={r.id} className="rounded-lcars border border-edge bg-panel/60 p-3 flex flex-col gap-1">
                          <div className="flex items-start justify-between gap-2">
                            <span className="text-sm font-medium text-foreground">{r.title}</span>
                            <span className="text-[9px] text-lcars-muted shrink-0">{relativeTime(r.created_at)}</span>
                          </div>
                          <div className="flex gap-1.5 flex-wrap">
                            {r.lesson_type && (
                              <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-science text-science">
                                {r.lesson_type}
                              </span>
                            )}
                            {r.domain && (
                              <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-edge text-lcars-muted">
                                {r.domain}
                              </span>
                            )}
                          </div>
                          {r.description && (
                            <p className="text-xs text-lcars-muted">{snippet(r.description, 100)}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  ));
                })()
              ) : (
                filteredLessons.map((r) => (
                  <div key={r.id} className="rounded-lcars border border-edge bg-panel/60 p-3 flex flex-col gap-1">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm font-medium text-foreground">{r.title}</span>
                      <span className="text-[9px] text-lcars-muted shrink-0">{relativeTime(r.created_at)}</span>
                    </div>
                    <div className="flex gap-1.5 flex-wrap">
                      {r.lesson_type && (
                        <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-science text-science">
                          {r.lesson_type}
                        </span>
                      )}
                      {r.domain && (
                        <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-edge text-lcars-muted">
                          {r.domain}
                        </span>
                      )}
                    </div>
                    {r.description && (
                      <p className="text-xs text-lcars-muted">{snippet(r.description, 100)}</p>
                    )}
                  </div>
                ))
              )}
            </div>
          )}

          {/* INTELLIGENCE */}
          {activeTab === 'intelligence' && (
            <div className="space-y-2">
              {filteredBriefs.length === 0 ? (
                <p className="text-sm text-lcars-muted">No intelligence records found.</p>
              ) : (
                filteredBriefs.map((r) => (
                  <div key={r.brief_id} className="rounded-lcars border border-edge bg-panel/60 p-3 flex flex-col gap-1">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm font-medium text-foreground">ORI Brief — {r.brief_id.slice(0, 8)}</span>
                      <span className="text-[9px] text-lcars-muted shrink-0">{relativeTime(r.generated_at)}</span>
                    </div>
                    <div className="flex gap-1.5 flex-wrap">
                      {r.overall_risk && (
                        <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-science text-science w-fit">
                          Risk: {r.overall_risk}
                        </span>
                      )}
                      {r.period_end && (
                        <span className="text-[9px] text-lcars-muted">Period to {r.period_end.slice(0, 10)}</span>
                      )}
                    </div>
                    {(r.executive_snapshot || r.bottom_line) && (
                      <p className="text-xs text-lcars-muted">{snippet(r.executive_snapshot ?? r.bottom_line, 150)}</p>
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
                          <span className="text-sm font-medium text-foreground">{rec.title}</span>
                          <span className="text-[9px] text-lcars-muted shrink-0">{relativeTime(rec.created_at)}</span>
                        </div>
                        <div className="flex gap-1.5 flex-wrap">
                          <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-command text-command">
                            Decision
                          </span>
                          {rec.decision_type && (
                            <span className={`text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border ${decisionTypeAccent(rec.decision_type)}`}>
                              {rec.decision_type}
                            </span>
                          )}
                          {rec.status && (
                            <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-edge text-lcars-muted">
                              {rec.status}
                            </span>
                          )}
                        </div>
                        {rec.description && (
                          <p className="text-xs text-lcars-muted">{snippet(rec.description, 100)}</p>
                        )}
                      </div>
                    );
                  }
                  if (r._source === 'lesson') {
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
                          {rec.lesson_type && (
                            <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-science text-science">
                              {rec.lesson_type}
                            </span>
                          )}
                          {rec.domain && (
                            <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-edge text-lcars-muted">
                              {rec.domain}
                            </span>
                          )}
                        </div>
                        {rec.description && (
                          <p className="text-xs text-lcars-muted">{snippet(rec.description, 100)}</p>
                        )}
                      </div>
                    );
                  }
                  // brief
                  const rec = r as { _source: 'brief' } & BriefRecord;
                  return (
                    <div key={`b-${rec.brief_id}`} className="rounded-lcars border border-edge bg-panel/60 p-3 flex flex-col gap-1">
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-sm font-medium text-foreground">ORI Brief — {rec.brief_id.slice(0, 8)}</span>
                        <span className="text-[9px] text-lcars-muted shrink-0">{relativeTime(rec.generated_at)}</span>
                      </div>
                      <div className="flex gap-1.5 flex-wrap">
                        <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-medical text-medical">
                          Intelligence
                        </span>
                        {rec.overall_risk && (
                          <span className="text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-science text-science">
                            Risk: {rec.overall_risk}
                          </span>
                        )}
                      </div>
                      {(rec.executive_snapshot || rec.bottom_line) && (
                        <p className="text-xs text-lcars-muted">{snippet(rec.executive_snapshot ?? rec.bottom_line, 150)}</p>
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
