/**
 * Weekly Review — cross-workbench aggregation.
 *
 * GET  returns one computed snapshot: system-wide rollups + one section
 *      per existing workbench, each with 4-6 domain-specific signals.
 *      Every underlying query is independently try/caught (Promise.allSettled)
 *      so one renamed/broken table degrades that one signal to "unavailable"
 *      rather than failing the whole review — this route reads across ~15
 *      tables it doesn't own, schema drift in any one of them is expected
 *      over time.
 * POST marks the current week's review complete — persists a frozen summary
 *      snapshot + notes to weekly_reviews (see migration 0164). Does not
 *      mutate any of the source tables it read from.
 *
 * No new data pipeline: every query here mirrors an existing, already-live
 * query pattern from that workbench's own API routes (see file comments per
 * section) — this route is read-only composition, not a new source of truth.
 */

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import type { Signal, SignalItem, SystemSummary, WorkbenchSection } from '@/lib/weeklyReview';
import { buildSynthesis, flattenSignalCounts } from './synthesis';
import { getAssessedContext } from '@/app/api/human-systems/assessed-context';

type SB = Awaited<ReturnType<typeof createSupabaseServerClient>>;

const DAY_MS = 86_400_000;

function weekWindow() {
  const now = new Date();
  const weekStart = new Date(now.getTime() - 7 * DAY_MS);
  return { weekStart, weekEnd: now, weekStartISO: weekStart.toISOString(), weekEndISO: now.toISOString() };
}

/** Runs a query builder and returns rows, or [] + unavailable=true on any
 * error — never throws, never lets one broken table sink the whole review. */
async function safe<T>(fn: () => PromiseLike<{ data: T[] | null; error: unknown }>): Promise<{ rows: T[]; unavailable: boolean }> {
  try {
    const { data, error } = await fn();
    if (error) return { rows: [], unavailable: true };
    return { rows: data ?? [], unavailable: false };
  } catch {
    return { rows: [], unavailable: true };
  }
}

function signal(key: string, label: string, rows: SignalItem[], tone: Signal['tone'], unavailable = false): Signal {
  return { key, label, count: rows.length, tone, items: rows.slice(0, 8), unavailable };
}

// ── Captain's Chair ──────────────────────────────────────────────────────────
// Sources: mission_delivery (lib/delivery.ts pattern), decide_ledger,
// captured_items (mission/unreviewed), intelligence_notes.
async function reviewChair(sb: SB, since: string): Promise<WorkbenchSection> {
  const [blocked, decisions, unreviewed, notes] = await Promise.all([
    safe(() => sb.from('mission_delivery').select('title, delivery_state, pr_url').eq('delivery_state', 'blocked').limit(20)),
    safe(() => sb.from('decide_ledger').select('id, question, action, decided_at').eq('action', 'hold').gte('decided_at', since).limit(20)),
    safe(() => sb.from('captured_items').select('id, title, captured_at').eq('classification', 'mission').eq('review_status', 'unreviewed').gte('captured_at', since).limit(20)),
    safe(() => sb.from('intelligence_notes').select('id, title, status, created_at').gte('created_at', since).limit(20)),
  ]);

  return {
    key: 'chair', title: "Captain's Chair", href: '/captains-chair-workbench',
    signals: [
      signal('blocked', 'Blocked / at risk', blocked.rows.map((r) => ({ id: r.title, title: r.title, meta: r.pr_url ?? undefined })), 'crit', blocked.unavailable),
      signal('decisions', 'Unresolved decisions (held)', decisions.rows.map((r) => ({ id: r.id, title: r.question })), 'warn', decisions.unavailable),
      signal('unreviewed', 'Mission captures awaiting review', unreviewed.rows.map((r) => ({ id: r.id, title: r.title ?? '(untitled)' })), 'warn', unreviewed.unavailable),
      signal('notes', 'Notes captured this week', notes.rows.map((r) => ({ id: r.id, title: r.title, meta: r.status })), 'neutral', notes.unavailable),
    ],
  };
}

