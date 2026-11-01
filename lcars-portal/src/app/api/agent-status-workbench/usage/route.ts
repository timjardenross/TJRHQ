// Usage tab API (Agent & Job Status workbench).
//
// Reads the two views added by migration 0197 — llm_usage_by_model_30d and
// llm_usage_daily_totals_14d — built directly on top of llm_call_metrics
// (migration 0085, Issue 21 cost governance). No scoring/estimation logic
// lives here; this route only shapes the view rows for display.
//
// Today's providers are Gemini/Mistral/Ollama/Qwen/Kimi/GLM (see
// core/llm/provider_chain.py) — there is no Anthropic/Claude or OpenAI
// traffic in this app yet. This view generalizes across whatever
// provider/model_name strings get logged, so it needs no changes if/when
// those start logging calls through log_call().

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();

    const [{ data: byModel, error: byModelErr }, { data: dailyTotals, error: dailyErr }] = await Promise.all([
      sb.from('llm_usage_by_model_30d').select('*'),
      sb.from('llm_usage_daily_totals_14d').select('*'),
    ]);

    if (byModelErr) throw byModelErr;
    if (dailyErr) throw dailyErr;

    return NextResponse.json({
      fetchedAt: new Date().toISOString(),
      byModel: byModel ?? [],
      dailyTotals: dailyTotals ?? [],
      note: 'Reflects only providers/models actually logged via llm_call_metrics — currently Gemini, Mistral, Ollama, Qwen, Kimi, and GLM. No Claude/OpenAI traffic exists in this app yet; this view will pick those up automatically if that changes.',
    });
  } catch (err) {
    console.error('[agent-status-workbench/usage] read failed:', err);
    return NextResponse.json(
      { error: 'usage_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
