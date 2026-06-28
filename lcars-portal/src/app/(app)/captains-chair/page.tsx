'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { LCARSPanel } from '@/components/LCARSPanel';
import { fetchInboxCaptures } from '@/lib/capture';

// ── Types ─────────────────────────────────────────────────────────────────────

interface MissionSummary {
  mission_id: string;
  title: string;
  priority: string | null;
  status: string;
}

interface IntelSignal {
  event_id: string;
  raw_title: string;
  event_type: string | null;
  customer_impact: string | null;
  banking_relevance: string | null;
  organisation: string | null;
  rank_score: number | null;
  collected_at: string;
  canonical_url: string | null;
}

interface OperatingPicture {
  generated_at: string;
  missions: {
    active_count: number;
    blocked_count: number;
    awaiting_approval_count: number;
    active: MissionSummary[];
    blocked: MissionSummary[];
    awaiting_approval: MissionSummary[];
  };
  decisions: {
    open_count: number;
  };
  top_signals: IntelSignal[];
  next_actions: string[];
}

interface WellnessData {
  daily: {
    log_date: string;
    sleep_hours: number | null;
    sleep_quality: string | null;
    energy: string | null;
    mood: string | null;
    nervous_system_state: string | null;
    from_pulse?: boolean;
  } | null;
  pulse: {
    energy: string | null;
    mood: string | null;
    stress: string | null;
    pain_score: number | null;
    captured_at: string;
  } | null;
  insights: {
    llm_narrative: string | null;
    risk_flags: string[] | null;
  } | null;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const PRIORITY_EMOJI: Record<string, string> = { P0: '🔥', P1: '⚡', P2: '•', P3: '·' };

function energyScore(energy: string | null): number | null {
  if (!energy) return null;
  const map: Record<string, number> = { high: 90, good: 75, moderate: 60, low: 40, depleted: 20 };
  return map[energy.toLowerCase()] ?? null;
}

function scoreColour(score: number): string {
  if (score >= 70) return 'text-science-on';
  if (score >= 40) return 'text-operations-on';
  return 'text-destructive';
}

function sleepColour(hours: number | null): string {
  if (!hours) return 'text-lcars-muted';
  if (hours >= 7) return 'text-science-on';
  if (hours >= 5.5) return 'text-operations-on';
  return 'text-destructive';
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Skeleton({ className }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-panel-2/60 ${className ?? 'h-4 w-full'}`} />;
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CaptainsChairPage() {
  const [op, setOp] = useState<OperatingPicture | null>(null);
  const [wellness, setWellness] = useState<WellnessData | null>(null);
  const [inboxCount, setInboxCount] = useState<number | null>(null);
  const [opLoading, setOpLoading] = useState(true);
  const [wellnessLoading, setWellnessLoading] = useState(true);
  const [opError, setOpError] = useState(false);

  const fetchOp = useCallback(async () => {
    setOpLoading(true);
    setOpError(false);
    try {
      const res = await fetch('/api/operating-picture');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: OperatingPicture = await res.json();
      setOp(data);
    } catch {
      setOpError(true);
    } finally {
      setOpLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOp();

    // Wellness
    (async () => {
      try {
        const res = await fetch('/api/wellness');
        if (res.ok) setWellness(await res.json());
      } catch { /* degrade gracefully */ }
      finally { setWellnessLoading(false); }
    })();

    // Capture inbox count
    (async () => {
      try {
        const items = await fetchInboxCaptures({ limit: 100 });
        setInboxCount(items.length);
      } catch {
        setInboxCount(0);
      }
    })();
  }, [fetchOp]);

  // ── Derived values ──────────────────────────────────────────────────────────

  const activeMissions = op?.missions.active ?? [];
  const highPriority = activeMissions
    .filter(m => m.priority === 'P0' || m.priority === 'P1')
    .slice(0, 3);

  const todayStr = new Date().toISOString().slice(0, 10);
  const energyVal = energyScore(wellness?.daily?.energy ?? null);
  const sleepHours = wellness?.daily?.sleep_hours ?? null;
  const hasHealthData = !!wellness?.daily || !!wellness?.pulse;
  const isToday = wellness?.daily?.log_date === todayStr || !!wellness?.pulse;
  const fromPulseOnly = !wellness?.daily?.sleep_hours && !!wellness?.pulse;

  return (
    <div className="flex flex-col gap-4">

      {/* ── Section 1: Operating Picture ───────────────────────────────────── */}
      <LCARSPanel
        title="Operating Picture"
        accent="command"
        eyebrow="MSN-3C · Captain's Chair"
        actions={
          <button
            onClick={fetchOp}
            disabled={opLoading}
            className="rounded-lcars border border-edge px-3 py-1 text-[10px] uppercase tracking-wider text-lcars-muted transition-colors hover:border-command hover:text-command-on disabled:opacity-40"
          >
            {opLoading ? 'Loading…' : 'Refresh'}
          </button>
        }
      >
        {opLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-5 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <div className="flex gap-2">
              <Skeleton className="h-6 w-20" />
              <Skeleton className="h-6 w-24" />
            </div>
          </div>
        ) : opError ? (
          <p className="text-sm text-lcars-muted italic">Operating picture unavailable.</p>
        ) : op ? (
          <div className="space-y-3">
            {op.next_actions.length > 0 && (
              <p className="font-semibold text-lcars-text leading-relaxed">
                {op.next_actions[0]}
              </p>
            )}
            {op.next_actions.length > 1 && (
              <ul className="space-y-1">
                {op.next_actions.slice(1).map((a, i) => (
                  <li key={i} className="text-sm text-lcars-muted">— {a}</li>
                ))}
              </ul>
            )}
            {op.next_actions.length === 0 && (
              <p className="text-sm text-lcars-muted italic">No flags. System nominal.</p>
            )}
            <div className="flex flex-wrap gap-2 pt-1">
              {op.missions.blocked_count > 0 && (
                <span className="rounded-full border border-destructive/40 bg-destructive/10 px-3 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-destructive">
                  {op.missions.blocked_count} blocked
                </span>
              )}
              {op.missions.awaiting_approval_count > 0 && (
                <span className="rounded-full border border-operations/40 bg-operations/10 px-3 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-operations-on">
                  {op.missions.awaiting_approval_count} awaiting approval
                </span>
              )}
              {op.decisions.open_count > 0 && (
                <span className="rounded-full border border-science/40 bg-science/10 px-3 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-science-on">
                  {op.decisions.open_count} open decisions
                </span>
              )}
              {op.missions.blocked_count === 0 && op.missions.awaiting_approval_count === 0 && op.decisions.open_count === 0 && (
                <span className="rounded-full border border-science/30 bg-science/10 px-3 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-science-on">
                  All clear
                </span>
              )}
            </div>
            <p className="text-[10px] text-lcars-muted">
              Generated {new Date(op.generated_at).toLocaleTimeString()}
            </p>
          </div>
        ) : null}
      </LCARSPanel>

      {/* ── Section 2: Three-column grid ───────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">

        {/* Col A: Health Today */}
        <LCARSPanel title="Health Today" accent="medical" eyebrow="Human Systems">
          {wellnessLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-12 w-20" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          ) : !hasHealthData || !isToday ? (
            <div className="space-y-2">
              <p className="text-sm text-lcars-muted italic">No health data for today.</p>
              <Link href="/medical" className="inline-block rounded-lcars border border-medical/40 px-3 py-1.5 text-xs font-semibold text-medical-on transition-colors hover:bg-medical/10">
                Log recovery pulse →
              </Link>
            </div>
          ) : (
            <div className="space-y-3">
              {fromPulseOnly && (
                <p className="text-[10px] uppercase tracking-wider text-medical-on/70">
                  ● From recovery pulse · {wellness?.pulse?.captured_at ? new Date(wellness.pulse.captured_at).toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: false }) : ''}
                </p>
              )}
              {energyVal !== null && (
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-lcars-muted mb-1">Energy score</p>
                  <p className={`font-lcars text-4xl font-bold ${scoreColour(energyVal)}`}>{energyVal}</p>
                </div>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {sleepHours !== null && (
                  <div className="rounded-lcars border border-edge bg-panel-2/40 p-2 text-center">
                    <p className={`font-lcars text-xl font-bold ${sleepColour(sleepHours)}`}>{sleepHours}h</p>
                    <p className="text-[9px] uppercase tracking-wider text-lcars-muted">Sleep</p>
                  </div>
                )}
                {wellness?.daily?.energy && (
                  <div className="rounded-lcars border border-edge bg-panel-2/40 p-2 text-center">
                    <p className="font-lcars text-sm font-bold text-lcars-text capitalize">{wellness.daily.energy}</p>
                    <p className="text-[9px] uppercase tracking-wider text-lcars-muted">Energy</p>
                  </div>
                )}
                {wellness?.daily?.mood && (
                  <div className="rounded-lcars border border-edge bg-panel-2/40 p-2 text-center">
                    <p className="font-lcars text-sm font-bold text-lcars-text capitalize">{wellness.daily.mood}</p>
                    <p className="text-[9px] uppercase tracking-wider text-lcars-muted">Mood</p>
                  </div>
                )}
                {wellness?.daily?.nervous_system_state && (
                  <div className="rounded-lcars border border-edge bg-panel-2/40 p-2 text-center">
                    <p className="font-lcars text-xs font-bold text-lcars-text capitalize">{wellness.daily.nervous_system_state}</p>
                    <p className="text-[9px] uppercase tracking-wider text-lcars-muted">NS State</p>
                  </div>
                )}
                {wellness?.daily?.sleep_quality && (
                  <div className="rounded-lcars border border-edge bg-panel-2/40 p-2 text-center col-span-2">
                    <p className="font-lcars text-sm font-bold text-lcars-text capitalize">{wellness.daily.sleep_quality}</p>
                    <p className="text-[9px] uppercase tracking-wider text-lcars-muted">Sleep quality</p>
                  </div>
                )}
              </div>
              {wellness?.pulse?.pain_score != null && wellness.pulse.pain_score > 0 && (
                <p className="text-[11px] text-operations-on">⚠ Pain: {wellness.pulse.pain_score}/10</p>
              )}
              {wellness?.insights?.risk_flags && wellness.insights.risk_flags.length > 0 && (
                <div className="space-y-1">
                  {wellness.insights.risk_flags.slice(0, 2).map((flag, i) => (
                    <p key={i} className="text-[11px] text-operations-on">⚠ {flag}</p>
                  ))}
                </div>
              )}
            </div>
          )}
        </LCARSPanel>

        {/* Col B: Active Missions */}
        <LCARSPanel title="Active Missions" accent="command" eyebrow="Operations">
          {opLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-10 w-16" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          ) : opError ? (
            <p className="text-sm text-lcars-muted italic">Unavailable</p>
          ) : op ? (
            <div className="space-y-3">
              <div className="flex gap-3">
                <div className="rounded-lcars border border-edge bg-panel-2/40 p-3 text-center flex-1">
                  <p className="font-lcars text-3xl font-bold text-command-on">{op.missions.active_count}</p>
                  <p className="text-[9px] uppercase tracking-wider text-lcars-muted">Active</p>
                </div>
                {op.missions.blocked_count > 0 && (
                  <div className="rounded-lcars border border-destructive/40 bg-destructive/10 p-3 text-center flex-1">
                    <p className="font-lcars text-3xl font-bold text-destructive">{op.missions.blocked_count}</p>
                    <p className="text-[9px] uppercase tracking-wider text-lcars-muted">Blocked</p>
                  </div>
                )}
              </div>
              {highPriority.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-[10px] uppercase tracking-wider text-lcars-muted">High priority</p>
                  {highPriority.map(m => (
                    <div key={m.mission_id} className="flex items-start gap-2 text-xs">
                      <span className="shrink-0">{PRIORITY_EMOJI[m.priority ?? 'P3'] ?? '·'}</span>
                      <span className="text-lcars-text line-clamp-2">{m.title}</span>
                    </div>
                  ))}
                </div>
              )}
              <Link
                href="/missions"
                className="inline-block text-[11px] font-semibold text-command-on hover:underline"
              >
                View all missions →
              </Link>
            </div>
          ) : null}
        </LCARSPanel>

        {/* Col C: Signal Board */}
        <LCARSPanel title="Signal Board" accent="science" eyebrow="Intelligence · Last 7 days">
          {opLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-5/6" />
            </div>
          ) : opError ? (
            <p className="text-sm text-lcars-muted italic">Unavailable</p>
          ) : op ? (
            <div className="space-y-2">
              {(op.top_signals ?? []).length === 0 ? (
                <p className="text-sm text-lcars-muted">No signals this period.</p>
              ) : (
                (op.top_signals ?? []).map((s) => {
                  const impact = s.customer_impact ?? s.banking_relevance ?? '';
                  const dot = impact === 'high' ? 'bg-red-400' : impact === 'medium' ? 'bg-yellow-400' : 'bg-edge';
                  return (
                    <div key={s.event_id} className="flex items-start gap-2">
                      <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
                      <div className="min-w-0">
                        {s.canonical_url ? (
                          <a href={s.canonical_url} target="_blank" rel="noopener noreferrer"
                             className="text-xs text-lcars-text leading-snug hover:text-science line-clamp-2">
                            {s.raw_title}
                          </a>
                        ) : (
                          <p className="text-xs text-lcars-text leading-snug line-clamp-2">{s.raw_title}</p>
                        )}
                        <p className="text-[10px] text-lcars-muted mt-0.5">
                          {s.event_type?.replace(/_/g, ' ')}
                          {s.organisation ? ` · ${s.organisation}` : ''}
                        </p>
                      </div>
                    </div>
                  );
                })
              )}
              <Link
                href="/intelligence?tab=signals"
                className="inline-block text-[11px] font-semibold text-science hover:underline pt-1"
              >
                View all signals →
              </Link>
            </div>
          ) : null}
        </LCARSPanel>

      </div>

      {/* ── Section 3: Capture Inbox ────────────────────────────────────────── */}
      <div className="rounded-lcars border border-edge bg-panel/60 px-4 py-3 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <span className="text-xl">📥</span>
          {inboxCount === null ? (
            <Skeleton className="h-4 w-40" />
          ) : inboxCount === 0 ? (
            <p className="text-sm text-lcars-muted">Inbox clear</p>
          ) : (
            <p className="text-sm text-lcars-text font-semibold">
              <span className="text-operations-on font-bold">{inboxCount}</span>{' '}
              item{inboxCount !== 1 ? 's' : ''} pending review
            </p>
          )}
        </div>
        <Link
          href="/capture"
          className="rounded-lcars border border-edge px-3 py-1.5 text-[11px] uppercase tracking-wide text-lcars-muted transition-colors hover:border-command hover:text-command-on"
        >
          Open capture →
        </Link>
      </div>

    </div>
  );
}