// ── Technical OSINT ───────────────────────────────────────────────────────────
// Sources: intelligence_events, signal_corroboration, signal_escalation_history.
async function reviewOsint(sb: SB, since: string): Promise<WorkbenchSection> {
  const [highConf, escalations, thisWeekEvents] = await Promise.all([
    safe(() => sb.from('intelligence_events').select('event_id, raw_title, canonical_url, confidence, collected_at').eq('suppressed', false).gte('collected_at', since).gte('confidence', 0.7).order('confidence', { ascending: false }).limit(20)),
    safe(() => sb.from('signal_escalation_history').select('signal_id, reason, escalated_at').gte('escalated_at', since).limit(20)),
    safe(() => sb.from('intelligence_events').select('event_id').eq('suppressed', false).gte('collected_at', since).limit(500)),
  ]);

  let corroboration: { rows: { signal_id: string }[]; unavailable: boolean } = { rows: [], unavailable: false };
  if (!thisWeekEvents.unavailable && thisWeekEvents.rows.length > 0) {
    const ids = thisWeekEvents.rows.map((r) => r.event_id);
    corroboration = await safe(() => sb.from('signal_corroboration').select('signal_id').in('signal_id', ids));
  }
  const corroboratedIds = new Set(corroboration.rows.map((r) => r.signal_id));
  const uncorroboratedCount = thisWeekEvents.rows.filter((r) => !corroboratedIds.has(r.event_id)).length;

  return {
    key: 'osint', title: 'Technical OSINT', href: '/intelligence-workbench',
    signals: [
      signal('high-confidence', 'New high-confidence findings', highConf.rows.map((r) => ({ id: r.event_id, title: r.raw_title, href: r.canonical_url ?? undefined, meta: `${Math.round((r.confidence ?? 0) * 100)}%` })), 'ok', highConf.unavailable),
      signal('escalated', 'Crossed an escalation threshold', escalations.rows.map((r) => ({ id: r.signal_id, title: r.reason ?? '(no reason recorded)' })), 'crit', escalations.unavailable),
      { key: 'uncorroborated', label: 'Needs corroboration', count: uncorroboratedCount, tone: 'warn', items: [], unavailable: thisWeekEvents.unavailable || corroboration.unavailable },
    ],
  };
}

// ── Health OSINT ──────────────────────────────────────────────────────────────
// Sources: health_signals (published/curation-pending), health_adverse_events.
async function reviewHealthOsint(sb: SB, since: string): Promise<WorkbenchSection> {
  const [published, pending, strong, adverse] = await Promise.all([
    safe(() => sb.from('health_signals').select('signal_id, title, canonical_url, confidence_level, collected_at').eq('suppressed', false).gte('collected_at', since).limit(30)),
    safe(() => sb.from('health_signals').select('signal_id, title, canonical_url, collected_at').eq('auto_ingested', true).eq('auto_ingest_reviewed', false).gte('collected_at', since).limit(20)),
    safe(() => sb.from('health_signals').select('signal_id, title, canonical_url, confidence_level').eq('suppressed', false).gte('collected_at', since).eq('confidence_level', 'HIGH').limit(20)),
    safe(() => sb.from('health_adverse_events').select('id, description, fda_flagged, created_at').eq('fda_flagged', true).gte('created_at', since).limit(20)),
  ]);

  return {
    key: 'health-osint', title: 'Health OSINT', href: '/health-osint',
    signals: [
      signal('published', 'New / updated evidence', published.rows.map((r) => ({ id: r.signal_id, title: r.title, href: r.canonical_url ?? undefined, meta: r.confidence_level ?? undefined })), 'neutral', published.unavailable),
      signal('appraisal', 'Needs critical appraisal', pending.rows.map((r) => ({ id: r.signal_id, title: r.title, href: r.canonical_url ?? undefined })), 'warn', pending.unavailable),
      signal('strong', 'High-confidence signals', strong.rows.map((r) => ({ id: r.signal_id, title: r.title, href: r.canonical_url ?? undefined })), 'ok', strong.unavailable),
      signal('flagged', 'FDA-flagged adverse events', adverse.rows.map((r) => ({ id: String(r.id), title: r.description ?? '(no description)' })), 'crit', adverse.unavailable),
    ],
  };
}

