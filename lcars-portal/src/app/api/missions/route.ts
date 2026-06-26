import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';

const CLOSED_STATUSES = ['Closed', 'completed', 'cancelled', 'deferred', 'Archived'];

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const status = searchParams.get('status');
  const limitParam = parseInt(searchParams.get('limit') ?? '25', 10);
  const limit = Number.isFinite(limitParam) ? Math.min(Math.max(1, limitParam), 100) : 25;

  try {
    const supabase = await createSupabaseServerClient();
    let query = supabase
      .from('missions')
      .select('mission_id, title, status, priority, owner, created_at, updated_at')
      .order('created_at', { ascending: false })
      .limit(limit);

    if (status) {
      query = query.eq('status', status);
    } else {
      query = query.not('status', 'in', `(${CLOSED_STATUSES.map(s => `"${s}"`).join(',')})`);
    }

    const { data, error } = await query;
    if (error) throw error;

    return NextResponse.json({ missions: data ?? [], count: data?.length ?? 0 });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: 'Failed to fetch missions', detail },
      { status: 500 },
    );
  }
}
