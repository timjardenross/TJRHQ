'use client';

// Operating Model — relocated from the retired (app)/operating-model page
// (Mission 7 deferred-register item 11's last open bullet, closed by
// Captain direction: relocate into Knowledge Workbench rather than retire
// or leave as an orphan). Same content, same live queries — this is
// exactly the kind of durable personal-doctrine reference Knowledge
// Workbench already owns (architecture_records et al.), just never filed
// there. Reshelled onto WorkbenchShell/Card/wb-* tokens instead of
// LCARSPanel.
//
// The original page colour-coded each Domain/Schedule row by department
// (medical/command/science/operations). Dropped here, not carried over:
// department tokens are explicitly disallowed inside *-workbench routes
// (WORKBENCH-REVIEW.md H9, eslint no-restricted-syntax) — workbenches are
// wb-*/state-* only. Priority tiers (P0-P3) now map onto the sanctioned
// state-* severity vocabulary instead (most-protected P0 -> state-crit,
// down to P3 -> state-ok) rather than inventing a new colour scheme; the
// per-domain/per-schedule-row colour was decorative in the original, not
// informative, so dropping it loses nothing real.
//
// Content reviewed and reaffirmed/revised 2026-09-20 (Mission 7 Phase 13,
// Chief of Staff pass, §5 item 11 fully closed): checked against
// knowledge/memory/captain_profile.txt (the platform's other canonical
// Captain-context document) rather than guessed — found a real gap (no
// Domain for TJR Mind & Body, though it's a named current_priorities item
// there) and a genuinely different Principles list (8 decision_principles
// vs. this page's prior 6). Captain confirmed the specific changes below;
// this is not an engineering author's edit.

import { useState, useEffect } from 'react';
import { WorkbenchShell, Card } from '@/components/ui';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

interface LiveData {
  activeMissionsCount: number | null;
  lastLog: { log_date: string; captain_capacity_rating: number | null; tomorrows_priority: string | null } | null;
  lastCheckin: { checkin_type: string | null; pain_score: number | null; capacity_state: string | null; regulation_state: string | null; captured_at: string | null } | null;
}

const DOMAINS = [
  { icon: '🏥', name: 'Health', description: 'Recovery-led operations. Pain management, CPAP adherence, fatigue mapping.', priority: 'P0' },
  { icon: '🚀', name: 'USS TJR', description: 'Command Centre build, intelligence systems, operational excellence.', priority: 'P1' },
  { icon: '💼', name: 'Career', description: 'Strategic positioning and professional development.', priority: 'P2' },
  { icon: '📚', name: 'Learning', description: 'AI/ML, systems thinking, leadership frameworks.', priority: 'P2' },
  { icon: '🤝', name: 'Relationships', description: 'Family, crew, professional network maintenance.', priority: 'P2' },
  { icon: '🎯', name: 'Personal', description: 'Identity, values, long-term vision.', priority: 'P3' },
  { icon: '🌱', name: 'TJR Mind & Body', description: 'Building TJR Mind & Body — human resilience and capacity coaching practice. Early-stage; not yet active day-to-day.', priority: 'P3' },
];

const PRINCIPLES = [
  { num: 1, title: 'Recovery First', body: 'No decision or commitment compromises recovery posture; capacity is protected before it’s spent.' },
  { num: 2, title: 'Mission Clarity', body: 'Every piece of work has a mission ID and a clear outcome.' },
  { num: 3, title: 'Intelligent Defaults', body: 'The system handles routine, automating what genuinely improves outcomes; the Captain handles judgement.' },
  { num: 4, title: 'Evidence-Based, Root-Cause Decisions', body: 'Decisions are logged, rated, and reviewed; seek root causes rather than repeatedly treating symptoms.' },
  { num: 5, title: 'Human Judgement on Consequential Calls', body: 'AI augments judgement rather than replacing it; the Captain holds final authority on anything consequential.' },
  { num: 6, title: 'Simple, Durable Systems', body: 'Favour simple, durable systems over unnecessary complexity; design around real behaviour, not idealised behaviour.' },
  { num: 7, title: 'Preserve Optionality', body: 'Where uncertainty is high, keep paths open rather than committing early.' },
  { num: 8, title: 'Continuous Learning', body: 'Lessons are captured and fed back into the system.' },
];

