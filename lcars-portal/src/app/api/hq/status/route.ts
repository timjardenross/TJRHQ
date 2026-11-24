import { NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { isHqEnabled } from '@/lib/hq/flag';

// Tells the existing workbench shell whether to show its HQ entry. Signed-in
// callers only, and it exposes only the on/off state and whether Notion search has a token (a boolean, never the token).
export async function GET() {
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  return NextResponse.json({ enabled: isHqEnabled(), notionConfigured: Boolean(process.env.NOTION_TOKEN?.trim()) }, { headers: { 'Cache-Control': 'no-store' } });
}
