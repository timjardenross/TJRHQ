// POST /api/content/signals-to-opportunities — Phase 1C batch converter.
// Atomically creates comms_content opportunities from top-ranked, non-suppressed
// content_signals. TS port of core/content/signal_opportunity_converter.py — this
// is the path the deployed Next.js app actually calls (Vercel has no Python
// runtime); the Python module remains the CLI/cron entry point for the same
// logic. Both must stay behaviourally identical.
//
// Atomicity: a single Supabase `.insert(rows)` call compiles to one SQL INSERT
// statement, so it is all-or-nothing at the database level — either every row
// lands or the whole request fails and nothing is written. No client-side
// rollback step exists or is needed.
//
// Body: { signal_ids?: string[], limit?: number, min_rank_score?: number, domain?: 'health' | 'operational' | null }
// If signal_ids is given, that exact set is used (the Signals tab's checkbox
// selection) — otherwise the top `limit` signals by rank_score are taken
// (the "batch create top N" one-click flow).

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

const DOMAIN_FORMAT_DEFAULT: Record<string, string> = {
  health: 'case_study',
  operational: 'executive_insight',
};

function serviceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );
}

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const signalIds: string[] | null = Array.isArray(body.signal_ids) && body.signal_ids.length > 0 ? body.signal_ids : null;
  const limit: number = Number.isFinite(body.limit) ? body.limit : 5;
  const minRankScore: number = Number.isFinite(body.min_rank_score) ? body.min_rank_score : 0.7;
  const domain: string | null = body.domain === 'health' || body.domain === 'operational' ? body.domain : null;

  if (!signalIds && limit < 1) {
    return NextResponse.json({ error: 'limit must be >= 1' }, { status: 400 });
  }

  const sb = serviceClient();

  try {
    let query = sb
      .from('content_signals')
      .select('id,event_id_text,raw_title,pillar_key,rank_score,domain,suggested_angle')
      .eq('suppressed', false);

    if (signalIds) {
      query = query.in('event_id_text', signalIds);
    } else {
      query = query.gte('rank_score', minRankScore).order('rank_score', { ascending: false }).limit(limit);
      if (domain) query = query.eq('domain', domain);
    }

    const { data: signals, error: fetchErr } = await query;
    if (fetchErr) throw fetchErr;

    if (signalIds && signals && signals.length !== signalIds.length) {
      // Some selected signals were suppressed/removed since the UI loaded them — abort rather
      // than silently create a partial batch of a different size than the user chose.
      return NextResponse.json({
        domain, min_rank_score: minRankScore,
        status: 'failed', requested: signalIds.length, created: 0, opportunity_ids: [],
        error: `${signalIds.length - signals.length} selected signal(s) are no longer eligible (suppressed or removed) — batch not created`,
      });
    }

    const base = { domain, min_rank_score: minRankScore };

    if (!signals || signals.length === 0) {
      return NextResponse.json({ ...base, status: 'no_signals', requested: 0, created: 0, opportunity_ids: [] });
    }

    // Pre-flight validation — any invalid signal aborts the whole batch before
    // the insert is ever attempted (all-or-nothing, per the Phase 1C review
    // board's Condition 2).
    const errors: string[] = [];
    const rows: Record<string, unknown>[] = [];
    const writtenSignalIds: string[] = [];
    for (const s of signals) {
      if (!s.raw_title || !s.event_id_text) {
        errors.push(`signal ${s.id}: missing raw_title or event_id_text`);
        continue;
      }
      rows.push({
        title: s.raw_title,
        pillar: s.pillar_key,
        source_kind: 'signal',
        source_ref: s.event_id_text,
        signal_source_id: s.event_id_text,
        classification: 'publishable',
        status: 'opportunity',
        format: DOMAIN_FORMAT_DEFAULT[s.domain as string] ?? 'executive_insight',
        notes: s.suggested_angle ?? null,
      });
      writtenSignalIds.push(s.event_id_text);
    }

    if (errors.length > 0) {
      return NextResponse.json({
        ...base,
        status: 'failed',
        requested: signals.length,
        created: 0,
        opportunity_ids: [],
        error: errors.join('; '),
      });
    }

    const { data: created, error: insertErr } = await sb
      .from('comms_content')
      .insert(rows)
      .select('id');

    if (insertErr) {
      return NextResponse.json({
        ...base,
        status: 'failed',
        requested: signals.length,
        created: 0,
        signal_ids: writtenSignalIds,
        opportunity_ids: [],
        error: `batch insert failed — 0 opportunities created, entire batch rolled back: ${insertErr.message}`,
      });
    }

    await sb.from('staff_autonomy_log').insert({
      actor: 'comms-workbench',
      action: 'batch_create_opportunities',
      rationale: `Batch completed: ${created?.length ?? 0} of ${signals.length} opportunities created (domain=${domain ?? 'both'}, min_rank_score=${minRankScore})`,
      mission_ref: 'MSN-1C-COMMS',
    }).then(() => {}, () => {}); // best-effort — never fail the request on audit-log errors

    return NextResponse.json({
      ...base,
      status: 'completed',
      requested: signals.length,
      created: created?.length ?? 0,
      signal_ids: writtenSignalIds,
      opportunity_ids: (created ?? []).map((r: { id: string }) => r.id),
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Batch create failed', detail }, { status: 500 });
  }
}