const SCHEDULE = [
  { label: 'Peak performance', time: 'Morning (0800–1000)' },
  { label: 'Managed capacity', time: 'Midday–Afternoon (1000–1500)' },
  { label: 'Wind-down', time: 'Afternoon–Evening (1500–2000)' },
  { label: 'Recovery priority', time: 'Deep sleep, CPAP compliance, pain management' },
];

function priorityColor(p: string) {
  if (p === 'P0') return 'text-state-crit-on bg-state-crit/10 border border-state-crit/30';
  if (p === 'P1') return 'text-state-warn-on bg-state-warn/10 border border-state-warn/30';
  if (p === 'P2') return 'text-state-info-on bg-state-info/10 border border-state-info/30';
  return 'text-state-ok-on bg-state-ok/10 border border-state-ok/30';
}

export default function OperatingModelPage() {
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [data, setData] = useState<LiveData>({ activeMissionsCount: null, lastLog: null, lastCheckin: null });

  useEffect(() => {
    const supabase = createSupabaseBrowserClient();
    async function fetchAll() {
      try {
        const [missionsRes, logRes, checkinRes] = await Promise.all([
          supabase
            .from('missions')
            .select('mission_id', { count: 'exact', head: true })
            .not('status', 'in', '(COMPLETE,DEFERRED,CLOSED)'),
          supabase
            .from('captains_log_entries')
            .select('log_date, captain_capacity_rating, tomorrows_priority')
            .order('log_date', { ascending: false })
            .limit(1)
            .maybeSingle(),
          supabase
            .from('capacity_checkins')
            .select('checkin_type, pain_score, capacity_state, regulation_state, captured_at')
            .order('captured_at', { ascending: false })
            .limit(1)
            .maybeSingle(),
        ]);

        const queryError = missionsRes.error ?? logRes.error ?? checkinRes.error;
        if (queryError) {
          setLoadError(queryError.message ?? 'Query failed');
        }

        setData({
          activeMissionsCount: missionsRes.count ?? 0,
          lastLog: logRes.data ?? null,
          lastCheckin: checkinRes.data ?? null,
        });
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : 'Failed to load live data');
      } finally {
        setLoading(false);
      }
    }
    fetchAll();
  }, []);

  const { activeMissionsCount, lastLog, lastCheckin } = data;

  return (
    <WorkbenchShell
      title="Operating Model"
      eyebrow="Captain TJR — Personal Operating Model"
      tagline="USS TJR · A unified view of how command is exercised, capacity allocated, and systems maintained"
      back={{ href: '/knowledge-workbench', label: 'Knowledge Workbench' }}
    >
      <div className="flex flex-col gap-4">
        <Card title="Live — latest values from source tables">
          {loadError && (
            <div className="mb-3 rounded-md border border-state-crit/50 bg-state-crit/10 px-3 py-2 text-xs text-state-crit-on">
              Couldn&rsquo;t load live data — the tiles below may be blank because of a connection error, not because there is nothing to show.
              <span className="mt-1 block font-mono text-[10px] text-wb-ink2">{loadError}</span>
            </div>
          )}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-md border border-wb-line bg-wb-bg p-4">
              <div className="mb-1 text-xs uppercase tracking-widest text-wb-ink2">Active Missions</div>
              <div className="font-serif text-3xl text-wb-ink">{loading ? '—' : activeMissionsCount ?? '—'}</div>
            </div>
            <div className="rounded-md border border-wb-line bg-wb-bg p-4">
              <div className="mb-1 text-xs uppercase tracking-widest text-wb-ink2">Capacity Rating</div>
              <div className="font-serif text-3xl text-wb-ink">
                {loading ? '—' : lastLog?.captain_capacity_rating != null ? `${lastLog.captain_capacity_rating}/10` : '—'}
              </div>
            </div>
            <div className="rounded-md border border-wb-line bg-wb-bg p-4">
              <div className="mb-1 text-xs uppercase tracking-widest text-wb-ink2">Last Check-in</div>
              <div className="truncate font-serif text-2xl capitalize text-wb-ink">{loading ? '—' : lastCheckin?.capacity_state ?? '—'}</div>
            </div>
          </div>
        </Card>

        <Card title="Domains & Capacity Allocation">
          <p className="mb-3 text-[11px] uppercase tracking-wide text-wb-ink2">Reference · Operational focus (authored doctrine, not live data)</p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {DOMAINS.map((d) => (
              <div key={d.name} className="flex flex-col gap-2 rounded-md border border-wb-line bg-wb-bg p-4">
                <div className="flex items-center justify-between">
                  <span className="text-xl">{d.icon}</span>
                  <span className={`rounded px-2 py-0.5 font-sans text-xs ${priorityColor(d.priority)}`}>{d.priority}</span>
                </div>
                <div className="font-serif text-lg text-wb-ink">{d.name}</div>
                <p className="text-sm leading-snug text-wb-ink2">{d.description}</p>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Operating Principles">
          <p className="mb-3 text-[11px] uppercase tracking-wide text-wb-ink2">Reference · Decision framework (authored doctrine, not live data)</p>
          <ol className="space-y-3">
            {PRINCIPLES.map((p) => (
              <li key={p.num} className="flex items-start gap-4 rounded-md border border-wb-line bg-wb-bg px-4 py-3">
                <span className="w-6 shrink-0 font-serif text-xl text-wb-sage-deep">{p.num}</span>
                <div>
                  <div className="text-sm text-wb-ink">{p.title}</div>
                  <div className="mt-0.5 text-sm text-wb-ink2">{p.body}</div>
                </div>
              </li>
            ))}
          </ol>
        </Card>

        <Card title="Current Priorities">
          <p className="mb-3 text-[11px] uppercase tracking-wide text-wb-ink2">This week</p>
          {loading ? (
            <div className="text-sm text-wb-ink2">Loading…</div>
          ) : lastLog?.tomorrows_priority ? (
            <div>
              <blockquote className="border-l-4 border-wb-sage-deep pl-4 text-base leading-relaxed text-wb-ink">
                {lastLog.tomorrows_priority}
              </blockquote>
              <p className="mt-3 text-xs text-wb-ink2">Updated from last Captain&rsquo;s Log entry · {lastLog.log_date}</p>
            </div>
          ) : (
            <div className="text-sm text-wb-ink2">No Captain&rsquo;s Log entry found.</div>
          )}
        </Card>

        <Card title="Energy & Recovery Profile">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div>
              <div className="mb-3 text-xs uppercase tracking-widest text-wb-ink2">
                Operating Envelope <span className="normal-case tracking-normal text-wb-ink2/60">· reference</span>
              </div>
              <ul className="space-y-2">
                {SCHEDULE.map((s) => (
                  <li key={s.label} className="flex items-start gap-3 rounded-md border border-wb-line bg-wb-bg px-4 py-2">
                    <span className="w-44 shrink-0 text-sm text-wb-ink">{s.label}</span>
                    <span className="text-sm text-wb-ink2">{s.time}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <div className="mb-3 text-xs uppercase tracking-widest text-wb-ink2">
                Last Capacity Check-in <span className="normal-case tracking-normal text-wb-ink2/60">· live</span>
              </div>
              {loading ? (
                <div className="text-sm text-wb-ink2">Loading…</div>
              ) : lastCheckin ? (
                <div className="space-y-2 rounded-md border border-wb-line bg-wb-bg p-4">
                  <div className="flex justify-between">
                    <span className="text-sm text-wb-ink2">Type</span>
                    <span className="font-sans text-sm capitalize text-wb-ink">{lastCheckin.checkin_type ?? '—'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-wb-ink2">Pain</span>
                    <span className="font-sans text-sm text-wb-ink">{lastCheckin.pain_score != null ? `${lastCheckin.pain_score}/10` : '—'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-wb-ink2">Capacity</span>
                    <span className="font-sans text-sm capitalize text-wb-ink">{lastCheckin.capacity_state ?? '—'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-wb-ink2">Nervous system</span>
                    <span className="font-sans text-sm capitalize text-wb-ink">{lastCheckin.regulation_state ?? '—'}</span>
                  </div>
                  {lastCheckin.captured_at && (
                    <div className="border-t border-wb-line pt-1 text-xs text-wb-ink2">
                      Captured: {new Date(lastCheckin.captured_at).toLocaleString()}
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-sm text-wb-ink2">No capacity check-in data available.</div>
              )}
            </div>
          </div>
        </Card>
      </div>
    </WorkbenchShell>
  );
}
