import { NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { isHqEnabled } from '@/lib/hq/flag';

// Tells the existing workbench shell whether to show its HQ entry. Signed-in
// callers only, and it exposes nothing but the on/off state.
export async function GET() {
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  return NextResponse.json({ enabled: isHqEnabled() }, { headers: { 'Cache-Control': 'no-store' } });
}
