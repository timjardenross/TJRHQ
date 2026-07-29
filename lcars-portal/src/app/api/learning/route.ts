import { NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { requireSession } from '@/lib/supabase-server';

// USS-TJR-MSN-0080 — Learning Intelligence Visibility.
// Read-only LEARNING STATUS for the Captain's Chair. Mirrors /api/wellness:
// direct Supabase reads from authenticated context. The Python
// outcome_capture.learning_status() remains the authoritative service; this route
// re-derives the same simple, explainable counts/health for the dashboard.

function getSupabase() {
  // outcome_records holds sensitive personal_story / not_for_publication content.
  // This is a SERVER-side route handler, so use the service-role key (never exposed
  // to the browser). Requires session authentication first.
  const key =
    process.env.SUPABASE_SERVICE_ROLE_KEY ?? process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
  return createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, key);
}

const SENSITIVE = ['coaching', 'wellness', 'personal_story', 'internal_work'];
const INTERNAL = ['internal_work', 'personal_story'];

function ageDays(ts: string | null | undefined): number | null {
  if (!ts) return null;
  const t = Date.parse(String(ts));
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.floor((Date.now() - t) / 86400000));
}

function health(pending: number, overdue: number, velocity: number): string {
  if (overdue > 0 && velocity === 0) return 'RED';
  if (pending >= 10) return 'RED';
  if (pending <= 3 && (velocity >= 1 || pending === 0)) return 'GREEN';
  return 'AMBER';
}

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const supabase = getSupabase();

    const [outRes, lessonRes, missionRes, decisionRes] = await Promise.all([
      supabase.from('outcome_records')
        .select('source_type,source_id,content_classification,content_potential,reusable_insight,created_at')
        .limit(1000),
      supabase.from('lessons_learned').select('lesson_id').limit(1000),
      supabase.from('missions').select('id,mission_id,status,updated_at,created_at').eq('status', 'Closed').limit(500),
      supabase.from('decisions').select('id,updated_at,created_at').limit(500),
    ]);

    const outcomes = outRes.data ?? [];
    const lessons = lessonRes.data ?? [];
    const missions = missionRes.data ?? [];
    const decisions = decisionRes.data ?? [];

    // Captured source keys.
    const captured = new Set<string>();
    outcomes.forEach((o: any) => captured.add(`${o.source_type}:${o.source_id}`));

    // Pending (uncaptured) closed missions + decisions, with ages.
    const pendingAges: number[] = [];
    missions.forEach((m: any) => {
      const sid = String(m.mission_id ?? m.id ?? '');
      if (sid && !captured.has(`mission:${sid}`)) {
        pendingAges.push(ageDays(m.updated_at ?? m.created_at) ?? 0);
      }
    });
    decisions.forEach((d: any) => {
      const sid = String(d.id ?? '');
      if (sid && !captured.has(`decision:${sid}`)) {
        pendingAges.push(ageDays(d.updated_at ?? d.created_at) ?? 0);
      }
    });

    const pending = pendingAges.length;
    const overdue = pendingAges.filter((a) => a >= 15).length;
    const oldestUncapturedDays = pending ? Math.max(...pendingAges) : null;

    const velocity7d = outcomes.filter((o: any) => {
      const a = ageDays(o.created_at);
      return a !== null && a <= 7;
    }).length;

    const reusable = outcomes.filter((o: any) => !!o.reusable_insight).length;
    const content = outcomes.filter((o: any) =>
      ['medium', 'high'].includes(String(o.content_potential)) &&
      o.content_classification !== 'not_for_publication' &&
      !INTERNAL.includes(String(o.content_classification)),
    ).length;
    const sensitive = outcomes.filter((o: any) =>
      ['medium', 'high'].includes(String(o.content_potential)) &&
      SENSITIVE.includes(String(o.content_classification)),
    ).length;

    return NextResponse.json({
      outcomes: outcomes.length,
      pending,
      overdue,
      lessons: lessons.length,
      reusable,
      content,
      sensitive,
      velocity7d,
      oldestUncapturedDays,
      health: health(pending, overdue, velocity7d),
    });
  } catch (err) {
    return NextResponse.json(
      { outcomes: 0, pending: 0, overdue: 0, lessons: 0, reusable: 0, content: 0,
        sensitive: 0, velocity7d: 0, oldestUncapturedDays: null, health: 'UNKNOWN',
        error: String(err) },
      { status: 500 },
    );
  }
}
