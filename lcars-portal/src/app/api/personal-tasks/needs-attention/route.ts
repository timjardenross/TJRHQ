/**
 * Personal Tasks — Needs Attention (Issue 24)
 *
 * Returns high-priority personal tasks for display on the Home/Captain's Chair dashboard.
 * Priority score = urgency + importance - (effort_minutes / 60)
 * Returns top 5 tasks sorted by priority score descending.
 */

import { NextRequest, NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { createSupabaseServerClient } from '@/lib/supabase-server';

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const supabase = createSupabaseServerClient();

    // Fetch personal tasks that are not yet completed or abandoned
    const { data: tasks, error } = await supabase
      .from('personal_tasks')
      .select('id, title, context, urgency, importance, effort_minutes, work_state, created_at')
      .in('work_state', ['captured', 'in_progress', 'blocked', 'paused'])
      .order('created_at', { ascending: false })
      .limit(20);

    if (error || !tasks) {
      console.error('[personal-tasks/needs-attention] Query failed:', error);
      return NextResponse.json({ error: 'Could not load personal tasks' }, { status: 500 });
    }

    // Compute priority scores and filter to top 5
    interface TaskWithScore {
      id: string;
      title: string;
      context: string | null;
      urgency: number;
      importance: number;
      effort_minutes: number;
      work_state: string;
      created_at: string;
      priority_score: number;
    }

    const scored: TaskWithScore[] = tasks.map((t: any) => ({
      ...t,
      priority_score: t.urgency + t.importance - (t.effort_minutes / 60),
    }));

    scored.sort((a, b) => b.priority_score - a.priority_score);
    const top5 = scored.slice(0, 5);

    return NextResponse.json({
      tasks: top5,
      count: top5.length,
      total_available: scored.length,
    });
  } catch (err) {
    console.error('[personal-tasks/needs-attention] Error:', err);
    return NextResponse.json({ error: 'Server error' }, { status: 500 });
  }
}