// ── Content Workbench ─────────────────────────────────────────────────────────
// Source: comms_content. No performance/engagement table exists in this
// schema — "performance after publication" is deliberately omitted rather
// than faked.
//
// FIX (2026-09-05, Weekly Review synthesis mission): this section's
// "Drafts created" signal queried status='draft', a value that has never
// existed in comms_content's live status enum (confirmed live:
// archived/review/opportunity/ready_to_publish/published) — it always
// silently returned 0, a false zero rather than an honest "unavailable" or
// a real count, exactly the class of bug brief §29 warns against.
// Replaced with draft_generated_at (a real timestamp column) for "drafts
// generated," and added the 'ready' signal (status='ready_to_publish') the
// synthesis layer needs for the "Decide" carry-forward framing (brief §25).
async function reviewContent(sb: SB, since: string): Promise<WorkbenchSection> {
  const [drafted, published, review, ready, blocked] = await Promise.all([
    safe(() => sb.from('comms_content').select('id, title, draft_generated_at').gte('draft_generated_at', since).limit(20)),
    safe(() => sb.from('comms_content').select('id, title, updated_at').eq('status', 'published').gte('updated_at', since).limit(20)),
    safe(() => sb.from('comms_content').select('id, title, created_at').eq('status', 'review').gte('created_at', since).limit(20)),
    safe(() => sb.from('comms_content').select('id, title, scheduled_for').eq('status', 'ready_to_publish').limit(20)),
    safe(() => sb.from('comms_content').select('id, title, qa_status').eq('qa_status', 'qa_failed').limit(20)),
  ]);

  return {
    key: 'content', title: 'Content Workbench', href: '/content-workbench',
    signals: [
      signal('drafted', 'Drafts generated', drafted.rows.map((r) => ({ id: r.id, title: r.title ?? '(untitled)' })), 'neutral', drafted.unavailable),
      signal('published', 'Published', published.rows.map((r) => ({ id: r.id, title: r.title ?? '(untitled)' })), 'ok', published.unavailable),
      signal('review', 'Awaiting review', review.rows.map((r) => ({ id: r.id, title: r.title ?? '(untitled)' })), 'warn', review.unavailable),
      signal('ready', 'Ready to publish — decide', ready.rows.map((r) => ({ id: r.id, title: r.title ?? '(untitled)' })), 'warn', ready.unavailable),
      signal('blocked', 'Blocked (QA failed)', blocked.rows.map((r) => ({ id: r.id, title: r.title ?? '(untitled)' })), 'crit', blocked.unavailable),
    ],
  };
}

// ── Human Systems ─────────────────────────────────────────────────────────────
// Sources: physical_workout_sessions, capacity_checkins.
async function reviewHumanSystems(sb: SB, since: string): Promise<WorkbenchSection> {
  const [completed, overload, declined] = await Promise.all([
    safe(() => sb.from('physical_workout_sessions').select('id, session_type, started_at').eq('status', 'completed').gte('started_at', since).limit(20)),
    safe(() => sb.from('capacity_checkins').select('log_date, capacity_state, active_loads').eq('checkin_type', 'capacity').in('capacity_state', ['orange', 'red']).gte('log_date', since.slice(0, 10)).limit(20)),
    safe(() => sb.from('capacity_checkins').select('log_date, day_trajectory').eq('checkin_type', 'evening').eq('day_trajectory', 'declined').gte('log_date', since.slice(0, 10)).limit(20)),
  ]);

  return {
    key: 'human-systems', title: 'Human Systems', href: '/human-systems-workbench',
    signals: [
      signal('routines', 'Routines completed', completed.rows.map((r) => ({ id: r.id, title: r.session_type ?? 'session' })), 'ok', completed.unavailable),
      signal('overload', 'Overload days (orange/red)', overload.rows.map((r) => ({ id: r.log_date, title: r.log_date, meta: (r.active_loads ?? []).join(', ') || undefined })), 'warn', overload.unavailable),
      signal('declined', 'Days that trended down', declined.rows.map((r) => ({ id: r.log_date, title: r.log_date })), 'crit', declined.unavailable),
    ],
  };
}

