// POST /api/health-osint-curation/[id]/reject — reject an auto-ingested
// health signal. Doesn't delete it (keeps a record of what was reviewed
// and declined, same reasoning as this platform's other suppress-don't-
// delete patterns) — sets auto_ingest_reviewed=true (migration 0143) so it
// drops off the /pending queue permanently, and leaves suppressed=true so
// it never shows in the main dashboard either.

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { requireSession } from '@/lib/supabase-server';
import { fetchGovernedRow } from '@/lib/governedFetch';

interface HealthSignalRow {
  signal_id: string;
  auto_ingested: boolean;
}

function serviceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );
}

// Shared human-feedback reason vocabulary (mission §19) — kept in sync
// with the CHECK constraint on health_signals.human_feedback_reason
// (migration 0186) and intelligence_events.human_feedback_reason.
const VALID_FEEDBACK_REASONS = new Set([
  'IRRELEVANT_TOPIC', 'WRONG_POPULATION', 'WRONG_GEOGRAPHY',
  'NO_OPERATIONAL_RELEVANCE', 'TOO_GENERIC', 'DUPLICATE', 'ALREADY_KNOWN',
  'COMMENTARY_ONLY', 'MARKETING_COMMERCIAL', 'WEAK_EVIDENCE',
  'LOW_INFORMATION_VALUE', 'OUT_OF_SCOPE', 'OTHER',
]);

export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  // OSINT Ingestion Quality & Relevance Mission Phase 9: optional structured
  // feedback reason captured on reject. Body is optional — omitting it keeps
  // reject working exactly as before (mission §19: "do not make feedback
  // burdensome").
  let feedbackReason: string | null = null;
  let feedbackNote: string | null = null;
  try {
    const body = await req.json();
    if (body && typeof body.reason === 'string' && VALID_FEEDBACK_REASONS.has(body.reason)) {
      feedbackReason = body.reason;
    }
    if (body && typeof body.note === 'string' && body.note.trim()) {
      feedbackNote = body.note.trim().slice(0, 2000);
    }
  } catch {
    // No body / not JSON — proceed with no feedback reason, same as before.
  }

  try {
    const sb = serviceClient();
    const fetched = await fetchGovernedRow<HealthSignalRow>(
      sb,
      'health_signals',
      'signal_id',
      params.id,
      'signal_id, auto_ingested',
      {
        predicate: (r) => r.auto_ingested,
        ineligibleStatus: 400,
        ineligibleMessage: () => 'Not an auto-ingested signal — nothing to reject',
      },
    );
    if (!fetched.ok) {
      return NextResponse.json({ error: fetched.error }, { status: fetched.status });
    }

    const { error: updateErr } = await sb
      .from('health_signals')
      .update({
        suppressed: true,
        auto_ingest_reviewed: true,
        disposition: 'SUPPRESS',
        disposition_reason: 'human_rejected',
        ...(feedbackReason ? { human_feedback_reason: feedbackReason } : {}),
        ...(feedbackNote ? { human_feedback_note: feedbackNote } : {}),
      })
      .eq('signal_id', params.id);
    if (updateErr) throw updateErr;

    return NextResponse.json({ success: true });
  } catch (err) {
    console.error('[health-osint-curation/reject]', err);
    return NextResponse.json({ error: 'Internal error' }, { status: 500 });
  }
}
