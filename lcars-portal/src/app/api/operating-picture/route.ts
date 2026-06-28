// MSN-0177: Operating Picture API — read-only consolidated status endpoint.
// No counter increments, no status mutations, no mission creation.
// Consumers: LCARS Captain's Chair, Telegram /operating_picture, future mobile app.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';
import * as fs from 'fs';
import * as path from 'path';

const ACTIVE_STATUSES = [
  'Idea', 'Designed', 'Implemented', 'Tested',
  'Awaiting Number One Review', 'Validated', 'Awaiting XO Approval',
  'Requires Rework',
];
const AWAITING_APPROVAL_STATUSES = ['Awaiting Captain Approval', 'Awaiting XO Approval'];
const BLOCKED_STATUSES = ['Blocked'];

function readCounterState(): Record<string, number> | null {
  try {
    const REPO_ROOT = process.env.REPO_ROOT
      ? path.resolve(process.env.REPO_ROOT)
      : path.resolve(process.cwd(), '..');
    const raw = fs.readFileSync(path.join(REPO_ROOT, '.id-counters.json'), 'utf8');
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export async function GET() {
  const generatedAt = new Date().toISOString();

  try {
    const supabase = await createSupabaseServerClient();

    // Fetch non-closed missions in a single query
    const { data: allMissions, error: mErr } = await supabase
      .from('missions')
      .select('mission_id, title, status, priority, created_by, created_at, updated_at')
      .not('status', 'in', '("Closed","Archived")')
      .order('created_at', { ascending: false })
      .limit(200);

    if (mErr) throw mErr;

    const missions = allMissions ?? [];

    const awaitingApproval = missions.filter(m =>
      AWAITING_APPROVAL_STATUSES.includes(m.status),
    );
    const blocked = missions.filter(m => BLOCKED_STATUSES.includes(m.status));
    const active = missions.filter(m =>
      ACTIVE_STATUSES.includes(m.status) &&
      !AWAITING_APPROVAL_STATUSES.includes(m.status) &&
      !BLOCKED_STATUSES.includes(m.status),
    );
    const approved = missions.filter(m => m.status === 'Approved');

    // Open decisions count
    let decisionsOpenCount = 0;
    let recentDecisions: unknown[] = [];
    try {
      const { data: dec } = await supabase
        .from('decisions')
        .select('id, title, status, created_at')
        .not('status', 'in', '("Closed","Resolved","Archived")')
        .order('created_at', { ascending: false })
        .limit(10);
      recentDecisions = dec ?? [];
      decisionsOpenCount = recentDecisions.length;
    } catch { /* degrade gracefully */ }

    // Top intelligence signals — high/medium risk, last 7 days, not suppressed
    let topSignals: unknown[] = [];
    try {
      const since = new Date(Date.now() - 7 * 86_400_000).toISOString();
      const { data: sigs } = await supabase
        .from('intelligence_events')
        .select('event_id,raw_title,event_type,customer_impact,banking_relevance,organisation,rank_score,collected_at,canonical_url')
        .eq('suppressed', false)
        .gte('collected_at', since)
        .in('customer_impact', ['high', 'medium'])
        .order('rank_score', { ascending: false })
        .limit(5);
      topSignals = sigs ?? [];
      // Fall back to any recent events if no high/medium
      if (topSignals.length === 0) {
        const { data: fallback } = await supabase
          .from('intelligence_events')
          .select('event_id,raw_title,event_type,customer_impact,banking_relevance,organisation,rank_score,collected_at,canonical_url')
          .eq('suppressed', false)
          .gte('collected_at', since)
          .order('rank_score', { ascending: false })
          .limit(5);
        topSignals = fallback ?? [];
      }
    } catch { /* degrade gracefully */ }

    // Recent state transitions (last 10 approvals/rejections)
    let recentTransitions: unknown[] = [];
    try {
      const { data: trans } = await supabase
        .from('mission_state_transitions')
        .select('mission_id, from_state, to_state, actor, created_at')
        .in('to_state', ['Approved', 'Requires Rework'])
        .order('created_at', { ascending: false })
        .limit(10);
      recentTransitions = trans ?? [];
    } catch { /* degrade gracefully */ }

    // Counter state (read-only filesystem read)
    const counters = readCounterState();

    return NextResponse.json({
      generated_at: generatedAt,
      missions: {
        active_count:            active.length,
        awaiting_approval_count: awaitingApproval.length,
        blocked_count:           blocked.length,
        approved_count:          approved.length,
        active:                  active,
        awaiting_approval:       awaitingApproval,
        blocked:                 blocked,
        approved:                approved,
      },
      decisions: {
        open_count: decisionsOpenCount,
        items:      recentDecisions,
      },
      top_signals: topSignals,
      recent_transitions: recentTransitions,
      counters: counters
        ? { MSN: counters.MSN, next_MSN: `USS-TJR-MSN-${String(counters.MSN + 1).padStart(4, '0')}` }
        : null,
      next_actions: [
        ...(awaitingApproval.length > 0
          ? [`${awaitingApproval.length} mission(s) awaiting Captain approval`]
          : []),
        ...(blocked.length > 0
          ? [`${blocked.length} mission(s) blocked — requires attention`]
          : []),
        ...(decisionsOpenCount > 0
          ? [`${decisionsOpenCount} open decision(s) pending resolution`]
          : []),
      ],
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      {
        generated_at: generatedAt,
        error: 'Operating picture unavailable',
        detail,
        missions: { active_count: 0, awaiting_approval_count: 0, blocked_count: 0, approved_count: 0, active: [], awaiting_approval: [], blocked: [], approved: [] },
        decisions: { open_count: 0, items: [] },
        top_signals: [],
        recent_transitions: [],
        counters: null,
        next_actions: [],
      },
      { status: 500 },
    );
  }
}