// ── Ready Room (Human Execution Loop mission, brief §21/§26/§29) ───────────────
// Source: personal_tasks. Weekly Review reads execution evidence Ready Room
// already owns — it never queries this table anywhere else in this file
// before now, and never writes to it here either (brief §30/§51: carry
// forward is an attention decision, not a task-state mutation). Completion
// is reported as evidence for "what mattered," not a productivity score
// (brief §50/§58) — non-completion of a low-importance item is not framed
// as failure anywhere below.
async function reviewReadyRoom(sb: SB, since: string): Promise<WorkbenchSection> {
  const [completed, importantOpen, newlyWaiting, parked] = await Promise.all([
    safe(() => sb.from('personal_tasks').select('id, title, completed_at').eq('work_state', 'completed').gte('completed_at', since).limit(20)),
    safe(() => sb.from('personal_tasks').select('id, title, importance, due_date').gte('importance', 4).not('work_state', 'in', '(completed,abandoned)').limit(20)),
    safe(() => sb.from('personal_tasks').select('id, title, waiting_on, updated_at').eq('work_state', 'blocked').gte('updated_at', since).limit(20)),
    // Low-importance, no due date, untouched this week — genuinely safe to
    // leave parked (brief §31: "unavailable ≠ safe" — this is an evidenced
    // absence of urgency, not a guess), never itself a carry-forward item.
    safe(() => sb.from('personal_tasks').select('id, title').lte('importance', 2).is('due_date', null).not('work_state', 'in', '(completed,abandoned,blocked)').lt('updated_at', since).limit(20)),
  ]);

  return {
    key: 'ready-room', title: 'Ready Room', href: '/ready-room',
    signals: [
      signal('completed', 'Completed this week', completed.rows.map((r) => ({ id: r.id, title: r.title ?? '(untitled)' })), 'ok', completed.unavailable),
      signal('important-open', 'Important and still open', importantOpen.rows.map((r) => ({ id: r.id, title: r.title ?? '(untitled)', meta: r.due_date ?? undefined })), 'warn', importantOpen.unavailable),
      signal('newly-waiting', 'Newly waiting on someone else', newlyWaiting.rows.map((r) => ({ id: r.id, title: r.title ?? '(untitled)', meta: r.waiting_on ?? undefined })), 'neutral', newlyWaiting.unavailable),
      signal('parked', 'Low-priority, untouched this week', parked.rows.map((r) => ({ id: r.id, title: r.title ?? '(untitled)' })), 'neutral', parked.unavailable),
    ],
  };
}

// ── Advisory ───────────────────────────────────────────────────────────────────
// Source: advisory_sessions. No "actioned" column exists on this table — the
// closest real proxy for "not yet actioned" is result.attention_required on
// board sessions (the field the workbench itself already uses to flag a
// result as needing follow-up), not an invented status.
async function reviewAdvisory(sb: SB, since: string): Promise<WorkbenchSection> {
  const { rows, unavailable } = await safe(() =>
    sb.from('advisory_sessions').select('id, mode, question, result, created_at').gte('created_at', since).order('created_at', { ascending: false }).limit(50)
  );

  const carryForward = rows.filter((r) => {
    const result = r.result as { attention_required?: boolean } | null;
    return result?.attention_required === true;
  });

  return {
    key: 'advisory', title: 'Advisory', href: '/advisory-workbench',
    signals: [
      signal('sessions', 'Questions posed this week', rows.map((r) => ({ id: r.id, title: r.question, meta: r.mode })), 'neutral', unavailable),
      signal('carry-forward', 'Flagged for follow-up', carryForward.map((r) => ({ id: r.id, title: r.question })), 'warn', unavailable),
    ],
  };
}

