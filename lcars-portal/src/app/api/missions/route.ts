import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { nextId, appendToRegistry } from '@/lib/id-registry';
import { recordHeartbeatServerSide } from '@/lib/heartbeat';

// Valid Supabase status values (CHECK constraint on missions.status)
const VALID_STATUSES = [
  'Idea', 'Designed', 'Approved for Engineering', 'Implemented', 'Tested',
  'Awaiting Number One Review', 'Validated', 'Awaiting XO Approval',
  'Awaiting Captain Approval', 'Approved',
  'Closed', 'Blocked', 'Archived', 'Requires Rework',
] as const;
const CLOSED_STATUSES = ['Closed', 'Archived'];

export async function GET(request: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const { searchParams } = new URL(request.url);
  const status = searchParams.get('status');
  const limitParam = parseInt(searchParams.get('limit') ?? '25', 10);
  const limit = Number.isFinite(limitParam) ? Math.min(Math.max(1, limitParam), 100) : 25;

  try {
    const supabase = await createSupabaseServerClient();
    let query = supabase
      .from('missions')
      .select('mission_id, title, status, priority, created_by, created_at, updated_at')
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

// MSN-0171: Mission creation endpoint — single canonical write gate
export async function POST(request: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }

  const title = typeof body.title === 'string' ? body.title.trim() : '';
  if (!title) {
    return NextResponse.json({ error: 'title is required' }, { status: 400 });
  }

  const rawStatus  = typeof body.status === 'string' ? body.status.trim() : 'Idea';
  const status     = (VALID_STATUSES as readonly string[]).includes(rawStatus) ? rawStatus : 'Idea';
  const priority   = typeof body.priority    === 'string' ? body.priority.trim()    : null;
  const created_by = typeof body.created_by  === 'string' ? body.created_by.trim()  : null;
  const description = typeof body.description === 'string' ? body.description.trim() : null;

  try {
    const mission_id = await nextId('MSN');

    const supabase = await createSupabaseServerClient();
    const { data, error } = await supabase
      .from('missions')
      .insert({
        mission_id,
        title,
        status,
        ...(priority    !== null && { priority }),
        ...(created_by  !== null && { created_by }),
        ...(description !== null && { description }),
      })
      .select('mission_id, title, status, created_at')
      .single();

    if (error) throw error;

    // Non-blocking runtime registry append (MSN-0145 pattern)
    appendToRegistry(mission_id, title, 'LCARS-API', status);

    // Chief Engineer follow-up (.claude/skills/bot-reviews/fixes-2026-08-09/
    // final-4-domains.md): this route is the confirmed-live mission
    // creation path — called directly by tg-xo.service's /mission_create
    // command (telegram-bots/xo/app.py). One of several genuinely-real,
    // non-shared `missions` write sites; see that doc for the full
    // multi-writer disposition (same "wire all the real ones" judgment
    // used for the `decisions` domain).
    void recordHeartbeatServerSide({
      domainKey: 'missions',
      status: 'ok',
      detail: `create mission_id=${mission_id}`,
    });

    return NextResponse.json({ mission: data }, { status: 201 });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: 'Failed to create mission', detail },
      { status: 500 },
    );
  }
}
