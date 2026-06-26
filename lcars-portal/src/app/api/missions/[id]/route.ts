import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';

export async function GET(
  _request: NextRequest,
  { params }: { params: { id: string } },
) {
  const id = decodeURIComponent(params.id ?? '').trim();
  if (!id) {
    return NextResponse.json({ error: 'Mission ID required' }, { status: 400 });
  }

  try {
    const supabase = await createSupabaseServerClient();
    const { data, error } = await supabase
      .from('missions')
      .select('*')
      .ilike('mission_id', `%${id}%`)
      .limit(1)
      .maybeSingle();

    if (error) throw error;

    if (!data) {
      return NextResponse.json(
        { error: 'Mission not found', id },
        { status: 404 },
      );
    }

    return NextResponse.json({ mission: data });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: 'Failed to fetch mission', detail },
      { status: 500 },
    );
  }
}
