import { NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { isHqEnabled } from '@/lib/hq/flag';
import { sanitiseWeeklyReview, type RawWeeklyReview } from '@/lib/hq/weeklyReview';
import { GET as getWeeklyReview } from '@/app/api/weekly-review/route';

// HQ's view of the weekly review. It reuses the existing review (same
// computation, same short-lived cache) and sanitises it SERVER-side, so the
// personal-health and personal-task sections never reach the browser.
export async function GET() {
  if (!isHqEnabled()) return NextResponse.json({ error: 'Not found' }, { status: 404 });
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const upstream = await getWeeklyReview();
  if (!upstream.ok) return NextResponse.json({ error: 'weekly_review_unavailable' }, { status: 502 });
  const raw = (await upstream.json()) as RawWeeklyReview;
  return NextResponse.json(sanitiseWeeklyReview(raw), { headers: { 'Cache-Control': 'no-store' } });
}
