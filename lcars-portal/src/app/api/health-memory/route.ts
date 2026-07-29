// Health Memory Workflow API
// Simple commit/discard workflow for health insights
// No complex escalation — just "keep in memory" or "discard"

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

export async function POST(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  try {
    const body = await req.json();
    const { action, insight_id, decision } = body;

    if (!insight_id || !decision) {
      return NextResponse.json(
        { error: 'missing_fields', required: ['insight_id', 'decision'] },
        { status: 400 },
      );
    }

    const sb = await createSupabaseServerClient();

    if (decision === 'commit') {
      // Mark insight as committed to memory
      const { error } = await sb
        .from('health_insights')
        .update({ 
          committed_to_memory: true,
          committed_at: new Date().toISOString(),
        })
        .eq('insight_id', insight_id);

      if (error) throw error;

      return NextResponse.json({
        status: 'ok',
        action: 'committed',
        insight_id,
      });
    } else if (decision === 'discard') {
      // Mark insight as reviewed but not committed
      const { error } = await sb
        .from('health_insights')
        .update({ 
          reviewed_at: new Date().toISOString(),
          committed_to_memory: false,
        })
        .eq('insight_id', insight_id);

      if (error) throw error;

      return NextResponse.json({
        status: 'ok',
        action: 'discarded',
        insight_id,
      });
    }

    return NextResponse.json(
      { error: 'invalid_decision', valid: ['commit', 'discard'] },
      { status: 400 },
    );
  } catch (err) {
    return NextResponse.json(
      { error: 'health_memory_failed', detail: String(err) },
      { status: 500 },
    );
  }
}
