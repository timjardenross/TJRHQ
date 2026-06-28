'use client';

import { useState, useEffect } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { StatusBadge } from '@/components/StatusBadge';

interface LiveData {
  activeMissionsCount: number | null;
  lastLog: { log_date: string; captain_capacity_rating: number | null; todays_intention: string | null } | null;
  lastPulse: { pulse_type: string | null; pain_score: number | null; energy: number | null; mood: number | null; captured_at: string | null } | null;
}

const DOMAINS = [
  { icon: '🏥', name: 'Health', description: 'Recovery-led operations. Pain management, CPAP adherence, fatigue mapping.', priority: 'P0', accent: 'text-medical-on' },
  { icon: '💼', name: 'Career', description: 'Strategic positioning and professional development.', priority: 'P1', accent: 'text-command-on' },
  { icon: '🚀', name: 'USS TJR', description: 'Command Centre build, intelligence systems, operational excellence.', priority: 'P1', accent: 'text-command-on' },
  { icon: '📚', name: 'Learning', description: 'AI/ML, systems thinking, leadership frameworks.', priority: 'P2', accent: 'text-science-on' },
  { icon: '🤝', name: 'Relationships', description: 'Family, crew, professional network maintenance.', priority: 'P2', accent: 'text-science-on' },
  { icon: '🎯', name: 'Personal', description: 'Identity, values, long-term vision.', priority: 'P3', accent: 'text-operations-on' },
];

const PRINCIPLES = [
  { num: 1, title: 'Recovery First', body: 'No decision or commitment that compromises recovery posture.' },
  { num: 2, title: 'Mission Clarity', body: 'Every piece of work has a mission ID and a clear outcome.' },
  { num: 3, title: 'Intelligent Defaults', body: 'The system handles routine; the Captain handles judgement.' },
  { num: 4, title: 'Evidence-Based Decisions', body: 'Decisions are logged, rated, and reviewed.' },
  { num: 5, title: 'Sustainable Pace', body: 'Capacity is protected. Overcommitment is flagged and resolved.' },
  { num: 6, title: 'Continuous Learning', body: 'Lessons are captured and fed back into the system.' },
];

const SCHEDULE = [
  { label: 'Peak performance', time: 'Morning (0800–1200)', accent: 'text-engineering-on' },
  { label: 'Managed capacity', time: 'Afternoon (1200–1600)', accent: 'text-science-on' },
  { label: 'Wind-down', time: 'Evening (1600–2000)', accent: 'text-operations-on' },
  { label: 'Recovery priority', time: 'Deep sleep, CPAP compliance, pain management', accent: 'text-medical-on' },
];

function priorityColor(p: string) {
  if (p === 'P0') return 'text-medical-on bg-medical/10 border border-medical/30';
  if (p === 'P1') return 'text-command-on bg-command/10 border border-command/30';
  if (p === 'P2') return 'text-science-on bg-science/10 border border-science/30';
  return 'text-operations-on bg-operations/10 border border-operations/30';
}