// ── Briefs ─────────────────────────────────────────────────────────────────────
// Source: intelligence_briefs + outcome_records (source_type='intelligence_brief').
// No "consumed/read" tracking exists — omitted rather than faked.
async function reviewBriefs(sb: SB, since: string): Promise<WorkbenchSection> {
  const [generated, risky] = await Promise.all([
    safe(() => sb.from('intelligence_briefs').select('brief_id, generated_at, overall_risk').gte('generated_at', since).order('generated_at', { ascending: false }).limit(20)),
    safe(() => sb.from('intelligence_briefs').select('brief_id, generated_at, overall_risk').gte('generated_at', since).in('overall_risk', ['AMBER', 'RED']).limit(20)),
  ]);

  let triggered: { rows: { source_id: string; decision_or_action_taken: string | null }[]; unavailable: boolean } = { rows: [], unavailable: false };
  if (!generated.unavailable && generated.rows.length > 0) {
    triggered = await safe(() =>
      sb.from('outcome_records').select('source_id, decision_or_action_taken').eq('source_type', 'intelligence_brief').in('source_id', generated.rows.map((r) => r.brief_id))
    );
  }

  return {
    key: 'briefs', title: 'Briefs', href: '/briefs',
    signals: [
      signal('generated', 'Briefs this week', generated.rows.map((r) => ({ id: r.brief_id, title: new Date(r.generated_at).toLocaleDateString('en-AU'), href: `/intelligence-workbench/brief/${r.brief_id}`, meta: r.overall_risk ?? undefined })), 'neutral', generated.unavailable),
      signal('risk', 'Amber / Red risk', risky.rows.map((r) => ({ id: r.brief_id, title: new Date(r.generated_at).toLocaleDateString('en-AU'), href: `/intelligence-workbench/brief/${r.brief_id}`, meta: r.overall_risk ?? undefined })), 'crit', risky.unavailable),
      signal('triggered', 'Triggered a decision / action', triggered.rows.filter((r) => r.decision_or_action_taken).map((r) => ({ id: r.source_id, title: r.decision_or_action_taken ?? '' })), 'ok', triggered.unavailable),
    ],
  };
}

// ── HQ Status ──────────────────────────────────────────────────────────────────
// Sources: domain_heartbeat_latest (view), domain_heartbeats (failure history).
async function reviewAgentStatus(sb: SB, since: string): Promise<WorkbenchSection> {
  const [stale, neverSucceeded, failuresThisWeek] = await Promise.all([
    safe(() => sb.from('domain_heartbeat_latest').select('domain_key, last_status, last_checked_at').eq('is_stale', true).limit(20)),
    safe(() => sb.from('domain_heartbeat_latest').select('domain_key, never_succeeded').eq('never_succeeded', true).limit(20)),
    safe(() => sb.from('domain_heartbeats').select('domain_key, status, checked_at').eq('status', 'failed').gte('checked_at', since).limit(500)),
  ]);

  const failCounts = new Map<string, number>();
  for (const r of failuresThisWeek.rows) failCounts.set(r.domain_key, (failCounts.get(r.domain_key) ?? 0) + 1);
  const repeated = Array.from(failCounts.entries()).filter(([, n]) => n >= 2);

  return {
    key: 'agent-status', title: 'HQ Status', href: '/agent-status-workbench',
    signals: [
      signal('stale', 'Stale schedules (automation drift)', stale.rows.map((r) => ({ id: r.domain_key, title: r.domain_key, meta: r.last_status ?? undefined })), 'warn', stale.unavailable),
      signal('never', 'Never succeeded (needs escalation)', neverSucceeded.rows.map((r) => ({ id: r.domain_key, title: r.domain_key })), 'crit', neverSucceeded.unavailable),
      { key: 'repeated', label: 'Repeated failures this week', count: repeated.length, tone: 'crit', items: repeated.slice(0, 8).map(([key, n]) => ({ id: key, title: key, meta: `${n}×` })), unavailable: failuresThisWeek.unavailable },
    ],
  };
}

