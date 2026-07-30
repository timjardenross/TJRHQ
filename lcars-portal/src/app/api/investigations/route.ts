import { NextRequest, NextResponse } from 'next/server';
import { openInvestigation } from '@/lib/investigationEngine';
import { investigationByType } from '@/lib/investigations/registry';
import { requireSession } from '@/lib/supabase-server';

// EOS Phase 2 Priority 2 (docs/EOS-CANONICAL-ARCHITECTURE-DECISIONS.md,
// Executive Intelligence): the Investigation Engine (MSN-0357) had zero
// user-facing surface before this route - a real, tested engine and ten
// definitions, never called from anywhere. This is the ONE generic bridge,
// not ten custom endpoints: it accepts any registered `type` and runs it
// through the exact same openInvestigation() every one of the 22 real
// journeys already runs through - no per-type branching here either.
//
// Deliberately calls openInvestigation() ONLY - stages 1-4 (Trigger through
// Decision Options), never resolveInvestigation(). This route can never
// mutate anything, by construction, regardless of which type is requested:
// several types (queue-resolution, queue-triage, downstream-verification-gap)
// have real execute() functions that write to Supabase, but nothing here
// ever supplies a decision to run them. Per Priority 4's "no independent
// reasoning or decision logic in the interface" - this surfaces evidence
// and options for a human to read; turning an option into a real action
// goes through the existing governed Decide flow, not through this route.

export async function GET(request: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const { searchParams } = new URL(request.url);
  const type = searchParams.get('type');
  const reason = searchParams.get('reason');
  const originRef = searchParams.get('originRef') ?? undefined;

  if (!type) {
    return NextResponse.json({ error: 'type is required' }, { status: 400 });
  }
  if (!reason) {
    return NextResponse.json({ error: 'reason is required - investigations begin with a trigger, not a menu (MSN-0353)' }, { status: 400 });
  }

  const definition = investigationByType(type);
  if (!definition) {
    return NextResponse.json({ error: `unknown investigation type "${type}"` }, { status: 404 });
  }

  try {
    const state = await openInvestigation(definition, {
      investigationType: type,
      reason,
      originatedAt: new Date().toISOString(),
      originRef,
    });

    return NextResponse.json({
      type: definition.type,
      label: definition.label,
      owner: definition.owner,
      triggerDescription: definition.triggerDescription,
      stagesReached: state.stagesReached,
      validation: state.validation,
      // Only id/label/isReversible - `value` can carry internals (e.g.
      // queue-triage's archiveIds) not meant for display, and is never
      // needed here since this route never resolves a decision anyway.
      decisionOptions: (state.decisionOptions ?? []).map((o) => ({
        id: o.id,
        label: o.label,
        isReversible: o.isReversible,
      })),
      completion: state.completion,
      audit: state.audit,
    });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : 'investigation failed to run' },
      { status: 502 }
    );
  }
}