export default function OperatingModelPage() {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<LiveData>({ activeMissionsCount: null, lastLog: null, lastPulse: null });

  useEffect(() => {
    const supabase = createSupabaseBrowserClient();
    async function fetchAll() {
      const [missionsRes, logRes, pulseRes] = await Promise.all([
        supabase
          .from('missions')
          .select('mission_id', { count: 'exact', head: true })
          .not('status', 'in', '(COMPLETE,DEFERRED,CLOSED)'),
        supabase
          .from('captains_log_entries')
          .select('log_date, captain_capacity_rating, todays_intention')
          .order('log_date', { ascending: false })
          .limit(1)
          .maybeSingle(),
        supabase
          .from('recovery_pulses')
          .select('pulse_type, pain_score, energy, mood, captured_at')
          .order('captured_at', { ascending: false })
          .limit(1)
          .maybeSingle(),
      ]);

      setData({
        activeMissionsCount: missionsRes.count ?? 0,
        lastLog: logRes.data ?? null,
        lastPulse: pulseRes.data ?? null,
      });
      setLoading(false);
    }
    fetchAll();
  }, []);

  const { activeMissionsCount, lastLog, lastPulse } = data;

  return (
    <div className="space-y-6 p-6">
      {/* Section 1 — Header + Live Stats */}
      <LCARSPanel title="Operating Model" accent="command" eyebrow="USS-TJR-MSN-3B-002">
        <div className="mb-6">
          <h1 className="font-lcars text-2xl text-foreground tracking-wide">
            Captain TJR — Personal Operating Model
          </h1>
          <p className="text-lcars-muted text-sm mt-1">
            A unified view of how command is exercised, capacity allocated, and systems maintained.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-panel border border-edge rounded-lcars p-4">
            <div className="text-lcars-muted text-xs uppercase tracking-widest mb-1">Active Missions</div>
            <div className="font-lcars text-3xl text-command-on">
              {loading ? '—' : activeMissionsCount ?? '—'}
            </div>
          </div>
          <div className="bg-panel border border-edge rounded-lcars p-4">
            <div className="text-lcars-muted text-xs uppercase tracking-widest mb-1">Capacity Rating</div>
            <div className="font-lcars text-3xl text-science-on">
              {loading ? '—' : lastLog?.captain_capacity_rating != null ? `${lastLog.captain_capacity_rating}/10` : '—'}
            </div>
          </div>
          <div className="bg-panel border border-edge rounded-lcars p-4">
            <div className="text-lcars-muted text-xs uppercase tracking-widest mb-1">Last Recovery</div>
            <div className="font-lcars text-2xl text-medical-on truncate">
              {loading ? '—' : lastPulse?.pulse_type ?? '—'}
            </div>
          </div>
        </div>
      </LCARSPanel>

      {/* Section 2 — Domains */}
      <LCARSPanel title="Domains & Capacity Allocation" accent="science" eyebrow="Operational focus">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {DOMAINS.map((d) => (
            <div key={d.name} className="bg-panel border border-edge rounded-lcars p-4 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-xl">{d.icon}</span>
                <span className={`text-xs font-lcars px-2 py-0.5 rounded ${priorityColor(d.priority)}`}>
                  {d.priority}
                </span>
              </div>
              <div className={`font-lcars text-lg ${d.accent}`}>{d.name}</div>
              <p className="text-lcars-muted text-sm leading-snug">{d.description}</p>
            </div>
          ))}
        </div>
      </LCARSPanel>

      {/* Section 3 — Operating Principles */}
      <LCARSPanel title="Operating Principles" accent="medical" eyebrow="Decision framework">
        <ol className="space-y-3">
          {PRINCIPLES.map((p) => (
            <li key={p.num} className="flex gap-4 items-start bg-panel border border-edge rounded-lcars px-4 py-3">
              <span className="font-lcars text-medical-on text-xl w-6 shrink-0">{p.num}</span>
              <div>
                <div className="font-lcars text-foreground text-sm">{p.title}</div>
                <div className="text-lcars-muted text-sm mt-0.5">{p.body}</div>
              </div>
            </li>
          ))}
        </ol>
      </LCARSPanel>

      {/* Section 4 — Current Priorities */}
      <LCARSPanel title="Current Priorities" accent="command" eyebrow="This week">
        {loading ? (
          <div className="text-lcars-muted text-sm">Loading...</div>
        ) : lastLog?.todays_intention ? (
          <div>
            <blockquote className="border-l-4 border-command pl-4 text-foreground text-base leading-relaxed">
              {lastLog.todays_intention}
            </blockquote>
            <p className="text-lcars-muted text-xs mt-3">
              Updated from last Captain&apos;s Log entry · {lastLog.log_date}
            </p>
          </div>
        ) : (
          <div className="text-lcars-muted text-sm">No Captain&apos;s Log entry found.</div>
        )}
      </LCARSPanel>

      {/* Section 5 — Energy & Recovery Profile */}
      <LCARSPanel title="Energy & Recovery Profile" accent="medical" eyebrow="Operational posture">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div>
            <div className="text-lcars-muted text-xs uppercase tracking-widest mb-3">Operating Envelope</div>
            <ul className="space-y-2">
              {SCHEDULE.map((s) => (
                <li key={s.label} className="flex items-start gap-3 bg-panel border border-edge rounded-lcars px-4 py-2">
                  <span className={`font-lcars text-sm w-44 shrink-0 ${s.accent}`}>{s.label}</span>
                  <span className="text-lcars-muted text-sm">{s.time}</span>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <div className="text-lcars-muted text-xs uppercase tracking-widest mb-3">Last Recovery Pulse</div>
            {loading ? (
              <div className="text-lcars-muted text-sm">Loading...</div>
            ) : lastPulse ? (
              <div className="bg-panel border border-edge rounded-lcars p-4 space-y-2">
                <div className="flex justify-between">
                  <span className="text-lcars-muted text-sm">Type</span>
                  <span className="text-foreground text-sm font-lcars">{lastPulse.pulse_type ?? '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-lcars-muted text-sm">Pain</span>
                  <span className="text-medical-on text-sm font-lcars">{lastPulse.pain_score != null ? `${lastPulse.pain_score}/10` : '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-lcars-muted text-sm">Energy</span>
                  <span className="text-engineering-on text-sm font-lcars">{lastPulse.energy != null ? `${lastPulse.energy}/10` : '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-lcars-muted text-sm">Mood</span>
                  <span className="text-science-on text-sm font-lcars">{lastPulse.mood != null ? `${lastPulse.mood}/10` : '—'}</span>
                </div>
                {lastPulse.captured_at && (
                  <div className="text-lcars-muted text-xs pt-1 border-t border-edge">
                    Captured: {new Date(lastPulse.captured_at).toLocaleString()}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-lcars-muted text-sm">No recovery pulse data available.</div>
            )}
          </div>
        </div>
      </LCARSPanel>
    </div>
  );
}
