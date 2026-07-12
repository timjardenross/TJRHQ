'use client';

import { useState, useEffect } from 'react';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { Card } from '@/components/ui';
import { ArchitectureIndex } from './ArchitectureIndex';

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
  { id: 'architecture', label: 'ADR Index' },
  { id: 'all', label: 'All' },
];

type AllRecord =
  | ({ _source: 'decision' } & DecisionRecord)
  | ({ _source: 'lesson' } & LessonRecord);

export function MemoryView() {
  const [activeTab, setActiveTab] = useState<TabId>('all');
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [lessons, setLessons] = useState<LessonRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
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
    ])
      .then(([d, l]) => {
        if (d.error || l.error) {
          setLoadError(d.error?.message ?? l.error?.message ?? 'Query failed');
          return;
        }
        setDecisions((d.data as DecisionRecord[]) ?? []);
        setLessons((l.data as LessonRecord[]) ?? []);
      })
      .catch((e) => {
        setLoadError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
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
      {/* Search input */}
      <div className="space-y-2">
        <input
          type="text"
          placeholder="Search records…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full rounded-lg border border-wb-line bg-transparent px-3 py-2 text-sm text-wb-ink placeholder:text-wb-ink2 focus:border-wb-ink focus:outline-none"
        />
        <p className="text-xs text-wb-ink2">
          {loading ? 'Loading…' : loadError ? 'Records unavailable' : `${totalRecords} records`}
        </p>
      </div>

      {/* Tab bar */}
      <div className="flex border-b border-wb-line overflow-x-auto">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm font-sans transition-colors whitespace-nowrap ${
              activeTab === tab.id
                ? 'border-b-2 border-wb-sage-deep text-wb-ink -mb-px'
                : 'text-wb-ink2 hover:text-wb-ink'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <p className="text-sm text-wb-ink2">Loading knowledge records…</p>
      ) : loadError ? (
        <Card className="border-wb-line bg-wb-bg/50 p-3">
          <p className="text-sm text-wb-ink">Couldn&apos;t load knowledge records — try again.</p>
        </Card>
      ) : (
        <>
          {/* DECISIONS */}
          {activeTab === 'decisions' && (
            <div className="space-y-2">
              {filteredDecisions.length === 0 ? (
                <p className="text-sm text-wb-ink2">No decision records found.</p>
              ) : (
                filteredDecisions.map((r) => (
                  <Card key={r.id} className="border-wb-line bg-wb-bg/30 p-3 flex flex-col gap-1">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm font-serif text-wb-ink">{r.decision_title}</span>
                      <span className="text-[11px] text-wb-ink2 shrink-0">{relativeTime(r.created_at)}</span>
                    </div>
                    <div className="flex gap-1.5 flex-wrap">
                      {r.route && (
                        <span className="text-[11px] px-1.5 py-0.5 rounded border border-wb-line text-wb-ink2">
                          {r.route}
                        </span>
                      )}
                      {r.source && (
                        <span className="text-[11px] px-1.5 py-0.5 rounded border border-wb-line text-wb-ink2">
                          {r.source}
                        </span>
                      )}
                    </div>
                    {r.decision_summary && (
                      <p className="text-xs text-wb-ink2">{snippet(r.decision_summary, 120)}</p>
                    )}
                  </Card>
                ))
              )}
            </div>
          )}

          {/* LESSONS */}
          {activeTab === 'lessons' && (
            <div className="space-y-2">
              {filteredLessons.length === 0 ? (
                <p className="text-sm text-wb-ink2">No lesson records found.</p>
              ) : (
                filteredLessons.map((r) => (
                  <Card key={r.id} className="border-wb-line bg-wb-bg/30 p-3 flex flex-col gap-1">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm font-serif text-wb-ink">{r.title}</span>
                      <span className="text-[11px] text-wb-ink2 shrink-0">{relativeTime(r.created_at)}</span>
                    </div>
                    <div className="flex gap-1.5 flex-wrap">
                      {r.source && (
                        <span className="text-[11px] px-1.5 py-0.5 rounded border border-wb-line text-wb-ink2">
                          {r.source}
                        </span>
                      )}
                      {r.mission_id && (
                        <span className="text-[11px] px-1.5 py-0.5 rounded border border-wb-line text-wb-ink2">
                          {r.mission_id}
                        </span>
                      )}
                    </div>
                    {(r.lesson_text ?? r.context) && (
                      <p className="text-xs text-wb-ink2">{snippet(r.lesson_text ?? r.context, 120)}</p>
                    )}
                  </Card>
                ))
              )}
            </div>
          )}

          {/* ARCHITECTURE */}
          {activeTab === 'architecture' && <ArchitectureIndex />}

          {/* ALL */}
          {activeTab === 'all' && (
            <div className="space-y-2">
              {allRecords.length === 0 ? (
                <p className="text-sm text-wb-ink2">No records found.</p>
              ) : (
                allRecords.map((r) => {
                  if (r._source === 'decision') {
                    const rec = r as { _source: 'decision' } & DecisionRecord;
                    return (
                      <Card key={`d-${rec.id}`} className="border-wb-line bg-wb-bg/30 p-3 flex flex-col gap-1">
                        <div className="flex items-start justify-between gap-2">
                          <span className="text-sm font-serif text-wb-ink">{rec.decision_title}</span>
                          <span className="text-[11px] text-wb-ink2 shrink-0">{relativeTime(rec.created_at)}</span>
                        </div>
                        <div className="flex gap-1.5 flex-wrap">
                          <span className="text-[11px] px-1.5 py-0.5 rounded border border-wb-line text-wb-ink2">
                            Decision
                          </span>
                          {rec.route && (
                            <span className="text-[11px] px-1.5 py-0.5 rounded border border-wb-line text-wb-ink2">
                              {rec.route}
                            </span>
                          )}
                          {rec.source && (
                            <span className="text-[11px] px-1.5 py-0.5 rounded border border-wb-line text-wb-ink2">
                              {rec.source}
                            </span>
                          )}
                        </div>
                        {rec.decision_summary && (
                          <p className="text-xs text-wb-ink2">{snippet(rec.decision_summary, 100)}</p>
                        )}
                      </Card>
                    );
                  }
                  // lesson
                  const rec = r as { _source: 'lesson' } & LessonRecord;
                  return (
                    <Card key={`l-${rec.id}`} className="border-wb-line bg-wb-bg/30 p-3 flex flex-col gap-1">
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-sm font-serif text-wb-ink">{rec.title}</span>
                        <span className="text-[11px] text-wb-ink2 shrink-0">{relativeTime(rec.created_at)}</span>
                      </div>
                      <div className="flex gap-1.5 flex-wrap">
                        <span className="text-[11px] px-1.5 py-0.5 rounded border border-wb-line text-wb-ink2">
                          Lesson
                        </span>
                        {rec.source && (
                          <span className="text-[11px] px-1.5 py-0.5 rounded border border-wb-line text-wb-ink2">
                            {rec.source}
                          </span>
                        )}
                        {rec.mission_id && (
                          <span className="text-[11px] px-1.5 py-0.5 rounded border border-wb-line text-wb-ink2">
                            {rec.mission_id}
                          </span>
                        )}
                      </div>
                      {(rec.lesson_text ?? rec.context) && (
                        <p className="text-xs text-wb-ink2">{snippet(rec.lesson_text ?? rec.context, 100)}</p>
                      )}
                    </Card>
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