// "Newly important" and "Safe to ignore" removed here 2026-09-05 — see
// lib/weeklyReview.ts's SystemSummary doc comment for why. openLoops/
// waitingOn/urgentThisWeek remain as secondary diagnostics (brief §21).
function computeSummary(weekStartISO: string, weekEndISO: string, sections: WorkbenchSection[], lastCompletedAt: string | null): SystemSummary {
  let openLoops = 0, waitingOn = 0, urgentThisWeek = 0;
  for (const section of sections) {
    for (const s of section.signals) {
      if (s.unavailable) continue;
      if (s.tone === 'crit') { urgentThisWeek += s.count; }
      if (s.tone === 'warn') { openLoops += s.count; }
      if (s.key.includes('waiting') || s.key.includes('blocked') || s.key === 'appraisal' || s.key === 'never' || s.key === 'stale' || s.key === 'uncorroborated' || s.key === 'decisions') waitingOn += s.count;
    }
  }

  const reviewDebtDays = lastCompletedAt ? Math.floor((Date.now() - new Date(lastCompletedAt).getTime()) / DAY_MS) : null;

  return {
    weekStart: weekStartISO, weekEnd: weekEndISO,
    openLoops, waitingOn, urgentThisWeek,
    reviewDebtDays, lastCompletedAt,
  };
}

// ── Capacity-adjusted posture (brief §6/§16/§39) ─────────────────────────────
// Reuses Human Systems' own small assessed-context boundary rather than
// inventing a competing taxonomy (brief §16) or re-querying capacity_checkins
// itself (brief §39 — "do not import one workbench's implementation
// machinery into another"). getAssessedContext() is the same read every
// other consumer (Ready Room included) goes through.
async function fetchStrategicPosture(sb: SB) {
  try {
    const context = await getAssessedContext(sb);
    return {
      posture: context.strain_or_recovery_context.strategic_posture,
      message: context.strain_or_recovery_context.message,
      hasSignal: context.strain_or_recovery_context.trajectory !== 'insufficient_data',
    };
  } catch {
    // Human Systems couldn't be checked this run — fall back to a neutral
    // posture rather than crash the whole review; hasStrategicSignal=false
    // tells the synthesis layer to omit the recovery-trajectory learned
    // item/watch line rather than fabricate one.
    return { posture: 'steady' as const, message: 'Human Systems data was unavailable this run — posture defaults to steady.', hasSignal: false };
  }
}

export async function GET() {
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  try {
    const sb = await createSupabaseServerClient();
    const { weekStartISO, weekEndISO } = weekWindow();

    const [chair, osint, healthOsint, content, humanSystems, readyRoom, advisory, briefs, agentStatus, lastReview, posture] = await Promise.all([
      reviewChair(sb, weekStartISO),
      reviewOsint(sb, weekStartISO),
      reviewHealthOsint(sb, weekStartISO),
      reviewContent(sb, weekStartISO),
      reviewHumanSystems(sb, weekStartISO),
      reviewReadyRoom(sb, weekStartISO),
      reviewAdvisory(sb, weekStartISO),
      reviewBriefs(sb, weekStartISO),
      reviewAgentStatus(sb, weekStartISO),
      // Full summary jsonb (not just completed_at) — signalCounts, the
      // accepted next-week posture/carry-forward, and last week's
      // reflection all live inside it (brief §34/§36/§38's feedback loop).
      safe(() => sb.from('weekly_reviews').select('completed_at, summary, notes').not('completed_at', 'is', null).order('completed_at', { ascending: false }).limit(1)),
      fetchStrategicPosture(sb),
    ]);

    const workbenches = [chair, osint, healthOsint, content, humanSystems, readyRoom, advisory, briefs, agentStatus];
    const lastCompletedAt = lastReview.rows[0]?.completed_at ?? null;
    const summary = computeSummary(weekStartISO, weekEndISO, workbenches, lastCompletedAt);

    const priorSummary = lastReview.rows[0]?.summary as {
      signalCounts?: Record<string, number>;
      nextWeekPosture?: string;
      nextWeekPostureAccepted?: boolean;
      acceptedCarryForward?: string[];
    } | null;
    const priorSignalCounts = priorSummary?.signalCounts ?? null;
    const synthesis = buildSynthesis(workbenches, priorSignalCounts, posture.posture, posture.message, posture.hasSignal);
    const signalCounts = flattenSignalCounts(workbenches);

    // What was planned last week vs. what today's live evidence says now —
    // shown side by side, never merged. Fresh Human Systems evidence
    // (posture, computed above from today's own check-in/window) always
    // wins for current-day decisions; the prior plan is read-only context,
    // exactly the Sunday-STEADY/Monday-PROTECT example (brief §34).
    const priorReflection = (lastReview.rows[0] as { notes?: string | null } | undefined)?.notes ?? null;
    const priorWeek = priorSummary?.nextWeekPostureAccepted || priorReflection
      ? {
          posture: priorSummary?.nextWeekPostureAccepted ? priorSummary.nextWeekPosture ?? null : null,
          carryForward: priorSummary?.nextWeekPostureAccepted ? priorSummary.acceptedCarryForward ?? [] : [],
          reflection: priorReflection,
        }
      : null;

    return NextResponse.json({ summary, workbenches, synthesis, signalCounts, priorWeek });
  } catch (err) {
    return NextResponse.json({ error: 'Failed to build weekly review', detail: err instanceof Error ? err.message : String(err) }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  try {
    const body = await req.json();
    const notes = typeof body?.notes === 'string' ? body.notes.slice(0, 4000) : null;
    const summary = body?.summary ?? null;
    // signalCounts rides inside the same summary jsonb (additive field, not
    // a new table) — next week's GET reads it back out for What Changed's
    // week-over-week diff. Older rows simply lack this key, which
    // buildSynthesis already treats as "no prior data" (noHistory), never
    // as "no change."
    const signalCounts = body?.signalCounts && typeof body.signalCounts === 'object' ? body.signalCounts : null;
    const nextWeekPostureAccepted = body?.nextWeekPostureAccepted === true;
    // Actual accepted posture label + carry-forward, so next week's GET can
    // read back what was planned (brief §34/§38) — previously only the
    // boolean rode along, so the plan itself was silently discarded the
    // moment the review closed.
    const nextWeekPosture = nextWeekPostureAccepted && typeof body?.nextWeekPosture === 'string' ? body.nextWeekPosture.slice(0, 200) : null;
    const acceptedCarryForward = nextWeekPostureAccepted && Array.isArray(body?.acceptedCarryForward)
      ? body.acceptedCarryForward.filter((v: unknown): v is string => typeof v === 'string').slice(0, 10)
      : [];
    const storedSummary = summary ? { ...summary, signalCounts, nextWeekPostureAccepted, nextWeekPosture, acceptedCarryForward } : null;

    const sb = await createSupabaseServerClient();
    const { weekStart, weekEnd } = weekWindow();
    const weekStartDate = weekStart.toISOString().slice(0, 10);
    const weekEndDate = weekEnd.toISOString().slice(0, 10);

    const { error } = await sb.from('weekly_reviews').upsert(
      { week_start: weekStartDate, week_end: weekEndDate, completed_at: new Date().toISOString(), summary: storedSummary, notes },
      { onConflict: 'week_start' },
    );
    if (error) throw error;

    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json({ error: 'Failed to complete review', detail: err instanceof Error ? err.message : String(err) }, { status: 500 });
  }
}
